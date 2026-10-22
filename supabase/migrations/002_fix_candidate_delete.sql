-- Atualiza a função existente sem apagar candidatos nem votos ao executar a migração.
begin;
do $fix$
declare
  definition text;
begin
  definition := pg_get_functiondef(
    'public.urna_configure(text,integer,jsonb)'::regprocedure
  );
  definition := regexp_replace(
    definition,
    'delete\s+from\s+urna_private\.candidates\s*;',
    'delete from urna_private.candidates where number is not null;',
    'gi'
  );
  execute definition;
end;
$fix$;
notify pgrst, 'reload schema';
commit;
