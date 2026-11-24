"""Redefine a senha de uma conta do sistema (quando alguém esquece a senha).

Uso:
    python scripts/redefinir_senha.py pessoa@empresa.com.br

A nova senha é pedida no terminal, sem aparecer na tela. As sessões abertas
dessa conta são encerradas.
"""
from __future__ import annotations

import getpass
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))


def main() -> int:
    from fastapi import HTTPException
    from pontocerto.app.auth import Accounts, Credentials

    contas = Accounts(RAIZ / "artifacts" / "local" / "accounts.sqlite3")
    if len(sys.argv) < 2:
        print(__doc__)
        print("Contas cadastradas:", ", ".join(contas.emails()) or "nenhuma")
        return 1
    email = sys.argv[1]
    senha = getpass.getpass("Nova senha: ")
    if senha != getpass.getpass("Repita a nova senha: "):
        print("[erro] As senhas não conferem.")
        return 1
    try:
        contas.redefinir(Credentials(email=email, password=senha))
    except HTTPException as exc:
        print(f"[erro] {exc.detail}")
        return 1
    print(f"[ok] Senha de {email} redefinida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
