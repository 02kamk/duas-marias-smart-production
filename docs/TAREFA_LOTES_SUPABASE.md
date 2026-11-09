# Tarefa: modulo de Lotes de Inspecao com Supabase

## Contexto

Este e o **Ponto Certo**, projeto integrador de IA (SATC) para a facção **Duas Marias
Confecções** (Criciúma/SC). Hoje o sistema inspeciona costura por câmera com uma CNN
(MobileNetV3) e um LLM de apoio via OpenRouter. Leia `README.md` e `docs/ARQUITETURA.md`
antes de mexer em qualquer coisa.

**Problema:** os eventos de inspeção ficam só na memória (`app/state.py`, `EstadoSessao`).
Ao reiniciar o servidor, o histórico some, e nenhuma inspeção é ligada a um lote de
produção. O documento do projeto promete cadastro de clientes e lotes, histórico de
defeitos, alertas e dashboard. Este módulo entrega isso.

**Prazo:** precisa estar funcionando antes da visita à facção em **16/11**, quando vamos
cadastrar um lote real e inspecionar peças dele.

## O que já está pronto (não recriar)

- O projeto Supabase já existe. O esquema já foi criado com `supabase/schema.sql`
  (tabelas `clientes`, `lotes`, `inspecoes` e a view `resumo_lotes`). **Leia esse arquivo**:
  ele é a fonte da verdade das colunas. Não altere o esquema sem me perguntar.
  - `inspecoes.classe_final` e `inspecoes.aprovada` são colunas **geradas** pelo banco.
    Nunca escreva nelas.
  - O RLS está ligado e não há policies. O backend conecta como `postgres` (dono das
    tabelas), então o RLS não o bloqueia. **Não crie policies e não use a API REST
    pública para as tabelas.**
- O bucket privado `capturas` já existe no Storage.
- O `.env` na raiz de `pontocerto/` já tem:
  ```
  SUPABASE_DB_URL=...      # connection string do Session pooler (porta 5432)
  SUPABASE_URL=...
  SUPABASE_SECRET_KEY=...
  SUPABASE_BUCKET=capturas
  ```
  **Nunca imprima, logue ou devolva esses valores** em erro, igual ao que o
  `llm/openrouter.py` já faz com a chave do OpenRouter.

## Regras de projeto (obrigatórias)

1. **O sistema continua funcionando sem Supabase.** Mesma filosofia de "funciona sem
   chave do OpenRouter": sem as variáveis ou sem internet, a câmera, a CNN, o Grad-CAM e
   o histórico em memória seguem normais. A interface mostra "Banco desconectado" e a
   aba Lotes avisa isso. Nada pode quebrar na subida do servidor.
2. **Nunca travar a thread de inferência.** `registrar_evento` é chamado pela thread do
   `Motor` (`app/server.py`, perto da linha 466). Gravar no banco ou subir a foto **não**
   pode acontecer nessa thread. Use uma fila (`queue.Queue`) e uma thread
   trabalhadora dedicada que grava no banco e no Storage.
3. **Fila resistente a queda de internet.** Se a gravação falhar, a inspeção vai para um
   arquivo local de pendências (ex.: `artifacts/pendentes.jsonl`) e é reenviada quando a
   conexão voltar. A rota de status informa quantas estão pendentes. Na facção a
   internet pode ser instável.
4. Não mexer na CNN, no treino, na suavização temporal nem nos prompts do LLM.
5. Seguir o padrão do código existente: português sem acento em identificadores,
   docstrings em português, configuração em `config.yaml` quando fizer sentido (ex.:
   tamanho da fila, intervalo de reenvio).
6. Dependências novas vão no `requirements.txt`. Preferência: `psycopg[binary]` e
   `psycopg_pool` para o banco; `supabase` (ou chamadas HTTP diretas com `httpx`) só
   para o Storage.

## O que construir

### Backend

**`src/pontocerto/app/db.py`** (novo): lê as variáveis (estendendo o padrão de
`config.py`, que hoje só procura `OPENROUTER_API_KEY` no `.env`), cria o pool de conexões
de forma preguiçosa, expõe `disponivel`/`erro` como o `Preditor` faz, e tem as funções de
acesso: clientes, lotes, inspeções, resumo, upload da foto e URL assinada.

