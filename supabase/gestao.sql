-- Gestão com base vazia: não migra nem sobrescreve a demonstração local.
create table if not exists public.gestao_estado (
  id integer primary key check (id = 1),
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.gestao_estado enable row level security;
revoke all on public.gestao_estado from anon, authenticated;
insert into public.gestao_estado(id,payload) values (1,
 '{"schemaVersion":1,"dataOrigin":"local","orders":[],"employees":[],"records":[],"audit":[],"assignments":[],"decisions":[],"receipts":[]}'::jsonb
) on conflict (id) do nothing;
