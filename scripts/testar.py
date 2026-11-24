"""Roda os testes Python com o caminho src configurado, sem alterar a base local.

Uso:
    python scripts/testar.py                # todos os testes
    python scripts/testar.py management     # só tests/test_management.py
"""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))

if __name__ == '__main__':
    padrao = f'test_{sys.argv[1]}.py' if len(sys.argv) > 1 else 'test_*.py'
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern=padrao)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
