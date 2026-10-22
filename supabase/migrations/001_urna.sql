-- Aplicar como administrador pelo Supabase. Não exige nenhuma chave privilegiada no navegador.
begin;
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create schema if not exists urna_private;
revoke all on schema urna_private from public, anon, authenticated;

create table if not exists urna_private.election (
 id integer primary key check (id=1), title text not null check(length(title) between 1 and 100),
 status text not null check(status in ('draft','open','closed')), digits integer not null check(digits between 2 and 5)
);
insert into urna_private.election values(1,'Minha votação','draft',2) on conflict do nothing;
create table if not exists urna_private.candidates (
 number text primary key check(number ~ '^[0-9]{2,5}$'), name text not null check(length(name) between 1 and 80),
 party text not null default '' check(length(party)<=60)
);
create table if not exists urna_private.totals(choice text primary key, count bigint not null default 0 check(count>=0));
create table if not exists urna_private.credentials(digest text primary key);
create table if not exists urna_private.secret(id integer primary key check(id=1), key bytea not null);
insert into urna_private.secret values(1,extensions.gen_random_bytes(32)) on conflict do nothing;
create table if not exists urna_private.admins(user_id uuid primary key references auth.users(id) on delete cascade);

alter table urna_private.election enable row level security;
alter table urna_private.candidates enable row level security;
alter table urna_private.totals enable row level security;
alter table urna_private.credentials enable row level security;
alter table urna_private.secret enable row level security;
alter table urna_private.admins enable row level security;
revoke all on all tables in schema urna_private from public,anon,authenticated;

create or replace function urna_private.require_admin() returns void
language plpgsql security definer set search_path='' as $$
begin
 if auth.uid() is null or not exists(select 1 from urna_private.admins where user_id=auth.uid()) then
  raise exception 'Administração não autorizada.' using errcode='42501';
 end if;
end $$;
revoke all on function urna_private.require_admin() from public,anon,authenticated;

create or replace function public.urna_state() returns jsonb
language plpgsql security definer set search_path='' as $$
declare e urna_private.election%rowtype; result jsonb;
begin
 select * into e from urna_private.election where id=1;
 result=jsonb_build_object('title',e.title,'status',e.status,'digits',e.digits,'access','cpf',
  'candidates',coalesce((select jsonb_agg(jsonb_build_object('number',number,'name',name,'party',party) order by number) from urna_private.candidates),'[]'::jsonb));
 if e.status='closed' then
  result=result||jsonb_build_object('totals',coalesce((select jsonb_object_agg(choice,count) from urna_private.totals),'{}'::jsonb));
 end if;
 return result;
end $$;

create or replace function public.urna_admin() returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform urna_private.require_admin();
 return jsonb_build_object('state',public.urna_state(),'csrf','bearer-auth');
end $$;

