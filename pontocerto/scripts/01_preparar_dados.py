"""Ponto Certo - etapa 01: preparacao dos dados.

Varre o dataset bruto (11 tecidos x 11 classes), confere a estrutura e grava o
manifesto unico do projeto em artifacts/splits.csv, ja com a divisao
estratificada por (tecido, classe) em treino 70% / validacao 15% / teste 15%.

Este arquivo e so o atalho de linha de comando. A logica de verdade esta em
src/pontocerto/data/split.py.

Uso:
    python scripts/01_preparar_dados.py
    python scripts/01_preparar_dados.py --forcar     # refaz o manifesto do zero
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

CABECALHO = """
================================================================================
  PONTO CERTO  |  ETAPA 01 - PREPARAR DADOS
  Varredura do dataset e divisao estratificada treino/validacao/teste
================================================================================
"""

AJUDA_IMPORT = """
Nao consegui importar 'pontocerto.data.split'.

Possiveis causas e solucoes:

  1. Dependencias faltando. Instale tudo com:
         pip install -r requirements.txt
     (esta etapa precisa de pandas, numpy e pyyaml)

  2. Voce esta rodando de fora da pasta do projeto. Entre na pasta 'pontocerto'
     (a que contem o config.yaml) e rode de novo:
         cd caminho\\ate\\pontocerto
         python scripts/01_preparar_dados.py

  3. O ambiente virtual nao esta ativo:
         .venv\\Scripts\\activate

Rode 'python scripts/00_verificar_ambiente.py' para um diagnostico completo.
"""


def main() -> int:
    print(CABECALHO)
    try:
        from pontocerto.data.split import main as etapa
    except ImportError as exc:
        print(f"[erro] {type(exc).__name__}: {exc}")
        print(AJUDA_IMPORT)
        return 1

    etapa(sys.argv[1:])
    print()
    print("[ok] Etapa 01 concluida. Proximo passo: python scripts/02_treinar.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
