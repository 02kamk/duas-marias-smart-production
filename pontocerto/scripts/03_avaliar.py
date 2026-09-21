"""Ponto Certo - etapa 03: avaliacao no conjunto de teste.

Roda o modelo treinado sobre o split "teste" (imagens que a rede nunca viu) e
grava em artifacts/avaliacao:

    matriz_confusao.png            matriz 11x11 com contagens
    matriz_confusao_normalizada.png  a mesma matriz em percentual por linha
    relatorio_classes.csv          precisao, revocacao e F1 por classe
    metricas.json                  acuracia, macro-F1, acuracia OK/NG, por tecido
    acertos_por_tecido.png         onde o modelo acerta mais e menos

Este arquivo e so o atalho de linha de comando. A logica de verdade esta em
src/pontocerto/training/evaluate.py.

Uso:
    python scripts/03_avaliar.py
    python scripts/03_avaliar.py --modelo artifacts/modelo.pt
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

CABECALHO = """
================================================================================
  PONTO CERTO  |  ETAPA 03 - AVALIAR
  Matriz de confusao, metricas por classe e por tecido no conjunto de teste
================================================================================
"""

AJUDA_IMPORT = """
Nao consegui importar 'pontocerto.training.evaluate'.

Possiveis causas e solucoes:

  1. Dependencias faltando (torch, scikit-learn, matplotlib, pandas):
         pip install -r requirements.txt

  2. O modelo ainda nao foi treinado. Rode antes:
         python scripts/02_treinar.py

  3. O manifesto ainda nao foi gerado:
         python scripts/01_preparar_dados.py

  4. Voce esta fora da pasta do projeto. Entre na pasta 'pontocerto'
     (a que contem o config.yaml) e rode de novo.

Rode 'python scripts/00_verificar_ambiente.py' para um diagnostico completo.
"""


def main() -> int:
    print(CABECALHO)
    try:
        from pontocerto.training.evaluate import main as etapa
    except ImportError as exc:
        print(f"[erro] {type(exc).__name__}: {exc}")
        print(AJUDA_IMPORT)
        return 1

    etapa(sys.argv[1:])
    print()
    print("[ok] Etapa 03 concluida. Graficos e metricas em artifacts/avaliacao.")
    print("     Proximo passo: python scripts/05_rodar_app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
