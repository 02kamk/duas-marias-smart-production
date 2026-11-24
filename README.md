# Ponto Certo

Sistema da Ponto Certo para inspecionar costuras, num servidor só e com login (`/`):

- **Inspeção**: câmera ou foto + rede neural que aprova ou reprova cada costura. Mostra onde a IA olhou, guarda o histórico por dia e pede conferência humana só de defeitos e leituras incertas.
- **Lotes**: cada lote (código, cliente e quantidade) junta as peças de um pedido e mostra quantas foram inspecionadas, quantas tiveram defeito e quais defeitos, com relatório de qualidade em PDF. Os lotes ficam no Supabase.

No celular, o sistema pode ser instalado como aplicativo (PWA). A análise das fotos roda no servidor.

O contexto do projeto está em [docs/CONTEXTO_PROJETO.md](docs/CONTEXTO_PROJETO.md) e a arquitetura da inspeção em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Instalar (uma vez)

Python 3.11 ou mais novo. No PowerShell, na raiz do repositório:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-treino.txt   # servidor + modelo local/treino (~1 GB por causa do torch)
python scripts\verificar_ambiente.py
```

O verificador lista o que falta e diz qual é o próximo comando. O modelo treinado já vem no repositório (`artifacts/modelo.pt`), então o dataset só é necessário para treinar de novo.

Para treinar, os dados ficam em `dados/` (fora do git):
- **StitchingNet** (costura, 11 tecidos, normal + 10 falhas; [Mendeley](https://data.mendeley.com/datasets/6tdthsjgfc/1), uso não comercial): as pastas `A. Cotton-Poly` … `K. Polyester (coated)-Core` vão em `dados/treino/`.
- **ZJU-Leaper** (defeitos de tecido, 19 padrões; [página](https://nico-zck.github.io/zju-leaper), CC BY-NC-SA 4.0, uso acadêmico): o `.7z` vai em `dados/zju-leaper/zju-leaper.zip` e o `05_preparar_zju.py` gera os recortes da classe **Defeito no tecido**. Precisa do 7-Zip instalado.

Se o `pip install` falhar por caminho longo demais (comum dentro do OneDrive), crie o ambiente fora da pasta: `python -m venv "$env:TEMP\ponto-certo-venv"`. O atalho abaixo encontra esse ambiente sozinho.


## Usar

```powershell
.\Iniciar.ps1           # abre o sistema neste computador
.\Iniciar.ps1 -Rede     # também pelo celular, na mesma rede Wi-Fi
```

O navegador abre em **http://127.0.0.1:8000/login**. No primeiro acesso, crie a conta com senha forte; não existe senha padrão. As contas das outras pessoas são criadas, redefinidas e removidas em **Ajustes › Contas**. Com o Supabase Auth ligado (veja abaixo), quem esquecer a senha usa **Esqueci a senha** na tela de entrar e recebe um link por e-mail. Se ninguém mais consegue entrar, use `python scripts\redefinir_senha.py email` no computador do sistema. Com `-Rede`, a janela mostra o endereço para abrir no celular. Pelo celular, use **Fotografar**: a câmera ao vivo do navegador exige HTTPS.

Sem o atalho: `python scripts\rodar.py` (aceita `--rede`, `--porta 8080` e `--abrir`).

### No dia a dia

O menu tem Início, Inspecionar, Conferir, Histórico, Lotes e Relatórios; embaixo ficam o seu perfil, Ajustes e Sair.

- **Início**: o dia em números (inspecionadas, aprovadas, com defeito, aguardando conferência), os defeitos de hoje e os lotes em aberto.
- **Relatórios**: escolha *Hoje*, *7 dias*, *30 dias* ou as datas; mostra os defeitos por tipo, por lote e por dia, e baixa o PDF do período.
- **Perfil** (no seu nome, embaixo do menu): nome, foto e troca da própria senha.

1. **Lotes**: *Novo lote* pede código, cliente, quantidade e, se quiser, a peça. Toque num lote para ver os defeitos encontrados, baixar o relatório de qualidade (PDF), *Inspecionar este lote* ou *Concluir lote*.
2. **Inspecionar**: escolha o lote no topo (ou deixe *Sem lote*) e use *Fotografar* ou *Enviar foto*. O resultado mostra a foto, o veredito e o que fazer; *Está certo* confirma com um toque, *Corrigir* abre a lista de defeitos e *Próxima peça* repete a captura.
3. **Conferir**: fila das peças com defeito ou leitura incerta, uma por vez. O número ao lado do menu mostra quantas faltam.

### Configuração opcional (`.env`)

Copie `.env.example` para `.env`. Sem ele tudo funciona e fica guardado neste computador:

- **`OPENROUTER_API_KEY`**: com ela, **cada peça é lida por uma IA de visão** (Claude Haiku 5.5, cerca de US$ 0,50 a cada 1000 peças e 5 s por leitura). A IA recebe a foto, a lista dos 12 tipos de defeito e um quadro com um exemplo de cada um (`artifacts/referencia_defeitos.jpg`), e marca onde está o defeito. Na câmera ao vivo do computador, a leitura acontece sozinha quando a peça fica parada. O teto diário é `llm.leitura_limite_diario` no `config.yaml` (400). Sem a chave, ou passado o teto, vale o modelo local, que foi treinado em fotos de laboratório e erra bastante em fotos reais.
- **`SUPABASE_*`**: grava lotes, inspeções e fotos de defeito no banco. Rode [supabase/schema.sql](supabase/schema.sql) no SQL Editor, crie um bucket **privado** `Capturas` e preencha as variáveis. Sem o Supabase, a inspeção funciona neste computador, mas não há lotes. Sem internet, as gravações esperam em `artifacts/pendentes.jsonl` e são reenviadas depois.
  Com `SUPABASE_URL` e `SUPABASE_SECRET_KEY` preenchidas, as **contas de login** ficam no **Supabase Auth** (Authentication › Users no painel), então a mesma conta entra em qualquer computador e *Esqueci a senha* manda o link por e-mail. Em Authentication › URL Configuration, cadastre em *Redirect URLs* o endereço `http://127.0.0.1:8000/redefinir-senha` (e o do celular, se usar `-Rede`). O e-mail padrão do Supabase só envia para membros da equipe do projeto e poucos por hora; para mandar a qualquer pessoa, configure um SMTP próprio em Authentication › Emails. Para entrar é preciso internet; quem já entrou continua usando o sistema se ela cair. Sem essas variáveis, as contas ficam só neste computador.

