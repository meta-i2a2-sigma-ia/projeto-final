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
execute format('create schema if not exists %I', p_schema);
execute format('create table if not exists %I.%I ()', p_schema, p_table);

for k, t in
select key, lower(trim(value))
from jsonb_each_text(p_cols)
    loop
    if t not in ('text','boolean','bigint','double precision','date','timestamp with time zone') then
    t := 'text';
end if;
execute format('alter table %I.%I add column if not exists %I %s', p_schema, p_table, k, t);
end loop;
end $$;

revoke all on function public.ensure_table(text,text,jsonb) from public;
grant execute on function public.ensure_table(text,text,jsonb) to service_role;

NOTIFY pgrst, 'reload schema';
