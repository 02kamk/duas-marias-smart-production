"""Avaliacao do modelo treinado sobre o split de teste.

Gera os artefatos que vao para a apresentacao e para a aba "Treinamento" da
interface: matriz de confusao (bruta e normalizada), relatorio por classe,
desempenho por tecido e um metricas.json consumido pela API.

    python scripts/03_avaliar.py
    python scripts/03_avaliar.py --modelo artifacts/modelo.pt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # sem interface grafica: roda em qualquer terminal
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from matplotlib.colors import LinearSegmentedColormap

from pontocerto.config import carregar_config, garantir_pasta
from pontocerto.data.dataset import construir_dataloaders
from pontocerto.labels import (
    CLASS_KEYS,
    CLASS_NAMES_PT,
    NUM_CLASSES,
    OK_INDEX,
    fabric_by_letter,
)
from pontocerto.training.model import carregar_checkpoint, resolver_dispositivo
from pontocerto.training.train import (
    acuracia_ok_ng,
    ajustar_threads,
    macro_f1,
    matriz_confusao,
    metricas_por_classe,
)

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    def tqdm(it, **kw):  # type: ignore[misc]
        return it


# ---------------------------------------------------------------------------
# Paleta do projeto (branco -> terracota -> barro). Nada de viridis/jet.
# ---------------------------------------------------------------------------
CORES_PONTOCERTO = ["#FFFFFF", "#F7E9E2", "#E08258", "#C1502E", "#7C3A1F"]
CMAP = LinearSegmentedColormap.from_list("pontocerto", CORES_PONTOCERTO)

TERRACOTA = "#C1502E"
TERRACOTA_CLARO = "#E08258"
SAGE = "#4F7A56"
TINTA = "#1C1917"
LINHA = "#E4DAD1"


def _estilo_base(ax) -> None:
    ax.set_facecolor("#FFFFFF")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(LINHA)
    ax.tick_params(colors=TINTA, labelsize=9)


# ---------------------------------------------------------------------------
# Inferencia sobre o split de teste
# ---------------------------------------------------------------------------
def prever_split(modelo, loader, dispositivo) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devolve (rotulos_reais, preditos, probabilidades) na ordem do DataLoader."""
    reais: list[int] = []
    preditos: list[int] = []
    probs: list[np.ndarray] = []

    modelo.eval()
    with torch.inference_mode():
        for x, y in tqdm(loader, desc="avaliando", ncols=88, unit="lote", leave=False):
            x = x.to(dispositivo)
            saida = modelo(x)
            p = torch.softmax(saida, dim=1).cpu().numpy()
            probs.append(p)
            preditos.extend(p.argmax(axis=1).tolist())
            reais.extend(y.numpy().tolist())

    return (
        np.asarray(reais, dtype=np.int64),
        np.asarray(preditos, dtype=np.int64),
        np.concatenate(probs, axis=0) if probs else np.zeros((0, NUM_CLASSES)),
    )


# ---------------------------------------------------------------------------
# Graficos
# ---------------------------------------------------------------------------
def plot_matriz(mc: np.ndarray, destino: Path, normalizada: bool = False) -> None:
    dados = mc.astype(np.float64)
    if normalizada:
        soma = dados.sum(axis=1, keepdims=True)
        dados = np.divide(dados, soma, out=np.zeros_like(dados), where=soma > 0)

    fig, ax = plt.subplots(figsize=(12.5, 10.5), dpi=130)
    im = ax.imshow(dados, cmap=CMAP, vmin=0, vmax=1 if normalizada else max(1, dados.max()))

    ax.set_xticks(range(NUM_CLASSES))
    ax.set_yticks(range(NUM_CLASSES))
    ax.set_xticklabels(CLASS_NAMES_PT, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(CLASS_NAMES_PT, fontsize=9)
    ax.set_xlabel("Previsto pela rede", fontsize=11, color=TINTA, labelpad=10)
    ax.set_ylabel("Rotulo verdadeiro", fontsize=11, color=TINTA, labelpad=10)
    titulo = "Matriz de confusao (proporcao por linha)" if normalizada else "Matriz de confusao (contagem)"
    ax.set_title(titulo, fontsize=14, color=TINTA, pad=16, fontweight="bold")

    # Texto dentro das celulas, com cor que contrasta com o fundo quente.
    limite = (1 if normalizada else max(1, dados.max())) * 0.55
    for i in range(NUM_CLASSES):
        for j in range(NUM_CLASSES):
            v = dados[i, j]
            if normalizada:
                texto = f"{v*100:.0f}" if v >= 0.005 else ""
            else:
                texto = f"{int(v)}" if v else ""
            if texto:
                ax.text(j, i, texto, ha="center", va="center", fontsize=8,
                        color="#FFFFFF" if v > limite else TINTA)

    ax.set_xticks(np.arange(-0.5, NUM_CLASSES, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, NUM_CLASSES, 1), minor=True)
    ax.grid(which="minor", color=LINHA, linewidth=1)
    ax.tick_params(which="minor", length=0)

    barra = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.03)
    barra.outline.set_edgecolor(LINHA)
    barra.ax.tick_params(colors=TINTA, labelsize=8)

    fig.tight_layout()
    fig.savefig(destino, facecolor="#FFFFFF")
    plt.close(fig)