O passo a passo completo está em [docs/testes/CONFIGURACAO_LOCAL.md](docs/testes/CONFIGURACAO_LOCAL.md).

## Colocar online (Vercel, plano gratuito)

O sistema roda na Vercel em "modo online": sem disco permanente e sem tarefa de fundo, então histórico das peças, sessões de login, ajustes, gasto da IA e fotos ficam no Supabase (tabelas `pc_*`, criadas sozinhas, e a pasta `capturas/` do bucket). A leitura das peças é sempre pela IA; o modelo local (PyTorch) não vai para a Vercel. A entrada é o `app.py` da raiz e a configuração está em `vercel.json`; a Vercel instala só o `requirements.txt`.

1. Em [vercel.com](https://vercel.com), **Add New › Project** e importe este repositório do GitHub (framework: FastAPI, sem comando de build).
2. Em **Settings › Environment Variables**, cadastre: `SUPABASE_DB_URL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_BUCKET`, `OPENROUTER_API_KEY` e `ADMIN_EMAILS` (e-mails de quem aprova contas novas, separados por vírgula). Sem `ADMIN_EMAILS`, qualquer pessoa na internet consegue criar conta e entrar.
3. Faça o deploy. No Supabase, em **Authentication › URL Configuration**, cadastre `https://SEU-ENDERECO.vercel.app/redefinir-senha` em *Redirect URLs*.

**Publicação automática:** a Vercel acompanha a `main` de [raffamichels/duas-marias-smart-production](https://github.com/raffamichels/duas-marias-smart-production), que é só um espelho da `main` deste repositório. A Action `espelho.yml` de lá (na branch `espelho`) copia a `main` a cada 30 minutos; para publicar na hora, rode `gh workflow run espelho.yml -R raffamichels/duas-marias-smart-production`. Não faça commits na `main` do espelho. Endereço: https://duas-marias-smart-production.vercel.app

Contas novas ficam "aguardando aprovação" até um administrador aprovar em **Perfil › Ajustes › Contas**. No plano gratuito do Supabase, o projeto pausa depois de uma semana sem uso; é só reativar no painel.

## Testar

```powershell
python scripts\testar.py              # testes Python
python scripts\testar.py acceptance   # só um arquivo (tests/test_acceptance.py)
```

## Treinar o modelo (opcional)

| Comando | O que faz |
|---|---|
| `python scripts\05_preparar_zju.py` | Gera recortes 224×224 do ZJU-Leaper (defeitos de tecido) em `dados/treino/Z. ZJU-Leaper` |
| `python scripts\01_preparar_dados.py` | Gera os splits do dataset (`artifacts/splits.csv`) a partir de `dados/treino` |
| `python scripts\02_treinar.py` | Treina a CNN (`artifacts/modelo.pt`; horas em CPU) |
| `python scripts\03_avaliar.py` | Métricas e matriz de confusão no split de teste |
| `python scripts\04_auditar_rotulos.py --dry-run` | Plano da auditoria de rótulos com LLM (sem gastar) |

Cada correção feita na conferência humana entra em `artifacts/correcoes_operador.csv`, que serve de base para o próximo treino.

## Interface

Todas as telas ficam em `src/pontocerto/app/static/index.html`, com uma folha de estilo só (`css/style.css`). `js/app.js` cuida da inspeção, conferência, histórico e lotes; `js/paineis.js`, do Início, Relatórios e Perfil. A fonte (IBM Plex Sans, licença OFL) fica em `static/fonts`, então o sistema tem a mesma aparência sem internet.

Sobre as cores: a paleta creme e terracota foi mantida por decisão do projeto. Terracota é a cor da marca e dos botões. Verde, âmbar e carmim ficam reservados para estado (aprovado, conferir, defeito) e sempre aparecem com texto, porque terracota e carmim são tons próximos e a cor sozinha não basta para distinguir.

## Estrutura do repositório

```
.
├── Iniciar.ps1                 # atalho do Windows
├── config.yaml, requirements.txt, .env.example
├── src/pontocerto/
│   ├── principal.py  # monta inspeção + lotes + login
│   ├── app/          # servidor, interface, login, lotes, relatórios, Supabase
│   ├── data/         # dataset e transformações de imagem
│   ├── inference/    # preditor, suavização, Grad-CAM
│   ├── llm/          # OpenRouter: diagnóstico, segunda opinião, relatório
│   └── training/     # treino da CNN
├── scripts/          # rodar, testar, verificar_ambiente e etapas de treino
├── tests/
├── artifacts/        # modelos treinados, métricas e dados locais
├── supabase/         # schema.sql (lotes e inspeções)
└── docs/             # contexto, arquitetura, testes e histórico
```

Registros de testes ficam em [docs/testes](docs/testes/README.md) e as etapas anteriores do desenvolvimento em [docs/historico](docs/historico/README.md).
