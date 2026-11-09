"""Prompts e esquemas JSON da camada de LLM do Ponto Certo.

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
      corretiva na maquina de costura, e escreve o relatorio de turno.

Todos os prompts deste modulo injetam a taxonomia real de `labels.CLASSES` e
obrigam o modelo a responder escolhendo uma das 11 chaves canonicas. Nada de
inventar nome de defeito: a saida precisa casar com o vocabulario da CNN.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from pontocerto.labels import CLASS_KEYS, CLASSES, class_by_key

__all__ = [
    "TAXONOMIA_TEXTO",
    "SISTEMA_INSPETOR",
    "SISTEMA_AUDITOR",
    "SISTEMA_TECNICO",
    "ESQUEMA_REVISAO",
    "ESQUEMA_DIAGNOSTICO",
    "ESQUEMA_AUDITORIA",
    "montar_prompt_revisao",
    "montar_prompt_diagnostico",
    "montar_prompt_auditoria",
    "montar_prompt_relatorio",
]


# ---------------------------------------------------------------------------
# Taxonomia injetada dinamicamente (nunca escrita a mao aqui)
# ---------------------------------------------------------------------------

def _bloco_taxonomia() -> str:
    linhas = []
    for c in CLASSES:
        marca = "SEM DEFEITO" if c.gravidade == "ok" else f"gravidade {c.gravidade}"
        linhas.append(f'  {c.index:>2}. {c.key} = "{c.pt}" ({marca}) - {c.descricao}')
    return "\n".join(linhas)


TAXONOMIA_TEXTO: str = _bloco_taxonomia()

_LISTA_CHAVES = ", ".join(CLASS_KEYS)


# ---------------------------------------------------------------------------
# Prompts de sistema
# ---------------------------------------------------------------------------

SISTEMA_INSPETOR = f"""Voce e um inspetor de qualidade de costura industrial com vinte anos de chao de
fabrica em confeccao. Voce olha a foto de um trecho de costura e diz o que esta
acontecendo ali, sem enrolacao.

Trabalhe SEMPRE dentro desta taxonomia fechada de 11 classes (use exatamente a
chave em snake_case, nunca traduza nem invente uma nova):

{TAXONOMIA_TEXTO}

Regras de trabalho:
- Sua resposta precisa ser um unico objeto JSON valido, sem texto em volta.
- O campo de classe so aceita uma destas chaves: {_LISTA_CHAVES}.
- Se a imagem estiver escura, desfocada, cortada ou nao mostrar costura, diga
  isso na justificativa e use confianca baixa. Nao chute defeito.
- A confianca e um numero entre 0 e 1 e representa a SUA certeza, nao a da rede.
- Justificativa curta, no maximo tres frases, em portugues do Brasil, citando o
  que se ve na imagem (vao entre pontos, lacada solta, franzido, furo, mancha).
- Voce esta auxiliando uma rede neural que ja deu um palpite. Concordar com ela
  quando a imagem confirma e tao util quanto discordar quando ela erra. Nao
  discorde so para parecer util, e nao concorde so para agradar."""


SISTEMA_AUDITOR = f"""Voce e um auditor de base de dados de visao computacional especializado em
defeitos de costura. Sua funcao e conferir se o rotulo gravado para uma imagem
de treino corresponde ao que a imagem realmente mostra. Imagem mal rotulada
envenena o treino da rede, entao seu olho precisa ser conservador: so aponte
erro quando a evidencia visual for clara.

Taxonomia fechada (responda sempre com a chave em snake_case):

{TAXONOMIA_TEXTO}

Regras:
- Responda apenas com um objeto JSON valido.
- classe_sugerida deve ser uma destas: {_LISTA_CHAVES}.
- Na duvida, concorde com o rotulo existente e use confianca baixa.
- Justificativa de uma ou duas frases, em portugues do Brasil."""


SISTEMA_TECNICO = f"""Voce e um tecnico de manutencao de maquinas de costura industrial (reta,
overloque e interloque) que treina operadores no chao de fabrica. Voce explica
defeito de costura em linguagem direta, apontando regulagem de maquina, agulha,
linha, calcador, dentes impelentes, tensao superior e tensao da bobina.

