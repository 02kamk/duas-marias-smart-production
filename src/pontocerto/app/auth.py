"""Login com sessão opaca, cadastro aberto e contas no Supabase Auth.

Com SUPABASE_URL e SUPABASE_SECRET_KEY, as contas ficam no Supabase Auth: a
senha é conferida por ele, e "Esqueci a senha" manda o link de redefinição por
e-mail. Sem essas variáveis (e nos testes), as contas ficam no SQLite local.
Em ambos os casos a sessão do navegador é guardada no SQLite deste computador,
então quem já entrou continua usando o sistema se a internet cair.
"""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from threading import Lock
from pathlib import Path
from contextlib import contextmanager

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

COOKIE = 'dm_session'
SEM_CONEXAO = 'Sem conexão com o serviço de contas. Confira a internet e tente de novo.'


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class EmailOnly(BaseModel):
    email: str = Field(min_length=5, max_length=254)


class Perfil(BaseModel):
    nome: str = Field(default='', max_length=80)
    avatar: str | None = Field(default=None, max_length=120_000)


class TrocaSenha(BaseModel):
    atual: str = Field(min_length=1, max_length=128)
    nova: str = Field(min_length=1, max_length=128)


class NovaSenha(BaseModel):
    access_token: str = Field(min_length=10, max_length=4096)
    password: str = Field(min_length=1, max_length=128)


def _validar_avatar(avatar):
    """Aceita só uma foto pequena em data URL (JPEG/PNG/WebP) que abra de verdade."""
    if not avatar:
        return None
    import base64
    import io
    m = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)', avatar)
    if not m:
        raise HTTPException(422, 'Foto inválida. Use JPG ou PNG.')
    try:
        from PIL import Image
        bruto = base64.b64decode(m.group(2), validate=True)
        with Image.open(io.BytesIO(bruto)) as img:
            img.verify()
    except Exception:
        raise HTTPException(422, 'Não consegui abrir essa foto. Tente outra.') from None
    return avatar


