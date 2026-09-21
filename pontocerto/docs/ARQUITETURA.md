# Arquitetura do Ponto Certo

Documento tecnico: como o sistema esta montado, o que cada arquivo faz, qual e o
contrato da API e **por que** cada decisao foi tomada.

---

## 1. Fluxo completo

```
 +------------------------------------------------------------------------+
 |                        TEMPO DE PREPARACAO (offline)                    |
 +------------------------------------------------------------------------+

  dataset bruto                  01_preparar_dados         04_auditar_rotulos
  11 tecidos x 11 classes  --->  data/split.py       --->  llm/auditoria.py
  14.565 JPG 224x224             artifacts/splits.csv      (opcional, usa LLM)
                                        |                        |
                                        |                        v
                                        |               auditoria_rotulos.csv
                                        |               (revisao humana)
                                        v
                                 02_treinar                03_avaliar
                                 training/train.py   --->  training/evaluate.py
                                 artifacts/modelo.pt       artifacts/avaliacao/
                                                            matriz_confusao.png
                                                            metricas.json


 +------------------------------------------------------------------------+
 |                         TEMPO DE USO (em tempo real)                    |
 +------------------------------------------------------------------------+

   +----------+     +---------+     +------------+     +------------------+
   |  CAMERA  | --> |   ROI   | --> |    CNN     | --> |   SUAVIZACAO     |
   | thread A |     | recorte |     | predictor  |     |   TEMPORAL       |
   | 1280x720 |     | 50%x50% |     | 224x224    |     | EMA + N quadros  |
   +----------+     +---------+     +------------+     +------------------+
        |                                  |                    |
        | ultimo quadro                    | Grad-CAM           | Veredito
        | (descarta os velhos)             v                    v
        |                           mapa de calor         +-----------+
        |                                  |              | VEREDITO  |
        v                                  v              | ok |      |
   +-------------------------------------------------+    | incerto | |
   |          MOTOR (thread B, unica)                |    | falha     |
   |  desenha overlay -> JPEG em memoria             |<---+-----------+
   +-------------------------------------------------+          |
        |                          |                            | novo_evento
        v                          v                            v
   GET /api/video            GET /api/status            +----------------+
   (MJPEG, so repete         (le o estado,              |  EVENTO        |
    o ultimo JPEG)            nunca infere)             |  state.py      |
                                                        |  + captura JPG |
                                                        +----------------+
                                                                |
                    +-------------------------------------------+
                    |                          |                |
                    v                          v                v
           (2) SEGUNDA OPINIAO       (3) DIAGNOSTICO      RELATORIO DE TURNO
           llm/review.py             llm/diagnosis.py     llm/diagnosis.py
           so quando a confianca     causa provavel +     markdown em
           < limiar_incerteza        acao na maquina      artifacts/relatorios/
                    |                          |                |
                    +----------> LLM MULTIMODAL (OpenRouter) <---+
                                 llm/openrouter.py
                                 SEM chave -> fallback local, nada quebra
```

Ponto central do desenho: **existe uma unica thread de inferencia** (o `Motor`).
A camera roda em outra thread e so guarda o quadro mais recente. As rotas HTTP
apenas **leem** estado compartilhado. Nenhuma requisicao fica presa esperando a
rede neural — que e o bug classico quando a inferencia roda dentro do gerador
MJPEG (`/api/status` trava enquanto o video roda).

---

## 2. Modulos, arquivo por arquivo

### Fundacao

| Arquivo | Responsabilidade |
|---|---|
| `config.yaml` | Configuracao unica do sistema. Todo caminho relativo aqui e resolvido contra a pasta do arquivo. |
| `src/pontocerto/config.py` | `carregar_config()` devolve um `dict` com acesso por ponto (`cfg.treino.epocas`). Resolve caminhos para absolutos, acha `OPENROUTER_API_KEY` no ambiente ou no `.env`. |
| `src/pontocerto/labels.py` | **Taxonomia canonica.** 11 `ClassInfo` (indice, chave, pasta, nome PT, descricao, gravidade) e 11 `FabricInfo`. Nenhum outro modulo redefine essas listas. |