Taxonomia de defeitos do sistema:

{TAXONOMIA_TEXTO}

Regras:
- Responda apenas com um objeto JSON valido, sem texto em volta.
- Portugues do Brasil, vocabulario de chao de fabrica, frases curtas no
  imperativo ("troque a agulha", "reduza a tensao superior").
- Nada de conselho generico do tipo "verifique a maquina". Cite a peca, o ajuste
  e, quando fizer sentido, a ordem de grandeza (numero da agulha, fracao de
  volta no parafuso da caixa de bobina, pontos por centimetro).
- Nao recomende nada perigoso sem avisar para desligar a maquina antes."""


# ---------------------------------------------------------------------------
# Esquemas JSON (formato do OpenRouter: {"name", "strict", "schema"})
# Com strict=true todo objeto precisa de additionalProperties=false e de
# "required" listando TODAS as chaves de "properties".
# ---------------------------------------------------------------------------

ESQUEMA_REVISAO: dict[str, Any] = {
    "name": "revisao_costura",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "concorda": {
                "type": "boolean",
                "description": "true se a classe prevista pela rede confere com a imagem.",
            },
            "classe_sugerida": {
                "type": "string",
                "enum": list(CLASS_KEYS),
                "description": "Chave canonica da classe que voce considera correta.",
            },
            "confianca": {
                "type": "number",
                "description": "Sua certeza entre 0 e 1.",
            },
            "justificativa": {
                "type": "string",
                "description": "Ate tres frases em portugues explicando o que se ve.",
            },
            "sinais": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Evidencias visuais curtas, por exemplo 'vao de 3 pontos'.",
            },
        },
        "required": ["concorda", "classe_sugerida", "confianca", "justificativa", "sinais"],
    },
}


ESQUEMA_DIAGNOSTICO: dict[str, Any] = {
    "name": "diagnostico_costura",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "resumo": {
                "type": "string",
                "description": "Uma frase explicando o defeito para o operador.",
            },
            "causas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "De 3 a 5 causas provaveis, da mais comum para a menos comum.",
            },
            "acoes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "De 3 a 5 acoes corretivas na maquina, em ordem de execucao.",
            },
            "prevencao": {
                "type": "array",
                "items": {"type": "string"},
                "description": "De 2 a 3 medidas para o defeito nao voltar.",
            },
        },
        "required": ["resumo", "causas", "acoes", "prevencao"],
    },
}


ESQUEMA_AUDITORIA: dict[str, Any] = {
    "name": "auditoria_rotulo",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "concorda": {
                "type": "boolean",
                "description": "true se o rotulo gravado confere com a imagem.",
            },
            "classe_sugerida": {
                "type": "string",
                "enum": list(CLASS_KEYS),
                "description": "Chave canonica correta para esta imagem.",
            },
            "confianca": {
                "type": "number",
                "description": "Sua certeza entre 0 e 1.",
            },
            "justificativa": {
                "type": "string",
                "description": "Uma ou duas frases em portugues.",
            },
        },
        "required": ["concorda", "classe_sugerida", "confianca", "justificativa"],
    },
}


# ---------------------------------------------------------------------------
# Montadores de prompt
# ---------------------------------------------------------------------------

def _nome_classe(chave: str | None) -> str:
    if not chave:
        return "desconhecida"
    try:
        return class_by_key(chave).pt
    except KeyError:
        return str(chave)


def _linha_tecido(tecido: str | None) -> str:
    if not tecido:
        return "Tecido: nao informado pelo operador."
    return f"Tecido informado pelo operador: {tecido}."


def montar_prompt_revisao(predicao: Mapping[str, Any], tecido: str | None = None) -> str:
    """Prompt da SEGUNDA OPINIAO: a CNN ficou insegura e pede revisao da imagem.

    `predicao` e o dict devolvido por `Predicao.to_dict()` do preditor.
    """
    predicao = predicao or {}
    chave = predicao.get("classe_key") or ""
    nome = predicao.get("nome") or _nome_classe(chave)
    confianca = predicao.get("confianca")
    try:
        conf_txt = f"{float(confianca):.2f}"
    except (TypeError, ValueError):
        conf_txt = "desconhecida"

    topo = predicao.get("top") or []
    linhas_topo = []
    for item in topo[:3]:
        if not isinstance(item, Mapping):
            continue
        try:
            prob = f"{float(item.get('prob', 0.0)):.2f}"
        except (TypeError, ValueError):
            prob = "?"
        linhas_topo.append(
            f"  - {item.get('key', '?')} ({item.get('nome', '?')}): {prob}"
        )
    bloco_topo = "\n".join(linhas_topo) or "  - (ranking nao informado)"

    return f"""Uma rede neural convolucional treinada em 14.565 imagens de costura analisou o
