"""Cliente sincrono do OpenRouter usado pelo Ponto Certo.

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

Este modulo e a unica porta de saida para a internet do projeto. Tudo aqui foi
escrito para o sistema continuar funcionando SEM chave de API: quem chama recebe
`configurado == False` e cai no fallback offline em vez de quebrar.

Guardas implementadas:
  - timeout de `cfg.llm.timeout_s` em toda requisicao;
  - retentativa com backoff exponencial (1s, 2s, 4s) apenas em 429 e 5xx,
    limitada por `cfg.llm.max_tentativas`; nunca repete em 401/402;
  - limite de taxa interno de janela deslizante por `cfg.llm.max_chamadas_por_minuto`;
  - saida estruturada via `response_format: json_schema` com parser de resguardo
    que extrai o primeiro objeto JSON do texto, inclusive dentro de bloco
    markdown com crases;
  - a chave da API nunca e impressa, logada nem devolvida em mensagem de erro.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx

from pontocerto.config import chave_openrouter

__all__ = [
    "ErroOpenRouter",
    "RespostaLLM",
    "ClienteOpenRouter",
    "extrair_primeiro_json",
]


class ErroOpenRouter(RuntimeError):
    """Falha ao falar com o OpenRouter, com mensagem acionavel em portugues."""

    def __init__(self, mensagem: str, status: int | None = None, repetivel: bool = False):
        super().__init__(mensagem)
        self.status = status
        self.repetivel = repetivel


@dataclass
class RespostaLLM:
    texto: str
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    ms: float
    bruto: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "texto": self.texto,
            "modelo": self.modelo,
            "tokens_entrada": self.tokens_entrada,
            "tokens_saida": self.tokens_saida,
            "ms": self.ms,
        }


# ---------------------------------------------------------------------------
# Parser de resguardo: o modelo nem sempre honra o json_schema
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _tentar_carregar(fragmento: str) -> dict | None:
    fragmento = (fragmento or "").strip()
    if not fragmento:
        return None
    try:
        dados = json.loads(fragmento)
    except (ValueError, TypeError):
        return None
    return dados if isinstance(dados, dict) else None


def _varrer_balanceado(texto: str) -> dict | None:
    """Acha o primeiro objeto JSON balanceado, ignorando chaves dentro de string."""
    inicio = -1
    profundidade = 0
    em_string = False
    escapado = False
    for i, ch in enumerate(texto):
        if em_string:
            if escapado:
                escapado = False
            elif ch == "\\":
                escapado = True
            elif ch == '"':
                em_string = False
            continue
        if ch == '"':
            em_string = True
            continue
        if ch == "{":
            if profundidade == 0:
                inicio = i
            profundidade += 1
            continue
        if ch == "}":
            if profundidade > 0:
                profundidade -= 1
                if profundidade == 0 and inicio >= 0:
                    dados = _tentar_carregar(texto[inicio:i + 1])
                    if dados is not None:
                        return dados
                    inicio = -1
    return None


def extrair_primeiro_json(texto: str) -> dict | None:
    """Extrai o primeiro objeto JSON de um texto de LLM.

    Aceita JSON puro, JSON dentro de bloco markdown com crases e JSON cercado de
    conversa. Devolve None quando nao encontra nada valido.
    """
    if not texto:
        return None
    dados = _tentar_carregar(texto)
    if dados is not None:
        return dados
    for bloco in _FENCE.findall(texto):
        dados = _tentar_carregar(bloco)
        if dados is not None:
            return dados
        dados = _varrer_balanceado(bloco)
        if dados is not None:
            return dados
    return _varrer_balanceado(texto)


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

_MSG_SEM_CHAVE = (
    "OPENROUTER_API_KEY nao encontrada. Crie uma chave em "
    "https://openrouter.ai/keys e grave no arquivo .env da raiz do projeto na "
    "forma OPENROUTER_API_KEY=sk-or-v1-... O sistema continua funcionando sem "
    "ela, usando a base de conhecimento local."
)

_MSG_DESATIVADO = (
    "O LLM esta desativado no config.yaml (llm.ativo: false). "
    "Troque para true se quiser segunda opiniao e diagnostico online."
)


class ClienteOpenRouter:
    """Fala com a API de chat completions do OpenRouter (compativel com OpenAI)."""

    def __init__(self, cfg: Any, api_key: str | None = None):
        self._cfg = cfg
        llm = {}
        try:
            llm = dict(cfg["llm"])
        except Exception:
            llm = {}
        self._llm = llm

        self._ativo = bool(llm.get("ativo", True))
        self._base_url = str(llm.get("base_url", "https://openrouter.ai/api/v1")).rstrip("/")
        self._modelo_visao = str(llm.get("modelo_visao", "openai/gpt-4o-mini"))
        self._modelo_texto = str(llm.get("modelo_texto", self._modelo_visao))
        self._timeout = float(llm.get("timeout_s", 45))
        self._max_tentativas = max(1, int(llm.get("max_tentativas", 3)))
        self._temperatura = float(llm.get("temperatura", 0.2))
        self._max_tokens = int(llm.get("max_tokens", 700))
        self._max_por_minuto = max(1, int(llm.get("max_chamadas_por_minuto", 8)))
        self._detalhe_imagem = str(llm.get("detalhe_imagem", "auto"))
        self._exigir_parametros = bool(llm.get("exigir_parametros", False))

        chave = api_key if api_key is not None else chave_openrouter()
        self._api_key = (chave or "").strip() or None

        self._chamadas: deque[float] = deque()
        self._cache_modelos: list[dict] | None = None
        self._erro_catalogo: str | None = None
        self.ultima_resposta: RespostaLLM | None = None
        self._stats = {"chamadas": 0, "tokens_entrada": 0, "tokens_saida": 0, "erros": 0}

    # -- propriedades -------------------------------------------------------

    @property
    def cfg(self) -> Any:
        return self._cfg

    @property
    def configurado(self) -> bool:
        """True quando ha chave carregada E o LLM esta ligado no config.yaml."""
        return bool(self._api_key) and self._ativo

    @property
    def tem_chave(self) -> bool:
        return bool(self._api_key)

    @property
    def ativo(self) -> bool:
        return self._ativo

    @property
    def modelo_visao(self) -> str:
        return self._modelo_visao

    @property
    def modelo_texto(self) -> str:
        return self._modelo_texto

    @property
    def estatisticas(self) -> dict:
        return dict(self._stats)

    # -- utilidades internas ------------------------------------------------

    def _mascarar(self, texto: str) -> str:
        """Remove qualquer vestigio da chave antes de a mensagem circular."""
        if not texto:
            return ""
        if self._api_key and self._api_key in texto:
            texto = texto.replace(self._api_key, "***")
        return re.sub(r"sk-or-[A-Za-z0-9\-_]{6,}", "***", texto)

    def _cabecalhos(self) -> dict:
        cab = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        nome_app = os.environ.get("OPENROUTER_APP_NAME")
        if not nome_app:
            try:
                nome_app = str(self._cfg["projeto"]["nome"])
            except Exception:
                nome_app = "Ponto Certo"
        site = os.environ.get("OPENROUTER_SITE_URL")
        if site:
            cab["HTTP-Referer"] = site
        if nome_app:
            cab["X-Title"] = nome_app
        return cab

    def _limpar_janela(self, agora: float) -> None:
        while self._chamadas and agora - self._chamadas[0] >= 60.0:
            self._chamadas.popleft()

    def espera_recomendada(self) -> float:
        """Segundos a aguardar para caber no limite de taxa (0 se ha vaga agora).

        Usado pela auditoria em lote, que prefere esperar a tomar excecao.
        """
        agora = time.time()
        self._limpar_janela(agora)
        if len(self._chamadas) < self._max_por_minuto:
            return 0.0
        return max(0.0, 60.0 - (agora - self._chamadas[0])) + 0.05

    def _reservar_vaga(self) -> None:
        agora = time.time()
        self._limpar_janela(agora)
        if len(self._chamadas) >= self._max_por_minuto:
            espera = max(0.0, 60.0 - (agora - self._chamadas[0]))
            raise ErroOpenRouter(
                f"limite interno de {self._max_por_minuto} chamadas por minuto atingido "
                f"(guarda de custo do config.yaml). Aguarde {espera:.0f}s ou aumente "
                "llm.max_chamadas_por_minuto.",
                repetivel=True,
            )
        self._chamadas.append(agora)

    def _traduzir_status(self, status: int, corpo: str) -> ErroOpenRouter:
        detalhe = ""
        try:
            dados = json.loads(corpo)
            erro = dados.get("error")
            if isinstance(erro, Mapping):
                detalhe = str(erro.get("message") or "")
            elif isinstance(erro, str):
                detalhe = erro
        except (ValueError, TypeError, AttributeError):
            detalhe = (corpo or "")[:300]
        detalhe = self._mascarar(detalhe).strip()
        sufixo = f" Detalhe do servidor: {detalhe}" if detalhe else ""

        if status == 401:
            return ErroOpenRouter(
                "chave invalida: gere outra em https://openrouter.ai/keys e coloque no .env"
                + sufixo,
                status=401,
                repetivel=False,
            )
        if status == 402:
            return ErroOpenRouter(
                "sem creditos na conta do OpenRouter. Adicione saldo em "
                "https://openrouter.ai/credits ou use um modelo mais barato." + sufixo,
                status=402,
                repetivel=False,
            )
        if status == 429:
            return ErroOpenRouter(
                "limite de requisicoes atingido, tente em alguns segundos." + sufixo,
                status=429,
                repetivel=True,
            )
        if status == 404:
            return ErroOpenRouter(
                "modelo ou rota nao encontrada no OpenRouter. Confira o id em "
                "llm.modelo_visao do config.yaml (use checar() para ver ids validos)."
                + sufixo,
                status=404,
                repetivel=False,
            )
        if 500 <= status < 600:
            return ErroOpenRouter(
                f"falha do provedor upstream (HTTP {status}). Tentando de novo em instantes."
                + sufixo,
                status=status,
                repetivel=True,
            )
        return ErroOpenRouter(
            f"resposta inesperada do OpenRouter (HTTP {status})." + sufixo,
            status=status,
            repetivel=False,
        )

    def _post(self, caminho: str, corpo: dict) -> dict:
        """POST com retentativa exponencial em 429/5xx e falha de rede."""
        url = f"{self._base_url}{caminho}"
        ultimo: ErroOpenRouter | None = None
        for tentativa in range(1, self._max_tentativas + 1):
            try:
                with httpx.Client(timeout=self._timeout) as cliente:
                    resp = cliente.post(url, headers=self._cabecalhos(), json=corpo)
            except httpx.TimeoutException:
                ultimo = ErroOpenRouter(
                    f"tempo esgotado depois de {self._timeout:.0f}s falando com o OpenRouter. "
                    "Confira a internet ou aumente llm.timeout_s.",
                    repetivel=True,
                )
            except httpx.HTTPError as exc:
                ultimo = ErroOpenRouter(
                    "falha de rede ao falar com o OpenRouter: "
                    + self._mascarar(str(exc) or exc.__class__.__name__),
                    repetivel=True,
                )
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except (ValueError, TypeError) as exc:
                        raise ErroOpenRouter(
                            "o OpenRouter respondeu algo que nao e JSON: "
                            + self._mascarar(str(exc))
                        ) from exc
                erro = self._traduzir_status(resp.status_code, resp.text)
                if not erro.repetivel:
                    raise erro
                ultimo = erro

            if tentativa < self._max_tentativas:
                time.sleep(float(2 ** (tentativa - 1)))  # 1s, 2s, 4s
        raise ultimo or ErroOpenRouter("falha desconhecida ao falar com o OpenRouter.")

    @staticmethod
    def _normalizar_schema(json_schema: Mapping[str, Any]) -> dict:
        """Aceita tanto o envelope {name, strict, schema} quanto o schema cru."""
        if "schema" in json_schema and "properties" not in json_schema:
            return dict(json_schema)
        return {"name": "resposta", "strict": True, "schema": dict(json_schema)}

    def _contabilizar(self, dados: Mapping[str, Any], inicio: float) -> RespostaLLM:
        escolhas = dados.get("choices") or []
        texto = ""
        if escolhas:
            msg = (escolhas[0] or {}).get("message") or {}
            conteudo = msg.get("content")
            if isinstance(conteudo, str):
                texto = conteudo
            elif isinstance(conteudo, list):
                partes = []
                for bloco in conteudo:
                    if isinstance(bloco, Mapping) and isinstance(bloco.get("text"), str):
                        partes.append(bloco["text"])
                texto = "\n".join(partes)
        uso = dados.get("usage") or {}
        entrada = int(uso.get("prompt_tokens", 0) or 0)
        saida = int(uso.get("completion_tokens", 0) or 0)

        self._stats["chamadas"] += 1
        self._stats["tokens_entrada"] += entrada
        self._stats["tokens_saida"] += saida

        resposta = RespostaLLM(
            texto=texto or "",
            modelo=str(dados.get("model") or ""),
            tokens_entrada=entrada,
            tokens_saida=saida,
            ms=(time.perf_counter() - inicio) * 1000.0,
            bruto=dict(dados),
        )
        self.ultima_resposta = resposta
        return resposta

    def _exigir_pronto(self) -> None:
        if not self._ativo:
            raise ErroOpenRouter(_MSG_DESATIVADO)
        if not self._api_key:
            raise ErroOpenRouter(_MSG_SEM_CHAVE, status=401)

    # -- API publica --------------------------------------------------------

    def chat(
        self,
        mensagens: Sequence[Mapping[str, Any]],
        modelo: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
        max_tokens: int | None = None,
        temperatura: float | None = None,
    ) -> RespostaLLM:
        """Chamada de chat completions. Levanta ErroOpenRouter em qualquer falha."""
        self._exigir_pronto()
        corpo: dict[str, Any] = {
            "model": modelo or self._modelo_texto,
            "messages": [dict(m) for m in mensagens],
            "temperature": self._temperatura if temperatura is None else float(temperatura),
            "max_tokens": self._max_tokens if max_tokens is None else int(max_tokens),
        }
        if json_schema:
            corpo["response_format"] = {
                "type": "json_schema",
                "json_schema": self._normalizar_schema(json_schema),
            }
            if self._exigir_parametros:
                corpo["provider"] = {"require_parameters": True}

        inicio = time.perf_counter()
        self._reservar_vaga()
        try:
            dados = self._post("/chat/completions", corpo)
        except ErroOpenRouter:
            self._stats["erros"] += 1
            raise
        return self._contabilizar(dados, inicio)

    def chat_visao(
        self,
        prompt: str,
        imagem_jpeg: bytes,
        modelo: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
        max_tokens: int | None = None,
        temperatura: float | None = None,
        prompt_sistema: str | None = None,
    ) -> RespostaLLM:
        """Chamada multimodal: um texto mais uma imagem JPEG em base64."""
        if not imagem_jpeg:
            raise ErroOpenRouter("nenhuma imagem foi entregue para analise visual.")
        b64 = base64.b64encode(bytes(imagem_jpeg)).decode("ascii")
        conteudo: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": self._detalhe_imagem,
                },
            },
        ]
        mensagens: list[dict[str, Any]] = []
        if prompt_sistema:
            mensagens.append({"role": "system", "content": prompt_sistema})
        mensagens.append({"role": "user", "content": conteudo})

        return self.chat(
            mensagens,
            modelo=modelo or self._modelo_visao,
            json_schema=json_schema,
            max_tokens=max_tokens,
            temperatura=temperatura,
        )

    def chat_json(
        self,
        mensagens: Sequence[Mapping[str, Any]],
        esquema: Mapping[str, Any],
        **kw: Any,
    ) -> dict:
        """Como `chat`, mas devolve o dict ja parseado.

        A resposta completa fica em `self.ultima_resposta` para quem precisar de
        modelo, tokens e tempo.
        """
        kw.pop("json_schema", None)
        resposta = self.chat(mensagens, json_schema=esquema, **kw)
        dados = extrair_primeiro_json(resposta.texto)
        if dados is None:
            self._stats["erros"] += 1
            trecho = self._mascarar((resposta.texto or "")[:200]).replace("\n", " ")
            raise ErroOpenRouter(
                "o modelo nao devolveu JSON valido mesmo com response_format. "
                f"Inicio da resposta: {trecho!r}"
            )
        return dados

    def listar_modelos(self, recarregar: bool = False) -> list[dict]:
        """Catalogo publico do OpenRouter. Devolve [] se nao der para consultar."""
        if self._cache_modelos is not None and not recarregar:
            return self._cache_modelos
        url = f"{self._base_url}/models"
        try:
            with httpx.Client(timeout=self._timeout) as cliente:
                resp = cliente.get(url, headers={"Content-Type": "application/json"})
            if resp.status_code != 200:
                self._erro_catalogo = f"HTTP {resp.status_code} ao consultar {url}"
                self._cache_modelos = []
                return []
            dados = resp.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            self._erro_catalogo = self._mascarar(str(exc) or exc.__class__.__name__)
            self._cache_modelos = []
            return []
        itens = dados.get("data") if isinstance(dados, Mapping) else None
        self._cache_modelos = [m for m in (itens or []) if isinstance(m, Mapping)]
        self._erro_catalogo = None
        return self._cache_modelos

    @staticmethod
    def _aceita_imagem(modelo: Mapping[str, Any]) -> bool:
        arq = modelo.get("architecture")
        if isinstance(arq, Mapping):
            entradas = arq.get("input_modalities") or arq.get("modality") or []
            if isinstance(entradas, str):
                return "image" in entradas.lower()
            if isinstance(entradas, (list, tuple)):
                return any("image" in str(x).lower() for x in entradas)
        return False

    def sugestoes_visao(self, limite: int = 8) -> list[str]:
        """Ids 'openai/*' do catalogo que aceitam imagem na entrada."""
        ids = []
        for m in self.listar_modelos():
            mid = str(m.get("id") or "")
            if mid.startswith("openai/") and self._aceita_imagem(m):
                ids.append(mid)
        ids.sort(key=lambda s: (("mini" not in s and "nano" not in s), s))
        return ids[:limite]

    def _consultar_chave(self) -> tuple[dict | None, ErroOpenRouter | None]:
        """GET /key: limites e uso da chave. Tolerante a mudanca de formato."""
        url = f"{self._base_url}/key"
        try:
            with httpx.Client(timeout=self._timeout) as cliente:
                resp = cliente.get(url, headers=self._cabecalhos())
        except httpx.HTTPError as exc:
            return None, ErroOpenRouter(
                "nao foi possivel falar com o OpenRouter: "
                + self._mascarar(str(exc) or exc.__class__.__name__),
                repetivel=True,
            )
        if resp.status_code != 200:
            return None, self._traduzir_status(resp.status_code, resp.text)
        try:
            dados = resp.json()
        except (ValueError, TypeError):
            return None, None
        if isinstance(dados, Mapping):
            interno = dados.get("data")
            return (dict(interno) if isinstance(interno, Mapping) else dict(dados)), None
        return None, None

    def checar(self) -> dict:
        """Diagnostico da camada de LLM, pronto para a rota /api/llm/status.

        Sempre devolve dict; nunca levanta excecao.
        """
        base = {
            "ok": False,
            "mensagem": "",
            "modelo_visao": self._modelo_visao,
            "creditos": None,
        }
        if not self._ativo:
            base["mensagem"] = _MSG_DESATIVADO
            return base
        if not self._api_key:
            base["mensagem"] = _MSG_SEM_CHAVE
            return base

        creditos, erro = self._consultar_chave()
        if erro is not None and erro.status in (401, 402):
            base["mensagem"] = str(erro)
            return base
        base["creditos"] = creditos

        catalogo = self.listar_modelos()
        if not catalogo:
            base["ok"] = True
            base["mensagem"] = (
                "chave carregada, mas nao foi possivel consultar o catalogo de modelos"
                + (f" ({self._erro_catalogo})" if self._erro_catalogo else "")
                + f". Seguindo com o modelo configurado '{self._modelo_visao}'."
            )
            return base

        ids = {str(m.get("id") or "") for m in catalogo}
        if self._modelo_visao not in ids:
            sugestoes = self.sugestoes_visao()
            lista = ", ".join(sugestoes) if sugestoes else "nenhum id 'openai/' com visao encontrado"
            base["mensagem"] = (
                f"o modelo '{self._modelo_visao}' nao aparece no catalogo atual do "
                "OpenRouter. Edite llm.modelo_visao no config.yaml e use um destes "
                f"ids que aceitam imagem: {lista}."
            )
            return base

        visao_ok = any(
            str(m.get("id")) == self._modelo_visao and self._aceita_imagem(m)
            for m in catalogo
        )
        base["ok"] = True
        if visao_ok:
            base["mensagem"] = (
                f"OpenRouter pronto. Modelo de visao '{self._modelo_visao}' disponivel "
                f"e limite interno de {self._max_por_minuto} chamadas por minuto."
            )
        else:
            base["mensagem"] = (
                f"o modelo '{self._modelo_visao}' existe no catalogo, mas o campo de "
                "modalidades nao confirma entrada de imagem. Segunda opiniao visual "
                "pode falhar; considere um id 'openai/*-mini' com visao."
            )
        return base
