"""Auditoria de rotulos do conjunto de treino assistida por LLM.

FILOSOFIA DESTA CAMADA
----------------------
A rede neural convolucional e quem decide em tempo real. Ela e rapida, roda
offline e foi treinada nas 14.565 imagens do proprio dataset. O LLM multimodal
NAO substitui a CNN e nao a "treina" por magica. Ele entra em tres papeis
concretos e verificaveis:

  (1) AUDITOR DE ROTULOS, antes do treino: revisa amostras do conjunto de treino
      e aponta imagens provavelmente mal rotuladas, melhorando o dado que
      alimenta a CNN.  <-- este modulo
  (2) SEGUNDA OPINIAO, em tempo de uso: quando a confianca da CNN cai na faixa
      de incerteza, o frame vai para o modelo de visao, que concorda ou discorda
      e justifica.
  (3) EXPLICADOR TECNICO: converte a classe prevista em causa provavel e acao
      corretiva na maquina de costura, e escreve o relatorio de turno.

Este e o papel (1) e o mais facil de justificar num projeto integrador: o LLM
nao treina nada, ele apenas le uma amostra do dataset e devolve uma lista de
imagens suspeitas. Quem decide o que fazer com elas e a pessoa. O CSV gerado
serve de insumo para uma limpeza manual antes do proximo treino.

Uso:
    python -m pontocerto.llm.auditoria --amostras 12
    python -m pontocerto.llm.auditoria --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

if __name__ == "__main__" and __package__ in (None, ""):  # pragma: no cover
    # Permite "python src/pontocerto/llm/auditoria.py" alem de "python -m ...".
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pontocerto.config import carregar_config, garantir_pasta
from pontocerto.labels import CLASS_KEYS, fabric_by_folder
from pontocerto.llm.openrouter import (
    ClienteOpenRouter,
    ErroOpenRouter,
    extrair_primeiro_json,
)
from pontocerto.llm.prompts import (
    ESQUEMA_AUDITORIA,
    SISTEMA_AUDITOR,
    montar_prompt_auditoria,
)

__all__ = ["auditar_rotulos", "main"]

COLUNAS = [
    "caminho",
    "classe_real",
    "classe_sugerida",
    "concorda",
    "confianca",
    "justificativa",
]


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------

def _barra(iteravel, total: int, descricao: str):
    """tqdm quando disponivel; caso contrario devolve o iteravel cru."""
    try:
        from tqdm import tqdm
    except ImportError:
        return iteravel
    return tqdm(iteravel, total=total, desc=descricao, unit="img", ncols=90)


def _carregar_manifesto(cfg: Any) -> pd.DataFrame:
    """Le o manifesto via data.split; se o modulo faltar, le o CSV direto."""
    try:
        from pontocerto.data.split import carregar_manifesto  # type: ignore
        return carregar_manifesto(cfg)
    except ImportError:
        pass
    destino = Path(cfg["dados"]["manifesto"])
    if not destino.exists():
        raise FileNotFoundError(
            f"manifesto nao encontrado em {destino}. "
            "Rode antes: python scripts/01_preparar_dados.py"
        )
    return pd.read_csv(destino, encoding="utf-8")


def _amostrar(df: pd.DataFrame, por_classe: int, semente: int) -> pd.DataFrame:
    """Sorteia ate `por_classe` imagens do split de treino, por classe."""
    if "split" in df.columns:
        treino = df[df["split"] == "treino"]
        if treino.empty:
            treino = df
    else:
        treino = df

    pedacos = []
    for chave in CLASS_KEYS:
        sub = treino[treino["classe_key"] == chave]
        if sub.empty:
            continue
        n = min(int(por_classe), len(sub))
        pedacos.append(sub.sample(n=n, random_state=int(semente)))
    if not pedacos:
        return treino.head(0)
    amostra = pd.concat(pedacos, ignore_index=True)
    return amostra.sample(frac=1.0, random_state=int(semente)).reset_index(drop=True)


def _nome_tecido(linha: Any) -> str | None:
    pasta = linha.get("tecido_pasta") if hasattr(linha, "get") else None
    if not pasta:
        return None
    try:
        return fabric_by_folder(str(pasta)).pt
    except KeyError:
        return str(pasta)


def _normalizar_chave(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto in CLASS_KEYS:
        return texto
    achatado = texto.lower().replace("-", "_").replace(" ", "_")
    if achatado in CLASS_KEYS:
        return achatado
    if achatado.isdigit():
        idx = int(achatado)
        if 0 <= idx < len(CLASS_KEYS):
            return CLASS_KEYS[idx]
    for chave in CLASS_KEYS:
        if chave in achatado:
            return chave
    return ""


def _normalizar_confianca(valor: Any) -> float:
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if f > 1.0:
        f = f / 100.0
    return max(0.0, min(1.0, f))


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------

def auditar_rotulos(
    cfg: Any,
    cliente: ClienteOpenRouter,
    amostras_por_classe: int | None = None,
    saida: str | None = None,
) -> pd.DataFrame:
    """Sorteia imagens do treino, pede ao LLM que confirme o rotulo e grava CSV.

    Colunas do CSV: caminho, classe_real, classe_sugerida, concorda, confianca,
    justificativa. Uma imagem que falhar (rede, rate limit, JSON invalido) vira
    uma linha com `justificativa` iniciando por "erro:" e a varredura continua.
    """
    aud = {}
    try:
        aud = dict(cfg["llm"]["auditoria"])
    except Exception:
        aud = {}
    por_classe = int(amostras_por_classe or aud.get("amostras_por_classe", 12))
    destino = Path(saida or aud.get("saida") or (Path(cfg["_raiz"]) / "artifacts" / "auditoria_rotulos.csv"))
    try:
        semente = int(cfg["divisao"]["semente"])
    except Exception:
        semente = 42
    raiz_dados = Path(cfg["dados"]["raiz"])

    df = _carregar_manifesto(cfg)
    amostra = _amostrar(df, por_classe, semente)
    total = len(amostra)
    print(
        f"Auditoria de rotulos: {total} imagens sorteadas "
        f"({por_classe} por classe, split de treino, semente {semente})."
    )
    if total == 0:
        vazio = pd.DataFrame(columns=COLUNAS)
        garantir_pasta(destino.parent)
        vazio.to_csv(destino, index=False, encoding="utf-8")
        return vazio

    checagem = cliente.checar()
    if not checagem.get("ok"):
        print("[aviso] " + str(checagem.get("mensagem") or "LLM indisponivel."))
        print("        A auditoria precisa do modelo de visao. Nada foi consultado.")
        linhas = [
            {
                "caminho": str(linha["caminho"]),
                "classe_real": str(linha["classe_key"]),
                "classe_sugerida": "",
                "concorda": "",
                "confianca": 0.0,
                "justificativa": "erro: " + str(checagem.get("mensagem") or "LLM indisponivel"),
            }
            for _, linha in amostra.iterrows()
        ]
        resultado = pd.DataFrame(linhas, columns=COLUNAS)
        garantir_pasta(destino.parent)
        resultado.to_csv(destino, index=False, encoding="utf-8")
        print(f"CSV com o motivo da falha gravado em {destino}")
        return resultado

    print(f"Modelo de visao: {checagem.get('modelo_visao')}")
    linhas: list[dict] = []
    erros = 0
    discordancias = 0
    inicio = time.perf_counter()

    iterador = _barra(list(amostra.itertuples(index=False)), total, "auditando")
    for reg in iterador:
        dados_linha = reg._asdict() if hasattr(reg, "_asdict") else dict(reg)
        rel = str(dados_linha.get("caminho", ""))
        classe_real = str(dados_linha.get("classe_key", ""))
        registro = {
            "caminho": rel,
            "classe_real": classe_real,
            "classe_sugerida": "",
            "concorda": "",
            "confianca": 0.0,
            "justificativa": "",
        }

        arquivo = raiz_dados / rel
        try:
            imagem = arquivo.read_bytes()
        except OSError as exc:
            registro["justificativa"] = f"erro: nao foi possivel ler a imagem ({exc})"
            linhas.append(registro)
            erros += 1
            continue

        # Respeita o limite de taxa esperando a vaga em vez de tomar excecao.
        espera = cliente.espera_recomendada()
        if espera > 0:
            time.sleep(espera)

        try:
            prompt = montar_prompt_auditoria(classe_real, tecido=_nome_tecido(dados_linha))
            resposta = cliente.chat_visao(
                prompt,
                imagem,
                json_schema=ESQUEMA_AUDITORIA,
                prompt_sistema=SISTEMA_AUDITOR,
                max_tokens=300,
            )
            parsed = extrair_primeiro_json(resposta.texto)
        except ErroOpenRouter as exc:
            registro["justificativa"] = f"erro: {exc}"
            linhas.append(registro)
            erros += 1
            continue
        except Exception as exc:  # nao deixe uma imagem ruim derrubar o lote
            registro["justificativa"] = f"erro: falha inesperada ({exc})"
            linhas.append(registro)
            erros += 1
            continue

        if not isinstance(parsed, dict):
            registro["justificativa"] = "erro: o modelo respondeu sem JSON valido"
            linhas.append(registro)
            erros += 1
            continue

        sugerida = _normalizar_chave(parsed.get("classe_sugerida")) or classe_real
        concorda = parsed.get("concorda")
        if not isinstance(concorda, bool):
            concorda = sugerida == classe_real
        registro["classe_sugerida"] = sugerida
        registro["concorda"] = bool(concorda)
        registro["confianca"] = _normalizar_confianca(parsed.get("confianca"))
        registro["justificativa"] = str(parsed.get("justificativa") or "").strip()
        if not concorda:
            discordancias += 1
        linhas.append(registro)

    resultado = pd.DataFrame(linhas, columns=COLUNAS)
    garantir_pasta(destino.parent)
    resultado.to_csv(destino, index=False, encoding="utf-8")

    segundos = time.perf_counter() - inicio
    avaliadas = total - erros
    taxa = (100.0 * (avaliadas - discordancias) / avaliadas) if avaliadas else 0.0
    stats = cliente.estatisticas
    print()
    print("--- Auditoria concluida ---")
    print(f"Imagens sorteadas .......: {total}")
    print(f"Avaliadas pelo modelo ...: {avaliadas}")
    print(f"Linhas com erro .........: {erros}")
    print(f"Rotulos confirmados .....: {avaliadas - discordancias} ({taxa:.1f}%)")
    print(f"Rotulos contestados .....: {discordancias}")
    print(f"Tokens (entrada/saida) ..: {stats['tokens_entrada']}/{stats['tokens_saida']}")
    print(f"Tempo ...................: {segundos:.1f}s")
    print(f"CSV .....................: {destino}")
    if discordancias:
        print()
        print("Imagens contestadas (revise a mao antes do proximo treino):")
        suspeitas = resultado[resultado["concorda"] == False]  # noqa: E712
        for _, linha in suspeitas.head(20).iterrows():
            print(
                f"  {linha['caminho']}: rotulo '{linha['classe_real']}' -> "
                f"sugerido '{linha['classe_sugerida']}' "
                f"(conf {float(linha['confianca']):.2f})"
            )
    return resultado


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _dry_run(cfg: Any, cliente: ClienteOpenRouter, por_classe: int, destino: Path) -> pd.DataFrame:
    df = _carregar_manifesto(cfg)
    try:
        semente = int(cfg["divisao"]["semente"])
    except Exception:
        semente = 42
    amostra = _amostrar(df, por_classe, semente)
    total = len(amostra)
    try:
        por_minuto = int(cfg["llm"]["max_chamadas_por_minuto"])
    except Exception:
        por_minuto = 8
    minutos = total / max(1, por_minuto)

    checagem = cliente.checar()
    print("--- Simulacao (dry-run): nenhuma chamada foi feita ao OpenRouter ---")
    print(f"Manifesto ...............: {cfg['dados']['manifesto']}")
    print(f"Amostras por classe .....: {por_classe}")
    print(f"Total de imagens ........: {total}")
    print(f"Limite de taxa ..........: {por_minuto} chamadas/min -> ~{minutos:.1f} min")
    print(f"CSV que seria gravado ...: {destino}")
    print(f"LLM pronto ..............: {checagem.get('ok')}")
    print(f"Mensagem ................: {checagem.get('mensagem')}")
    print()
    contagem = amostra["classe_key"].value_counts() if total else {}
    for chave in CLASS_KEYS:
        try:
            qtd = int(contagem.get(chave, 0))
        except Exception:
            qtd = 0
        print(f"  {chave:<20} {qtd}")
    if total:
        print()
        print("Primeiras imagens sorteadas:")
        for caminho in amostra["caminho"].head(5):
            print(f"  {caminho}")
    return amostra


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pontocerto.llm.auditoria",
        description=(
            "Auditoria de rotulos do conjunto de treino com o modelo de visao do "
            "OpenRouter. Gera um CSV com as imagens provavelmente mal rotuladas."
        ),
    )
    parser.add_argument(
        "--amostras", type=int, default=None,
        help="imagens sorteadas por classe (padrao: llm.auditoria.amostras_por_classe)",
    )
    parser.add_argument(
        "--saida", type=str, default=None,
        help="caminho do CSV de saida (padrao: llm.auditoria.saida)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="mostra o plano e o custo estimado sem chamar o LLM",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    cliente = ClienteOpenRouter(cfg)

    aud = {}
    try:
        aud = dict(cfg["llm"]["auditoria"])
    except Exception:
        aud = {}
    por_classe = int(args.amostras or aud.get("amostras_por_classe", 12))
    destino = Path(
        args.saida
        or aud.get("saida")
        or (Path(cfg["_raiz"]) / "artifacts" / "auditoria_rotulos.csv")
    )

    if args.dry_run:
        _dry_run(cfg, cliente, por_classe, destino)
        return

    auditar_rotulos(cfg, cliente, amostras_por_classe=por_classe, saida=str(destino))


if __name__ == "__main__":  # pragma: no cover
    main()
