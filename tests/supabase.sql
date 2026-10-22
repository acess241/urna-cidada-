\set ON_ERROR_STOP on
begin;
insert into auth.users values('00000000-0000-0000-0000-000000000001');
insert into urna_private.admins values('00000000-0000-0000-0000-000000000001');
set local role anon;
do $$ begin
 if has_table_privilege(current_user,'urna_private.credentials','SELECT') then raise exception 'CPF signatures exposed'; end if;
 if has_function_privilege(current_user,'public.urna_configure(text,integer,jsonb)','EXECUTE') then raise exception 'Anonymous admin allowed'; end if;
 if public.urna_state()->>'status'<>'draft' then raise exception 'Bad draft'; end if;
 begin perform public.urna_vote('12345678909','91'); raise exception 'Voting before opening';
 exception when raise_exception then if SQLERRM='Voting before opening' then raise; end if; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
 begin perform public.urna_admin(); raise exception 'Unlisted admin allowed';
 exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
select public.urna_configure('Teste',2,'[{"number":"91","name":"Opção A"},{"number":"92","name":"Opção B"}]'::jsonb);
select public.urna_transition('start');
set local role anon;
select set_config('request.jwt.claim.sub','',true);
select public.urna_vote('123.456.789-09','91');
do $$ begin
 if public.urna_state() ? 'totals' then raise exception 'Early results'; end if;
 begin perform public.urna_vote('12345678909','92'); raise exception 'Duplicate CPF accepted';
 exception when raise_exception then if SQLERRM='Duplicate CPF accepted' then raise; end if; end;
 begin perform public.urna_vote('11111111111','91'); raise exception 'Invalid CPF accepted';
 exception when raise_exception then if SQLERRM='Invalid CPF accepted' then raise; end if; end;
end $$;
reset role;
-- Verificar ausência de ligação entre assinatura de CPF e escolha.
do $$ begin
 if (select count(*) from urna_private.credentials)<>1 then raise exception 'Bad credential total'; end if;
 if (select count(*) from information_schema.columns where table_schema='urna_private' and table_name='credentials')<>1 then raise exception 'Credential contains extra information'; end if;
 if (select count from urna_private.totals where choice='91')<>1 then raise exception 'Bad vote total'; end if;
end $$;
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
select public.urna_transition('close');
set local role anon;
select set_config('request.jwt.claim.sub','',true);
do $$ begin
 if (public.urna_state()->'totals'->>'91')::integer<>1 then raise exception 'Bad final tally'; end if;
 begin perform public.urna_vote('12345678909','91'); raise exception 'Vote after closure';
 exception when raise_exception then if SQLERRM='Vote after closure' then raise; end if; end;
end $$;
rollback;
