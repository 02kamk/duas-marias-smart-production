import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


class ReviewRule(unittest.TestCase):
    def test_only_defects_and_uncertain_readings_need_review(self):
        from pontocerto.app.state import Evento
        base=dict(id='x',timestamp=0,hora='00:00:00',classe_idx=0,nome='',gravidade='baixa')
        self.assertFalse(Evento(classe_key='normal',confianca=.95,**base).precisa_revisao)
        self.assertTrue(Evento(classe_key='normal',confianca=.40,**base).precisa_revisao)
        self.assertTrue(Evento(classe_key='crooked_seam',confianca=.95,**base).precisa_revisao)
        self.assertFalse(Evento(classe_key='crooked_seam',confianca=.95,revisao_humana={'decisao':'confirmada'},**base).precisa_revisao)



class AccountsTest(unittest.TestCase):
    def test_reset_password_ends_sessions_and_keeps_policy(self):
        from fastapi import HTTPException
        from pontocerto.app.auth import Accounts, Credentials
        with tempfile.TemporaryDirectory() as tmp:
            contas = Accounts(Path(tmp) / 'a.sqlite3')
            contas.register(Credentials(email='ana@example.com', password='Senha@123'))
            token = contas.login(Credentials(email='ana@example.com', password='Senha@123'), '1.1.1.1')
            contas.redefinir(Credentials(email='ana@example.com', password='Nova@4567'))
            self.assertIsNone(contas.user(token))
            self.assertTrue(contas.login(Credentials(email='ana@example.com', password='Nova@4567'), '1.1.1.1'))
            with self.assertRaises(HTTPException):
                contas.redefinir(Credentials(email='ana@example.com', password='fraca'))
            with self.assertRaises(HTTPException):
                contas.redefinir(Credentials(email='ninguem@example.com', password='Nova@4567'))
            self.assertEqual(contas.emails(), ['ana@example.com'])

    def test_remove_account_keeps_own_access_and_ends_sessions(self):
        from fastapi import HTTPException
        from pontocerto.app.auth import Accounts, Credentials
        with tempfile.TemporaryDirectory() as tmp:
            contas = Accounts(Path(tmp) / 'a.sqlite3')
            contas.register(Credentials(email='ana@example.com', password='Senha@123'))
            contas.register(Credentials(email='bia@example.com', password='Senha@123'))
            token = contas.login(Credentials(email='bia@example.com', password='Senha@123'), '1.1.1.1')
            # Ninguém remove a própria conta, então sempre sobra alguém com acesso.
            with self.assertRaises(HTTPException):
                contas.remover('Ana@Example.com', 'ana@example.com')
            with self.assertRaises(HTTPException):
                contas.remover('ninguem@example.com', 'ana@example.com')
            self.assertEqual(contas.remover('bia@example.com', 'ana@example.com'), 'bia@example.com')
            self.assertIsNone(contas.user(token))
            self.assertEqual(contas.emails(), ['ana@example.com'])