def plot_por_tecido(acertos: dict, destino: Path) -> None:
    letras = list(acertos.keys())
    nomes = [acertos[l]["nome"] for l in letras]
    valores = [acertos[l]["acuracia"] * 100 for l in letras]

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=130)
    _estilo_base(ax)
    barras = ax.bar(nomes, valores, color=TERRACOTA, width=0.62, zorder=3)
    media = float(np.mean(valores)) if valores else 0.0
    ax.axhline(media, color=SAGE, linestyle="--", linewidth=1.4, zorder=4,
               label=f"media geral: {media:.1f}%")

    for barra, valor in zip(barras, valores):
        ax.text(barra.get_x() + barra.get_width() / 2, valor + 1.2, f"{valor:.1f}",
                ha="center", va="bottom", fontsize=9, color=TINTA)

    ax.set_ylim(0, 105)
    ax.set_ylabel("Acuracia no teste (%)", fontsize=11, color=TINTA)
    ax.set_title("Desempenho por tipo de tecido", fontsize=14, color=TINTA,
                 pad=14, fontweight="bold")
    ax.grid(axis="y", color=LINHA, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(destino, facecolor="#FFFFFF")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main(argv=None) -> None:
    cfg = carregar_config()
    p = argparse.ArgumentParser(
        prog="03_avaliar",
        description="Avalia o modelo treinado sobre o split de teste.",
    )
    p.add_argument("--modelo", default=str(cfg.inferencia.modelo))
    p.add_argument("--batch-size", type=int, default=int(cfg.treino.batch_size))
    p.add_argument("--workers", type=int, default=int(cfg.treino.workers))
    p.add_argument("--limite-por-classe", type=int, default=None)
    args = p.parse_args(argv)

    caminho_modelo = Path(args.modelo)
    if not caminho_modelo.is_absolute():
        caminho_modelo = Path(cfg["_raiz"]) / caminho_modelo
    if not caminho_modelo.exists():
        raise SystemExit(
            f"[erro] modelo nao encontrado em {caminho_modelo}.\n"
            "       Rode primeiro:  python scripts/02_treinar.py"
        )

    threads = ajustar_threads()
    dispositivo = resolver_dispositivo(str(cfg.inferencia.dispositivo))
    modelo, meta = carregar_checkpoint(caminho_modelo, dispositivo)
    print(f"[ok] modelo '{meta.get('backbone')}' carregado ({dispositivo}, {threads} threads).")

    cfg.treino["batch_size"] = int(args.batch_size)
    cfg.treino["workers"] = max(0, int(args.workers))
    dados = construir_dataloaders(cfg, limite_por_classe=args.limite_por_classe)
    loader = dados["teste"]
    if len(loader.dataset) == 0:
        raise SystemExit("[erro] o split de teste esta vazio.")

    t0 = time.time()
    reais, preditos, probs = prever_split(modelo, loader, dispositivo)
    segundos = time.time() - t0

    mc = matriz_confusao(reais, preditos)
    por_classe = metricas_por_classe(mc)
    acuracia = float((reais == preditos).mean()) if len(reais) else 0.0
    f1 = macro_f1(mc)
    okng = acuracia_ok_ng(reais, preditos)

    # Desempenho por tecido: o DataLoader de teste nao embaralha, entao a ordem
    # das predicoes casa linha a linha com o DataFrame do split de teste.
    df_teste = dados["df"]
    df_teste = df_teste[df_teste["split"] == "teste"].reset_index(drop=True)
    por_tecido: dict[str, dict] = {}
    if len(df_teste) == len(reais):
        df_teste = df_teste.assign(predito=preditos, real=reais)
        for letra, grupo in df_teste.groupby("tecido_letra", sort=True):
            certo = float((grupo["predito"] == grupo["real"]).mean())
            try:
                nome = fabric_by_letter(str(letra)).pt
            except KeyError:
                nome = str(letra)
            por_tecido[str(letra)] = {
                "nome": nome,
                "acuracia": round(certo, 4),
                "amostras": int(len(grupo)),
            }
    else:
        print("[aviso] nao consegui alinhar as predicoes com os tecidos; "
              "pulando o relatorio por tecido.")

    saida_dir = garantir_pasta(cfg.avaliacao.saida_dir)
    plot_matriz(mc, saida_dir / "matriz_confusao.png", normalizada=False)
    plot_matriz(mc, saida_dir / "matriz_confusao_normalizada.png", normalizada=True)
    if por_tecido:
        plot_por_tecido(por_tecido, saida_dir / "acertos_por_tecido.png")

    linhas = []
    for i, chave in enumerate(CLASS_KEYS):
        m = por_classe[chave]
        linhas.append({
            "classe_idx": i,
            "classe_key": chave,
            "nome": m["nome"],
            "precisao": m["precisao"],
            "recall": m["recall"],
            "f1": m["f1"],
            "suporte": m["suporte"],
        })
    pd.DataFrame(linhas).to_csv(saida_dir / "relatorio_classes.csv",
                                index=False, encoding="utf-8")

    metricas = {
        "modelo": str(caminho_modelo),
        "backbone": meta.get("backbone"),
        "amostras_teste": int(len(reais)),
        "acuracia": round(acuracia, 4),
        "macro_f1": round(f1, 4),
        "acuracia_ok_ng": round(okng, 4),
        "segundos_inferencia": round(segundos, 2),
        "ms_por_imagem": round(segundos * 1000 / max(1, len(reais)), 2),
        "por_classe": por_classe,
        "por_tecido": por_tecido,
        "matriz_confusao": mc.tolist(),
        "classes": list(CLASS_KEYS),
        "nomes": list(CLASS_NAMES_PT),
        "avaliado_em": datetime.now().isoformat(timespec="seconds"),
    }
    (saida_dir / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ------------------------------------------------------------------
    print("-" * 74)
    print(f"  Amostras de teste ........ {len(reais)}")
    print(f"  Acuracia (11 classes) .... {acuracia*100:.2f}%")
    print(f"  Macro-F1 ................. {f1*100:.2f}%")
    print(f"  Acuracia aprovado/reprovado {okng*100:.2f}%   <- a metrica da linha")
    print(f"  Tempo de inferencia ...... {metricas['ms_por_imagem']:.1f} ms/imagem")
    print("-" * 74)
    print("  Por classe (F1):")
    for chave in CLASS_KEYS:
        m = por_classe[chave]
        print(f"    {m['nome']:<26} F1 {m['f1']*100:5.1f}%   "
              f"prec {m['precisao']*100:5.1f}%   rec {m['recall']*100:5.1f}%   n={m['suporte']}")
    if por_tecido:
        print("  Por tecido (acuracia):")
        for letra, t in por_tecido.items():
            print(f"    {letra}. {t['nome']:<24} {t['acuracia']*100:5.1f}%   n={t['amostras']}")
    print("-" * 74)
    print(f"  Artefatos gravados em: {saida_dir}")
    print("    matriz_confusao.png, matriz_confusao_normalizada.png,")
    print("    acertos_por_tecido.png, relatorio_classes.csv, metricas.json")
    print("-" * 74)


if __name__ == "__main__":
    sys.exit(main())
