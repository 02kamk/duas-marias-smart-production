"""Explicador tecnico: da classe prevista para a causa e o ajuste na maquina.

FILOSOFIA DESTA CAMADA
----------------------
A rede neural convolucional e quem decide em tempo real. Ela e rapida, roda
offline e foi treinada nas 14.565 imagens do proprio dataset. O LLM multimodal
NAO substitui a CNN e nao a "treina" por magica. Ele entra em tres papeis
concretos e verificaveis:

  (1) AUDITOR DE ROTULOS, antes do treino: revisa amostras do conjunto de treino
      e aponta imagens provavelmente mal rotuladas, melhorando o dado que
      alimenta a CNN.
  (2) SEGUNDA OPINIAO, em tempo de uso: quando a confianca da CNN cai na faixa
      de incerteza, o frame vai para o modelo de visao, que concorda ou discorda
      e justifica.
  (3) EXPLICADOR TECNICO: converte a classe prevista em causa provavel e acao
      corretiva na maquina de costura, e escreve o relatorio de turno.  <-- aqui

BASE_CONHECIMENTO abaixo e o coracao do fallback offline. Ela foi escrita a mao
com pratica de costura industrial (reta, overloque e interloque) e cobre
EXATAMENTE as 11 chaves de `labels.CLASS_KEYS`. Sem chave de API, sem internet,
sem credito no OpenRouter, o operador continua recebendo causa provavel e acao
corretiva. O LLM, quando disponivel, so acrescenta contexto do tecido especifico.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterable, Mapping

from pontocerto.labels import CLASS_KEYS, class_by_key
from pontocerto.llm.openrouter import (
    ClienteOpenRouter,
    ErroOpenRouter,
    extrair_primeiro_json,
)
from pontocerto.llm.prompts import (
    ESQUEMA_DIAGNOSTICO,
    SISTEMA_TECNICO,
    montar_prompt_diagnostico,
    montar_prompt_relatorio,
)

__all__ = ["BASE_CONHECIMENTO", "diagnosticar", "gerar_relatorio"]


# ---------------------------------------------------------------------------
# Base de conhecimento offline (fallback obrigatorio)
# ---------------------------------------------------------------------------

BASE_CONHECIMENTO: dict[str, dict[str, Any]] = {
    "normal": {
        "resumo": (
            "Costura dentro do padrao: pontos uniformes, entrelacamento no meio "
            "das camadas e tecido liso ao longo da carreira."
        ),
        "causas": [
            "Tensao da linha superior e da bobina equilibradas, com o no travando "
            "no meio da espessura do tecido.",
            "Agulha nova, do sistema e numero certos para o tecido, montada ate o "
            "batente com o escape voltado para a lancadeira.",
            "Pressao do calcador suficiente para o tecido nao flutuar, sem marcar.",
            "Dentes impelentes limpos e com altura correta, arrastando as duas "
            "camadas por igual.",
        ],
        "acoes": [
            "Siga a producao sem mexer em regulagem.",
            "Anote os parametros atuais (numero da agulha, linha, tensao, pontos "
            "por centimetro) como referencia deste lote.",
            "Amostre uma peca a cada bloco de pecas para confirmar que o ajuste "
            "se mantem.",
        ],
        "prevencao": [
            "Manter a ficha de parametros por tecido afixada no posto.",
            "Troca programada de agulha por turno, antes de aparecer defeito.",
            "Limpeza do gancho e da caixa de bobina no fim do turno.",
        ],
    },
    "skipped_stitch": {
        "resumo": (
            "Ponto falhado: a agulha subiu e o bico da lancadeira nao pegou a laca "
            "da linha superior, deixando um vao na carreira."
        ),
        "causas": [
            "Agulha cega, torta ou com ponta errada para o material (ponta bola em "
            "tecido plano, ponta redonda em malha).",
            "Agulha mal montada: nao foi ate o batente ou o escape nao esta voltado "
            "para a lancadeira.",
            "Folga entre a agulha e o bico do gancho fora do especificado, ou "
            "temporizacao (altura da barra de agulha) desregulada.",
            "Tecido flutuando por pressao de calcador baixa ou furo da chapa de "
            "agulha grande demais para o material.",
            "Linha ressecada, de baixa qualidade ou grossa demais para o olhal da "
            "agulha, o que atrapalha a formacao da laca.",
        ],
        "acoes": [
            "Desligue a maquina e troque a agulha por uma nova, do sistema e numero "
            "corretos para o tecido.",
            "Remonte a agulha ate o batente com o escape (canal longo) voltado para "
            "o bico da lancadeira.",
            "Ajuste a folga agulha-bico do gancho em torno de 0,05 a 0,10 mm e "
            "confira a altura da barra de agulha.",
            "Aumente a pressao do calcador aos poucos ate o tecido parar de subir "
            "junto com a agulha.",
            "Reduza a velocidade no trecho e, se for malha ou tecido elastico, "
            "troque para agulha de ponta bola.",
        ],
        "prevencao": [
            "Trocar a agulha a cada 8 horas de producao ou a cada troca de lote.",
            "Padronizar sistema e numero de agulha por tipo de tecido em ficha no posto.",
            "Conferir temporizacao e folga do gancho na manutencao preventiva semanal.",
        ],
    },
    "broken_stitch": {
        "resumo": (
            "Ponto quebrado: a linha rompeu durante a costura e a carreira ficou "
            "interrompida."
        ),
        "causas": [
            "Tensao da linha superior alta demais, esticando a linha alem do que ela "
            "aguenta em alta velocidade.",
            "Rebarba ou arranhao no furo da chapa de agulha, no olhal da agulha, no "
            "calcador ou no gancho, cortando a linha.",
            "Agulha aquecida em costura longa e rapida, derretendo linha sintetica.",
            "Enfiamento errado: linha fora de um guia, presa no cone ou passando "
            "torcida pelo estica-fio.",
            "Linha velha, ressecada ou de titulo incompativel com o olhal da agulha.",
        ],
        "acoes": [
            "Reduza a tensao da linha superior meia volta por vez e teste em retalho.",
            "Passe uma meia de nylon pelo caminho da linha (chapa, calcador, olhal, "
            "gancho) para achar rebarba; polir com lixa fina ou trocar a peca.",
            "Repasse todo o enfiamento com o calcador levantado, conferindo cada guia.",
            "Use agulha um numero maior para dar folga ao olhal, ou linha mais fina.",
            "Reduza a rotacao em costuras longas ou use agulha com acabamento que "
            "dissipa calor.",
        ],
        "prevencao": [
            "Inspecionar chapa, calcador e gancho toda vez que uma agulha quebrar.",
            "Guardar a linha protegida de sol e umidade, fora do chao.",
            "Padronizar o par linha-agulha por operacao e registrar na ficha.",
        ],
    },
    "pinched_fabric": {
        "resumo": (
            "Tecido beliscado: uma dobra do pano entrou sob o calcador e foi "
            "costurada junto, prendendo camadas que deveriam ficar soltas."
        ),
        "causas": [
            "Camadas mal alinhadas na entrada do calcador, com sobra de pano dobrando.",
            "Excesso de tecido acumulado na guia ou na mesa, empurrando o pano de lado.",
            "Pressao do calcador insuficiente no inicio da costura, deixando o pano escorregar.",
            "Operador puxando ou segurando o tecido em vez de deixar o arraste conduzir.",
            "Tecido escorregadio (cetim, chiffon, nylon) costurado sem guia ou gabarito.",
        ],
        "acoes": [
            "Pare a maquina, descosture o trecho e reposicione as camadas antes de retomar.",
            "Alise o pano com a mao aberta antes do calcador e use guia ou regua para "
            "manter a margem.",
            "Aumente a pressao do calcador o suficiente para segurar as duas camadas "
            "desde o primeiro ponto.",
            "Troque para calcador de mola dupla ou de transporte duplo em tecido escorregadio.",
            "Nao puxe nem segure o pano durante a costura: apenas conduza.",
        ],
        "prevencao": [
            "Treinar o alimentador de pecas no posicionamento das camadas.",
            "Usar gabarito, guia magnetica ou marcacao de margem na chapa.",
            "Conferir a primeira peca de cada pacote antes de liberar o lote.",
        ],
    },
    "crooked_seam": {
        "resumo": (
            "Costura torta: a carreira fugiu da linha de referencia e a margem "
            "ficou irregular ao longo da peca."
        ),
        "causas": [
            "Falta de guia de margem, ou guia deslocada da distancia especificada.",
            "Operador conduzindo o pano no olho, sem referencia fisica.",
            "Arraste desigual entre as camadas: a de baixo anda mais que a de cima e "
            "a costura desvia.",
            "Dentes impelentes gastos ou com altura irregular, puxando o pano de lado.",
            "Velocidade alta em curva ou em mudanca de direcao sem reposicionar a peca.",
        ],
        "acoes": [
            "Instale ou reposicione a guia de margem na distancia da ficha e trave o parafuso.",
            "Troque para calcador de transporte duplo (walking foot) ou ligue a "
            "alimentacao superior para as camadas andarem juntas.",
            "Troque os dentes impelentes gastos e confira a altura acima da chapa.",
            "Reduza a velocidade nas curvas e pare com a agulha embaixo para girar a peca.",
            "Alinhe os piques das camadas antes de comecar e confira na metade da costura.",
        ],
        "prevencao": [
            "Piquetar e marcar as pecas no corte para dar referencia ao operador.",
            "Conferir a distancia da margem com gabarito na primeira peca de cada pacote.",
            "Incluir dentes impelentes e chapa na rota de manutencao preventiva.",
        ],
    },
    "thread_sagging": {
        "resumo": (
            "Linha frouxa: lacadas soltas na costura por tensao insuficiente na "
            "linha superior ou na da bobina."
        ),
        "causas": [
            "Tensao superior baixa, ou linha enfiada com o calcador abaixado e por "
            "isso fora dos discos de tensao.",
            "Discos de tensao sujos de fiapo e goma, sem conseguir segurar a linha.",
            "Linha escapou de um guia ou do estica-fio, perdendo o percurso correto.",
            "Mola do estica-fio fraca, empenada ou quebrada.",
            "Bobina mal enrolada (enrolada a mao ou frouxa) ou mola da caixa de "
            "bobina folgada.",
        ],
        "acoes": [
            "Reenfie a maquina com o calcador LEVANTADO, para a linha entrar entre os "
            "discos, e so depois abaixe o calcador.",
            "Limpe os discos de tensao, o estica-fio e o percurso da linha com ar e pincel.",
            "Aumente a tensao superior meia volta por vez, testando em retalho ate a "
            "laca travar no meio das camadas.",
            "Aperte o parafuso da mola da caixa de bobina 1/8 de volta por vez, ate a "
            "caixa descer devagar no teste do ioio.",
            "Descarte bobinas mal enroladas e reenrole na propria maquina.",
        ],
        "prevencao": [
            "Fazer teste de costura em retalho a cada troca de linha ou de cor.",
            "Limpar discos de tensao e caixa de bobina no fim de cada turno.",
            "Enrolar bobina sempre na maquina, com a linha passando pelo tensor do enchedor.",
        ],
    },
    "puckering": {
        "resumo": (
            "Franzimento: o tecido enrugou ao longo da costura, formando ondas na "
            "margem em vez de ficar liso."
        ),
        "causas": [
            "Tensao da linha superior e da bobina alta demais, encolhendo a costura "
            "depois de pronta.",
            "Tecido leve e de trama fechada (chiffon, cetim, nylon, poliester fino) "
            "costurado sem estabilizador.",
            "Arraste desigual entre as camadas, com a de baixo sendo empurrada mais "
            "que a de cima.",
            "Agulha grossa demais para o tecido, deslocando os fios da trama.",
            "Pontos por centimetro excessivos, acumulando linha na costura.",
            "Linha com muita retracao, que encolhe depois de costurada ou passada.",
        ],
        "acoes": [
            "Baixe a tensao superior e a da bobina ate o minimo que ainda trava a "
            "laca no meio das camadas.",
            "Troque para agulha mais fina de ponta fina, por exemplo 65/9 ou 70/10 em "
            "tecido leve.",
            "Use calcador de transporte duplo ou coloque papel de seda / entretela "
            "soluvel embaixo da costura em chiffon e cetim.",
            "Reduza os pontos por centimetro (por exemplo de 5 para 4 pontos por cm).",
            "Reduza a pressao do calcador ao minimo que ainda segura o tecido e use "
            "linha de poliester fina, de baixa retracao.",
        ],
        "prevencao": [
            "Manter ficha de parametro por tecido com agulha, linha, tensao e pontos "
            "por centimetro.",
            "Fazer teste de costura em retalho do mesmo lote antes de liberar a producao.",
            "Nunca reaproveitar a regulagem de tecido pesado ao trocar para tecido leve.",
        ],
    },
    "stain_damage": {
        "resumo": (
            "Mancha ou dano: sujeira, oleo, furo ou rasgo no tecido na regiao da "
            "costura, o que condena a peca."
        ),
        "causas": [
            "Vazamento ou excesso de oleo da maquina, deixando mancha escura perto do "
            "furo da agulha.",
            "Mao suja, giz, marcador permanente ou graxa da esteira em contato com a peca.",
            "Furo ou rasgo provocado por agulha cega, torta ou grossa demais para a trama.",
            "Peca arrastada sobre rebarba da mesa, do gabarito ou da chapa de agulha.",
            "Fio puxado no manuseio ou no empilhamento das pecas.",
        ],
        "acoes": [
            "Separe a peca para retrabalho ou limpeza e identifique o lote antes de "
            "misturar com as boas.",
            "Verifique o nivel e o retorno de oleo, limpe o excesso, troque o feltro e "
            "corra algumas pecas de teste em retalho ate sair limpo.",
            "Troque a agulha e passe a mao na chapa, no calcador e no gabarito atras "
            "de rebarba; lixe ou substitua o que estiver arranhando.",
            "Revise as pecas produzidas desde a ultima peca comprovadamente boa.",
            "Limpe a mesa, o gabarito e as maos antes de retomar a producao.",
        ],
        "prevencao": [
            "Plano de limpeza e troca de oleo da maquina com registro por turno.",
            "Proibir marcador permanente e caneta perto da linha de costura; usar giz "
            "ou marcador que sai na lavagem.",
            "Inspecao visual a cada bloco de pecas, antes do empilhamento.",
        ],
    },
    "needle_mark": {
        "resumo": (
            "Marca de agulha: furos visiveis ao longo da carreira, porque a agulha "
            "rompeu os fios em vez de afasta-los."
        ),
        "causas": [
            "Agulha grossa demais para a densidade do tecido.",
            "Agulha cega ou com ponta danificada, que arrebenta o fio da trama.",
            "Tipo de ponta errado: ponta cortante em tecido plano fino, ou ponta bola "
            "grossa demais.",
            "Material revestido, laminado ou de fibra sintetica que nao fecha o furo "
            "depois que a agulha passa.",
            "Costura descosturada e refeita exatamente sobre a mesma linha de furos.",
        ],
        "acoes": [
            "Desligue a maquina e troque por uma agulha nova, de numero menor (por "
            "exemplo de 80/12 para 70/10).",
            "Use ponta adequada ao material: ponta redonda fina (R/SES) em tecido "
            "plano leve, ponta bola leve em malha.",
            "Em tecido revestido, aumente o comprimento do ponto para reduzir a "
            "quantidade de furos por centimetro.",
            "Nunca refaca a costura sobre a mesma linha de furos: desloque a carreira "
            "1 a 2 mm.",
            "Se o material permitir, vaporize e prense levemente para fechar a marca.",
        ],
        "prevencao": [
            "Afixar tabela agulha x tecido no posto e conferir a cada troca de artigo.",
            "Troca programada de agulha, sem esperar defeito aparecer.",
            "Teste em retalho do proprio lote antes de liberar tecido revestido ou "
            "muito fechado.",
        ],
    },
    "bobbin_pullup": {
        "resumo": (
            "Linha da bobina subindo: o entrelacamento saiu do meio das camadas e a "
            "linha de baixo aparece na face de cima."
        ),
        "causas": [
            "Tensao da linha superior alta demais em relacao a da bobina, puxando a "
            "laca para cima.",
            "Enfiamento superior fora dos discos de tensao ou do estica-fio.",
            "Fiapo preso sob a mola da caixa de bobina, ou parafuso da mola frouxo.",
            "Bobina errada, empenada ou mal encaixada na caixa, girando solta.",
            "Linhas de titulos diferentes em cima e embaixo, com comportamento de "
            "tensao diferente.",
        ],
        "acoes": [
            "Reenfie toda a parte de cima com o calcador levantado e confirme que a "
            "linha assentou entre os discos.",
            "Retire a caixa de bobina, limpe o fiapo sob a mola e recoloque ate travar.",
            "Reduza a tensao superior meia volta por vez ate o no voltar para o meio "
            "das camadas no teste em retalho.",
            "Faca o teste do ioio: segurando a linha, a caixa de bobina deve descer "
            "devagar; se cair livre, aperte o parafuso 1/8 de volta.",
            "Use a mesma linha em cima e embaixo, do mesmo titulo e fabricante.",
        ],
        "prevencao": [
            "Fazer o teste do ioio a cada troca de bobina.",
            "Limpeza diaria do gancho, da pista e da caixa de bobina.",
            "Padronizar bobinas do fabricante da maquina e descartar as amassadas.",
        ],
    },
    "overlapped_stitch": {
        "resumo": (
            "Ponto sobreposto: duas carreiras de pontos se sobrepoem no mesmo trecho, "
            "engrossando e endurecendo a costura."
        ),
        "causas": [
            "Reinicio da costura fora do ponto de parada, sobrepondo mais do que o "
            "remate previsto.",
            "Travete ou remate longo demais, ou acionado duas vezes.",
            "Arraste travando: o tecido para de andar e a maquina costura no mesmo lugar.",
            "Fechamento de costura circular sem alinhar com o inicio da carreira.",
            "Corta-linha nao acionado e peca reposicionada por cima da costura pronta.",
        ],
        "acoes": [
            "Padronize o remate em 2 a 4 pontos re, sem repetir o acionamento.",
            "Ao retomar, posicione a agulha exatamente no ultimo furo antes de seguir.",
            "Verifique se os dentes impelentes estao subindo acima da chapa e se a "
            "pressao do calcador nao esta travando o pano.",
            "Ajuste o parametro de travete no painel da maquina eletronica.",
            "Use o corta-linha e a parada com agulha embaixo para nao perder a posicao.",
        ],
        "prevencao": [
            "Definir o remate padrao por operacao e treinar o operador.",
            "Checar o arraste e a altura dos dentes na manutencao preventiva.",
            "Marcar o ponto de fechamento em costuras circulares.",
        ],
    },
}

# Trava de coerencia: a base precisa cobrir exatamente a taxonomia do projeto.
_FALTAM = set(CLASS_KEYS) - set(BASE_CONHECIMENTO)
_SOBRAM = set(BASE_CONHECIMENTO) - set(CLASS_KEYS)
if _FALTAM or _SOBRAM:  # pragma: no cover - erro de programacao, nao de runtime
    raise RuntimeError(
        "BASE_CONHECIMENTO fora de sincronia com labels.CLASS_KEYS. "
        f"Faltando: {sorted(_FALTAM)} | Sobrando: {sorted(_SOBRAM)}"
    )


# ---------------------------------------------------------------------------
# Cache em memoria
# ---------------------------------------------------------------------------

_CACHE: dict[tuple[str, str], dict] = {}
_CACHE_LOCK = threading.Lock()


def limpar_cache() -> None:
    """Esvazia o cache de diagnosticos (util em testes e ao trocar de modelo)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_ligado(cliente: Any) -> bool:
    cfg = getattr(cliente, "cfg", None)
    try:
        return bool(cfg["llm"]["cache_diagnostico"])
    except Exception:
        return True


