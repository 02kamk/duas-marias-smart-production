"""Ponto Certo - etapa 05: subir a aplicacao (API + interface web).

Sobe o servidor FastAPI com a interface de inspecao em
http://127.0.0.1:8000 . A camera NAO e aberta automaticamente: use o botao
"Ligar camera" na aba "Ao vivo".

Este arquivo e so o atalho de linha de comando. A logica de verdade esta em
src/pontocerto/app/server.py.

Uso:
    python scripts/05_rodar_app.py
    python scripts/05_rodar_app.py --porta 8080
    python scripts/05_rodar_app.py --host 0.0.0.0        # acessivel na rede local
    python scripts/05_rodar_app.py --recarregar          # desenvolvimento
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

CABECALHO = """
================================================================================
  PONTO CERTO  |  ETAPA 05 - RODAR A APLICACAO
  Interface de inspecao + API  |  Ctrl+C encerra
================================================================================
"""

AJUDA_IMPORT = """
Nao consegui importar 'pontocerto.app.server'.

Possiveis causas e solucoes:

  1. Dependencias faltando (fastapi, uvicorn, python-multipart, opencv-python):
         pip install -r requirements.txt

  2. Voce esta fora da pasta do projeto. Entre na pasta 'pontocerto'
     (a que contem o config.yaml) e rode de novo.

  3. O ambiente virtual nao esta ativo:
         .venv\\Scripts\\activate

Observacao: o servidor SOBE mesmo sem o modelo treinado. Ele mostra um aviso
na tela e a rota /api/saude informa o que esta faltando. Para ter veredito de
verdade, rode antes 'python scripts/02_treinar.py'.

Rode 'python scripts/00_verificar_ambiente.py' para um diagnostico completo.
"""


def main() -> int:
    print(CABECALHO)
    try:
        from pontocerto.app.server import main as etapa
    except ImportError as exc:
        print(f"[erro] {type(exc).__name__}: {exc}")
        print(AJUDA_IMPORT)
        return 1

    print("  Abra o navegador em http://127.0.0.1:8000 depois que o servidor subir.")
    print("  A camera so liga quando voce clicar em 'Ligar camera'.")
    print()

    try:
        etapa(sys.argv[1:])
    except KeyboardInterrupt:
        print()
        print("[ok] Servidor encerrado.")
        return 0
    except OSError as exc:
        print()
        print(f"[erro] Nao consegui subir o servidor: {exc}")
        print("       Se a mensagem fala em endereco/porta em uso, outra copia do")
        print("       Ponto Certo ja esta rodando. Feche a outra janela ou use")
        print("       outra porta:  python scripts/05_rodar_app.py --porta 8080")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
