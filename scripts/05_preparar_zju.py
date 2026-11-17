"""Ponto Certo - etapa 05: recortes do ZJU-Leaper (defeitos de tecido).

O ZJU-Leaper (Zhang et al., IEEE TAI 2020, CC BY-NC-SA 4.0, uso acadêmico) tem
fotos 512x512 de 19 padrões de tecido, marcadas só como "com defeito" ou "sem
defeito". O defeito costuma ocupar menos de 1% da foto, então reduzir a foto
inteira para 224 o apagaria. Este script:

  1. sorteia, por padrão de tecido, N fotos com defeito e M sem defeito;
  2. extrai só essas fotos (e os XML com a caixa do defeito) do arquivo .7z;
  3. grava recortes 224x224 no tamanho original:
       - com defeito: centrado na caixa do defeito, com um deslocamento aleatório;
       - sem defeito: em posição aleatória;
  4. salva em <destino>/Z. ZJU-Leaper/{0. Normal, 11. Fabric defect}/,
     no mesmo formato de pastas do StitchingNet, para a etapa 01 achar sozinha.

Uso:
    python scripts/05_preparar_zju.py --arquivo dados/zju-leaper/zju-leaper.zip
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from pontocerto.labels import class_by_key, fabric_by_letter  # noqa: E402

SETE_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")
LADO = 224


def extrair(arquivo: Path, destino: Path, caminhos: list[str]) -> None:
    """Extrai só os caminhos pedidos do .7z (via arquivo de lista)."""
    exe = str(SETE_ZIP) if SETE_ZIP.exists() else (shutil.which("7z") or "7z")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as lista:
        lista.write("\n".join(caminhos))
    try:
        subprocess.run([exe, "x", "-y", "-bso0", "-bsp0", str(arquivo), f"-o{destino}", f"@{lista.name}"],
                       check=True)
    finally:
        Path(lista.name).unlink(missing_ok=True)


def caixa(xml: Path) -> tuple[int, int, int, int] | None:
    raiz = ET.parse(xml).getroot()
    bb = raiz.find("bbox")
    if bb is None:
        return None
    return tuple(int(float(bb.findtext(k))) for k in ("xmin", "ymin", "xmax", "ymax"))  # type: ignore[return-value]


def recorte(img: Image.Image, cx: int, cy: int, rng: random.Random, jitter: int) -> Image.Image:
    w, h = img.size
    cx += rng.randint(-jitter, jitter)
    cy += rng.randint(-jitter, jitter)
    x0 = min(max(cx - LADO // 2, 0), w - LADO)
    y0 = min(max(cy - LADO // 2, 0), h - LADO)
    return img.crop((x0, y0, x0 + LADO, y0 + LADO))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", type=Path, default=RAIZ / "dados/zju-leaper/zju-leaper.zip")
    p.add_argument("--destino", type=Path, default=RAIZ / "dados/treino")
    p.add_argument("--defeitos-por-padrao", type=int, default=160)
    p.add_argument("--normais-por-padrao", type=int, default=80)
    p.add_argument("--semente", type=int, default=42)
    a = p.parse_args(argv)

    rng = random.Random(a.semente)
    trabalho = a.arquivo.parent / "extraido"
    padroes_dir = trabalho / "ZJU-Leaper/ImageSets/Patterns"
    if not padroes_dir.is_dir():
        extrair(a.arquivo, trabalho, ["ZJU-Leaper/ImageSets/Patterns/*"])

    # 1. Sorteio por padrão (treino e teste do ZJU juntos; a etapa 01 refaz a divisão)
    escolhidos: list[tuple[str, str]] = []  # (id, "defect" | "normal")
    for arq in sorted(padroes_dir.glob("pattern*.json"), key=lambda x: int(x.stem[7:])):
        dados = json.loads(arq.read_text(encoding="utf-8"))
        for tipo, n in (("defect", a.defeitos_por_padrao), ("normal", a.normais_por_padrao)):
            ids = sorted(set(dados[tipo]["train"]) | set(dados[tipo]["test"]))
            escolhidos += [(i, tipo) for i in rng.sample(ids, min(n, len(ids)))]
    print(f"[..] {len(escolhidos)} fotos sorteadas; extraindo do arquivo...")

    caminhos = [f"ZJU-Leaper/Images/{i}.jpg" for i, _ in escolhidos]
    caminhos += [f"ZJU-Leaper/Annotations/xmls/{i}.xml" for i, t in escolhidos if t == "defect"]
    extrair(a.arquivo, trabalho, caminhos)

    # 2. Recortes
    tecido = fabric_by_letter("Z").folder
    pastas = {"normal": class_by_key("normal"), "defect": class_by_key("fabric_defect")}
    for info in pastas.values():
        pasta = a.destino / tecido / info.folder
        if pasta.exists():
            shutil.rmtree(pasta)
        pasta.mkdir(parents=True)

    contagem = {"normal": 0, "defect": 0}
    sem_caixa = 0
    for i, tipo in escolhidos:
        img = Image.open(trabalho / f"ZJU-Leaper/Images/{i}.jpg").convert("RGB")
        if tipo == "defect":
            bb = caixa(trabalho / f"ZJU-Leaper/Annotations/xmls/{i}.xml")
            if bb is None:
                sem_caixa += 1
                continue
            cx, cy = (bb[0] + bb[2]) // 2, (bb[1] + bb[3]) // 2
            # Deslocamento pequeno: o defeito nunca sai do recorte.
            peca = recorte(img, cx, cy, rng, jitter=48)
        else:
            w, h = img.size
            peca = recorte(img, rng.randint(LADO // 2, w - LADO // 2), rng.randint(LADO // 2, h - LADO // 2), rng, 0)
        info = pastas[tipo]
        contagem[tipo] += 1
        nome = f"Z_{info.index:02d}_{contagem[tipo]:04d}.jpg"
        peca.save(a.destino / tecido / info.folder / nome, quality=95)

    print(f"[ok] {contagem['defect']} recortes com defeito e {contagem['normal']} sem defeito "
          f"em {a.destino / tecido}" + (f" ({sem_caixa} sem caixa ignorados)" if sem_caixa else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
