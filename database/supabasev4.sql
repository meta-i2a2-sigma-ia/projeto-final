-- Função usada pelo RPC /rest/v1/rpc/ensure_table
-- Cria schema/tabela e adiciona colunas (idempotente).
-- Espera p_cols como JSONB no formato: {"col_a":"text", "col_b":"text", ...}

create or replace function public.ensure_table(
  p_schema text,
  p_table  text,
  p_cols   jsonb
) returns void
language plpgsql
security definer
as $$
declare
k text;
  t text;
begin
  -- garante schema e tabela
execute format('create schema if not exists %I', p_schema);
execute format('create table if not exists %I.%I ()', p_schema, p_table);

-- para cada coluna solicitada, adiciona se não existir
for k, t in
select key, lower(trim(value))
from jsonb_each_text(p_cols)
    loop
    -- whitelist mínima de tipos; se vier algo diferente, força text
    if t not in ('text','boolean','bigint','double precision','date','timestamp with time zone') then
    t := 'text';
end if;

execute format('alter table %I.%I add column if not exists %I %s',
               p_schema, p_table, k, t);
end loop;

  -- recarrega o cache do PostgREST para a tabela/colunas ficarem disponíveis na API
  NOTIFY pgrst, 'reload schema';
end $$;

-- Permissões: só service_role pode chamar via RPC
revoke all on function public.ensure_table(text,text,jsonb) from public;
grant execute on function public.ensure_table(text,text,jsonb) to service_role;
