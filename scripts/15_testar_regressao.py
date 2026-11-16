"""Executa os testes Python com o caminho src configurado, sem alterar a base local."""
from pathlib import Path
import sys
import unittest
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py'))
    raise SystemExit(0 if result.wasSuccessful() else 1)