frame em anexo e ficou com confianca baixa. Preciso da sua segunda opiniao.

Palpite da rede: {chave} ({nome}), confianca {conf_txt}.
Ranking da rede:
{bloco_topo}
{_linha_tecido(tecido)}

Olhe a imagem e responda:
1. A classe apontada pela rede confere com o que a imagem mostra?
2. Se nao confere, qual das 11 chaves canonicas descreve melhor a imagem?
3. Quais sinais visuais sustentam sua conclusao?

Lembre que a classe "normal" existe e e uma resposta legitima: costura boa deve
ser classificada como normal, nao como um defeito leve qualquer.

Responda apenas com o JSON no formato pedido."""


def montar_prompt_diagnostico(
    classe_key: str,
    tecido: str | None = None,
    confianca: float | None = None,
) -> str:
    """Prompt do EXPLICADOR TECNICO: classe prevista -> causa e acao na maquina."""
    try:
        info = class_by_key(classe_key)
        nome = info.pt
        descricao = info.descricao
        gravidade = info.gravidade
    except KeyError:
        nome = str(classe_key)
        descricao = "classe fora da taxonomia conhecida"
        gravidade = "desconhecida"

    if confianca is None:
        linha_conf = "A rede nao informou a confianca."
    else:
        try:
            linha_conf = f"Confianca da rede nesta classificacao: {float(confianca):.2f}."
        except (TypeError, ValueError):
            linha_conf = "A rede nao informou a confianca."

    if classe_key == "normal":
        pedido = """A costura foi classificada como conforme. Explique, em linguagem de chao de
fabrica, o que sustenta esse resultado e o que o operador deve manter e conferir
para o lote nao sair do padrao. Mesmo aqui, preencha causas (fatores que
sustentam o resultado), acoes (o que fazer agora no posto) e prevencao."""
    else:
        pedido = """Explique este defeito para o operador da maquina e diga o que ele deve mexer
AGORA no posto de trabalho. Cite regulagem de tensao superior e da bobina, tipo
e numero da agulha, estado da ponta, calcador e sua pressao, dentes impelentes,
tipo de linha, velocidade e uso de estabilizador quando o tecido pedir."""

    return f"""Defeito detectado pelo sistema de inspecao: {classe_key} ({nome}).
Definicao no sistema: {descricao}
Gravidade cadastrada: {gravidade}.
{_linha_tecido(tecido)}
{linha_conf}

{pedido}

Se o tecido for leve ou escorregadio (chiffon, cetim, nylon, poliester fino),
considere estabilizador, agulha mais fina e reducao de tensao. Se for pesado
(jeans, oxford, jacquard, veludo cotele), considere agulha mais grossa, linha
mais forte e pressao de calcador maior.