### Dados

| Arquivo | Responsabilidade |
|---|---|
| `data/split.py` | Varre `<raiz>/<tecido>/<classe>/*.jpg` e grava `artifacts/splits.csv` com as colunas `caminho, classe_idx, classe_key, classe_pasta, tecido_letra, tecido_pasta, split`. Estratifica por par (tecido, classe): cada um dos 121 grupos e embaralhado com semente derivada de `divisao.semente` e fatiado 70/15/15. Deterministico — rodar de novo gera o mesmo CSV. |
| `data/dataset.py` | `DatasetCostura` (le o CSV, abre a imagem, aplica transform) e `construir_dataloaders(cfg, limite_por_classe=None)`, que devolve `{"treino", "validacao", "teste", "pesos_classe", "df"}`. Os pesos compensam o excesso de imagens "Normal". |
| `data/transforms.py` | Aumentos pensados para costura: flip, rotacao pequena, jitter de cor, `RandomResizedCrop` conservador, borrao aleatorio (camera fora de foco) e ruido gaussiano (ganho alto). Normalizacao ImageNet. `preparar_frame_bgr()` e o caminho usado em producao. |

### Treino

| Arquivo | Responsabilidade |
|---|---|
| `training/model.py` | `criar_modelo(backbone, num_classes, pretrained)` para `mobilenet_v3_small`, `mobilenet_v3_large` e `resnet18`, trocando a ultima camada. `camada_alvo_gradcam()` devolve o ultimo bloco convolucional. `salvar_checkpoint()` / `carregar_checkpoint()` no formato do projeto (escrita atomica: Ctrl+C no meio do save nao corrompe). `resolver_dispositivo()`. |
| `training/train.py` | Laco de treino: `CrossEntropyLoss` com `weight=pesos_classe` e `label_smoothing`, `AdamW`, warmup + `CosineAnnealingLR`, early stopping por macro-F1 de validacao. Grava o **melhor** checkpoint e o historico por epoca em JSON. |
| `training/evaluate.py` | Avalia o split `teste`: matriz de confusao (contagem e normalizada), `relatorio_classes.csv`, `metricas.json` e `acertos_por_tecido.png`. Colormap proprio branco -> terracota -> marrom (nada de viridis/jet), rotulos em portugues. |
| `training/export.py` | TorchScript para `artifacts/modelo.torchscript.pt` e tentativa de ONNX para `artifacts/modelo.onnx` (falha de ONNX nao quebra a execucao). |

### Inferencia

| Arquivo | Responsabilidade |
|---|---|
| `inference/predictor.py` | `Preditor(cfg)` carrega o checkpoint. **O construtor nunca levanta excecao**: sem modelo treinado ele nasce com `disponivel == False` e `erro` preenchido, e a API sobe assim mesmo. `prever_bgr()`, `prever_bytes()`, `prever_arquivo()`, `prever_tensor()`. Caminho rapido em `torch.inference_mode()`; caminho com Grad-CAM em `enable_grad()`, fora do `inference_mode` (tensores criados dentro dele nao entram no autograd). Todo forward sob lock, porque varias threads usam o mesmo modelo. |
| `inference/gradcam.py` | `GradCAM(modelo, camada_alvo)` com hooks de ativacao e gradiente, e `aplicar_mapa()` que mistura o mapa ao quadro BGR com o colormap quente do projeto. |
| `inference/smoothing.py` | `SuavizadorTemporal(cfg)`: media exponencial das probabilidades (`ema_alpha`) + exigencia de `frames_para_confirmar` quadros consecutivos acima de `limiar_alerta`, com `cooldown_evento_s` entre dois eventos iguais. Devolve um `Veredito` com `estado` (`aquecendo` / `ok` / `incerto` / `falha`), `estavel`, `novo_evento` e `pede_llm`. |

### Aplicacao