def _lista_texto(valor: Any, limite: int = 6) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, str):
        item = valor.strip()
        return [item] if item else []
    if isinstance(valor, (list, tuple)):
        saida = [str(x).strip() for x in valor if str(x).strip()]
        return saida[:limite]
    return [str(valor)]


def _do_local(classe_key: str) -> dict:
    base = BASE_CONHECIMENTO[classe_key]
    try:
        nome = class_by_key(classe_key).pt
    except KeyError:
        nome = classe_key
    return {
        "classe_key": classe_key,
        "nome": nome,
        "resumo": base["resumo"],
        "causas": list(base["causas"]),
        "acoes": list(base["acoes"]),
        "prevencao": list(base["prevencao"]),
        "fonte": "base_local",
        "modelo": None,
        "ms": 0.0,
    }


# ---------------------------------------------------------------------------
# Diagnostico
# ---------------------------------------------------------------------------

def diagnosticar(
    cliente: ClienteOpenRouter | None,
    classe_key: str,
    tecido: str | None = None,
    confianca: float | None = None,
    usar_llm: bool = True,
) -> dict:
    """Explica o defeito e diz o que ajustar na maquina.

    Retorno:
        {"classe_key","nome","resumo","causas":[str],"acoes":[str],
         "prevencao":[str],"fonte":"llm"|"base_local","modelo":str|None,"ms":float}

    Com LLM disponivel, a resposta sai contextualizada para o tecido. Sem LLM,
    cai na BASE_CONHECIMENTO local, que cobre as 11 classes. Nunca levanta
    excecao: na duvida devolve o conteudo local.
    """
    inicio = time.perf_counter()

    if classe_key not in BASE_CONHECIMENTO:
        # Classe desconhecida: degrada para "normal" com aviso explicito.
        saida = _do_local("normal")
        saida["classe_key"] = str(classe_key)
        saida["nome"] = str(classe_key)
        saida["resumo"] = (
            f"classe '{classe_key}' nao consta na taxonomia do Ponto Certo; "
            "nao ha diagnostico cadastrado."
        )
        saida["causas"] = []
        saida["acoes"] = ["Confira o modelo carregado e a taxonomia em labels.py."]
        saida["prevencao"] = []
        saida["ms"] = (time.perf_counter() - inicio) * 1000.0
        return saida

    chave_cache = (classe_key, (tecido or "").strip().lower())
    usar_cache = usar_llm and cliente is not None and _cache_ligado(cliente)
    if usar_cache:
        with _CACHE_LOCK:
            guardado = _CACHE.get(chave_cache)
        if guardado is not None:
            saida = dict(guardado)
            saida["causas"] = list(saida["causas"])
            saida["acoes"] = list(saida["acoes"])
            saida["prevencao"] = list(saida["prevencao"])
            saida["ms"] = (time.perf_counter() - inicio) * 1000.0
            return saida

    local = _do_local(classe_key)

    if not usar_llm or cliente is None:
        local["ms"] = (time.perf_counter() - inicio) * 1000.0
        return local
    try:
        if not cliente.configurado:
            local["ms"] = (time.perf_counter() - inicio) * 1000.0
            return local
    except Exception:
        local["ms"] = (time.perf_counter() - inicio) * 1000.0
        return local

    try:
        prompt = montar_prompt_diagnostico(classe_key, tecido=tecido, confianca=confianca)
        resposta = cliente.chat(
            [
                {"role": "system", "content": SISTEMA_TECNICO},
                {"role": "user", "content": prompt},
            ],
            modelo=getattr(cliente, "modelo_texto", None),
            json_schema=ESQUEMA_DIAGNOSTICO,
        )
        dados = extrair_primeiro_json(resposta.texto)
    except (ErroOpenRouter, Exception):
        local["ms"] = (time.perf_counter() - inicio) * 1000.0
        return local

    if not isinstance(dados, Mapping):
        local["ms"] = (time.perf_counter() - inicio) * 1000.0
        return local

    causas = _lista_texto(dados.get("causas")) or local["causas"]
    acoes = _lista_texto(dados.get("acoes")) or local["acoes"]
    prevencao = _lista_texto(dados.get("prevencao"), limite=4) or local["prevencao"]
    resumo = str(dados.get("resumo") or "").strip() or local["resumo"]

    saida = {
        "classe_key": classe_key,
        "nome": local["nome"],
        "resumo": resumo,
        "causas": causas,
        "acoes": acoes,
        "prevencao": prevencao,
        "fonte": "llm",
        "modelo": resposta.modelo or getattr(cliente, "modelo_texto", None),
        "ms": float(resposta.ms),
    }
    if usar_cache:
        with _CACHE_LOCK:
            _CACHE[chave_cache] = dict(saida)
    saida["ms"] = (time.perf_counter() - inicio) * 1000.0
    return saida