create or replace function public.urna_configure(p_title text,p_digits integer,p_candidates jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare e urna_private.election%rowtype; candidate jsonb; n text; name_value text; party_value text;
begin
 perform urna_private.require_admin();
 select * into e from urna_private.election where id=1 for update;
 if e.status<>'draft' then raise exception 'A configuração está bloqueada após a abertura.'; end if;
 if p_title is null or length(trim(p_title)) not between 1 and 100 or p_digits is null or p_digits not between 2 and 5 then
  raise exception 'Título ou quantidade de dígitos inválidos.';
 end if;
 if jsonb_typeof(p_candidates) is distinct from 'array' then raise exception 'Informe os candidatos.'; end if;
 if jsonb_array_length(p_candidates) not between 2 and 100 then raise exception 'Cadastre de 2 a 100 candidatos.'; end if;
 delete from urna_private.candidates;
 for candidate in select value from jsonb_array_elements(p_candidates) loop
  n=trim(candidate->>'number'); name_value=trim(candidate->>'name'); party_value=trim(coalesce(candidate->>'party',''));
  if n is null or n !~ '^[0-9]+$' or length(n)<>p_digits or name_value is null or length(name_value) not between 1 and 80 or length(party_value)>60 then
   raise exception 'Confira os números e nomes dos candidatos.';
  end if;
  if exists(select 1 from urna_private.candidates where number=n) then raise exception 'Os números precisam ser únicos.'; end if;
  insert into urna_private.candidates values(n,name_value,party_value);
 end loop;
 update urna_private.election set title=trim(p_title),digits=p_digits where id=1;
 return jsonb_build_object('ok',true);
end $$;

create or replace function public.urna_transition(p_action text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare e urna_private.election%rowtype;
begin
 perform urna_private.require_admin();
 select * into e from urna_private.election where id=1 for update;
 if p_action='start' then
  if e.status<>'draft' or (select count(*) from urna_private.candidates)<2 then raise exception 'Cadastre os candidatos antes de iniciar.'; end if;
  update urna_private.election set status='open' where id=1;
 elsif p_action='close' then
  if e.status<>'open' then raise exception 'A votação não está aberta.'; end if;
  update urna_private.election set status='closed' where id=1;
 else raise exception 'Ação inválida.';
 end if;
 return jsonb_build_object('ok',true);
end $$;

create or replace function public.urna_vote(p_cpf text,p_choice text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare e urna_private.election%rowtype; cpf_value text; size_value integer; idx integer; checksum integer; digest_value text; choice_value text;
begin
 -- O bloqueio serializa votos e encerramento. A autorização e o incremento fazem parte da mesma transação.
 select * into e from urna_private.election where id=1 for update;
 if e.status<>'open' then raise exception 'A votação não está aberta.'; end if;
 if p_cpf is null or length(p_cpf)>20 then raise exception 'CPF inválido.'; end if;
 cpf_value=translate(p_cpf,'.- ','');
 if cpf_value !~ '^[0-9]{11}$' then raise exception 'CPF inválido.'; end if;
 if cpf_value=repeat(substr(cpf_value,1,1),11) then raise exception 'CPF inválido.'; end if;
 for size_value in 9..10 loop
  checksum=0;
  for idx in 1..size_value loop
   checksum=checksum+substr(cpf_value,idx,1)::integer*(size_value+2-idx);
  end loop;
  checksum=(checksum*10)%11;
  if checksum=10 then checksum=0; end if;
  if checksum<>substr(cpf_value,size_value+1,1)::integer then raise exception 'CPF inválido.'; end if;
 end loop;
 if p_choice is null or (p_choice<>'branco' and (p_choice !~ '^[0-9]+$' or length(p_choice)<>e.digits)) then
  raise exception 'Complete o número ou escolha BRANCO.';
 end if;
 select encode(extensions.hmac(convert_to(cpf_value,'UTF8'),key,'sha256'),'hex') into digest_value from urna_private.secret where id=1;
 if digest_value is null then raise exception 'A urna não está configurada.'; end if;
 begin
  insert into urna_private.credentials values(digest_value);
 exception when unique_violation then raise exception 'Não foi possível autorizar: CPF já utilizado nesta votação.';
 end;
 choice_value=case when p_choice='branco' or exists(select 1 from urna_private.candidates where number=p_choice) then p_choice else 'nulo' end;
 insert into urna_private.totals(choice,count) values(choice_value,1)
  on conflict(choice) do update set count=urna_private.totals.count+1;
 return jsonb_build_object('ok',true);
end $$;

revoke all on function public.urna_state() from public,anon,authenticated;
revoke all on function public.urna_admin() from public,anon,authenticated;
revoke all on function public.urna_configure(text,integer,jsonb) from public,anon,authenticated;
revoke all on function public.urna_transition(text) from public,anon,authenticated;
revoke all on function public.urna_vote(text,text) from public,anon,authenticated;
grant execute on function public.urna_state(),public.urna_vote(text,text) to anon,authenticated;
grant execute on function public.urna_admin(),public.urna_configure(text,integer,jsonb),public.urna_transition(text) to authenticated;
notify pgrst,'reload schema';
commit;
