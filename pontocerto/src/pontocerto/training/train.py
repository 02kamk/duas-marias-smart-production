"""Treinamento da rede de classificacao de falhas de costura.

Este e o unico lugar do projeto onde a CNN aprende. O LLM nao participa daqui:
quem aprende com as 14.565 imagens rotuladas e a rede convolucional. A camada de
LLM (pontocerto/llm) atua antes (auditando rotulos) e depois (explicando e dando
segunda opiniao), nunca no laco de otimizacao.

Uso tipico:
    python scripts/02_treinar.py                          # treino completo
    python scripts/02_treinar.py --limite-por-classe 40 --epocas 2   # demonstracao
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR, LambdaLR, SequentialLR

from pontocerto.config import carregar_config, garantir_pasta
from pontocerto.data.dataset import construir_dataloaders
from pontocerto.labels import CLASS_KEYS, CLASS_NAMES_PT, NUM_CLASSES, OK_INDEX
from pontocerto.training.model import (
    contar_parametros,
    criar_modelo,
    resolver_dispositivo,
    salvar_checkpoint,
)

try:  # a barra de progresso e um conforto, nao uma dependencia dura
    from tqdm import tqdm
except Exception:  # pragma: no cover
    def tqdm(it, **kw):  # type: ignore[misc]
        return it


# ---------------------------------------------------------------------------
# Reprodutibilidade e uso de CPU
# ---------------------------------------------------------------------------
def fixar_semente(semente: int) -> None:
    random.seed(semente)
    np.random.seed(semente)
    torch.manual_seed(semente)
    torch.cuda.manual_seed_all(semente)


def ajustar_threads() -> int:
    """Deixa 2 nucleos livres para o sistema (e para o servidor, se estiver no ar)."""
    cpus = os.cpu_count() or 4
    n = max(1, cpus - 2)
    torch.set_num_threads(n)
    return n


# ---------------------------------------------------------------------------
# Metricas
# ---------------------------------------------------------------------------
def matriz_confusao(reais: np.ndarray, preditos: np.ndarray, n: int = NUM_CLASSES) -> np.ndarray:
    m = np.zeros((n, n), dtype=np.int64)
    for r, p in zip(reais, preditos):
        if 0 <= r < n and 0 <= p < n:
            m[int(r), int(p)] += 1
    return m


def metricas_por_classe(mc: np.ndarray) -> dict:
    """Precisao, recall e F1 por classe a partir da matriz de confusao."""
    saida: dict[str, dict] = {}
    for i in range(mc.shape[0]):
        vp = float(mc[i, i])
        fp = float(mc[:, i].sum() - vp)
        fn = float(mc[i, :].sum() - vp)
        precisao = vp / (vp + fp) if (vp + fp) > 0 else 0.0
        recall = vp / (vp + fn) if (vp + fn) > 0 else 0.0
        f1 = 2 * precisao * recall / (precisao + recall) if (precisao + recall) > 0 else 0.0
        saida[CLASS_KEYS[i]] = {
            "nome": CLASS_NAMES_PT[i],
            "precisao": round(precisao, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "suporte": int(mc[i, :].sum()),
        }
    return saida


def macro_f1(mc: np.ndarray) -> float:
    porc = metricas_por_classe(mc)
    valores = [v["f1"] for v in porc.values() if v["suporte"] > 0]
    return float(np.mean(valores)) if valores else 0.0


def acuracia_ok_ng(reais: np.ndarray, preditos: np.ndarray) -> float:
    """Acuracia binaria aprovado/reprovado - a metrica que importa na linha.

    Confundir "franzimento" com "linha frouxa" ainda reprova a peca corretamente;
    confundir qualquer falha com "normal" deixa defeito passar. Por isso medimos
    tambem o problema reduzido a duas classes.
    """
    if len(reais) == 0:
        return 0.0
    r = (np.asarray(reais) != OK_INDEX)
    p = (np.asarray(preditos) != OK_INDEX)
    return float((r == p).mean())


# ---------------------------------------------------------------------------
# Um passe completo sobre um DataLoader
# ---------------------------------------------------------------------------
def rodar_epoca(
    modelo: nn.Module,
    loader,
    criterio,
    dispositivo,
    otimizador=None,
    escalonador=None,
    descricao: str = "",
) -> dict:
    """Treina (se otimizador for dado) ou avalia. Devolve perda e metricas."""
    treinando = otimizador is not None
    modelo.train(treinando)

    perda_total = 0.0
    vistos = 0
    reais: list[int] = []
    preditos: list[int] = []

    barra = tqdm(loader, desc=descricao, leave=False, ncols=88, unit="lote")
    for x, y in barra:
        x = x.to(dispositivo, non_blocking=False)
        y = y.to(dispositivo, non_blocking=False)

        if treinando:
            otimizador.zero_grad(set_to_none=True)
            saida = modelo(x)
            perda = criterio(saida, y)
            perda.backward()
            # Clipping evita que um lote ruim (tecido escuro, foto borrada) jogue
            # os pesos longe demais em CPU, onde nao da para repetir o treino barato.
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), max_norm=5.0)
            otimizador.step()
            if escalonador is not None:
                escalonador.step()
        else:
            with torch.inference_mode():
                saida = modelo(x)
                perda = criterio(saida, y)

        lote = y.size(0)
        perda_total += float(perda.detach()) * lote
        vistos += lote
        reais.extend(y.detach().cpu().numpy().tolist())
        preditos.extend(saida.detach().argmax(dim=1).cpu().numpy().tolist())

        if hasattr(barra, "set_postfix"):
            barra.set_postfix(perda=f"{perda_total / max(1, vistos):.4f}")

    r = np.asarray(reais, dtype=np.int64)
    p = np.asarray(preditos, dtype=np.int64)
    mc = matriz_confusao(r, p)

    return {
        "perda": perda_total / max(1, vistos),
        "acuracia": float((r == p).mean()) if len(r) else 0.0,
        "macro_f1": macro_f1(mc),
        "ok_ng": acuracia_ok_ng(r, p),
        "matriz": mc,
        "n": int(len(r)),
    }


# ---------------------------------------------------------------------------
# Escalonador: warmup linear + cosseno
# ---------------------------------------------------------------------------
def montar_escalonador(otimizador, lotes_por_epoca: int, epocas: int, warmup_epocas: float):
    passos_warmup = max(1, int(round(lotes_por_epoca * max(0.0, float(warmup_epocas)))))
    passos_totais = max(passos_warmup + 1, lotes_por_epoca * max(1, int(epocas)))

    aquecimento = LambdaLR(otimizador, lr_lambda=lambda passo: min(1.0, (passo + 1) / passos_warmup))
    cosseno = CosineAnnealingLR(otimizador, T_max=max(1, passos_totais - passos_warmup))
    return SequentialLR(otimizador, schedulers=[aquecimento, cosseno], milestones=[passos_warmup])


# ---------------------------------------------------------------------------
# Impressao
# ---------------------------------------------------------------------------
def _hms(segundos: float) -> str:
    segundos = int(max(0, segundos))
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _imprimir_cabecalho(cfg, args, dispositivo, threads, modelo, tamanhos: dict) -> None:
    par = contar_parametros(modelo)
    print("-" * 74)
    print(f"  Backbone ......... {args.backbone}")
    print(f"  Parametros ....... {par['total']:,} ({par['treinaveis']:,} treinaveis)".replace(",", "."))
    print(f"  Dispositivo ...... {dispositivo} ({threads} threads)")
    print(f"  Imagens .......... treino {tamanhos['treino']} | validacao {tamanhos['validacao']} | teste {tamanhos['teste']}")
    print(f"  Epocas ........... {args.epocas}   batch {args.batch_size}   lr {args.lr}")
    print(f"  Pesos por classe . {'sim' if cfg.treino.pesos_por_classe else 'nao'}")
    print(f"  Saida ............ {args.saida}")
    print("-" * 74)


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def montar_parser(cfg) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="02_treinar",
        description="Treina a CNN de deteccao de falhas de costura.",
    )
    p.add_argument("--backbone", default=str(cfg.treino.backbone),
                   help="mobilenet_v3_small | mobilenet_v3_large | resnet18")
    p.add_argument("--epocas", type=int, default=int(cfg.treino.epocas))
    p.add_argument("--batch-size", type=int, default=int(cfg.treino.batch_size))
    p.add_argument("--lr", type=float, default=float(cfg.treino.lr))
    p.add_argument("--workers", type=int, default=int(cfg.treino.workers))
    p.add_argument("--limite-por-classe", type=int, default=None,
                   help="usa no maximo N imagens por classe (treino de demonstracao)")
    p.add_argument("--saida", default=str(cfg.treino.saida))
    p.add_argument("--sem-pretrained", action="store_true",
                   help="nao baixa os pesos ImageNet (util offline)")
    return p


def main(argv=None) -> None:
    cfg = carregar_config()
    args = montar_parser(cfg).parse_args(argv)

    semente = int(getattr(cfg.treino, "seed", None) or cfg.divisao.semente)
    fixar_semente(semente)
    threads = ajustar_threads()
    dispositivo = resolver_dispositivo(str(cfg.inferencia.dispositivo))

    # construir_dataloaders le batch_size/workers do cfg: refletimos os argumentos
    # de linha de comando no cfg em memoria antes de chamar.
    cfg.treino["batch_size"] = int(args.batch_size)
    cfg.treino["workers"] = max(0, int(args.workers))

    dados = construir_dataloaders(cfg, limite_por_classe=args.limite_por_classe)
    loader_treino = dados["treino"]
    loader_val = dados["validacao"]
    tamanhos = {
        "treino": len(loader_treino.dataset),
        "validacao": len(loader_val.dataset),
        "teste": len(dados["teste"].dataset),
    }
    if tamanhos["treino"] == 0:
        raise SystemExit("[erro] o split de treino ficou vazio. Rode scripts/01_preparar_dados.py.")

    modelo = criar_modelo(args.backbone, NUM_CLASSES, pretrained=not args.sem_pretrained)
    modelo.to(dispositivo)
    _imprimir_cabecalho(cfg, args, dispositivo, threads, modelo, tamanhos)

    pesos = dados["pesos_classe"].to(dispositivo) if cfg.treino.pesos_por_classe else None
    criterio = nn.CrossEntropyLoss(
        weight=pesos,
        label_smoothing=float(cfg.treino.label_smoothing),
    )
    otimizador = AdamW(
        modelo.parameters(),
        lr=float(args.lr),
        weight_decay=float(cfg.treino.weight_decay),
    )
    escalonador = montar_escalonador(
        otimizador, max(1, len(loader_treino)), args.epocas, cfg.treino.warmup_epocas
    )

    historico: list[dict] = []
    melhor_f1 = -1.0
    melhor_epoca = 0
    paciencia = int(cfg.treino.early_stopping_paciencia)
    sem_melhora = 0
    inicio = time.time()

    for epoca in range(1, int(args.epocas) + 1):
        t0 = time.time()
        tr = rodar_epoca(
            modelo, loader_treino, criterio, dispositivo,
            otimizador=otimizador, escalonador=escalonador,
            descricao=f"epoca {epoca}/{args.epocas} treino",
        )
        val = rodar_epoca(
            modelo, loader_val, criterio, dispositivo,
            descricao=f"epoca {epoca}/{args.epocas} validacao",
        )
        segundos = time.time() - t0
        lr_atual = float(otimizador.param_groups[0]["lr"])

        historico.append({
            "epoca": epoca,
            "perda_treino": round(tr["perda"], 5),
            "perda_val": round(val["perda"], 5),
            "acc_val": round(val["acuracia"], 5),
            "f1_val": round(val["macro_f1"], 5),
            "ok_ng_val": round(val["ok_ng"], 5),
            "lr": lr_atual,
            "segundos": round(segundos, 1),
        })

        restantes = int(args.epocas) - epoca
        eta = _hms(segundos * restantes) if restantes else "-"
        marca = ""
        if val["macro_f1"] > melhor_f1:
            melhor_f1 = val["macro_f1"]
            melhor_epoca = epoca
            sem_melhora = 0
            marca = "  <- melhor"
            salvar_checkpoint(modelo, args.saida, {
                "backbone": args.backbone,
                "num_classes": NUM_CLASSES,
                "classes": list(CLASS_KEYS),
                "tamanho_imagem": int(cfg.dados.tamanho_imagem),
                "criado_em": datetime.now().isoformat(timespec="seconds"),
                "metricas": {
                    "epoca": epoca,
                    "acuracia_val": round(val["acuracia"], 4),
                    "macro_f1_val": round(val["macro_f1"], 4),
                    "ok_ng_val": round(val["ok_ng"], 4),
                    "perda_val": round(val["perda"], 4),
                },
                "treino": {
                    "epocas_pedidas": int(args.epocas),
                    "batch_size": int(args.batch_size),
                    "lr": float(args.lr),
                    "limite_por_classe": args.limite_por_classe,
                    "imagens_treino": tamanhos["treino"],
                },
            })
        else:
            sem_melhora += 1

        print(
            f"  epoca {epoca:>2}/{args.epocas}  "
            f"perda {tr['perda']:.4f}/{val['perda']:.4f}  "
            f"acc {val['acuracia']*100:5.2f}%  "
            f"F1 {val['macro_f1']*100:5.2f}%  "
            f"OK/NG {val['ok_ng']*100:5.2f}%  "
            f"lr {lr_atual:.2e}  {_hms(segundos)}  ETA {eta}{marca}"
        )

        # Grava o historico a cada epoca: um Ctrl+C no meio nao perde o grafico.
        try:
            destino_hist = Path(cfg.treino.historico)
            garantir_pasta(destino_hist.parent)
            destino_hist.write_text(
                json.dumps({
                    "backbone": args.backbone,
                    "epocas": historico,
                    "melhor_epoca": melhor_epoca,
                    "melhor_f1": round(melhor_f1, 5),
                    "imagens": tamanhos,
                    "atualizado_em": datetime.now().isoformat(timespec="seconds"),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover
            print(f"  [aviso] nao consegui gravar o historico: {exc}")

        if paciencia > 0 and sem_melhora >= paciencia:
            print(f"\n[!] {paciencia} epocas sem melhora no macro-F1. Parando cedo.")
            break

    total = time.time() - inicio
    print("-" * 74)
    print(f"  Treino concluido em {_hms(total)}.")
    if melhor_epoca:
        print(f"  Melhor epoca: {melhor_epoca}  (macro-F1 de validacao {melhor_f1*100:.2f}%)")
        print(f"  Checkpoint salvo em: {args.saida}")
        print(f"  Historico salvo em : {cfg.treino.historico}")
        print()
        print("  Proximo passo:  python scripts/03_avaliar.py")
    else:
        print("  [!] Nenhuma epoca melhorou o macro-F1 - nenhum checkpoint foi salvo.")
    print("-" * 74)


if __name__ == "__main__":
    # No Windows o DataLoader com workers > 0 exige este guard.
    sys.exit(main())
