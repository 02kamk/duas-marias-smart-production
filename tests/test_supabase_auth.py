"""Login com contas no Supabase Auth, contra um GoTrue falso (httpx.MockTransport)."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pontocerto.app.auth import secure

CHAVE = 'sb_secret_teste'


class GoTrueFalso:
    def __init__(self):
        self.usuarios = {}      # id -> {email, password}
        self.tokens = {}        # access_token de recuperação -> id
        self.recuperacoes = []  # (email, redirect_to)
        self.offline = False

    def __call__(self, req: httpx.Request):
        if self.offline:
            raise httpx.ConnectError('sem rede')
        caminho = req.url.path.removeprefix('/auth/v1')
        corpo = json.loads(req.content) if req.content else {}
        bearer = req.headers.get('authorization', '').removeprefix('Bearer ')
        if req.headers.get('apikey') != CHAVE:
            return httpx.Response(401, json={'message': 'Invalid API key'})
        admin = bearer == CHAVE
        if caminho == '/token' and req.method == 'POST':
            ok = any(u['email'] == corpo['email'] and u['password'] == corpo['password'] for u in self.usuarios.values())
            return httpx.Response(200, json={'access_token': 'x'}) if ok else \
                httpx.Response(400, json={'error_code': 'invalid_credentials', 'msg': 'Invalid login credentials'})
        if caminho == '/admin/users' and admin:
            if req.method == 'GET':
                pagina, por = int(req.url.params['page']), int(req.url.params['per_page'])
                todos = [{'id': i, 'email': u['email'], 'user_metadata': u.get('meta', {}), 'app_metadata': u.get('app', {})}
                         for i, u in self.usuarios.items()]
                return httpx.Response(200, json={'users': todos[(pagina-1)*por:pagina*por]})
            if any(u['email'] == corpo['email'] for u in self.usuarios.values()):
                return httpx.Response(422, json={'error_code': 'email_exists', 'msg': 'already registered'})
            uid = str(uuid.uuid4())
            self.usuarios[uid] = {'email': corpo['email'], 'password': corpo['password'], 'app': corpo.get('app_metadata', {})}
            return httpx.Response(200, json={'id': uid})
        if caminho.startswith('/admin/users/') and admin:
            uid = caminho.rsplit('/', 1)[1]
            if req.method == 'PUT':
                if 'password' in corpo:
                    self.usuarios[uid]['password'] = corpo['password']
                if 'user_metadata' in corpo:
                    self.usuarios[uid]['meta'] = corpo['user_metadata']
                if 'app_metadata' in corpo:
                    self.usuarios[uid]['app'] = corpo['app_metadata']
            else:
                del self.usuarios[uid]
            return httpx.Response(200, json={})
        if caminho == '/recover':
            self.recuperacoes.append((corpo['email'], req.url.params.get('redirect_to')))
            for uid, u in self.usuarios.items():
                if u['email'] == corpo['email']:
                    self.tokens['tok-' + uid] = uid
            return httpx.Response(200, json={})
        if caminho == '/user' and req.method == 'PUT':
            uid = self.tokens.pop(bearer, None)
            if not uid:
                return httpx.Response(401, json={'msg': 'invalid JWT'})
            self.usuarios[uid]['password'] = corpo['password']
            return httpx.Response(200, json={'email': self.usuarios[uid]['email']})
        return httpx.Response(404)


class SupabaseAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gotrue = GoTrueFalso()
        app = FastAPI()

        @app.get('/api/privado')
        def privado():
            return {'ok': True}
        secure(app, Path(self.tmp.name), admins=[], supabase={'url': 'https://proj.supabase.co', 'secret_key': CHAVE},
               transport=httpx.MockTransport(self.gotrue))
        self.c = TestClient(app)

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def test_cadastro_login_e_contas(self):
        c = self.c
        self.assertEqual(c.get('/api/auth/status').json(), {'user': None, 'recuperacao': True})
        ana = {'email': 'Ana@Example.com', 'password': 'Senha@123'}
        self.assertEqual(c.post('/api/auth/register', json=ana).status_code, 201)
        self.assertEqual([u['email'] for u in self.gotrue.usuarios.values()], ['ana@example.com'])
        # Cadastro aberto na tela de entrar: qualquer pessoa cria a própria conta, sem sessão.
        self.assertEqual(c.post('/api/auth/register', json={'email': 'cris@example.com', 'password': 'Senha@123'}).status_code, 201)
        self.assertEqual(c.post('/api/auth/register', json={'email': 'cris@example.com', 'password': 'Senha@123'}).status_code, 409)
        self.assertEqual(c.get('/api/privado').status_code, 401)
        self.assertEqual(c.post('/api/auth/login', json={**ana, 'password': 'Errada@123'}).status_code, 401)
        self.assertEqual(c.post('/api/auth/login', json=ana).status_code, 200)
        self.assertEqual(c.get('/api/privado').status_code, 200)

        bia = {'email': 'bia@example.com', 'password': 'Senha@123'}
        self.assertEqual(c.post('/api/auth/register', json=bia).status_code, 201)
        self.assertEqual(c.post('/api/auth/register', json=bia).status_code, 409)
        self.assertEqual(c.get('/api/auth/users').json()['users'], ['ana@example.com', 'bia@example.com', 'cris@example.com'])
        self.assertEqual(c.post('/api/auth/password', json={**bia, 'password': 'Nova@4567'}).status_code, 200)
        self.assertEqual(c.post('/api/auth/password', json={'email': 'ninguem@example.com', 'password': 'Nova@4567'}).status_code, 404)
        self.assertEqual(c.post('/api/auth/remove', json={'email': 'ana@example.com'}).status_code, 409)
        self.assertEqual(c.post('/api/auth/remove', json={'email': 'bia@example.com'}).status_code, 200)
        self.assertEqual(c.get('/api/auth/users').json()['users'], ['ana@example.com', 'cris@example.com'])

    def test_esqueci_a_senha_pelo_link(self):
        c = self.c
        ana = {'email': 'ana@example.com', 'password': 'Senha@123'}
        c.post('/api/auth/register', json=ana)
        c.post('/api/auth/login', json=ana)
        self.assertEqual(c.get('/api/privado').status_code, 200)
        # A resposta é a mesma com ou sem conta, para não revelar quem tem acesso.
        self.assertEqual(c.post('/api/auth/esqueci', json={'email': 'ana@example.com'}).json(), {'ok': True})
        self.assertEqual(c.post('/api/auth/esqueci', json={'email': 'ninguem@example.com'}).json(), {'ok': True})
        self.assertEqual(self.gotrue.recuperacoes[0], ('ana@example.com', 'http://testserver/redefinir-senha'))
        self.assertEqual(c.get('/redefinir-senha').status_code, 200)

        token = next(iter(self.gotrue.tokens))
        self.assertEqual(c.post('/api/auth/nova-senha', json={'access_token': token, 'password': 'fraca'}).status_code, 422)
        r = c.post('/api/auth/nova-senha', json={'access_token': token, 'password': 'Nova@4567'})
        self.assertEqual(r.status_code, 200)
        # Trocar a senha pelo link encerra as sessões abertas da conta.
        self.assertEqual(c.get('/api/privado').status_code, 401)
        self.assertEqual(c.post('/api/auth/nova-senha', json={'access_token': token, 'password': 'Outra@4567'}).status_code, 401)
        self.assertEqual(c.post('/api/auth/login', json={**ana, 'password': 'Nova@4567'}).status_code, 200)

    def test_sem_internet_avisa_e_sessao_aberta_continua(self):
        c = self.c
        ana = {'email': 'ana@example.com', 'password': 'Senha@123'}
        c.post('/api/auth/register', json=ana)
        c.post('/api/auth/login', json=ana)
        self.gotrue.offline = True
        self.assertEqual(c.get('/api/privado').status_code, 200)
        r = c.post('/api/auth/login', json=ana)
        self.assertEqual(r.status_code, 503)
        self.assertIn('Sem conexão', r.json()['detail'])

    def test_chave_errada_avisa_sem_vazar_a_chave(self):
        app = FastAPI()
        secure(app, Path(self.tmp.name) / 'outra', admins=[], supabase={'url': 'https://proj.supabase.co', 'secret_key': 'sb_secret_errada'},
               transport=httpx.MockTransport(self.gotrue))
        with TestClient(app) as c:
            r = c.post('/api/auth/login', json={'email': 'ana@example.com', 'password': 'Senha@123'})
        self.assertEqual(r.status_code, 503)
        self.assertIn('SUPABASE_SECRET_KEY', r.json()['detail'])
        self.assertNotIn('sb_secret_errada', r.text)


FOTO = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='


def _testar_perfil(teste, c):
    ana = {'email': 'ana@example.com', 'password': 'Senha@123'}
    c.post('/api/auth/register', json=ana)
    teste.assertEqual(c.get('/api/perfil').status_code, 401)
    c.post('/api/auth/login', json=ana)
    teste.assertEqual(c.get('/api/perfil').json(), {'email': 'ana@example.com', 'nome': '', 'avatar': None, 'admin': True})
    salvo = c.post('/api/perfil', json={'nome': '  Ana   Souza ', 'avatar': FOTO}).json()
    teste.assertEqual((salvo['nome'], salvo['avatar']), ('Ana Souza', FOTO))
    teste.assertEqual(c.get('/api/perfil').json()['nome'], 'Ana Souza')
    teste.assertEqual(c.post('/api/perfil', json={'nome': 'Ana', 'avatar': 'data:image/png;base64,naoeimagem'}).status_code, 422)
    teste.assertEqual(c.post('/api/perfil', json={'nome': 'Ana', 'avatar': 'https://exemplo.com/a.png'}).status_code, 422)
    teste.assertIsNone(c.post('/api/perfil', json={'nome': 'Ana', 'avatar': None}).json()['avatar'])
    # Trocar a própria senha pede a atual e mantém esta sessão aberta.
    teste.assertEqual(c.post('/api/perfil/senha', json={'atual': 'Errada@1', 'nova': 'Nova@4567'}).status_code, 400)
    teste.assertEqual(c.post('/api/perfil/senha', json={'atual': 'Senha@123', 'nova': 'fraca'}).status_code, 422)
    teste.assertEqual(c.post('/api/perfil/senha', json={'atual': 'Senha@123', 'nova': 'Nova@4567'}).status_code, 200)
    teste.assertEqual(c.get('/api/perfil').status_code, 200)
    c.post('/api/auth/logout')
    teste.assertEqual(c.post('/api/auth/login', json=ana).status_code, 401)
    teste.assertEqual(c.post('/api/auth/login', json={**ana, 'password': 'Nova@4567'}).status_code, 200)


class PerfilTest(unittest.TestCase):
    def test_perfil_com_supabase_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            secure(app, Path(tmp), admins=[], supabase={'url': 'https://proj.supabase.co', 'secret_key': CHAVE},
                   transport=httpx.MockTransport(GoTrueFalso()))
            with TestClient(app) as c:
                _testar_perfil(self, c)

    def test_perfil_com_contas_locais(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            secure(app, Path(tmp), admins=[])
            with TestClient(app) as c:
                _testar_perfil(self, c)


def _testar_aprovacao(teste, c):
    chefe = {'email': 'chefe@example.com', 'password': 'Chefe@123'}
    maria = {'email': 'maria@example.com', 'password': 'Maria@123'}
    # Quem não é administrador cria a conta, mas só entra depois de aprovada.
    teste.assertEqual(c.post('/api/auth/register', json=maria).json(), {'email': 'maria@example.com', 'pendente': True})
    r = c.post('/api/auth/login', json=maria)
    teste.assertEqual(r.status_code, 403)
    teste.assertIn('aprovação', r.json()['detail'])
    teste.assertEqual(c.post('/api/auth/register', json=chefe).json()['pendente'], False)
    c.post('/api/auth/login', json=chefe)
    d = c.get('/api/auth/users').json()
    teste.assertTrue(d['admin'])
    teste.assertEqual({x['email']: x['aprovado'] for x in d['contas']}, {'chefe@example.com': True, 'maria@example.com': False})
    teste.assertEqual(c.post('/api/auth/aprovar', json={'email': 'maria@example.com'}).status_code, 200)
    c.post('/api/auth/logout')
    teste.assertEqual(c.post('/api/auth/login', json=maria).status_code, 200)
    # Maria não é administradora: não aprova, não remove nem redefine senha de outros.
    teste.assertFalse(c.get('/api/auth/users').json()['admin'])
    teste.assertEqual(c.post('/api/auth/aprovar', json={'email': 'chefe@example.com'}).status_code, 403)
    teste.assertEqual(c.post('/api/auth/remove', json={'email': 'chefe@example.com'}).status_code, 403)
    teste.assertEqual(c.post('/api/auth/password', json={'email': 'chefe@example.com', 'password': 'Nova@4567'}).status_code, 403)


class AprovacaoTest(unittest.TestCase):
    def test_aprovacao_com_supabase_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            secure(app, Path(tmp), admins=['Chefe@example.com'], supabase={'url': 'https://proj.supabase.co', 'secret_key': CHAVE},
                   transport=httpx.MockTransport(GoTrueFalso()))
            with TestClient(app) as c:
                _testar_aprovacao(self, c)

    def test_aprovacao_com_contas_locais(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            secure(app, Path(tmp), admins=['chefe@example.com'])
            with TestClient(app) as c:
                _testar_aprovacao(self, c)


class SemSupabaseTest(unittest.TestCase):
    def test_contas_locais_nao_oferecem_link_por_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            secure(app, Path(tmp), admins=[])
            with TestClient(app) as c:
                self.assertFalse(c.get('/api/auth/status').json()['recuperacao'])
                self.assertEqual(c.post('/api/auth/esqueci', json={'email': 'ana@example.com'}).status_code, 501)


if __name__ == '__main__':
    unittest.main()
