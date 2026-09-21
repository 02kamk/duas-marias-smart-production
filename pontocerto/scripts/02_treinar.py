"""Ponto Certo - etapa 02: treino da CNN.

Treina o classificador de 11 classes a partir do manifesto artifacts/splits.csv
e grava o melhor checkpoint em artifacts/modelo.pt junto com o historico por
epoca em artifacts/historico_treino.json.

Este arquivo e so o atalho de linha de comando. A logica de verdade esta em
src/pontocerto/training/train.py.

Uso:
    python scripts/02_treinar.py
    python scripts/02_treinar.py --epocas 20 --batch-size 32
    python scripts/02_treinar.py --limite-por-classe 60     # ensaio rapido
    python scripts/02_treinar.py --backbone resnet18 --sem-pretrained

Em CPU o treino completo leva horas. Para um ensaio de poucos minutos use
--limite-por-classe 60 --epocas 2 (o resultado nao serve para producao, so
para conferir que o caminho inteiro funciona).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

CABECALHO = """
================================================================================
  PONTO CERTO  |  ETAPA 02 - TREINAR A REDE
  CNN de 11 classes  |  CPU  |  Ctrl+C interrompe sem perder o melhor checkpoint
================================================================================
"""

AJUDA_IMPORT = """
Nao consegui importar 'pontocerto.training.train'.

Possiveis causas e solucoes:

  1. Dependencias faltando (torch, torchvision, pandas, scikit-learn, tqdm):
         pip install -r requirements.txt

  2. O manifesto ainda nao foi gerado. Rode antes:
         python scripts/01_preparar_dados.py

  3. Voce esta fora da pasta do projeto. Entre na pasta 'pontocerto'
     (a que contem o config.yaml) e rode de novo.

  4. O ambiente virtual nao esta ativo:
         .venv\\Scripts\\activate

Rode 'python scripts/00_verificar_ambiente.py' para um diagnostico completo.
"""


def main() -> int:
    print(CABECALHO)
    try:
        from pontocerto.training.train import main as etapa
    except ImportError as exc:
        print(f"[erro] {type(exc).__name__}: {exc}")
        print(AJUDA_IMPORT)
        return 1

    try:
        etapa(sys.argv[1:])
    except KeyboardInterrupt:
        print()
        print("[!] Treino interrompido pelo usuario (Ctrl+C).")
        print("    O melhor checkpoint ate aqui continua em artifacts/modelo.pt.")
        return 130

    print()
    print("[ok] Etapa 02 concluida. Proximo passo: python scripts/03_avaliar.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
