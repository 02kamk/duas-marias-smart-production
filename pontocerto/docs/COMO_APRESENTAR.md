# Como apresentar o Ponto Certo em 8 minutos

Roteiro para a banca do projeto integrador. Cronometrado, com o que abrir, o que
dizer, o que a banca costuma perguntar e o plano B para quando a camera falhar.

---

## Antes de entrar na sala (15 minutos antes)

Faca isto **sempre**, mesmo que tenha funcionado ontem.

```powershell
cd caminho\ate\pontocerto
.venv\Scripts\activate
python scripts\00_verificar_ambiente.py
```

Voce quer ver `[ok]` em: pacotes, dataset, manifesto, **checkpoint** e
**camera**. Depois:

- [ ] `python scripts\05_rodar_app.py` e deixe rodando em uma janela minimizada.
- [ ] Abra `http://127.0.0.1:8000` e clique em **Ligar camera**. Confirme que o
      video aparece e que o FPS no canto e maior que 5.
- [ ] Ajuste a luz e a distancia **agora**, nao na hora (veja "Como apontar a
      camera" no README).
- [ ] Separe **duas pecas fisicas**: uma com costura boa e uma com defeito
      visivel (franzimento ou linha frouxa sao os mais faceis de reproduzir).
- [ ] Abra a aba **Testar imagem** e deixe uma pasta do dataset ja aberta no
      Explorer, pronta para arrastar — esse e o plano B.
- [ ] Abra `artifacts/avaliacao/matriz_confusao.png` em uma janela separada.
- [ ] Silencie notificacoes do Windows e **feche Teams, Zoom e OBS** (eles tomam
      a webcam).
- [ ] Deixe o `docs/ARQUITETURA.md` aberto em outra aba, para o caso de a banca
      pedir detalhe tecnico.

---

## O roteiro (8 minutos)

### 0:00 - 0:45 | O problema (sem slide, olhando para a banca)

> "Numa confeccao, o controle de qualidade da costura e feito a olho, peca por
> peca, por um inspetor que revisa milhares de pecas por turno. E um trabalho
> repetitivo, cansativo, e o erro aumenta no fim do turno. O Ponto Certo aponta
> uma camera comum para a costura e classifica em tempo real: costura normal ou
> um entre dez tipos de defeito — ponto falhado, ponto quebrado, franzimento,
> linha frouxa, e assim por diante."

Nao abra nada ainda. Esses 45 segundos sao os unicos em que a banca olha para
voce e nao para a tela.

### 0:45 - 1:30 | A arquitetura em uma frase

Abra `docs/ARQUITETURA.md` na secao 1 (o diagrama ASCII).

> "Sao duas inteligencias com papeis diferentes. A **CNN decide**: e uma rede
> convolucional treinada nas 14.565 imagens do dataset, roda na CPU desta
> maquina, offline, em tempo real. O **LLM multimodal apoia**: ele nao treina a
> rede e nao decide nada em producao. Ele audita os rotulos antes do treino, da
> segunda opiniao quando a confianca da rede cai, e explica a causa mecanica e a
> acao corretiva. Se eu tirar a internet agora, a inspecao continua funcionando."

Essa frase e a tese do projeto. Se a banca so guardar uma coisa, que seja esta.

### 1:30 - 3:30 | Demonstracao ao vivo (o coracao da apresentacao)

Va para a aba **Ao vivo**.

1. Coloque a **peca boa** sob a camera, dentro do retangulo da ROI.
   > "A faixa embaixo mostra 'Costura normal' com a confianca. Repare que o
   > retangulo e a unica regiao analisada — o resto do quadro e ignorado."

2. Troque pela **peca com defeito**. Espere o veredito estabilizar.
   > "O sistema nao muda de opiniao no primeiro quadro. Ele usa media
   > exponencial das probabilidades e so declara falha depois de quatro quadros
   > consecutivos concordarem. Sem isso, o alarme piscaria varias vezes por
   > segundo e o operador aprenderia a ignora-lo."

3. Aponte para o **mapa de calor** (Grad-CAM) sobre a ROI.
   > "Essa mancha quente e o Grad-CAM: a regiao que mais pesou na decisao da
   > rede. Serve para o operador saber onde olhar e para eu conseguir auditar se
   > a rede aprendeu o defeito ou algum atalho. Nao e uma caixa de deteccao — e
   > uma indicacao aproximada, e eu volto nisso nas limitacoes."

4. Mostre que o defeito virou um **evento** na lista lateral.

### 3:30 - 4:45 | Historico, LLM e relatorio

Va para a aba **Historico**.

> "Cada falha detectada vira um evento com a captura salva em disco."

Clique em **Diagnostico** em um evento.

> "Aqui entra o segundo papel do LLM: ele converte 'classe 5, linha frouxa' em
> causa mecanica provavel e acao na maquina — regular a tensao do estica-fio,
> conferir o enchimento da bobina. E o que o operador realmente precisa saber."

Aponte para o seletor de classe do evento.

> "E o operador pode discordar. A correcao vai para
> `artifacts/correcoes_operador.csv` e vira dado para o proximo ajuste fino. O
> humano continua no comando."

Va para **Relatorios** e gere o relatorio do turno.

> "Terceiro papel: o LLM escreve o relatorio de turno em markdown, com as
> estatisticas reais da sessao. Sem chave de API, sai a versao local — mais
> seca, mas sai."

### 4:45 - 6:00 | Como a rede foi treinada e o que ela acerta

Va para a aba **Treinamento** (ela le o historico real do treino) e depois abra
`artifacts/avaliacao/matriz_confusao.png`.

> "14.565 imagens, 11 tipos de tecido, 11 classes, divididas 70/15/15 de forma
> estratificada por par tecido-classe — todo tecido aparece nos tres splits, e
> nenhuma imagem de teste foi vista no treino. A classe Normal tem 2.436
> imagens e as outras dez ficam entre 1.162 e 1.257, entao a perda usa pesos por
> classe para a rede nao virar uma maquina de dizer 'normal'."

Aponte para a diagonal da matriz e depois para a celula mais escura fora dela.

> "A diagonal e o acerto. Onde a matriz erra mais e entre [CLASSE A] e
> [CLASSE B], e isso faz sentido visualmente porque [motivo]. A metrica que
> mais importa na fabrica nao e a acuracia das 11 classes — e a acuracia OK
> contra NG, normal contra qualquer defeito, que deu [VALOR]. Confundir dois
> tipos de defeito custa pouco: os dois param a peca. Deixar passar uma peca
> defeituosa como normal custa caro."

> **Preencha [CLASSE A], [CLASSE B], [motivo] e [VALOR] com os numeros reais de
> `artifacts/avaliacao/metricas.json` depois do treino.** Nunca invente numero:
> e a forma mais rapida de perder a banca.

### 6:00 - 6:45 | Limitacoes (diga voce, antes que perguntem)

> "Tres limitacoes honestas. Primeira: o dataset e de imagens estaticas 224x224
> ja recortadas, com luz controlada. A camera ao vivo e outro dominio —
> iluminacao, angulo, fundo, ruido — entao a acuracia real na bancada cai em
> relacao ao numero do teste. Segunda: o sistema classifica a ROI inteira, nao
> localiza a falha com caixa delimitadora, porque o dataset nao tem anotacao de
> caixas; o Grad-CAM da uma indicacao aproximada e so. Terceira: para uso real,
> o caminho e coletar algumas centenas de imagens com a propria camera da
> bancada e fazer um ajuste fino — a tela de Historico ja grava as correcoes do
> operador exatamente para isso."

Dizer isso voce mesmo transforma tres perguntas dificeis da banca em tres pontos
a seu favor.

### 6:45 - 7:30 | Engenharia (o que diferencia de um notebook Colab)

> "Tres decisoes de engenharia que valem mencionar. A inferencia roda em uma
> thread unica separada das rotas HTTP: abrir a pagina em duas abas nao dobra o
> custo de CPU, e o status nunca trava esperando a rede neural. A camera guarda
> so o quadro mais recente, entao a inferencia nunca analisa o passado. E o
> sistema inteiro sobe mesmo sem modelo treinado e sem chave de API — o que
> falta aparece como aviso em `/api/saude`, nunca como erro 500."

Se sobrar tempo, mostre `http://127.0.0.1:8000/docs` (a documentacao automatica
da API) por cinco segundos. Impressiona e custa nada.

### 7:30 - 8:00 | Fechamento

> "Resumindo: a CNN decide rapido e offline, o LLM audita o dado, questiona a
> decisao fraca e traduz para a linguagem de quem opera a maquina, e o operador
> continua tendo a palavra final. Posso mostrar qualquer parte do codigo ou
> responder o que quiserem."

---

## Perguntas provaveis da banca

**"O LLM treinou a rede?"**
> "Nao. A rede foi treinada por gradiente descendente sobre imagens rotuladas, do
> jeito classico: `training/train.py`, CrossEntropy com pesos de classe, AdamW,
> cosine annealing, early stopping por macro-F1. O LLM nunca produziu um
> gradiente. Ele atua em tres pontos fora do treino: revisa rotulos **antes** do
> treino para melhorar o dado de entrada, da segunda opiniao **depois** da
> predicao quando a confianca e baixa, e explica o resultado em texto. Se eu
> apagar a chave de API agora, o modelo continua exatamente o mesmo."

**"Por que nao usou YOLO / deteccao de objetos?"**
> "Porque o dataset nao tem caixas delimitadoras — sao 14.565 imagens 224x224 ja
> recortadas, organizadas por pasta de classe. Treinar um detector exigiria
> anotar milhares de caixas na mao. E a pergunta operacional e 'esta peca passa
> ou para?', que a classificacao responde com o dado que existe. O Grad-CAM
> cobre parcialmente a localizacao sem precisar dessa anotacao."

**"Qual a acuracia? Isso funciona numa fabrica de verdade?"**
> "No split de teste, [VALOR] de acuracia nas 11 classes e [VALOR] em OK contra
> NG. Mas eu nao apresentaria esse numero como a acuracia de fabrica: o teste e
> do mesmo dominio do treino. Numa bancada real, com outra luz e outro angulo, o
> numero cai. O caminho e o ajuste fino com imagens da propria camera, e o
> sistema ja coleta essas imagens quando o operador corrige um evento."

**"E se a rede errar e deixar passar uma peca ruim?"**
> "Tres camadas. Primeira: o limiar de alerta e ajustavel na aba Ajustes — da
> para deixar o sistema mais sensivel, aceitando mais falsos alarmes para deixar
> passar menos defeito. Segunda: na faixa de incerteza entra a segunda opiniao do
> LLM. Terceira, e a mais importante: o sistema e assistivo. Ele nao substitui o
> inspetor, ele chama a atencao dele. O operador aprova ou corrige, e a correcao
> fica gravada."

**"Por que MobileNet e nao um modelo maior?"**
> "Porque a maquina alvo nao tem GPU. O MobileNetV3-Small tem cerca de 2,5
> milhoes de parametros contra 11 milhoes do ResNet18 e foi projetado para
> inferencia em CPU. Ele precisa rodar em tempo real ao lado da captura de video
> e do servidor web. O codigo aceita `--backbone resnet18` para comparacao, mas o
> ganho de acuracia nao compensou a queda de FPS."

**"Quanto custa rodar isso?"**
> "A inspecao em si custa zero: roda offline, na CPU da propria maquina. O LLM e
> opcional e so e chamado em eventos incertos e na geracao do relatorio — sao
> centavos por turno com um modelo pequeno. O config.yaml ainda tem um limite
> interno de chamadas por minuto como guarda de custo."

**"Como voces garantiram que nao houve vazamento entre treino e teste?"**
> "A divisao e feita uma unica vez em `data/split.py`, gravada em
> `artifacts/splits.csv`, e e deterministica com semente 42. A estratificacao e
> por par tecido-classe, entao os 121 grupos aparecem nos tres splits. Nenhuma
> imagem esta em dois splits — ha uma verificacao explicita de caminhos
> duplicados no proprio script."

**"E se o tecido nao estiver nos 11 do dataset?"**
> "A rede vai chutar a classe mais parecida, provavelmente com confianca baixa —
> e a confianca baixa e justamente o que dispara a segunda opiniao. Mas e uma
> limitacao real: tecido estampado com padrao forte pode ser lido como defeito.
> Para um tecido novo, o caminho e coletar imagens dele e fazer ajuste fino."

**"Por que a suavizacao temporal? Nao atrasa a deteccao?"**
> "Atrasa alguns decimos de segundo, e vale a pena. Sem ela, o veredito muda
> varias vezes por segundo com qualquer sombra ou desfoque de movimento. Um
> alarme que pisca e um alarme que o operador aprende a ignorar. Numa bancada de
> costura, meio segundo de latencia nao muda nada; estabilidade muda tudo."

---

## Plano B: a camera falhou

**Nao tente consertar ao vivo.** Voce tem 8 minutos; depurar webcam consome
todos eles. Diga a frase e siga:

> "A camera nao esta cooperando com a iluminacao da sala — vou demonstrar com
> imagens do proprio conjunto de teste, que o modelo nunca viu no treino. E ate
> melhor, porque eu sei o rotulo verdadeiro de cada uma e voces podem conferir o
> acerto."

Entao:

1. Va para a aba **Testar imagem**.
2. Arraste uma imagem de `0. Normal` de qualquer tecido. Mostre "Costura
   normal" e a confianca.
3. Arraste uma de `6. Puckering` (franzimento) ou `5. Thread sagging` (linha
   frouxa) — sao os mais visiveis para quem nao e da area.
4. Mostre o **Grad-CAM** e o **top 3** de probabilidades.
5. Diga a frase de recuperacao:
   > "Repare que o nome do arquivo comeca com a letra do tecido e o numero da
   > classe — `A_06_014.jpg` e algodao, classe 6, franzimento. Entao da para
   > conferir o acerto na hora, imagem por imagem."

Isso cobre 100% do conteudo tecnico da demonstracao ao vivo. A unica coisa que
se perde e o efeito da suavizacao temporal — e para isso basta explicar em
palavras (roteiro dos 3:30) e apontar os parametros na aba **Ajustes**.

### Outros planos B

| Falhou | O que fazer |
|---|---|
| A porta 8000 esta ocupada | `python scripts\05_rodar_app.py --porta 8080` |
| O modelo nao carrega | Abra `/api/saude` e mostre o campo `modelo.erro` — vire isso a seu favor: "o sistema sobe mesmo sem modelo e diz exatamente o que falta, em vez de dar tela branca" |
| Sem internet / LLM fora do ar | Diga: "sem chave o sistema perde a segunda opiniao e o texto gerado, mas a inspecao continua — e exatamente por isso a CNN decide e o LLM so apoia" |
| O notebook travou | Mostre a matriz de confusao e os graficos de `artifacts/avaliacao/` direto do Explorer e conduza pela arquitetura em `docs/ARQUITETURA.md` |

---

## Checklist de 30 segundos antes de comecar

- [ ] `.venv` ativo e servidor rodando
- [ ] `http://127.0.0.1:8000` aberto, camera ligada, video visivel
- [ ] Peca boa e peca com defeito na mesa
- [ ] Pasta do dataset aberta no Explorer (plano B)
- [ ] `matriz_confusao.png` aberta em outra janela
- [ ] Notificacoes silenciadas, Teams e Zoom fechados
- [ ] Numeros reais de `metricas.json` decorados (acuracia, macro-F1, OK/NG)
