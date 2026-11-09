-- ---------------------------------------------------------------------------
-- Ponto Certo - esquema do banco (Supabase / PostgreSQL)
-- Cole no SQL Editor do Supabase e clique em "Run". Pode rodar de novo sem erro.
-- ---------------------------------------------------------------------------

-- Clientes: as empresas contratantes que enviam lotes para a faccao
create table if not exists public.clientes (
    id          bigint generated always as identity primary key,
    nome        text not null,
    cnpj        text,
    criado_em   timestamptz not null default now()
);

-- Lotes de producao recebidos pela faccao
create table if not exists public.lotes (
    id              bigint generated always as identity primary key,
    cliente_id      bigint not null references public.clientes(id) on delete restrict,
    codigo          text not null unique,               -- ex.: "L-2026-001"
    modelo_peca     text not null,                      -- ex.: "Camiseta basica gola careca"
    tecido          text,                               -- ex.: "Algodao"
    quantidade      integer not null check (quantidade > 0),
    prazo_entrega   date not null,
    limite_defeito  numeric(5,4) not null default 0.05  -- alerta quando a taxa passar disso (5%)
                    check (limite_defeito > 0 and limite_defeito < 1),
    status          text not null default 'aberto'
                    check (status in ('aberto', 'em_inspecao', 'concluido')),
    observacoes     text,
    criado_em       timestamptz not null default now()
);

-- Cada peca inspecionada pelo sistema (ao vivo ou por upload)
create table if not exists public.inspecoes (
    id                 bigint generated always as identity primary key,
    lote_id            bigint not null references public.lotes(id) on delete cascade,
    evento_id          text unique,                     -- id do evento gerado pelo app
    origem             text not null default 'ao_vivo'
                       check (origem in ('ao_vivo', 'upload')),
    classe_predita     text not null,                   -- chave da classe da CNN (labels.py)
    confianca          real not null check (confianca between 0 and 1),
    classe_confirmada  text,                            -- preenchida quando o operador corrige
    classe_final       text generated always as (coalesce(classe_confirmada, classe_predita)) stored,
    aprovada           boolean generated always as (coalesce(classe_confirmada, classe_predita) = 'normal') stored,
    imagem_path        text,                            -- caminho no bucket "capturas"
    diagnostico        jsonb,                           -- causa provavel / acao corretiva
    revisao_llm        jsonb,                           -- segunda opiniao do LLM, se houve
    criado_em          timestamptz not null default now(),
    constraint classes_validas check (
        classe_predita in ('normal','skipped_stitch','broken_stitch','pinched_fabric','crooked_seam',
                           'thread_sagging','puckering','stain_damage','needle_mark','bobbin_pullup',
                           'overlapped_stitch')
        and (classe_confirmada is null or classe_confirmada in
                          ('normal','skipped_stitch','broken_stitch','pinched_fabric','crooked_seam',
                           'thread_sagging','puckering','stain_damage','needle_mark','bobbin_pullup',
                           'overlapped_stitch'))
    )
);

create index if not exists idx_inspecoes_lote_data on public.inspecoes (lote_id, criado_em);
create index if not exists idx_lotes_cliente on public.lotes (cliente_id);

-- Resumo pronto para o painel de cada lote
create or replace view public.resumo_lotes
with (security_invoker = true) as
select
    l.id,
    l.codigo,
    c.nome                                   as cliente,
    l.modelo_peca,
    l.tecido,
    l.quantidade,
    l.prazo_entrega,
    l.status,
    l.limite_defeito,
    count(i.id)                              as inspecionadas,
    count(i.id) filter (where i.aprovada)    as aprovadas,
    count(i.id) filter (where not i.aprovada) as reprovadas,
    round(count(i.id)::numeric / l.quantidade, 4) as percentual_concluido,
    case when count(i.id) = 0 then 0
         else round((count(i.id) filter (where not i.aprovada))::numeric / count(i.id), 4)
    end                                      as taxa_defeito,
    min(i.criado_em)                         as primeira_inspecao,
    max(i.criado_em)                         as ultima_inspecao,
    (l.prazo_entrega - current_date)         as dias_restantes
from public.lotes l
join public.clientes c on c.id = l.cliente_id
left join public.inspecoes i on i.lote_id = l.id
group by l.id, c.nome;