Responda apenas com o JSON no formato pedido."""


def montar_prompt_auditoria(classe_real: str, tecido: str | None = None) -> str:
    """Prompt do AUDITOR DE ROTULOS: conferir o rotulo de uma imagem de treino."""
    nome = _nome_classe(classe_real)
    try:
        descricao = class_by_key(classe_real).descricao
    except KeyError:
        descricao = "classe fora da taxonomia conhecida"

    return f"""Esta imagem faz parte do conjunto de TREINO de um classificador de defeitos de
costura. O rotulo gravado para ela e:

  {classe_real} ({nome}) - {descricao}

{_linha_tecido(tecido)}

Confira se o rotulo confere com o que a imagem mostra. Seja conservador: estas
imagens sao recortes 224x224 de costura real, muitas vezes com iluminacao
irregular. Se a evidencia for fraca, marque concorda=true com confianca baixa em
vez de trocar o rotulo.

So marque concorda=false quando a imagem mostrar claramente outra coisa, por
exemplo: rotulo diz "normal" mas ha vao evidente entre pontos, ou rotulo diz
defeito mas a carreira esta perfeitamente uniforme.

Responda apenas com o JSON no formato pedido."""


def montar_prompt_relatorio(
    estatisticas: Mapping[str, Any],
    eventos: Iterable[Mapping[str, Any]],
) -> str:
    """Prompt do relatorio de turno (texto livre em Markdown, sem JSON)."""
    estatisticas = dict(estatisticas or {})
    lista = [e for e in (eventos or []) if isinstance(e, Mapping)]

    por_classe = estatisticas.get("por_classe") or {}
    linhas_classe = []
    for chave, qtd in sorted(por_classe.items(), key=lambda kv: (-int(kv[1] or 0), kv[0])):
        linhas_classe.append(f"  - {chave} ({_nome_classe(chave)}): {qtd}")
    bloco_classe = "\n".join(linhas_classe) or "  - (nenhuma ocorrencia registrada)"

    linhas_eventos = []
    for ev in lista[:40]:
        try:
            conf = f"{float(ev.get('confianca', 0.0)):.2f}"
        except (TypeError, ValueError):
            conf = "?"
        linhas_eventos.append(
            f"  - {ev.get('hora', '--:--:--')} | {ev.get('classe_key', '?')} "
            f"({ev.get('nome', '?')}) | confianca {conf} "
            f"| gravidade {ev.get('gravidade', '?')} | tecido {ev.get('tecido') or 'nao informado'}"
        )
    bloco_eventos = "\n".join(linhas_eventos) or "  - (nenhum evento no periodo)"

    resumo_numerico = json.dumps(
        {
            k: v
            for k, v in estatisticas.items()
            if k in {
                "total", "aprovadas", "reprovadas", "sequencia_ok", "melhor_sequencia",
                "taxa_aprovacao", "duracao_s", "meta_pecas", "progresso_meta",
            }
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""Escreva o relatorio de turno de uma celula de costura monitorada por um sistema
de inspecao automatica chamado Ponto Certo.

Numeros do turno:
{resumo_numerico}

Ocorrencias por classe:
{bloco_classe}

Ultimos eventos registrados:
{bloco_eventos}

Produza um relatorio em Markdown, em portugues do Brasil, com esta estrutura:

# Relatorio de turno - Ponto Certo
## Resumo
Tres a cinco linhas com o desempenho geral do turno e a taxa de aprovacao.
## Principais ocorrencias
Lista das classes mais frequentes com a leitura tecnica do que elas indicam.
## Causa provavel predominante
Um paragrafo apontando o ajuste de maquina mais provavel por tras do padrao
observado (tensao, agulha, calcador, arraste, linha).
## Acoes recomendadas
Lista numerada de acoes objetivas para o proximo turno.
## Observacoes
O que ficou sem explicacao ou precisa de acompanhamento.

Nao invente numeros que nao estejam acima. Se um dado faltar, diga que faltou.
Responda apenas com o Markdown, sem cercar em bloco de codigo."""