| Arquivo | Responsabilidade |
|---|---|
| `app/camera.py` | Captura em thread daemon, sempre guardando **so o quadro mais novo** (o consumidor nunca fica atrasado). No Windows tenta DSHOW, depois MSMF, depois ANY. `recortar_roi()` devolve o recorte e a caixa em pixels. `listar_dispositivos()` testa indices e libera o dispositivo. |
| `app/state.py` | `EstadoSessao`: fila de eventos em memoria (`app.max_eventos_memoria`), gravacao da captura JPEG de cada evento, estatisticas do turno, correcao de rotulo pelo operador (persistida em `artifacts/correcoes_operador.csv`) e anexo de diagnostico/revisao ao evento. |
| `app/server.py` | FastAPI: monta a app, sobe o `Motor`, serve a interface estatica e todas as rotas. Cada import de modulo "de outro time" e protegido por try/except — se algum faltar, o servidor sobe e reporta em `/api/saude` em vez de devolver 500 em tudo. |
| `app/static/` | Interface web em HTML/CSS/JS puro, com seis abas: **Ao vivo**, **Testar imagem**, **Historico**, **Treinamento**, **Relatorios** e **Ajustes**. |

### LLM

| Arquivo | Responsabilidade |
|---|---|
| `llm/openrouter.py` | **Unica porta de saida para a internet do projeto.** Cliente sincrono do OpenRouter: timeout, retentativa exponencial (1 s, 2 s, 4 s) apenas em 429 e 5xx, nunca em 401/402; limite interno de taxa por janela deslizante; saida estruturada via `response_format: json_schema` com parser de resguardo que extrai o primeiro objeto JSON do texto; `listar_modelos()` e `sugestoes_visao()` consultam o catalogo em tempo de execucao; a chave nunca aparece em log nem em mensagem de erro. |
| `llm/prompts.py` | Prompts e esquemas JSON de resposta, em portugues, com a taxonomia injetada. |
| `llm/review.py` | Papel (2): `revisar_predicao(cliente, imagem, predicao, tecido)` — segunda opiniao sobre um evento incerto. |
| `llm/diagnosis.py` | Papel (3): `diagnosticar(...)` (causa provavel + acao corretiva na maquina) e `gerar_relatorio(...)` (relatorio de turno em markdown). Tem base de conhecimento local usada como fallback quando nao ha chave. |
| `llm/auditoria.py` | Papel (1): sorteia imagens do split `treino`, pergunta ao modelo de visao se o rotulo faz sentido e grava `artifacts/auditoria_rotulos.csv` ordenado por suspeita. Tem `--dry-run` para estimar custo antes de gastar. |

---

## 3. Formato do checkpoint

`artifacts/modelo.pt` e um `dict` salvo com `torch.save`:

```python
{
    "state_dict":     dict,    # pesos, sempre em CPU
    "backbone":       str,     # "mobilenet_v3_small" | "mobilenet_v3_large" | "resnet18"
    "num_classes":    int,     # 11
    "classes":        list,    # CLASS_KEYS na ordem 0..10
    "tamanho_imagem": int,     # 224
    "metricas":       dict,    # acuracia, macro_f1, acuracia_ok_ng da melhor epoca
    "criado_em":      str,     # ISO 8601
}
```

Regras que dependem desse formato:

- `carregar_checkpoint(caminho, dispositivo)` devolve `(modelo_em_eval, meta)`,
  onde `meta` e tudo menos o `state_dict`. O `Preditor` usa `meta["backbone"]`
  para escolher a camada do Grad-CAM e `meta["tamanho_imagem"]` para o resize.
- O `state_dict` vai **sempre para CPU** antes de salvar: um checkpoint gravado
  em GPU nao carregaria numa maquina so de CPU sem `map_location`.
- A escrita e **atomica** (grava em `.tmp` e faz `os.replace`), entao um Ctrl+C
  no meio do save nao destroi o modelo bom da epoca anterior.
- `/api/saude` expoe `backbone` e `metricas` direto do `meta`, e a aba
  "Treinamento" da interface le `historico_treino.json` + `metricas.json`.

---

## 4. Contrato da API