# ---------------------------------------------------------------------------
# Relatorio de turno
# ---------------------------------------------------------------------------

def _relatorio_local(
    estatisticas: Mapping[str, Any],
    eventos: Iterable[Mapping[str, Any]],
) -> str:
    est = dict(estatisticas or {})
    lista = [e for e in (eventos or []) if isinstance(e, Mapping)]

    total = int(est.get("total", 0) or 0)
    aprovadas = int(est.get("aprovadas", 0) or 0)
    reprovadas = int(est.get("reprovadas", 0) or 0)
    try:
        taxa = float(est.get("taxa_aprovacao", 0.0) or 0.0)
    except (TypeError, ValueError):
        taxa = 0.0
    if taxa <= 1.0:
        taxa_pct = taxa * 100.0
    else:
        taxa_pct = taxa
    try:
        duracao = float(est.get("duracao_s", 0.0) or 0.0)
    except (TypeError, ValueError):
        duracao = 0.0
    horas, resto = divmod(int(duracao), 3600)
    minutos, segundos = divmod(resto, 60)

    por_classe: dict[str, int] = {}
    for k, v in (est.get("por_classe") or {}).items():
        try:
            por_classe[str(k)] = int(v or 0)
        except (TypeError, ValueError):
            continue
    ranking = sorted(
        ((k, v) for k, v in por_classe.items() if k != "normal" and v > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )

    linhas: list[str] = []
    linhas.append("# Relatorio de turno - Ponto Certo")
    linhas.append("")
    linhas.append(f"_Gerado em {time.strftime('%d/%m/%Y %H:%M:%S')} pela base de conhecimento local._")
    linhas.append("")
    linhas.append("## Resumo")
    linhas.append("")
    linhas.append(f"- Pecas inspecionadas: **{total}**")
    linhas.append(f"- Aprovadas: **{aprovadas}** | Reprovadas: **{reprovadas}**")
    linhas.append(f"- Taxa de aprovacao: **{taxa_pct:.1f}%**")
    linhas.append(f"- Duracao monitorada: **{horas:02d}h {minutos:02d}min {segundos:02d}s**")
    linhas.append(
        f"- Melhor sequencia sem falha: **{int(est.get('melhor_sequencia', 0) or 0)}** pecas"
    )
    meta = int(est.get("meta_pecas", 0) or 0)
    if meta:
        try:
            progresso = float(est.get("progresso_meta", 0.0) or 0.0)
        except (TypeError, ValueError):
            progresso = 0.0
        progresso_pct = progresso * 100.0 if progresso <= 1.0 else progresso
        linhas.append(f"- Meta do turno: **{meta}** pecas ({progresso_pct:.0f}% atingido)")
    linhas.append("")

    linhas.append("## Principais ocorrencias")
    linhas.append("")
    if not ranking:
        linhas.append("Nenhuma falha registrada no periodo. Costura dentro do padrao.")
    else:
        for chave, qtd in ranking[:6]:
            info = BASE_CONHECIMENTO.get(chave)
            try:
                nome = class_by_key(chave).pt
            except KeyError:
                nome = chave
            resumo = info["resumo"] if info else "sem descricao cadastrada"
            linhas.append(f"- **{nome}** ({chave}): {qtd} ocorrencia(s). {resumo}")
    linhas.append("")

    linhas.append("## Causa provavel predominante")
    linhas.append("")
    if ranking:
        principal = ranking[0][0]
        info = BASE_CONHECIMENTO.get(principal)
        try:
            nome = class_by_key(principal).pt
        except KeyError:
            nome = principal
        if info:
            linhas.append(
                f"O defeito mais frequente do turno foi **{nome}**. "
                f"A causa mais provavel e: {info['causas'][0]}"
            )
            linhas.append("")
            linhas.append("Outras hipoteses a verificar:")
            for causa in info["causas"][1:4]:
                linhas.append(f"- {causa}")
        else:
            linhas.append(f"O defeito mais frequente do turno foi **{nome}**.")
    else:
        linhas.append(
            "Nao houve defeito dominante. Mantenha a regulagem atual e a rotina de "
            "troca de agulha."
        )
    linhas.append("")

    linhas.append("## Acoes recomendadas")
    linhas.append("")
    if ranking:
        numero = 1
        for chave, _qtd in ranking[:3]:
            info = BASE_CONHECIMENTO.get(chave)
            if not info:
                continue
            try:
                nome = class_by_key(chave).pt
            except KeyError:
                nome = chave
            for acao in info["acoes"][:3]:
                linhas.append(f"{numero}. ({nome}) {acao}")
                numero += 1
    else:
        linhas.append("1. Seguir a producao e manter a amostragem por bloco de pecas.")
        linhas.append("2. Cumprir a troca programada de agulha no proximo turno.")
    linhas.append("")

    linhas.append("## Ultimos eventos")
    linhas.append("")
    if lista:
        linhas.append("| Hora | Classe | Confianca | Gravidade | Tecido |")
        linhas.append("| --- | --- | --- | --- | --- |")
        for ev in lista[:25]:
            try:
                conf = f"{float(ev.get('confianca', 0.0)):.2f}"
            except (TypeError, ValueError):
                conf = "-"
            linhas.append(
                f"| {ev.get('hora', '--:--:--')} "
                f"| {ev.get('nome') or ev.get('classe_key') or '?'} "
                f"| {conf} | {ev.get('gravidade', '-')} "
                f"| {ev.get('tecido') or 'nao informado'} |"
            )
    else:
        linhas.append("Nenhum evento registrado no periodo.")
    linhas.append("")

    linhas.append("## Observacoes")
    linhas.append("")
    linhas.append(
        "Relatorio montado offline, sem consulta ao modelo de linguagem. Os textos "
        "de causa e acao vem da base de conhecimento tecnica do proprio sistema. "
        "Com a chave do OpenRouter configurada, o relatorio passa a ser redigido "
        "pelo modelo com leitura cruzada dos eventos."
    )
    linhas.append("")
    return "\n".join(linhas)


def gerar_relatorio(
    cliente: ClienteOpenRouter | None,
    estatisticas: Mapping[str, Any],
    eventos: Iterable[Mapping[str, Any]],
    usar_llm: bool = True,
) -> dict:
    """Escreve o relatorio de turno em Markdown.

    Retorno: {"markdown": str, "fonte": "llm"|"base_local", "modelo": str|None}
    Nunca levanta excecao: sem LLM, monta o markdown por conta propria.
    """
    lista = [dict(e) for e in (eventos or []) if isinstance(e, Mapping)]
    est = dict(estatisticas or {})

    if usar_llm and cliente is not None:
        try:
            pronto = bool(cliente.configurado)
        except Exception:
            pronto = False
        if pronto:
            try:
                resposta = cliente.chat(
                    [
                        {"role": "system", "content": SISTEMA_TECNICO},
                        {"role": "user", "content": montar_prompt_relatorio(est, lista)},
                    ],
                    modelo=getattr(cliente, "modelo_texto", None),
                    max_tokens=max(900, int(getattr(cliente, "_max_tokens", 900) or 900)),
                )
                texto = (resposta.texto or "").strip()
                if texto.startswith("```"):
                    texto = texto.strip("`")
                    if texto.lower().startswith("markdown"):
                        texto = texto[len("markdown"):]
                    texto = texto.strip()
                if len(texto) > 120:
                    return {
                        "markdown": texto,
                        "fonte": "llm",
                        "modelo": resposta.modelo or getattr(cliente, "modelo_texto", None),
                    }
            except (ErroOpenRouter, Exception):
                pass

    return {
        "markdown": _relatorio_local(est, lista),
        "fonte": "base_local",
        "modelo": None,
    }
