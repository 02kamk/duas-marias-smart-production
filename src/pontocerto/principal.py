"""Entrada única do sistema Ponto Certo: inspeção + lotes, sempre com login.

Use `python scripts/rodar.py` (ou o atalho `Iniciar.ps1` no Windows).
"""
from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from typing import Any


def criar_app_completo(cfg: Any = None, root=None, admins=None):
    """Monta inspeção, lotes e login numa aplicação só."""
    from fastapi.responses import RedirectResponse

    from pontocerto.app.operational import extend as com_login
    from pontocerto.app.server import criar_app
    from pontocerto.config import credenciais_supabase

    app = criar_app(cfg)

    # A antiga tela de Gestão (React) saiu: os lotes ficam na própria inspeção.
    @app.get("/gestao", include_in_schema=False)
    @app.get("/gestao/", include_in_schema=False)
    def antiga_gestao():
        return RedirectResponse("/#lotes", status_code=307)

    # Com SUPABASE_URL e SUPABASE_SECRET_KEY no .env, as contas ficam no Supabase Auth.
    if root is not None:  # testes: contas e sessões numa pasta temporária
        return com_login(app, root, supabase=credenciais_supabase(), admins=admins)
    return com_login(app, supabase=credenciais_supabase())


def _ip_local() -> str | None:
    """IP desta máquina na rede local, para abrir pelo celular."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def main(argv: list[str] | None = None) -> None:
    from pontocerto.config import carregar_config

    cfg = carregar_config()
    parser = argparse.ArgumentParser(prog="rodar", description="Sobe o sistema Ponto Certo.")
    parser.add_argument("--porta", type=int, default=int(cfg.app.get("porta", 8000)),
                        help="porta TCP (padrão: %(default)s)")
    parser.add_argument("--rede", action="store_true",
                        help="aceita conexões de outros aparelhos da rede (celular, tablet)")
    parser.add_argument("--abrir", action="store_true", help="abre o navegador quando o servidor subir")
    parser.add_argument("--recarregar", action="store_true",
                        help="reinicia sozinho quando o código muda (desenvolvimento)")
    args = parser.parse_args(argv)

    host = "0.0.0.0" if args.rede else "127.0.0.1"
    endereco = f"http://127.0.0.1:{args.porta}/login"
    print(f"\n  Ponto Certo: abra {endereco}", flush=True)
    if args.rede:
        ip = _ip_local()
        if ip:
            print(f"  Pelo celular (mesma rede Wi-Fi): http://{ip}:{args.porta}/login", flush=True)
            print("  Pelo celular, use 'Fotografar'. A câmera ao vivo do celular exige HTTPS.", flush=True)
    print("  Mantenha esta janela aberta. Ctrl+C encerra.\n", flush=True)

    if args.abrir:
        threading.Timer(2.5, lambda: webbrowser.open(endereco)).start()

    import uvicorn

    if args.recarregar:
        uvicorn.run("pontocerto.principal:criar_app_completo", factory=True,
                    host=host, port=args.porta, reload=True)
    else:
        uvicorn.run(criar_app_completo(cfg), host=host, port=args.porta, log_level="info")


if __name__ == "__main__":
    main()
