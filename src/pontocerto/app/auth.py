"""Contas locais com senha derivada, sessão opaca e cadastro inicial único."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from threading import Lock
from pathlib import Path
from contextlib import contextmanager

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

COOKIE = 'dm_session'


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class EmailOnly(BaseModel):
    email: str = Field(min_length=5, max_length=254)


_DDL_CONTAS = (
    'CREATE TABLE IF NOT EXISTS public.contas('
    'email text PRIMARY KEY, salt text NOT NULL, hash text NOT NULL, criado_em timestamptz NOT NULL DEFAULT now());'
    'ALTER TABLE public.contas ENABLE ROW LEVEL SECURITY;'
    'REVOKE ALL ON public.contas FROM anon, authenticated;'
)


class ContasLocais:
    """Contas na tabela `users` do SQLite local (usado sem SUPABASE_DB_URL e nos testes)."""

    def __init__(self, accounts):
        self.accounts = accounts

    def exists(self):
        with self.accounts.db() as db:
            return bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())

    def emails(self):
        with self.accounts.db() as db:
            return [r[0] for r in db.execute('SELECT email FROM users ORDER BY email').fetchall()]

    def get(self, email):
        with self.accounts.db() as db:
            return db.execute('SELECT salt,hash FROM users WHERE email=?', (email,)).fetchone()

    def insert(self, email, salt, derived, allowed):
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone() and not allowed:
                raise HTTPException(403, 'O cadastro inicial já foi concluído. Entre para cadastrar outra conta.')
            try:
                db.execute('INSERT INTO users VALUES (?,?,?)', (email, salt, derived))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Conta já cadastrada.')

    def update(self, email, salt, derived):
        with self.accounts.db() as db:
            return bool(db.execute('UPDATE users SET salt=?, hash=? WHERE email=?', (salt, derived, email)).rowcount)

    def delete(self, email):
        with self.accounts.db() as db:
            return bool(db.execute('DELETE FROM users WHERE email=?', (email,)).rowcount)


class ContasSupabase:
    """Contas na tabela `public.contas` do Supabase, compartilhadas entre computadores.

    Só as contas vão para o banco; sessões e tentativas de login continuam no
    SQLite local, então quem já entrou segue usando o sistema se a internet cair.
    """

    def __init__(self, accounts, db_url):
        self.accounts = accounts
        self.db_url = db_url
        self.pronto = False

    @contextmanager
    def db(self):
        import psycopg
        try:
            conexao = psycopg.connect(self.db_url, connect_timeout=8, prepare_threshold=None)
        except psycopg.OperationalError:
            raise HTTPException(503, 'Sem conexão com o banco das contas. Confira a internet e tente de novo.') from None
        try:
            with conexao:
                if not self.pronto:
                    conexao.execute(_DDL_CONTAS)
                    self._importar_locais(conexao)
                    self.pronto = True
                yield conexao
        finally:
            conexao.close()

    def _importar_locais(self, conexao):
        """Leva para o banco as contas que existiam só neste computador (sem sobrescrever)."""
        with self.accounts.db() as local:
            linhas = local.execute('SELECT email,salt,hash FROM users').fetchall()
        for linha in linhas:
            conexao.execute('INSERT INTO public.contas(email,salt,hash) VALUES (%s,%s,%s) '
                            'ON CONFLICT (email) DO NOTHING', linha)

    def exists(self):
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM public.contas LIMIT 1').fetchone())

    def emails(self):
        with self.db() as db:
            return [r[0] for r in db.execute('SELECT email FROM public.contas ORDER BY email').fetchall()]

    def get(self, email):
        with self.db() as db:
            return db.execute('SELECT salt,hash FROM public.contas WHERE email=%s', (email,)).fetchone()

    def insert(self, email, salt, derived, allowed):
        with self.db() as db:
            # Serializa cadastros simultâneos para o "primeiro acesso" ser único.
            db.execute("SELECT pg_advisory_xact_lock(hashtext('public.contas'))")
            if db.execute('SELECT 1 FROM public.contas LIMIT 1').fetchone() and not allowed:
                raise HTTPException(403, 'O cadastro inicial já foi concluído. Entre para cadastrar outra conta.')
            if not db.execute('INSERT INTO public.contas(email,salt,hash) VALUES (%s,%s,%s) '
                              'ON CONFLICT (email) DO NOTHING', (email, salt, derived)).rowcount:
                raise HTTPException(409, 'Conta já cadastrada.')

    def update(self, email, salt, derived):
        with self.db() as db:
            return bool(db.execute('UPDATE public.contas SET salt=%s, hash=%s WHERE email=%s',
                                   (salt, derived, email)).rowcount)

    def delete(self, email):
        with self.db() as db:
            return bool(db.execute('DELETE FROM public.contas WHERE email=%s', (email,)).rowcount)


class Accounts:
    def __init__(self, path, db_url=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY,salt TEXT,hash TEXT);'
                             'CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,email TEXT,expires REAL);'
                             'CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY,count INTEGER,until REAL);')
        db_url = (db_url or '').strip()
        self.contas = ContasSupabase(self, db_url) if db_url else ContasLocais(self)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def exists(self):
        return self.contas.exists()

    @staticmethod
    def derive(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

    @staticmethod
    def validar(credentials):
        email = credentials.email.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise HTTPException(422, 'Email inválido.')
        password = credentials.password
        if len(password)<8 or not all(re.search(p, password) for p in (r'[A-Z]', r'[a-z]', r'\d', r'[^\w\s]')):
            raise HTTPException(422, 'Use ao menos 8 caracteres, com maiúscula, minúscula, número e caractere especial.')
        return email, password

    def emails(self):
        return self.contas.emails()

    def redefinir(self, credentials):
        """Troca a senha de uma conta existente e encerra as sessões abertas dela."""
        email, password = self.validar(credentials)
        salt = secrets.token_hex(16)
        derived = self.derive(password, salt)
        with self.lock:
            if not self.contas.update(email, salt, derived):
                raise HTTPException(404, 'Conta não encontrada.')
            with self.db() as db:
                db.execute('DELETE FROM sessions WHERE email=?', (email,))
        return email

    def remover(self, email, atual):
        """Remove o acesso de outra pessoa. Ninguém remove a própria conta por aqui."""
        email = email.strip().casefold()
        if email == (atual or '').casefold():
            raise HTTPException(409, 'Você não pode remover a própria conta.')
        with self.lock:
            if not self.contas.delete(email):
                raise HTTPException(404, 'Conta não encontrada.')
            with self.db() as db:
                db.execute('DELETE FROM sessions WHERE email=?', (email,))
        return email

    def register(self, credentials, allowed=False):
        email, password = self.validar(credentials)
        salt = secrets.token_hex(16)
        derived = self.derive(password, salt)
        with self.lock:
            self.contas.insert(email, salt, derived, allowed)
        return email

    def login(self, credentials, ip):
        email = credentials.email.strip().casefold()
        with self.db() as db:
            attempt = db.execute('SELECT count,until FROM attempts WHERE ip=?', (ip,)).fetchone()
            if attempt and attempt[0]>=10 and attempt[1]>time.time():
                raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
        row = self.contas.get(email)
        # Executa a derivação mesmo quando a conta não existe.
        candidate = self.derive(credentials.password, row[0] if row else '00'*16)
        if not row or not hmac.compare_digest(candidate, row[1]):
            with self.db() as db:
                count = (attempt[0] if attempt and attempt[1]>time.time() else 0)+1
                db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (ip,count,time.time()+900))
            raise HTTPException(401, 'Email ou senha inválidos.')
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


def secure(app, root, db_url=None):
    """Liga o login. Com `db_url` (SUPABASE_DB_URL) as contas ficam no Supabase."""
    accounts = Accounts(root/'artifacts'/'local'/'accounts.sqlite3', db_url)
    app.state.accounts = accounts

    @app.middleware('http')
    async def session(request: Request, call_next):
        path = request.url.path
        request.state.user = accounts.user(request.cookies.get(COOKIE))
        public = path in ('/login','/api/auth/status','/api/auth/register','/api/auth/login',
                          '/manifest.webmanifest','/sw.js','/offline','/favicon.ico') or path.startswith('/static/')
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
        return HTMLResponse((Path(__file__).parent/'static'/'login.html').read_text(encoding='utf-8'))

    @app.get('/api/auth/status')
    def auth_status(request: Request):
        return {'setupRequired':not accounts.exists(),'user':request.state.user}

    @app.get('/api/auth/users')
    def users(request: Request):
        return {'users': accounts.emails(), 'atual': request.state.user}

    @app.post('/api/auth/register',status_code=201)
    def register(body: Credentials,request: Request):
        email = accounts.register(body,allowed=bool(request.state.user))
        return {'email':email}

    @app.post('/api/auth/password')
    def trocar_senha(body: Credentials):
        """Quem já entrou redefine a senha de qualquer conta (substitui o script de terminal)."""
        return {'email': accounts.redefinir(body)}

    @app.post('/api/auth/remove')
    def remover_conta(body: EmailOnly, request: Request):
        return {'email': accounts.remover(body.email, request.state.user)}

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
