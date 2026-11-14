"""Persistência opcional do estado da gestão no PostgreSQL do Supabase.

Ativar GESTAO_STORAGE=supabase após executar supabase/gestao.sql.
Falhas de conexão não fazem fallback silencioso para dados locais.
"""
import copy
import json
from threading import RLock
from psycopg.types.json import Jsonb
import psycopg
from pontocerto.config import variavel_env
from .domain import now


class PostgresStore:
    backend='supabase'

    def __init__(self):
        self.lock=RLock()
        self.url=variavel_env('SUPABASE_DB_URL')
        if not self.url:
            raise RuntimeError('GESTAO_STORAGE=supabase exige SUPABASE_DB_URL no .env.')
        with self.connect() as db:
            row=db.execute('SELECT payload FROM public.gestao_estado WHERE id=1').fetchone()
            if not row:
                raise RuntimeError('Execute supabase/gestao.sql antes de iniciar a gestão Supabase.')

    def connect(self):
        return psycopg.connect(self.url,connect_timeout=10)

    def read(self):
        with self.lock,self.connect() as db:
            return copy.deepcopy(db.execute('SELECT payload FROM public.gestao_estado WHERE id=1').fetchone()[0])

    def update(self,action,reason,callback):
        with self.lock,self.connect() as db:
            state=db.execute('SELECT payload FROM public.gestao_estado WHERE id=1 FOR UPDATE').fetchone()[0]
            result=callback(state)
            state['audit'].append({'at':now(),'action':action,'reason':reason,'actor':'operador-autenticado'})
            db.execute('UPDATE public.gestao_estado SET payload=%s,updated_at=now() WHERE id=1',(Jsonb(state),))
            return result
