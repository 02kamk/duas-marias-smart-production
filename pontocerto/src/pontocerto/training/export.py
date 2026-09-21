"""Exportacao do modelo treinado para formatos de producao.

TorchScript e o formato principal: carrega sem o codigo Python do projeto, o que
facilita levar o modelo para outra maquina da fabrica. ONNX e opcional - se o
pacote nao estiver instalado, avisamos e seguimos, porque o sistema nao depende
dele para funcionar.

    python -m pontocerto.training.export
    python -m pontocerto.training.export --modelo artifacts/modelo.pt --sem-onnx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

from pontocerto.config import carregar_config, garantir_pasta
from pontocerto.labels import CLASS_KEYS
from pontocerto.training.model import carregar_checkpoint


def exportar_torchscript(modelo, exemplo: torch.Tensor, destino: Path) -> bool:
    """Tenta trace e, se falhar, script. Devolve True se gravou o arquivo."""
    garantir_pasta(destino.parent)
    try:
        with torch.inference_mode():
            tracado = torch.jit.trace(modelo, exemplo, strict=False)
        tracado = torch.jit.freeze(tracado.eval())
        tracado.save(str(destino))
        print(f"[ok] TorchScript (trace) gravado em {destino}")
        return True
    except Exception as exc:
        print(f"[aviso] trace falhou ({type(exc).__name__}: {exc}). Tentando script...")
    try:
        script = torch.jit.script(modelo)
        script.save(str(destino))
        print(f"[ok] TorchScript (script) gravado em {destino}")
        return True
    except Exception as exc:
        print(f"[erro] nao consegui exportar TorchScript: {type(exc).__name__}: {exc}")
        return False


def exportar_onnx(modelo, exemplo: torch.Tensor, destino: Path) -> bool:
    garantir_pasta(destino.parent)
    try:
        torch.onnx.export(
            modelo,
            exemplo,
            str(destino),
            input_names=["imagem"],
            output_names=["logits"],
            dynamic_axes={"imagem": {0: "lote"}, "logits": {0: "lote"}},
            opset_version=17,
        )
        print(f"[ok] ONNX gravado em {destino}")
        return True
    except ImportError as exc:
        print(f"[aviso] ONNX indisponivel (falta dependencia): {exc}")
    except Exception as exc:
        print(f"[aviso] exportacao ONNX falhou ({type(exc).__name__}: {exc}). "
              "Isso nao impede o sistema de funcionar.")
    return False


def verificar(caminho_ts: Path, modelo, exemplo: torch.Tensor) -> None:
    """Confere que o arquivo exportado devolve a mesma saida do modelo original."""
    try:
        carregado = torch.jit.load(str(caminho_ts))
        with torch.inference_mode():
            a = modelo(exemplo)
            b = carregado(exemplo)
        diferenca = float((a - b).abs().max())
        estado = "ok" if diferenca < 1e-4 else "!"
        print(f"[{estado}] diferenca maxima entre o modelo e o TorchScript: {diferenca:.2e}")
    except Exception as exc:
        print(f"[aviso] nao consegui verificar o TorchScript: {type(exc).__name__}: {exc}")


def main(argv=None) -> None:
    cfg = carregar_config()
    p = argparse.ArgumentParser(
        prog="export",
        description="Exporta o modelo treinado para TorchScript e ONNX.",
    )
    p.add_argument("--modelo", default=str(cfg.inferencia.modelo))
    p.add_argument("--sem-onnx", action="store_true")
    args = p.parse_args(argv)

    caminho = Path(args.modelo)
    if not caminho.is_absolute():
        caminho = Path(cfg["_raiz"]) / caminho
    if not caminho.exists():
        raise SystemExit(
            f"[erro] modelo nao encontrado em {caminho}.\n"
            "       Rode primeiro:  python scripts/02_treinar.py"
        )

    modelo, meta = carregar_checkpoint(caminho, "cpu")
    modelo.eval()
    tamanho = int(meta.get("tamanho_imagem") or cfg.dados.tamanho_imagem)
    exemplo = torch.randn(1, 3, tamanho, tamanho)

    print(f"[..] backbone {meta.get('backbone')}  |  entrada 1x3x{tamanho}x{tamanho}")
    print(f"[..] classes: {', '.join(meta.get('classes') or CLASS_KEYS)}")

    base = Path(cfg["_raiz"]) / "artifacts"
    destino_ts = base / "modelo.torchscript.pt"
    if exportar_torchscript(modelo, exemplo, destino_ts):
        verificar(destino_ts, modelo, exemplo)

    if not args.sem_onnx:
        exportar_onnx(modelo, exemplo, base / "modelo.onnx")
    else:
        print("[..] ONNX pulado (--sem-onnx).")


if __name__ == "__main__":
    sys.exit(main())