**Lote ativo:** o servidor guarda qual lote está sendo inspecionado agora. Com lote
ativo, todo evento novo (ao vivo e também `/api/analisar`) vira uma linha em `inspecoes`
com a foto no bucket em `lote_<id>/<evento_id>.jpg`. Sem lote ativo, nada vai para o
banco (só a memória, como hoje).

**Sincronizar as ações existentes com o banco:**
- correção do operador (`corrigir_rotulo`) → `update inspecoes set classe_confirmada`;
- diagnóstico (`anexar_diagnostico`) → coluna `diagnostico`;
- segunda opinião (`anexar_revisao`) → coluna `revisao_llm`.
Use `evento_id` para achar a linha.

**Rotas novas:**

| Método | Rota | O que faz |
|---|---|---|
| GET | `/api/db/status` | conectado?, erro (sem segredo), pendentes na fila |
| GET / POST | `/api/clientes` | listar / cadastrar (nome obrigatório, CNPJ opcional) |
| GET / POST | `/api/lotes` | listar com dados da view `resumo_lotes` / cadastrar |
| GET | `/api/lotes/{id}` | resumo + defeitos por classe + últimas 30 inspeções (com URL assinada da foto) + projeção + alerta |
| PATCH | `/api/lotes/{id}` | mudar status (`aberto`, `em_inspecao`, `concluido`) |
| GET / POST | `/api/lotes/ativo` | ver / definir o lote ativo (`{"lote_id": 3}` ou `null`) |

**Alerta de qualidade:** `taxa_defeito > limite_defeito`, **somente com pelo menos 20
peças inspecionadas** (configurável), para não alarmar com 1 defeito em 3 peças.

**Projeção de prazo** (conta simples, **não é IA**, e a interface deve deixar isso
claro): ritmo = peças inspecionadas / dias desde a primeira inspeção (mínimo 1 dia);
data projetada = hoje + (quantidade − inspecionadas) / ritmo; `em_risco` se passar do
`prazo_entrega`. Sem inspeções ainda → "sem dados para projetar".

### Interface (`app/static/`)

- **Aba nova "Lotes"** no menu lateral, no mesmo estilo das outras:
  - lista de lotes com cliente, modelo, barra de progresso, taxa de defeito, prazo e um
    selo de alerta quando houver;
  - formulário "Novo lote" (com opção de cadastrar cliente na hora);
  - tela de detalhe do lote: indicadores, gráfico simples de defeitos por classe,
    projeção de prazo, últimas inspeções com miniatura, e botões para mudar status e
    "Inspecionar este lote" (que define o lote ativo e vai para "Ao vivo").
- **Aba "Ao vivo":** seletor de lote ativo visível no topo. Sem lote ativo, mostrar o
  aviso "Inspeções não estão sendo salvas em nenhum lote".
- Indicador discreto de banco (conectado / desconectado / N pendentes).

## Como validar (faça e me mostre o resultado)

1. `python scripts\00_verificar_ambiente.py` deve ganhar uma linha para o Supabase
   (`[ok]` ou o motivo do erro, sem expor segredo).
2. Subir o app **sem** as variáveis do Supabase: tudo como antes, aba Lotes avisando.
3. Com as variáveis: cadastrar cliente e lote de teste, ativar o lote, analisar algumas
   imagens do dataset pela aba "Testar imagem" e conferir as linhas em `inspecoes` e as
   fotos no bucket.
4. Corrigir o rótulo de um evento e conferir que `aprovada` mudou no banco.
5. Simular queda: definir uma `SUPABASE_DB_URL` inválida, gerar inspeções, conferir o
   `pendentes.jsonl`, voltar a URL certa e conferir o reenvio.
6. Atualizar o `README.md` (seção nova "Banco de dados (Supabase)" e a estrutura de
   pastas) e o `docs/ARQUITETURA.md` (rotas novas e a decisão da fila).

Trabalhe em etapas e me mostre cada uma antes de seguir: (1) `db.py` + status,
(2) rotas, (3) integração com eventos e fila, (4) interface, (5) documentação.
No final, apague o cliente e o lote de teste do banco.