Base: `http://127.0.0.1:8000`. Todas as respostas sao JSON, exceto onde
indicado. As rotas abaixo sao as que existem de fato em `app/server.py`.

### Paginas e arquivos

| Metodo | Rota | Resposta |
|---|---|---|
| `GET` | `/` | `index.html` da interface (ou uma pagina de aviso se o arquivo faltar). |
| `GET` | `/favicon.ico` | Icone, ou 204. |
| `GET` | `/static/...` | Arquivos estaticos da interface. |
| `GET` | `/capturas/...` | JPEG das capturas de evento. |
| `GET` | `/docs` | Documentacao interativa gerada pelo FastAPI. |

### Saude e taxonomia

| Metodo | Rota | Corpo / parametros | Resposta |
|---|---|---|---|
| `GET` | `/api/saude` | — | `{ok, modelo:{carregado, erro, backbone, metricas}, camera:{...}, llm:{configurado, modelo}, versao, modulos_indisponiveis}` |
| `GET` | `/api/taxonomia` | — | `{classes:[{index, key, nome, descricao, gravidade, ok}], tecidos:[{letra, nome, familia, pasta}]}` |

### Ajustes em tempo de execucao

| Metodo | Rota | Corpo | Resposta |
|---|---|---|---|
| `GET` | `/api/ajustes` | — | `{ema_alpha, frames_para_confirmar, limiar_alerta, limiar_incerteza, cooldown_evento_s, gradcam, meta_pecas, tecido}` |
| `POST` | `/api/ajustes` | qualquer subconjunto das chaves acima | o mesmo objeto, ja com os valores aplicados e limitados a faixas seguras |

Mudar um limiar **recria o suavizador** sem reiniciar o servidor.

### Camera

| Metodo | Rota | Corpo | Resposta |
|---|---|---|---|
| `GET` | `/api/camera/dispositivos` | — | `{dispositivos:[0,1,...]}` |
| `POST` | `/api/camera/iniciar` | `{"indice": 0}` (opcional) | `{ok, camera:{ativa, indice, largura, altura, fps_real, erro}}` |
| `POST` | `/api/camera/parar` | — | `{ok}` |

A camera **nao abre automaticamente** quando o servidor sobe.

### Video e status

| Metodo | Rota | Resposta |
|---|---|---|
| `GET` | `/api/video` | Stream `multipart/x-mixed-replace; boundary=quadro` (MJPEG, ~20 fps). So repete o ultimo JPEG pronto; nao infere nada. |
| `GET` | `/api/status` | `{veredito, predicao, estatisticas, ultimo_evento, camera, fps, gradcam, erro}` |
| `POST` | `/api/gradcam` | `{"ligado": true\|false}` (ou vazio para alternar) -> `{ok, ligado}` |

### Analise de imagem avulsa

| Metodo | Rota | Corpo | Resposta |
|---|---|---|---|
| `POST` | `/api/analisar` | `multipart/form-data`, campo **`arquivo`** (JPG ou PNG, ate 10 MB) | `{predicao:{classe_idx, classe_key, nome, confianca, probabilidades, top, e_falha, gravidade, ms}, heatmap:"data:image/jpeg;base64,...", imagem:"data:..."}` ou `{erro}` |

E a rota usada pela aba "Testar imagem" — e o plano B da apresentacao quando a
camera falha.

### Eventos

| Metodo | Rota | Corpo / parametros | Resposta |
|---|---|---|---|
| `GET` | `/api/eventos` | `?limite=60&classe=<classe_key>` | `{eventos:[...], estatisticas:{...}}` |
| `POST` | `/api/eventos/{id}/rotulo` | `{"classe_key": "puckering"}` | `{ok}` — grava a correcao do operador em `artifacts/correcoes_operador.csv` |
| `POST` | `/api/eventos/{id}/diagnostico` | `{"usar_llm": true}` | `{diagnostico:{...}}` — papel (3) do LLM, com fallback local |
| `POST` | `/api/eventos/{id}/revisao` | — | `{revisao:{...}}` — papel (2), **exige chave**; sem chave devolve `{erro}` explicando |

