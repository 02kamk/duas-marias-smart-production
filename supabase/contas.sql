-- Contas de login, compartilhadas entre os computadores que usam o mesmo banco.
-- O servidor cria esta tabela sozinho na primeira vez; este arquivo e so referencia.
-- A senha nunca e guardada: so o salt e o hash PBKDF2-SHA256.
-- Sessoes e tentativas de login continuam no SQLite local de cada computador.
create table if not exists public.contas (
    email      text primary key,
    salt       text not null,
    hash       text not null,
    criado_em  timestamptz not null default now()
);
alter table public.contas enable row level security;
revoke all on public.contas from anon, authenticated;
