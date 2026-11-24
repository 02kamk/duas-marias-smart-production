"""Entrada da Vercel: o Ponto Certo online.

Na Vercel não há disco permanente nem tarefa de fundo, então o modo online
(PONTOCERTO_NUVEM=1) guarda histórico, sessões, ajustes e fotos no Supabase.
No computador, continue usando Iniciar.ps1 / scripts/rodar.py.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
os.environ.setdefault("PONTOCERTO_NUVEM", "1")

from pontocerto.principal import criar_app_completo  # noqa: E402

app = criar_app_completo()