### LLM e relatorio

| Metodo | Rota | Corpo | Resposta |
|---|---|---|---|
| `GET` | `/api/llm/status` | — | `{ok, mensagem, modelo_visao, creditos, estatisticas, configurado, ativo}` — faz uma consulta real ao OpenRouter e sugere ids validos se o modelo configurado sumiu do catalogo |
| `POST` | `/api/relatorio` | `{"limite": 200, "usar_llm": true}` | `{markdown, arquivo, fonte, modelo}` — tambem grava o `.md` em `artifacts/relatorios/` |

### Treino

| Metodo | Rota | Resposta |
|---|---|---|
| `GET` | `/api/treino/historico` | `{historico:[{epoca, perda_treino, perda_val, acc_val, f1_val, lr, segundos}], metricas:{...}}` — le `artifacts/historico_treino.json` e `artifacts/avaliacao/metricas.json`. Devolve `{}` se nada existe ainda. |

---

## 5. Decisoes de projeto

### Por que classificacao e nao deteccao de objetos

**O dataset nao tem caixas delimitadoras.** Ele tem 14.565 imagens 224x224 ja
recortadas, organizadas por pasta de classe. Treinar YOLO ou Faster R-CNN
exigiria anotar manualmente milhares de caixas — trabalho que nao cabe no
projeto e que produziria rotulos piores que os existentes.

Alem disso, **a pergunta operacional e binaria antes de ser espacial**: o
supervisor quer saber "esta peca passa ou para?". Saber onde exatamente esta o
ponto falhado e util, mas secundario. A classificacao responde a pergunta
principal com os dados que existem, e o Grad-CAM cobre parcialmente a
localizacao sem exigir uma anotacao que nao temos.

### Por que MobileNetV3-Small em CPU

A maquina alvo **nao tem GPU**. O sistema precisa rodar em tempo real numa CPU
de notebook, ao lado do navegador e da captura de video, sem monopolizar a
maquina.

- MobileNetV3-Small tem ~2,5 milhoes de parametros contra ~11 milhoes do
  ResNet18 — inferencia varias vezes mais rapida em CPU.
- As convolucoes separaveis em profundidade e os blocos squeeze-excitation
  foram projetados exatamente para esse cenario.
- O treino em CPU com o dataset completo ja leva horas; um backbone maior
  tornaria o projeto inviavel no prazo.
- Transferencia a partir dos pesos ImageNet cobre a falta de dados: 14.565
  imagens sao poucas para treinar do zero, mas suficientes para ajustar um
  extrator de caracteristicas ja bom em textura.
- `resnet18` e `mobilenet_v3_large` continuam disponiveis via `--backbone`,
  para comparacao na avaliacao.

Duas threads sao deixadas livres (`torch.set_num_threads(cpu_count - 2)`) para
que a captura de video e o servidor web nao disputem os mesmos nucleos da
inferencia. `pin_memory=False` porque nao ha GPU para onde transferir.

### Por que suavizacao temporal

Um classificador olhando quadros independentes **pisca**: em 30 quadros por
segundo, uma sombra, um reflexo ou um desfoque de movimento fazem a classe
predita mudar varias vezes por segundo. Um alarme que acende e apaga assim e
inutil — e pior, treina o operador a ignora-lo.

A solucao tem tres camadas:

1. **Media exponencial** das probabilidades (`ema_alpha`, padrao 0,45): cada
   quadro novo corrige a estimativa em vez de substitui-la.
2. **Confirmacao por N quadros** (`frames_para_confirmar`, padrao 4): so vira
   veredito de falha quando varios quadros consecutivos concordam acima de
   `limiar_alerta`.
3. **Cooldown** (`cooldown_evento_s`, padrao 3 s): impede que a mesma falha gere
   dezenas de eventos iguais enquanto a peca esta parada sob a camera.

O custo e a latencia: alguns decimos de segundo entre a falha aparecer e o
alarme. Numa bancada de costura isso e irrelevante; a estabilidade vale muito
mais.

