# Duas Marias Smart Production

Sistema da Duas Marias para a produção de costura, num servidor só e com login:

| Parte | O que faz | Endereço |
|---|---|---|
| **Inspeção** | Câmera ou foto + rede neural que aprova ou reprova cada costura. Mostra onde a IA olhou, guarda o histórico por dia e pede conferência humana só de defeitos e leituras incertas. | `/` |
| **Gestão** | Recebimento da OP com grade e aviamentos, lotes, apontamento de produção, distribuição de tarefas, equipe e previsão de entrega. | `/gestao` |

No celular, o sistema pode ser instalado como aplicativo (PWA). A análise das fotos roda no servidor.

O contexto do projeto está em [docs/CONTEXTO_PROJETO.md](docs/CONTEXTO_PROJETO.md) e a arquitetura da inspeção em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Instalar (uma vez)

Python 3.11 ou mais novo. No PowerShell, na raiz do repositório:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt      # ~1 GB por causa do torch
python scripts\verificar_ambiente.py
```

O verificador lista o que falta e diz qual é o próximo comando. O modelo treinado já vem no repositório (`artifacts/modelo.pt`), então o dataset só é necessário para treinar de novo.

Para treinar, os dados ficam em `dados/` (fora do git):
- **StitchingNet** (costura, 11 tecidos, normal + 10 falhas; [Mendeley](https://data.mendeley.com/datasets/6tdthsjgfc/1), uso não comercial): as pastas `A. Cotton-Poly` … `K. Polyester (coated)-Core` vão em `dados/treino/`.
- **ZJU-Leaper** (defeitos de tecido, 19 padrões; [página](https://nico-zck.github.io/zju-leaper), CC BY-NC-SA 4.0, uso acadêmico): o `.7z` vai em `dados/zju-leaper/zju-leaper.zip` e o `05_preparar_zju.py` gera os recortes da classe **Defeito no tecido**. Precisa do 7-Zip instalado.

Se o `pip install` falhar por caminho longo demais (comum dentro do OneDrive), crie o ambiente fora da pasta: `python -m venv "$env:TEMP\duas-marias-venv"`. O atalho abaixo encontra esse ambiente sozinho.

Para ler a foto da OP no recebimento (opcional): `pip install -r requirements-ocr.txt`.

## Usar

```powershell
.\Iniciar.ps1           # abre o sistema neste computador
.\Iniciar.ps1 -Rede     # também pelo celular, na mesma rede Wi-Fi
```

O navegador abre em **http://127.0.0.1:8000/login**. No primeiro acesso, crie a conta com senha forte; não existe senha padrão. As contas das outras pessoas são criadas, redefinidas e removidas em **Ajustes › Contas**. Se ninguém mais consegue entrar, use `python scripts\redefinir_senha.py email` no computador do sistema. Com `-Rede`, a janela mostra o endereço para abrir no celular. Pelo celular, use **Fotografar**: a câmera ao vivo do navegador exige HTTPS.

Sem o atalho: `python scripts\rodar.py` (aceita `--rede`, `--porta 8080` e `--abrir`).

### No dia a dia

O menu é o mesmo em todas as telas, em dois grupos: **Chão de fábrica** (Inspecionar, Conferir, Histórico, Lotes) e **Gestão** (Receber OP, Produção, Equipe, Relatórios).

1. **Receber OP**: dados da OP, grade pedida na horizontal (PP a XGG) e conferência. Se chegou diferente, marque *Há diferença* e corrija a linha *Recebido*. A quantidade do lote é a soma da grade.
2. **Inspecionar**: escolha o lote no topo e use *Fotografar* ou *Enviar foto*. O resultado mostra a foto, o veredito e o que fazer; *Está certo* confirma com um toque, *Corrigir* abre a lista de defeitos e *Próxima peça* repete a captura.
3. **Conferir**: fila das peças com defeito ou leitura incerta, uma por vez. O número ao lado do menu mostra quantas faltam.
4. **Lotes**: a lista já mostra *No prazo*, *Em risco* (com a data prevista) ou *Atrasado*. Toque num lote para ver o que fazer; *Inspecionar* leva o lote para a tela de inspeção.
5. **Produção**: *Apontamento* registra as peças do dia e permite corrigir ou excluir um lançamento (sempre com motivo); *Distribuir tarefas* reserva o tempo de cada pessoa.

### Configuração opcional (`.env`)

Copie `.env.example` para `.env`. Sem ele tudo funciona e fica guardado neste computador:

- **`OPENROUTER_API_KEY`**: sem ela, as explicações usam a base técnica local, sem segunda opinião da IA.
- **`SUPABASE_*`**: grava lotes, inspeções e fotos de defeito no banco. Rode [supabase/schema.sql](supabase/schema.sql) e [supabase/gestao.sql](supabase/gestao.sql) no SQL Editor, crie um bucket **privado** `Capturas`, preencha as variáveis e use `GESTAO_STORAGE=supabase`. Sem internet, as gravações esperam em `artifacts/pendentes.jsonl` e são reenviadas depois.
  Com a `SUPABASE_DB_URL` preenchida, as **contas de login** também ficam no banco (tabela `contas`, criada sozinha na primeira vez; veja [supabase/contas.sql](supabase/contas.sql)), então a mesma conta entra em qualquer computador. Contas que só existiam no computador são levadas para o banco automaticamente. Para entrar é preciso internet; quem já entrou continua usando o sistema se ela cair.
- **`OUTLOOK_*`**: avisos de recebimento por e-mail, sempre conferidos antes de enviar.

O passo a passo completo está em [docs/testes/CONFIGURACAO_LOCAL.md](docs/testes/CONFIGURACAO_LOCAL.md).

## Testar

```powershell
python scripts\testar.py              # testes Python
python scripts\testar.py management   # só um arquivo (tests/test_management.py)
cd frontend; npm ci; npm test          # testes da tela de Gestão
```

## Treinar o modelo (opcional)

| Comando | O que faz |
|---|---|
| `python scripts\05_preparar_zju.py` | Gera recortes 224×224 do ZJU-Leaper (defeitos de tecido) em `dados/treino/Z. ZJU-Leaper` |
| `python scripts\01_preparar_dados.py` | Gera os splits do dataset (`artifacts/splits.csv`) a partir de `dados/treino` |
| `python scripts\02_treinar.py` | Treina a CNN (`artifacts/modelo.pt`; horas em CPU) |
| `python scripts\03_avaliar.py` | Métricas e matriz de confusão no split de teste |
| `python scripts\04_auditar_rotulos.py --dry-run` | Plano da auditoria de rótulos com LLM (sem gastar) |
| `python scripts\06_treinar_gestao.py` | Treina o modelo experimental de atraso de lotes |

Cada correção feita na conferência humana entra em `artifacts/correcoes_operador.csv`, que serve de base para o próximo treino.

## Interface

Inspeção e Gestão usam uma folha de estilo só, `src/pontocerto/app/static/css/style.css`, e o mesmo menu (`static/index.html` e `frontend/src/management/Casca.tsx`; ao mudar um, mude o outro). A fonte (IBM Plex Sans, licença OFL) fica em `static/fonts`, então o sistema tem a mesma aparência sem internet.

Sobre as cores: a paleta creme e terracota foi mantida por decisão do projeto. Terracota é a cor da marca e dos botões. Verde, âmbar e carmim ficam reservados para estado (aprovado, conferir, defeito) e sempre aparecem com texto, porque terracota e carmim são tons próximos e a cor sozinha não basta para distinguir.

## Tela de Gestão (React)

As fontes ficam em `frontend/src/management`. Com Node.js 22.12+:

```powershell
cd frontend
npm ci
npm run dev      # com o servidor Python rodando na porta 8000
npm run build    # grava direto em src/pontocerto/management/static
```

## Estrutura do repositório

```
.
├── Iniciar.ps1                 # atalho do Windows
├── config.yaml, requirements.txt, .env.example
├── src/pontocerto/
│   ├── principal.py  # monta inspeção + gestão + login
│   ├── app/          # servidor da inspeção, interface, login, Supabase
│   ├── management/   # gestão (/gestao)
│   ├── data/         # dataset e transformações de imagem
│   ├── inference/    # preditor, suavização, Grad-CAM
│   ├── llm/          # OpenRouter: diagnóstico, segunda opinião, relatório
│   └── training/     # treino da CNN
├── scripts/          # rodar, testar, verificar_ambiente e etapas de treino
├── tests/
├── artifacts/        # modelos treinados, métricas e dados locais
├── supabase/         # schema.sql (inspeção) e gestao.sql
├── frontend/         # fontes React da tela de Gestão
└── docs/             # contexto, arquitetura, testes e histórico
```

Registros de testes ficam em [docs/testes](docs/testes/README.md) e as etapas anteriores do desenvolvimento em [docs/historico](docs/historico/README.md).
