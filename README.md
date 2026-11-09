# Duas Marias Smart Production

Sistema da Duas Marias para a produção de costura. Tem três partes:

| Parte | O que é | Onde fica |
|---|---|---|
| **Ponto Certo** (inspeção) | Câmera + rede neural que aprova ou reprova cada costura; histórico, diagnóstico com IA e lotes gravados no Supabase. | `src/pontocerto/` (app em `src/pontocerto/app/`) |
| **Gestão, financeiro e produtividade** | Extensões do mesmo servidor: `/gestao` (lotes e atrasos), `/financeiro` (lançamentos locais) e `/produtividade` (experimento com dados públicos UCI). | `src/pontocerto/management/` e `src/pontocerto/business/` |
| **Protótipo F0 (frontend)** | Protótipo React de gestão da produção, com dados fictícios. | `frontend/` |

O contexto do projeto está em [docs/CONTEXTO_PROJETO.md](docs/CONTEXTO_PROJETO.md) e a arquitetura da inspeção em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Instalar (uma vez)

Python 3.11 ou mais novo. No PowerShell, na raiz do repositório (a pasta deste README):

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt      # ~1 GB por causa do torch
python scripts\00_verificar_ambiente.py
```

O verificador lista o que falta (dataset, modelo, câmera, chaves) e diz qual é o próximo comando.

## Rodar

Todos os comandos partem da raiz do repositório, com o `.venv` ativo.

| Comando | O que sobe |
|---|---|
| `python scripts\11_rodar_completo.py` | **Tudo**: inspeção em `/`, `/gestao`, `/financeiro` e `/produtividade` |
| `python scripts\05_rodar_app.py` | Só a inspeção (câmera, histórico, lotes) |
| `python scripts\07_rodar_com_gestao.py` | Inspeção + `/gestao` |

Atalhos no Windows: `.\Iniciar-Completo.ps1` (tudo) e `.\Iniciar-Gestao.ps1` (inspeção + gestão). Abra http://127.0.0.1:8000. A câmera não liga sozinha: na aba **Ao vivo**, clique em **Ligar câmera**.

### Configuração opcional (`.env`)

Copie `.env.example` para `.env`. Sem ele tudo funciona, com estas limitações:

- **`OPENROUTER_API_KEY`**: sem ela, os diagnósticos usam a base técnica local e não há segunda opinião da IA.
- **`SUPABASE_*`**: sem elas, os lotes não são gravados no banco e tudo fica só neste computador. Para ativar, rode [supabase/schema.sql](supabase/schema.sql) no SQL Editor do Supabase, crie um bucket **privado** `Capturas` e preencha as 4 variáveis. Com um lote em produção (página **Lotes**), cada peça inspecionada é gravada nele; as fotos sobem só para peças com defeito. Sem internet, as gravações ficam em `artifacts/pendentes.jsonl` e são reenviadas depois.

## Treinar e testar

| Comando | O que faz |
|---|---|
| `python scripts\01_preparar_dados.py` | Gera os splits do dataset de costura (`artifacts/splits.csv`) |
| `python scripts\02_treinar.py` | Treina a CNN (`artifacts/modelo.pt`; horas em CPU) |
| `python scripts\03_avaliar.py` | Métricas e matriz de confusão no split de teste |
| `python scripts\04_auditar_rotulos.py --dry-run` | Plano da auditoria de rótulos com LLM (sem gastar) |
| `python scripts\06_treinar_gestao.py` | Treina o modelo sintético de atraso de lotes |
| `python scripts\10_treinar_produtividade_publica.py` | Treina o modelo de produtividade (dados UCI) |
| `python scripts\08_testar_gestao.py` | Testes da gestão |
| `python scripts\12_testar_financeiro_produtividade.py` | Testes do financeiro e da produtividade |
| `python scripts\09_verificar_integracao_gestao.py` | Sobe o app completo em memória e confere as rotas |

Detalhes e limites de cada extensão: [docs/GESTAO_ADITIVA.md](docs/GESTAO_ADITIVA.md) e [docs/FINANCEIRO_E_PRODUTIVIDADE_PUBLICA.md](docs/FINANCEIRO_E_PRODUTIVIDADE_PUBLICA.md). Os modelos de gestão e produtividade são experimentos, sem validação na Duas Marias, e não automatizam decisões.

## Protótipo F0 (frontend)

Node.js 22.12+ ou 24 LTS e npm:

```powershell
cd frontend
npm ci
npm run dev
```

Abra http://127.0.0.1:5173 e entre com email e senha **fictícios**. Para compilar: `npm run build`; para testar: `npm test`. Os builds das telas `/gestao` e `/financeiro` usam `vite.gestao.config.ts` e `vite.business.config.ts` e gravam direto em `src/pontocerto/management/static` e `src/pontocerto/business/static`.

O protótipo usa dados fictícios em memória: cadastros reiniciam ao recarregar, o upload de imagem não faz análise real e os scores de risco são fixos. Indicadores, regras e próximas etapas estão em [docs/ENTREGA_ATUAL.md](docs/ENTREGA_ATUAL.md), [docs/VERIFICACAO_F0.md](docs/VERIFICACAO_F0.md) e [docs/CONTINUIDADE_E_DATASETS.md](docs/CONTINUIDADE_E_DATASETS.md).

## Estrutura

```
.
├── config.yaml, requirements.txt, .env.example
├── Iniciar-Completo.ps1, Iniciar-Gestao.ps1   # atalhos do Windows
├── src/pontocerto/
│   ├── app/          # servidor FastAPI da inspeção, interface, Supabase
│   ├── data/         # dataset e transformações de imagem
│   ├── inference/    # preditor, suavização, Grad-CAM
│   ├── llm/          # OpenRouter: diagnóstico, segunda opinião, relatório
│   ├── training/     # treino da CNN
│   ├── management/   # extensão /gestao
│   └── business/     # extensões /financeiro e /produtividade
├── scripts/          # 00 a 12: verificar, treinar, avaliar, rodar, testar
├── tests/            # testes da gestão e do financeiro
├── artifacts/        # modelos treinados, métricas e dados locais
├── supabase/         # schema.sql do banco
├── frontend/         # protótipo React F0 e fontes das telas /gestao e /financeiro
└── docs/
```