### Por que Grad-CAM

Uma CNN que so devolve "ponto falhado, 87%" nao e auditavel. O operador nao tem
como discordar com fundamento, e a banca nao tem como saber se a rede aprendeu o
defeito ou um atalho (por exemplo, a cor do tecido que aparece mais naquela
classe).

O Grad-CAM usa os gradientes da classe prevista em relacao ao ultimo mapa de
ativacao convolucional para produzir um mapa de calor da regiao que mais pesou.
Ele **nao custa treino adicional** — sai de graca de um modelo ja treinado — e
serve para tres coisas: mostrar ao operador onde olhar, expor atalhos aprendidos
durante a avaliacao, e dar ao LLM um contexto visual melhor quando ha segunda
opiniao. **Nao e uma caixa de deteccao** e nao deve ser vendido como tal: e uma
indicacao aproximada, em resolucao baixa (o mapa nasce 7x7 e e interpolado).

### Por que o LLM nao decide sozinho

Quatro motivos, em ordem de peso:

1. **Latencia.** Uma chamada ao OpenRouter leva de 1 a 5 segundos. A linha de
   costura produz varias pecas por minuto. Nao da para colocar a internet no
   caminho critico da decisao.
2. **Custo e disponibilidade.** Cada chamada consome creditos e depende de rede.
   Uma fabrica sem internet — ou com a chave vencida — ficaria sem inspecao. A
   CNN roda offline, de graca, para sempre.
3. **Consistencia.** A CNN da a mesma resposta para a mesma imagem, sempre. Um
   LLM com temperatura > 0 varia, e o mesmo defeito pode virar duas
   classificacoes diferentes em dois turnos.
4. **Especializacao.** A CNN foi treinada em 14.565 imagens **deste** dominio. O
   LLM tem conhecimento geral e amplo, mas nao viu essas costuras.

O que o LLM faz melhor, e por isso e onde ele foi colocado: **linguagem e
contexto**. Ele explica a causa mecanica provavel, sugere a acao na maquina,
escreve o relatorio do turno, e questiona a CNN exatamente onde ela e fraca — na
faixa de baixa confianca. Por isso o gatilho da segunda opiniao e
`confianca < limiar_incerteza`, e nao "sempre".

### Por que a inferencia roda em uma thread separada das rotas

Se a inferencia acontecesse dentro do gerador de `/api/video`, cada cliente HTTP
conectado rodaria a rede neural de novo, e `/api/status` ficaria bloqueado
enquanto o video corresse. Com o `Motor` como thread unica produzindo um JPEG
pronto, `/api/video` vira um repetidor burro e `/api/status` e uma leitura de
dicionario. Abrir a pagina em duas abas nao dobra o custo de CPU.

### Por que a camera guarda so o quadro mais recente

Ler a camera dentro do laco de processamento acumula atraso: o buffer do driver
enche e o sistema passa a analisar o passado. A thread de captura sobrescreve o
quadro anterior a cada leitura, entao a inferencia sempre trabalha com o
presente, mesmo quando a CPU esta ocupada.

### Por que estratificar por (tecido, classe)

Uma divisao aleatoria simples poderia deixar, por exemplo, quase todo o veludo
cotele no treino e quase nada no teste. A metrica ficaria otimista e o sistema
falharia justo no tecido menos representado. Estratificando os 121 grupos, todo
tecido e toda classe aparecem nos tres splits — e `evaluate.py` consegue
reportar **acuracia por tecido**, que e onde os problemas reais aparecem.

### Por que tudo continua funcionando sem o modelo e sem a chave

O `Preditor` nasce com `disponivel == False` em vez de estourar; o `server.py`
protege cada import de modulo externo; o cliente do OpenRouter expoe
`configurado == False` e os modulos de diagnostico caem em base local. O
resultado e que **a interface sempre sobe**, e o que falta aparece como aviso em
`/api/saude` — nao como erro 500. Numa apresentacao ao vivo, isso e a diferenca
entre "falta treinar o modelo" e uma tela branca.
