"""Sobe o sistema Ponto Certo (inspeção + gestão, com login).

Uso:
    python scripts/rodar.py                 # só neste computador
    python scripts/rodar.py --rede          # também pelo celular na mesma rede
    python scripts/rodar.py --porta 8080
    python scripts/rodar.py --abrir         # abre o navegador sozinho

No Windows, o atalho Iniciar.ps1 faz tudo isso.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    try:
        from pontocerto.principal import main as rodar
    except ImportError as exc:
        print(f"[erro] {exc}")
        print("Instale as dependências com 'pip install -r requirements.txt' e ative o .venv.")
        print("Para um diagnóstico completo: python scripts/verificar_ambiente.py")
        return 1
    try:
        rodar(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n[ok] Servidor encerrado.")
    except OSError as exc:
        print(f"\n[erro] Não consegui subir o servidor: {exc}")
        print("       Se a porta está em uso, o sistema já está aberto em outra janela.")
        print("       Feche a outra janela ou use: python scripts/rodar.py --porta 8080")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
