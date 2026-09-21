# Ponto Certo

**Inspecao de costura em tempo real por visao computacional, com apoio de um LLM multimodal.**

---

## O que e o sistema

O Ponto Certo aponta uma camera comum para a costura e diz, quadro a quadro, se o
ponto esta bom ou se ha uma falha — e qual falha. O nucleo e uma rede neural
convolucional (CNN) treinada nas **14.565 imagens** do dataset de costura do
projeto, que classifica a regiao de interesse do video em uma das **11 classes**
da taxonomia (costura normal + 10 tipos de defeito). Essa rede roda **na CPU da
propria maquina, offline e sem custo por uso**: e ela, e somente ela, quem toma
a decisao em tempo real. O veredito passa ainda por uma suavizacao temporal
(media exponencial + N quadros consecutivos acima do limiar) para que o alarme
nao pisque a cada tremida da mao.

O segundo componente e um **LLM multimodal** (modelos com visao, acessados pelo
OpenRouter). Ele **nao treina a CNN, nao aprende com o dataset e nao decide
sozinho o veredito de producao**. Ele entra em tres papeis concretos e
verificaveis: **(1) auditor de rotulos**, antes do treino — revisa amostras do
conjunto de treino e aponta imagens provavelmente mal rotuladas, melhorando o
dado que alimenta a rede; **(2) segunda opiniao**, durante o uso — quando a
confianca da CNN cai na faixa de incerteza (`limiar_incerteza` no
`config.yaml`), o recorte vai para o modelo de visao, que concorda ou discorda e
justifica em texto; **(3) explicador tecnico** — converte a classe prevista em
causa provavel e acao corretiva na maquina de costura ("tensao da linha
superior alta demais", "troque a agulha por uma mais fina") e escreve o
relatorio de turno.

Essa separacao e deliberada e e a resposta honesta a pergunta "o LLM treinou a
rede?": **nao**. A rede foi treinada por gradiente descendente sobre imagens
rotuladas, do jeito classico. O LLM melhora o dado antes, questiona a decisao
quando ela e fraca, e traduz o resultado para a linguagem de quem opera a
maquina. Se voce rodar o sistema **sem chave de API**, tudo continua
funcionando: a camera, a CNN, o Grad-CAM, os eventos, o historico e o relatorio
local. Voce perde apenas o diagnostico generativo, a segunda opiniao e a
auditoria de rotulos.

---

## As 11 classes

| # | Classe (portugues) | Pasta no dataset | Gravidade | O que e |
|---|---|---|---|---|
| 0 | Costura normal | `0. Normal` | ok | Pontos uniformes, tensao equilibrada e alinhamento correto. |
| 1 | Ponto falhado | `1. Skipped stitch` | alta | A agulha nao prendeu a linha da bobina e deixou um vao na carreira. |
| 2 | Ponto quebrado | `2. Broken stitch` | alta | A linha rompeu durante a costura, interrompendo a carreira de pontos. |
| 3 | Tecido beliscado | `3. Pinched fabric` | alta | Uma dobra do tecido foi presa sob o calcador e costurada junto. |
| 4 | Costura torta | `4. Crooked seam` | media | A carreira fugiu da linha de referencia da peca. |
| 5 | Linha frouxa | `5. Thread sagging` | media | Lacadas soltas por tensao insuficiente na linha superior ou da bobina. |
| 6 | Franzimento | `6. Puckering` | media | O tecido enrugou ao longo da costura por tensao ou arraste desigual. |
| 7 | Mancha ou dano | `7. Stain and damage` | alta | Sujeira, oleo, furo ou rasgo no tecido na regiao da costura. |
| 8 | Marca de agulha | `8. Needle mark` | leve | Furos visiveis deixados pela agulha, geralmente por agulha grossa ou cega. |
| 9 | Linha da bobina subindo | `9. Bobbin thread pulling up` | media | A linha da bobina aparece na face superior por desequilibrio de tensao. |
| 10 | Ponto sobreposto | `10. Overlapped stitch` | leve | Duas carreiras de pontos se sobrepoem no mesmo trecho. |

A taxonomia vive em um unico lugar: `src/pontocerto/labels.py`. Nenhum outro
modulo redefine essa lista.

---

## O dataset

| Item | Valor |
|---|---|
| Imagens | **14.565** arquivos JPG |
| Resolucao | **224x224 RGB** (todas, ja recortadas) |
| Tecidos | **11** (`A. Cotton-Poly` ... `K. Polyester (coated)-Core`) |
| Classes | **11** (0 a 10) |
| Arquivos corrompidos | **0** (auditado) |
| Nome dos arquivos | `LETRA_CLASSE_SEQ.jpg`, por exemplo `A_00_001.jpg` |

Distribuicao por classe: a classe **Normal tem 2.436 imagens**; as **demais 10
classes ficam entre 1.162 e 1.257** cada. Esse desbalanceamento e compensado no
treino por pesos de classe na funcao de perda (`treino.pesos_por_classe: true`).

Divisao estratificada por par (tecido, classe), semente 42, gerada por
`scripts/01_preparar_dados.py`:

| Split | Imagens | Proporcao |
|---|---|---|
| treino | 10.198 | 70,0% |
| validacao | 2.189 | 15,0% |
| teste | 2.178 | 15,0% |

Cada um dos 121 grupos (11 tecidos x 11 classes) aparece nos tres splits — ou
seja, nenhum tecido fica de fora do teste.

---

## Instalacao no Windows

Abra o **PowerShell** na pasta que contem este README (`pontocerto`).

```powershell
# 1. Crie o ambiente virtual (uma unica vez)
python -m venv .venv

# 2. Ative o ambiente (toda vez que abrir um terminal novo)
.venv\Scripts\activate

# 3. Atualize o pip e instale as dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Confira se esta tudo no lugar
python scripts\00_verificar_ambiente.py
```

O passo 3 baixa cerca de 1 GB (torch e torchvision). Em uma conexao domestica
leva de 5 a 15 minutos.

> **Se o PowerShell recusar o `activate`** com "execucao de scripts desabilitada",
> rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

O verificador de ambiente e o mapa da situacao: ele lista pacote por pacote,
conta as imagens do dataset, diz se ha GPU, se o manifesto foi gerado, se o
modelo ja foi treinado, se a webcam responde — e termina imprimindo **o proximo
comando recomendado**.

### Onde o sistema procura o dataset

A chave `dados.raiz` do `config.yaml` vale `".."`, ou seja, **a pasta que contem
a pasta `pontocerto`**. E la que devem estar as 11 pastas `A. Cotton-Poly`,
`B. Linen-Poly`, ... `K. Polyester (coated)-Core`. Se o seu dataset estiver em
outro lugar, edite essa unica chave.

---

## Chave do OpenRouter (opcional)

O sistema funciona **sem chave nenhuma**. Com chave, voce ganha os tres papeis
do LLM descritos la em cima.

1. Crie uma conta e gere a chave em **https://openrouter.ai/keys**
   (a chave comeca com `sk-or-v1-...`).
2. Adicione alguns creditos em https://openrouter.ai/credits. Os modelos
   pequenos com visao custam centavos por dezenas de imagens.
3. Copie o arquivo de exemplo e preencha:

```powershell
copy .env.example .env
notepad .env
```

```
OPENROUTER_API_KEY=sk-or-v1-sua-chave-aqui
OPENROUTER_APP_NAME=Ponto Certo
OPENROUTER_SITE_URL=http://localhost:8000
```

4. Confira: `python scripts\00_verificar_ambiente.py` deve mostrar
   `[ok] OPENROUTER_API_KEY carregada`. Com o app no ar, a rota
   `GET /api/llm/status` faz um teste de verdade contra a API e lista modelos
   de visao validos se o id configurado nao existir mais.

O modelo usado esta em `llm.modelo_visao` / `llm.modelo_texto` do `config.yaml`
(padrao `openai/gpt-4o-mini`). O catalogo do OpenRouter muda com o tempo; por
isso o sistema **consulta a lista de modelos em tempo de execucao** em vez de
confiar cegamente em um id fixo, e sugere substitutos quando o id some.

**Nunca versione o arquivo `.env`.** A chave nunca e impressa em log nem
devolvida em mensagem de erro — o cliente mascara qualquer ocorrencia dela.

### O que voce perde sem a chave

| Recurso | Sem chave |
|---|---|
| Camera, CNN, veredito ao vivo | Funciona |
| Grad-CAM | Funciona |
| Historico, correcao de rotulo pelo operador | Funciona |
| Relatorio de turno | Funciona (versao local, sem redacao do LLM) |
| Diagnostico "causa provavel / acao corretiva" | Versao local da base de conhecimento, sem texto gerado |
| Segunda opiniao em caso de incerteza | **Indisponivel** |
| Auditoria de rotulos (etapa 04) | **Indisponivel** |

---

## Fluxo completo de uso

Todos os comandos rodam de dentro da pasta `pontocerto`, com o `.venv` ativo.

| # | Comando | O que faz | Tempo aproximado |
|---|---|---|---|
| 0 | `python scripts\00_verificar_ambiente.py` | Diagnostico do ambiente e proximo passo | 10 a 40 s |
| 1 | `python scripts\01_preparar_dados.py` | Varre o dataset e gera `artifacts/splits.csv` | 10 a 60 s |
| 2 | `python scripts\04_auditar_rotulos.py --dry-run` | Mostra o plano de auditoria e o custo, sem gastar | segundos |
| 3 | `python scripts\04_auditar_rotulos.py` | Auditoria de rotulos com o LLM (**opcional**) | 3 a 10 min |
| 4 | `python scripts\02_treinar.py` | Treina a CNN e grava `artifacts/modelo.pt` | **2 a 6 h em CPU** |
| 5 | `python scripts\03_avaliar.py` | Matriz de confusao e metricas no split de teste | 2 a 6 min |
| 6 | `python scripts\05_rodar_app.py` | Sobe a interface em http://127.0.0.1:8000 | instantaneo |

Detalhes uteis:

- **Etapa 1** so precisa rodar uma vez. Use `--forcar` para refazer do zero.
- **Etapa 3** e opcional e custa creditos. Rode sempre o `--dry-run` antes.
- **Etapa 4** e a demorada. Para um **ensaio de 3 a 8 minutos** que percorre o
  caminho inteiro (util para conferir que tudo funciona antes de deixar o treino
  de verdade rodando a noite):
  ```powershell
  python scripts\02_treinar.py --limite-por-classe 60 --epocas 2
  ```
  O modelo resultante **nao serve para producao**, so para validar o pipeline.
  Ctrl+C no meio do treino nao corrompe nada: o melhor checkpoint ja gravado
  continua valido.
- **Etapa 6**: a camera **nao liga sozinha**. Abra o navegador, va na aba
  "Ao vivo" e clique em "Ligar camera".

Opcoes do treino: `--backbone`, `--epocas`, `--batch-size`, `--lr`,
`--workers`, `--limite-por-classe`, `--saida`, `--sem-pretrained`. Todos os
padroes vem do `config.yaml`.

---

## Como apontar a camera

A qualidade do veredito depende muito mais da imagem do que do modelo. Em
ordem de impacto:

1. **Iluminacao difusa, nunca direta.** Uma luminaria de LED apontada para o
   teto ou para uma folha branca (rebatedor) da uma luz espalhada. Luz direta
   produz reflexo especular no fio de poliester e no tecido acetinado — o brilho
   branco vira "mancha" para a rede.
2. **Distancia de 15 a 30 cm** entre a lente e o tecido, com a camera
   aproximadamente perpendicular a superficie. Muito perto, a maioria das
   webcams perde o foco; muito longe, o ponto some.
3. **ROI sobre a costura.** O retangulo desenhado na tela e a unica regiao
   analisada — o resto do quadro e ignorado. Enquadre a **carreira de pontos
   ocupando a maior parte do retangulo**, na diagonal ou na horizontal. A ROI
   padrao e o quadrado central (50% x 50%); ajuste em `camera.roi` no
   `config.yaml` (`[x, y, largura, altura]` em fracao do quadro).
4. **Foco.** Se a webcam tem foco automatico, mexa a peca devagar ate a imagem
   ficar nitida e entao pare. Um quadro borrado derruba a confianca e joga o
   sistema para a faixa de incerteza.
5. **Fundo contrastante.** Tecido claro sobre mesa escura (e vice-versa) ajuda
   a rede a separar o tecido do plano de fundo.
6. **Sem tremida.** Apoie a camera em um suporte. O sistema so declara falha
   apos N quadros consecutivos concordarem (`inferencia.frames_para_confirmar`);
   tremor faz a confianca oscilar e o veredito demorar.

---

## Estrutura de pastas

```
pontocerto/
├── config.yaml                  # configuracao unica do sistema (caminhos, treino, LLM, camera)
├── requirements.txt             # dependencias Python
├── .env.example                 # modelo do .env (copie e preencha a chave)
├── README.md                    # este arquivo
│
├── docs/
│   ├── ARQUITETURA.md           # diagrama do fluxo, modulos, rotas da API, decisoes de projeto
│   └── COMO_APRESENTAR.md       # roteiro de 8 minutos para a banca
│
├── scripts/                     # atalhos de linha de comando (os "botoes" do projeto)
│   ├── 00_verificar_ambiente.py # diagnostico completo do ambiente
│   ├── 01_preparar_dados.py     # -> pontocerto.data.split
│   ├── 02_treinar.py            # -> pontocerto.training.train
│   ├── 03_avaliar.py            # -> pontocerto.training.evaluate
│   ├── 04_auditar_rotulos.py    # -> pontocerto.llm.auditoria (opcional, usa LLM)
│   └── 05_rodar_app.py          # -> pontocerto.app.server
│
├── src/pontocerto/              # o pacote de verdade
│   ├── config.py                # le o config.yaml, resolve caminhos, acha a chave do .env
│   ├── labels.py                # taxonomia unica: 11 classes e 11 tecidos
│   │
│   ├── data/
│   │   ├── split.py             # varre o dataset e gera artifacts/splits.csv estratificado
│   │   ├── dataset.py           # Dataset PyTorch + DataLoaders + pesos de classe
│   │   └── transforms.py        # aumentos de dados pensados para costura
│   │
│   ├── training/
│   │   ├── model.py             # cria o backbone, troca a cabeca, salva/carrega checkpoint
│   │   ├── train.py             # laco de treino, early stopping, historico
│   │   ├── evaluate.py          # matriz de confusao, metricas por classe e por tecido
│   │   └── export.py            # TorchScript e (tentativa de) ONNX
│   │
│   ├── inference/
│   │   ├── predictor.py         # carrega o modelo e classifica um frame BGR
│   │   ├── gradcam.py           # mapa de calor da regiao que pesou na decisao
│   │   └── smoothing.py         # suavizacao temporal e geracao de eventos
│   │
│   ├── llm/
│   │   ├── openrouter.py        # unico cliente HTTP do projeto (retry, rate limit, JSON)
│   │   ├── prompts.py           # prompts e esquemas JSON de resposta
│   │   ├── review.py            # segunda opiniao sobre uma predicao incerta
│   │   ├── diagnosis.py         # causa provavel, acao corretiva e relatorio de turno
│   │   └── auditoria.py         # auditoria de rotulos do conjunto de treino
│   │
│   └── app/
│       ├── server.py            # FastAPI: rotas, streaming MJPEG e thread de inferencia
│       ├── camera.py            # captura em thread, backend DSHOW no Windows, recorte da ROI
│       ├── state.py             # eventos da sessao, capturas, correcoes do operador
│       └── static/              # interface web (index.html, css, js)
│
└── artifacts/                   # tudo que e gerado (pode apagar e refazer)
    ├── splits.csv               # manifesto: caminho, classe, tecido, split
    ├── modelo.pt                # checkpoint treinado
    ├── historico_treino.json    # perda/acuracia/F1 por epoca
    ├── auditoria_rotulos.csv    # saida da etapa 04
    ├── avaliacao/               # matrizes de confusao, metricas.json, graficos
    ├── capturas/                # JPEG de cada evento detectado
    ├── relatorios/              # relatorios de turno em markdown
    └── correcoes_operador.csv   # rotulos corrigidos na tela de Historico
```

---

## Resultados

> **Preencher apos o treino.** Rode `python scripts\03_avaliar.py` e copie os
> numeros de `artifacts/avaliacao/metricas.json` para a tabela abaixo. Nao
> preencha com estimativa: a banca vai perguntar de onde veio o numero.

| Metrica | Valor |
|---|---|
| Acuracia geral (11 classes) | _preencher apos o treino_ |
| Macro-F1 | _preencher apos o treino_ |
| Acuracia OK / NG (Normal x resto) | _preencher apos o treino_ |
| Classe com pior F1 | _preencher apos o treino_ |
| Tecido com pior acuracia | _preencher apos o treino_ |
| Tempo de inferencia por quadro (CPU) | _preencher apos o treino_ |

A **acuracia OK/NG** e a metrica que mais importa na producao: confundir "ponto
falhado" com "ponto quebrado" custa pouco (os dois param a peca); deixar passar
uma peca defeituosa como normal custa caro.

---

## Solucao de problemas

### A camera nao abre no Windows

Sintoma: `[!] Nenhum backend conseguiu ler a camera 0` no verificador, ou
"Camera desligada" fixo na tela.

1. **Outro programa esta com a webcam.** Teams, Zoom, Meet, OBS e o app "Camera"
   do Windows tomam o dispositivo com exclusividade. Feche todos e tente de novo.
2. **Permissao do Windows.** Configuracoes > Privacidade e seguranca > Camera >
   ative "Permitir que aplicativos da area de trabalho acessem sua camera".
3. **Backend errado.** O padrao no Windows e o DirectShow (`CAP_DSHOW`), que abre
   muito mais rapido que o MSMF. Se a sua camera so funciona no MSMF, mude
   `camera.backend` no `config.yaml` para `msmf` (ou `any`).
4. **Indice errado.** Notebooks com camera integrada + webcam USB tem dois
   dispositivos. Teste: `python scripts\00_verificar_ambiente.py --camera 1`.
   No app, a rota `GET /api/camera/dispositivos` lista os indices que respondem.
5. **Camera virtual.** Drivers de camera virtual (OBS, NVIDIA Broadcast) as vezes
   ocupam o indice 0 sem entregar quadro. Desinstale ou use outro indice.

### "Modelo nao encontrado" / "Modelo nao carregado"

O servidor **sobe de proposito** sem modelo, para voce poder ver a interface.
A mensagem vem de `artifacts/modelo.pt` ausente. Rode
`python scripts\02_treinar.py`. Para conferir o diagnostico exato, abra
`http://127.0.0.1:8000/api/saude` — o campo `modelo.erro` diz o motivo real.

### `pip install` falha no torch

- Use Python **3.10 a 3.13, 64 bits**. O torch nao publica roda para 32 bits.
- Conexao instavel derruba o download de ~800 MB. Tente
  `pip install --no-cache-dir -r requirements.txt`.
- Se a instalacao tentar puxar uma versao CUDA gigante sem voce ter GPU, force a
  versao de CPU:
  `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`
- Sem espaco em disco: o pacote descompactado passa de 2 GB.

### Porta 8000 ocupada

Sintoma: `[WinError 10048] normalmente e permitida apenas uma utilizacao de cada
endereco de soquete`.

```powershell
# Descobrir quem esta na porta
netstat -ano | findstr :8000
# A ultima coluna e o PID; para encerrar:
taskkill /PID <numero> /F

# Ou simplesmente use outra porta
python scripts\05_rodar_app.py --porta 8080
```

### Erro 401 ou 402 do OpenRouter

- **401 (chave invalida):** a chave foi revogada, tem espaco sobrando, ou o
  `.env` guardou o valor de exemplo. Gere outra em
  https://openrouter.ai/keys e cole no `.env` **sem aspas**.
- **402 (sem creditos):** adicione saldo em https://openrouter.ai/credits, ou
  troque `llm.modelo_visao` por um modelo mais barato.
- **429 (limite de taxa):** o cliente ja repete sozinho com espera de 1 s, 2 s e
  4 s. Se persistir, reduza `llm.max_chamadas_por_minuto` no `config.yaml`.
- **404 (modelo nao existe):** o catalogo do OpenRouter mudou.
  `GET /api/llm/status` lista ids validos com entrada de imagem; escolha um e
  atualize `llm.modelo_visao`.

### O treino esta muito lento

Em CPU isso e esperado — nao ha AMP nem GPU nesta maquina. O que ajuda de verdade:

- Mantenha o backbone `mobilenet_v3_small` (o padrao). `resnet18` e
  `mobilenet_v3_large` custam varias vezes mais.
- `--workers 6` (padrao) ja e bom para 12 nucleos. Nao passe do numero de
  nucleos fisicos: o carregamento de imagem vira o gargalo.
- Feche navegador e Teams enquanto treina; eles disputam os mesmos nucleos.
- Para validar o pipeline em minutos, use
  `--limite-por-classe 60 --epocas 2`.
- Deixe o treino completo rodando a noite ou durante uma aula. O early stopping
  (paciencia de 4 epocas sem melhora no macro-F1) encerra sozinho.

### A tela fica em "Analisando..." e nao sai

A suavizacao temporal precisa acumular `inferencia.frames_para_confirmar`
quadros (padrao 4) antes de declarar qualquer coisa. Se ficar preso:

- a camera pode estar entregando quadros muito escuros ou borrados;
- a confianca pode estar abaixo de `inferencia.limiar_alerta` o tempo todo —
  ajuste na aba "Ajustes", sem reiniciar o servidor.

---

## Limitacoes honestas

Estas limitacoes sao reais e devem ser ditas na apresentacao antes que a banca
pergunte.

1. **O dataset e de imagens estaticas 224x224 ja recortadas.** Cada imagem e um
   close bem enquadrado da costura, com iluminacao controlada e fundo
   consistente. A camera ao vivo tem **dominio diferente**: outra iluminacao,
   outro angulo, outro fundo, ruido de ganho, desfoque de movimento, compressao
   da webcam. **A acuracia real na bancada cai** em relacao a acuracia medida no
   split de teste. Isso e deslocamento de dominio, nao bug.

2. **O sistema classifica a ROI inteira; nao localiza a falha.** O dataset nao
   tem caixas delimitadoras, entao nao da para treinar um detector de objetos.
   A resposta e "esta ROI parece um ponto falhado", nao "ha um ponto falhado
   nestas coordenadas". O **Grad-CAM da uma indicacao aproximada** da regiao que
   mais pesou na decisao — e util para o operador e para explicar o modelo, mas
   **nao e uma caixa de deteccao** e nao deve ser apresentado como tal.

3. **Uma classe por quadro.** Se a ROI contem franzimento *e* mancha, o modelo
   escolhe a mais provavel. A lista "top 3" na interface existe justamente para
   mostrar a segunda e a terceira hipoteses.

4. **11 tipos de tecido, nem um a mais.** Um tecido fora dessa lista (malha,
   couro, tecido estampado com padrao forte) pode confundir a rede, porque
   textura estampada se parece com defeito.

5. **Recomendacao pratica:** para uso real na bancada, **colete algumas centenas
   de imagens com a sua propria camera**, no seu proprio ponto de luz, rotule-as
   com a mesma taxonomia (a aba "Historico" ja grava as correcoes do operador em
   `artifacts/correcoes_operador.csv`) e faca um **ajuste fino** por cima do
   modelo atual. E o caminho mais curto entre a demonstracao e a producao.

6. **O LLM nao e infalivel.** A segunda opiniao e um modelo de linguagem com
   visao olhando um JPEG pequeno; ele erra, especialmente em defeitos sutis como
   marca de agulha. Ele foi colocado como **apoio a decisao humana**, nunca como
   arbitro final. O operador continua sendo quem decide, e a correcao dele e
   gravada.

---

## Licenca e creditos

Projeto integrador academico. O dataset de costura pertence aos seus autores
originais e e usado aqui apenas para fins de estudo.