def _derivar(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()


class ContasLocais:
    """Contas na tabela `users` do SQLite local (sem Supabase e nos testes)."""

    recuperacao = False

    def __init__(self, accounts):
        self.accounts = accounts

    def emails(self):
        with self.accounts.db() as db:
            return [r[0] for r in db.execute('SELECT email FROM users ORDER BY email').fetchall()]

    def contas(self):
        with self.accounts.db() as db:
            return [{'email': r[0], 'aprovado': bool(r[1])}
                    for r in db.execute('SELECT email, COALESCE(aprovado, 1) FROM users ORDER BY email').fetchall()]

    def aprovado(self, email):
        with self.accounts.db() as db:
            row = db.execute('SELECT COALESCE(aprovado, 1) FROM users WHERE email=?', (email,)).fetchone()
        return bool(row and row[0])

    def aprovar(self, email):
        with self.accounts.db() as db:
            return bool(db.execute('UPDATE users SET aprovado=1 WHERE email=?', (email,)).rowcount)

    def verificar(self, email, password):
        with self.accounts.db() as db:
            row = db.execute('SELECT salt,hash FROM users WHERE email=?', (email,)).fetchone()
        # Deriva mesmo quando a conta não existe, para o tempo de resposta não revelar quem tem conta.
        candidate = _derivar(password, row[0] if row else '00'*16)
        return bool(row) and hmac.compare_digest(candidate, row[1])

    def criar(self, email, password, aprovado=True):
        salt = secrets.token_hex(16)
        derived = _derivar(password, salt)
        with self.accounts.db() as db:
            try:
                db.execute('INSERT INTO users(email,salt,hash,aprovado) VALUES (?,?,?,?)',
                           (email, salt, derived, 1 if aprovado else 0))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Conta já cadastrada.')

    def trocar_senha(self, email, password):
        salt = secrets.token_hex(16)
        with self.accounts.db() as db:
            return bool(db.execute('UPDATE users SET salt=?, hash=? WHERE email=?',
                                   (salt, _derivar(password, salt), email)).rowcount)

    def remover(self, email):
        with self.accounts.db() as db:
            return bool(db.execute('DELETE FROM users WHERE email=?', (email,)).rowcount)

    def perfil(self, email):
        with self.accounts.db() as db:
            row = db.execute('SELECT nome, avatar FROM users WHERE email=?', (email,)).fetchone()
        return {'nome': row[0] or '', 'avatar': row[1]} if row else {'nome': '', 'avatar': None}

    def salvar_perfil(self, email, nome, avatar):
        with self.accounts.db() as db:
            return bool(db.execute('UPDATE users SET nome=?, avatar=? WHERE email=?', (nome, avatar, email)).rowcount)

    def perfis(self):
        """Nome e foto de todas as contas, numa consulta só (usado na análise da equipe)."""
        with self.accounts.db() as db:
            return {r[0]: {'nome': r[1] or '', 'avatar': r[2]}
                    for r in db.execute('SELECT email, nome, avatar FROM users').fetchall()}


class ContasSupabaseAuth:
    """Contas no Supabase Auth, pela API REST (GoTrue) com a chave secreta do servidor.

    A chave secreta nunca vai para o navegador: todas as chamadas saem daqui.
    """

    recuperacao = True

    def __init__(self, url, secret_key, transport=None):
        self.base = url.rstrip('/') + '/auth/v1'
        self.chave = secret_key
        self.transport = transport

    def _chamar(self, metodo, caminho, *, json=None, params=None, token=None):
        headers = {'apikey': self.chave, 'Authorization': f'Bearer {token or self.chave}'}
        try:
            with httpx.Client(timeout=15, transport=self.transport) as cliente:
                return cliente.request(metodo, self.base + caminho, json=json, params=params, headers=headers)
        except httpx.HTTPError:
            raise HTTPException(503, SEM_CONEXAO) from None

    @staticmethod
    def _erro(resposta):
        try:
            dados = resposta.json()
        except ValueError:
            dados = {}
        codigo = dados.get('error_code') or dados.get('code') or dados.get('error') or ''
        return str(codigo), str(dados.get('msg') or dados.get('message') or dados.get('error_description') or '')

    def _falhou(self, resposta):
        """Erros inesperados do Supabase Auth viram 502 com a mensagem dele (sem a chave)."""
        if resposta.status_code in (401, 403):
            raise HTTPException(503, 'O Supabase recusou a chave do servidor. Confira a SUPABASE_SECRET_KEY no .env.')
        codigo, mensagem = self._erro(resposta)
        if codigo == 'weak_password':
            raise HTTPException(422, 'Senha recusada pelo Supabase por ser fraca ou conhecida. Escolha outra.')
        raise HTTPException(502, f'Supabase Auth respondeu {resposta.status_code}: {mensagem or codigo}'.strip())

    def _usuarios(self):
        usuarios, pagina = [], 1
        while True:
            r = self._chamar('GET', '/admin/users', params={'page': pagina, 'per_page': 200})
            if r.status_code != 200:
                self._falhou(r)
            lote = r.json().get('users', [])
            usuarios += lote
            if len(lote) < 200:
                return usuarios
            pagina += 1

    def _usuario(self, email):
        for u in self._usuarios():
            if (u.get('email') or '').casefold() == email:
                return u
        return None

    def _id(self, email):
        u = self._usuario(email)
        return u['id'] if u else None

    def perfil(self, email):
        u = self._usuario(email) or {}
        meta = u.get('user_metadata') or {}
        return {'nome': str(meta.get('nome') or ''), 'avatar': meta.get('avatar') or None}

    def salvar_perfil(self, email, nome, avatar):
        u = self._usuario(email)
        if not u:
            return False
        meta = {**(u.get('user_metadata') or {}), 'nome': nome, 'avatar': avatar}
        r = self._chamar('PUT', f"/admin/users/{u['id']}", json={'user_metadata': meta})
        if r.status_code != 200:
            self._falhou(r)
        return True

    def emails(self):
        return sorted((u.get('email') or '').casefold() for u in self._usuarios() if u.get('email'))

    def perfis(self):
        saida = {}
        for u in self._usuarios():
            if u.get('email'):
                meta = u.get('user_metadata') or {}
                saida[u['email'].casefold()] = {'nome': str(meta.get('nome') or ''), 'avatar': meta.get('avatar') or None}
        return saida

    @staticmethod
    def _aprovado(u):
        # Contas anteriores à aprovação não têm a marca: continuam liberadas.
        return (u.get('app_metadata') or {}).get('aprovado', True) is not False

    def contas(self):
        return sorted(({'email': (u.get('email') or '').casefold(), 'aprovado': self._aprovado(u)}
                       for u in self._usuarios() if u.get('email')), key=lambda c: c['email'])

    def aprovado(self, email):
        u = self._usuario(email)
        return bool(u) and self._aprovado(u)

    def aprovar(self, email):
        u = self._usuario(email)
        if not u:
            return False
        meta = {**(u.get('app_metadata') or {}), 'aprovado': True}
        r = self._chamar('PUT', f"/admin/users/{u['id']}", json={'app_metadata': meta})
        if r.status_code != 200:
            self._falhou(r)
        return True

    def verificar(self, email, password):
        r = self._chamar('POST', '/token', params={'grant_type': 'password'},
                         json={'email': email, 'password': password})
        if r.status_code == 200:
            return True
        if r.status_code in (400, 422):   # invalid_credentials; 401/403 é chave do servidor recusada
            return False
        if r.status_code == 429:
            raise HTTPException(429, 'Muitas tentativas. Aguarde alguns minutos.')
        self._falhou(r)

    def criar(self, email, password, aprovado=True):
        r = self._chamar('POST', '/admin/users',
                         json={'email': email, 'password': password, 'email_confirm': True,
                               'app_metadata': {'aprovado': bool(aprovado)}})
        if r.status_code in (200, 201):
            return
        codigo, _ = self._erro(r)
        if codigo == 'email_exists' or r.status_code == 422 and 'already' in r.text:
            raise HTTPException(409, 'Conta já cadastrada.')
        self._falhou(r)

    def trocar_senha(self, email, password):
        uid = self._id(email)
        if not uid:
            return False
        r = self._chamar('PUT', f'/admin/users/{uid}', json={'password': password})
        if r.status_code != 200:
            self._falhou(r)
        return True

    def remover(self, email):
        uid = self._id(email)
        if not uid:
            return False
        r = self._chamar('DELETE', f'/admin/users/{uid}')
        if r.status_code not in (200, 204):
            self._falhou(r)
        return True

    def enviar_recuperacao(self, email, redirect_to):
        r = self._chamar('POST', '/recover', params={'redirect_to': redirect_to}, json={'email': email})
        if r.status_code == 429:
            raise HTTPException(429, 'Muitos pedidos de redefinição. Aguarde alguns minutos.')
        # Outras respostas não são repassadas: a tela não revela se o e-mail tem conta.

    def senha_pelo_link(self, access_token, password):
        """Troca a senha com o token do link de redefinição e devolve o e-mail da conta."""
        r = self._chamar('PUT', '/user', json={'password': password}, token=access_token)
        if r.status_code in (401, 403):
            raise HTTPException(401, 'O link expirou ou já foi usado. Peça um novo em "Esqueci a senha".')
        if r.status_code != 200:
            self._falhou(r)
        return (r.json().get('email') or '').casefold()


class Accounts:
    def __init__(self, path, supabase=None, transport=None, admins=None):
        from pontocerto import nuvem
        # Online as sessões e tentativas ficam no Supabase (pc_sessoes, pc_tentativas).
        self._nuvem = nuvem.ativo()
        if self._nuvem:
            path = nuvem.PASTA_TEMP / 'accounts.sqlite3'
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY,salt TEXT,hash TEXT);'
                             'CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,email TEXT,expires REAL);'
                             'CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY,count INTEGER,until REAL);')
            colunas = {r[1] for r in db.execute('PRAGMA table_info(users)')}
            for coluna in ('nome', 'avatar'):
                if coluna not in colunas:
                    db.execute(f'ALTER TABLE users ADD COLUMN {coluna} TEXT')
            if 'aprovado' not in colunas:
                db.execute('ALTER TABLE users ADD COLUMN aprovado INTEGER DEFAULT 1')
        self._perfis = {}  # email -> (instante, perfil): evita ir ao Supabase a cada tela
        # Administradores (ADMIN_EMAILS): só eles aprovam contas novas. Sem nenhum, o cadastro é livre.
        self.admins = {e.strip().casefold() for e in (admins or []) if e and e.strip()}
        supabase = supabase or {}
        url, chave = (supabase.get('url') or '').strip(), (supabase.get('secret_key') or '').strip()
        self.contas = ContasSupabaseAuth(url, chave, transport) if url and chave else ContasLocais(self)

    @contextmanager
    def db(self):
        if self._nuvem:
            from pontocerto import nuvem
            with nuvem.conexao() as db:
                yield db
            return
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    @property
    def recuperacao(self):
        return self.contas.recuperacao

    @staticmethod
    def validar(credentials):
        email = credentials.email.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise HTTPException(422, 'Email inválido.')
        return email, Accounts.validar_senha(credentials.password)

    @staticmethod
    def validar_senha(password):
        if len(password)<8 or not all(re.search(p, password) for p in (r'[A-Z]', r'[a-z]', r'\d', r'[^\w\s]')):
            raise HTTPException(422, 'Use ao menos 8 caracteres, com maiúscula, minúscula, número e caractere especial.')
        return password

    def emails(self):
        return self.contas.emails()

    @property
    def exige_aprovacao(self):
        return bool(self.admins)

    def eh_admin(self, email):
        return not self.exige_aprovacao or (email or '').casefold() in self.admins

    def exigir_admin(self, email):
        if not self.eh_admin(email):
            raise HTTPException(403, 'Só um administrador pode fazer isso.')

    def listar_contas(self):
        return [{**c, 'aprovado': c['aprovado'] or c['email'] in self.admins, 'admin': c['email'] in self.admins}
                for c in self.contas.contas()]

    def aprovar(self, email):
        email = email.strip().casefold()
        if not self.contas.aprovar(email):
            raise HTTPException(404, 'Conta não encontrada.')
        return email

    def _encerrar_sessoes(self, email, manter=None):
        """Derruba as sessões da conta; `manter` é o token da sessão que fica aberta."""
        with self.db() as db:
            if manter:
                db.execute('DELETE FROM sessions WHERE email=? AND token<>?',
                           (email, hashlib.sha256(manter.encode()).hexdigest()))
            else:
                db.execute('DELETE FROM sessions WHERE email=?', (email,))

    def perfil(self, email):
        guardado = self._perfis.get(email)
        if guardado and time.time() - guardado[0] < 60:
            return guardado[1]
        dados = {'email': email, **self.contas.perfil(email)}
        self._perfis[email] = (time.time(), dados)
        return dados

    def perfis(self):
        """{email: {nome, avatar}} de todas as contas; guardado por 60 s."""
        guardado = self._perfis.get('*todas*')
        if guardado and time.time() - guardado[0] < 60:
            return guardado[1]
        dados = self.contas.perfis()
        self._perfis['*todas*'] = (time.time(), dados)
        return dados

    def salvar_perfil(self, email, perfil):
        nome = ' '.join(perfil.nome.split())
        avatar = _validar_avatar(perfil.avatar)
        if not self.contas.salvar_perfil(email, nome, avatar):
            raise HTTPException(404, 'Conta não encontrada.')
        self._perfis.pop(email, None)
        self._perfis.pop('*todas*', None)
        return self.perfil(email)

    def trocar_propria_senha(self, email, troca, token_atual):
        """Pede a senha atual; as outras sessões da pessoa caem, a desta tela continua."""
        if not self.contas.verificar(email, troca.atual):
            raise HTTPException(400, 'A senha atual não confere.')
        nova = self.validar_senha(troca.nova)
        with self.lock:
            if not self.contas.trocar_senha(email, nova):
                raise HTTPException(404, 'Conta não encontrada.')
            self._encerrar_sessoes(email, manter=token_atual)

    def redefinir(self, credentials):
        """Troca a senha de uma conta existente e encerra as sessões abertas dela."""
        email, password = self.validar(credentials)
        with self.lock:
            if not self.contas.trocar_senha(email, password):
                raise HTTPException(404, 'Conta não encontrada.')
            self._encerrar_sessoes(email)
        return email

    def remover(self, email, atual):
        """Remove o acesso de outra pessoa. Ninguém remove a própria conta por aqui."""
        email = email.strip().casefold()
        if email == (atual or '').casefold():
            raise HTTPException(409, 'Você não pode remover a própria conta.')
        with self.lock:
            if not self.contas.remover(email):
                raise HTTPException(404, 'Conta não encontrada.')
            self._encerrar_sessoes(email)
        return email

    def register(self, credentials):
        """Cria a conta. Com administradores definidos, ela espera aprovação (devolve pendente=True)."""
        email, password = self.validar(credentials)
        aprovado = self.eh_admin(email)
        with self.lock:
            self.contas.criar(email, password, aprovado)
        return email, not aprovado

    def esqueci(self, email, redirect_to):
        if not self.recuperacao:
            raise HTTPException(501, 'Redefinição por e-mail indisponível. Peça a alguém com acesso para redefinir em Ajustes › Contas.')
        email = email.strip().casefold()
        if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            self.contas.enviar_recuperacao(email, redirect_to)

    def nova_senha(self, body):
        if not self.recuperacao:
            raise HTTPException(501, 'Redefinição por e-mail indisponível.')
        password = self.validar_senha(body.password)
        email = self.contas.senha_pelo_link(body.access_token, password)
        if email:
            self._encerrar_sessoes(email)
        return email

    def login(self, credentials, ip):
        email = credentials.email.strip().casefold()
        with self.db() as db:
            attempt = db.execute('SELECT count,until FROM attempts WHERE ip=?', (ip,)).fetchone()
            if attempt and attempt[0]>=10 and attempt[1]>time.time():
                raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
        if not self.contas.verificar(email, credentials.password):
            with self.db() as db:
                count = (attempt[0] if attempt and attempt[1]>time.time() else 0)+1
                db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (ip,count,time.time()+900))
            raise HTTPException(401, 'Email ou senha inválidos.')
        if self.exige_aprovacao and email not in self.admins and not self.contas.aprovado(email):
            raise HTTPException(403, 'Sua conta está aguardando a aprovação de um administrador.')
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM attempts WHERE ip=?', (ip,))
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),email,time.time()+28800))
        return token

    def user(self, token):
        if not token:
            return None
        with self.db() as db:
            row = db.execute('SELECT email FROM sessions WHERE token=? AND expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return row[0] if row else None


PUBLICAS = ('/login', '/redefinir-senha', '/api/auth/status', '/api/auth/register', '/api/auth/login',
            '/api/auth/esqueci', '/api/auth/nova-senha',
            '/manifest.webmanifest', '/sw.js', '/offline', '/favicon.ico')


def secure(app, root, supabase=None, transport=None, admins=None):
    """Liga o login. Com `supabase` ({url, secret_key}) as contas ficam no Supabase Auth.

    `admins`: e-mails que aprovam contas novas (padrão: ADMIN_EMAILS do ambiente/.env).
    """
    if admins is None:
        from pontocerto.config import variavel_env
        admins = (variavel_env('ADMIN_EMAILS') or '').replace(';', ',').split(',')
    accounts = Accounts(root/'artifacts'/'local'/'accounts.sqlite3', supabase, transport, admins)
    app.state.accounts = accounts
    estaticos = Path(__file__).parent/'static'

    @app.middleware('http')
    async def session(request: Request, call_next):
        path = request.url.path
        request.state.user = accounts.user(request.cookies.get(COOKIE))
        public = path in PUBLICAS or path.startswith('/static/')
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin = request.headers.get('origin')
            if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Origem não permitida.'},status_code=403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail':'Origem não permitida.'},status_code=403)
        if not public and not request.state.user:
            if path.startswith('/api/'):
                return JSONResponse({'detail':'Entre na sua conta.'},status_code=401)
            return RedirectResponse('/login',status_code=303)
        response = await call_next(request)
        if not path.startswith('/static/'):
            response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        return response

    @app.get('/login',include_in_schema=False)
    def login_page():
        return HTMLResponse((estaticos/'login.html').read_text(encoding='utf-8'))

    @app.get('/redefinir-senha',include_in_schema=False)
    def redefinir_page():
        # O link do e-mail traz o token no fragmento (#access_token=...), que não chega ao servidor.
        return HTMLResponse((estaticos/'redefinir-senha.html').read_text(encoding='utf-8'))

    @app.get('/api/auth/status')
    def auth_status(request: Request):
        return {'user':request.state.user,'recuperacao':accounts.recuperacao}

    @app.get('/api/auth/users')
    def users(request: Request):
        contas = accounts.listar_contas()
        return {'users': [c['email'] for c in contas], 'contas': contas, 'atual': request.state.user,
                'admin': accounts.eh_admin(request.state.user)}

    @app.post('/api/auth/register',status_code=201)
    def register(body: Credentials):
        email, pendente = accounts.register(body)
        return {'email': email, 'pendente': pendente}

    @app.post('/api/auth/aprovar')
    def aprovar(body: EmailOnly, request: Request):
        accounts.exigir_admin(request.state.user)
        return {'email': accounts.aprovar(body.email)}

    @app.post('/api/auth/password')
    def trocar_senha(body: Credentials, request: Request):
        """Um administrador redefine a senha de outra conta."""
        accounts.exigir_admin(request.state.user)
        return {'email': accounts.redefinir(body)}

    @app.post('/api/auth/remove')
    def remover_conta(body: EmailOnly, request: Request):
        """Remove (ou recusa, se ainda pendente) a conta de outra pessoa. Só administrador."""
        accounts.exigir_admin(request.state.user)
        return {'email': accounts.remover(body.email, request.state.user)}

    @app.get('/api/perfil')
    def ver_perfil(request: Request):
        return {**accounts.perfil(request.state.user), 'admin': accounts.eh_admin(request.state.user)}

    @app.post('/api/perfil')
    def salvar_perfil(body: Perfil, request: Request):
        return {**accounts.salvar_perfil(request.state.user, body), 'admin': accounts.eh_admin(request.state.user)}

    @app.post('/api/perfil/senha')
    def trocar_propria_senha(body: TrocaSenha, request: Request):
        accounts.trocar_propria_senha(request.state.user, body, request.cookies.get(COOKIE))
        return {'ok': True}

    @app.post('/api/auth/esqueci')
    def esqueci(body: EmailOnly, request: Request):
        accounts.esqueci(body.email, str(request.base_url).rstrip('/') + '/redefinir-senha')
        return {'ok': True}

    @app.post('/api/auth/nova-senha')
    def nova_senha(body: NovaSenha):
        return {'email': accounts.nova_senha(body)}

    @app.post('/api/auth/login')
    def login(body: Credentials,request: Request):
        token = accounts.login(body,request.client.host if request.client else 'local')
        response = JSONResponse({'ok':True})
        response.set_cookie(COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=28800)
        return response

    @app.post('/api/auth/logout')
    def logout(request: Request):
        token = request.cookies.get(COOKIE,'')
        with accounts.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
        response=JSONResponse({'ok':True})
        response.delete_cookie(COOKIE)
        return response
    return app
