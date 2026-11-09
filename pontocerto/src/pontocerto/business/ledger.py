"""Livro local em centavos. Não substitui contabilidade ou conciliação bancária."""
import copy
import csv
import io
import json
import os
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from threading import RLock
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def month_shift(month:str,delta:int):
    year,m=map(int,month[:7].split('-'))
    value=year*12+m-1+delta
    return f'{value//12:04d}-{value%12+1:02d}'


def cents(value):
    if isinstance(value,bool):
        raise ValueError('Valor monetário inválido.')
    text=str(value).strip()
    if ',' in text:
        text=text.replace('.','').replace(',','.')
    try:
        money=Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Informe valor como 1234.56 ou 1234,56.') from exc
    if not money.is_finite() or money<=0 or money>Decimal('1000000000') or money*100!=(money*100).to_integral_value():
        raise ValueError('Valor deve ser positivo e ter no máximo duas casas decimais.')
    return int(money*100)


def empty(environment):
    return {'schemaVersion':1,'environment':environment,'entries':[],'audit':[],
            'settings':{'openingDate':date.today().replace(day=1).isoformat(),'openingBalanceCents':0,
                        'historyStartMonth':None,'historyThroughMonth':None,'reserveMonths':3,
                        'equipmentPercent':20,'contingencyPercent':10,'scenarioPercent':15}}


def demo():
    state=empty('demo')
    first=month_shift(date.today().isoformat(),-18)
    state['settings'].update(openingDate=first+'-01',openingBalanceCents=5000000,
                              historyStartMonth=first,historyThroughMonth=month_shift(date.today().isoformat(),-1))
    # Fixtures determinísticas, não dados da empresa e não base pública financeira.
    for i in range(18):
        m=month_shift(first,i)
        for j,(kind,category,value) in enumerate([
            ('income','Serviços de confecção',2800000+i*45000+(i%3)*80000),
            ('expense','Pessoal',1450000+i*15000),('expense','Aluguel e energia',420000),
            ('expense','Insumos',380000+(i%4)*30000)]):
            state['entries'].append({'id':str(uuid4()),'reference':f'DEMO-{m}-{j}',
                'type':kind,'nature':'operating','category':category,'description':'Registro fictício para demonstrar o módulo',
                'amountCents':value,'documentDate':m+'-05','dueDate':m+'-15','settledDate':m+'-15',
                'status':'settled','createdAt':now(),'origin':'mock'})
    return state


class LedgerStore:
    def __init__(self,path:Path,environment:str):
        self.path,self.environment,self.lock=path,environment,RLock()
        self.state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else (demo() if environment=='demo' else empty('real'))
        if self.state.get('environment')!=environment or self.state.get('schemaVersion')!=1:
            raise ValueError('Origem/esquema do livro divergente; não será sobrescrito.')

    def read(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def update(self,action,reason,callback):
        with self.lock:
            draft=copy.deepcopy(self.state)
            result=callback(draft)
            draft['audit'].append({'id':str(uuid4()),'at':now(),'actor':'operador-local-sem-autenticacao',
                                    'action':action,'reason':reason})
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp,self.path)
            self.state=draft
            return result


def add_entry(state,entry,environment):
    if any(e['reference'].casefold()==entry['reference'].casefold() for e in state['entries']):
        raise ValueError('Referência já cadastrada; importação duplicada recusada.')
    if entry['documentDate']<state['settings']['openingDate']:
        raise ValueError('Documento anterior à data do saldo inicial. Configure o início do histórico antes de importar.')
    item={**entry,'id':str(uuid4()),'createdAt':now(),'origin':'mock' if environment=='demo' else 'user_provided'}
    state['entries'].append(item)
    return item


def csv_rows(text):
    if len(text)>500000:
        raise ValueError('CSV acima de 500 KB.')
    text=text.lstrip('\ufeff')
    if not text.strip():
        raise ValueError('CSV vazio.')
    delimiter=';' if ';' in text.splitlines()[0] else ','
    reader=csv.DictReader(io.StringIO(text),delimiter=delimiter)
    required={'reference','type','nature','category','description','amount','documentDate','dueDate','settledDate'}
    if not reader.fieldnames or set(reader.fieldnames)!=required:
        raise ValueError('Cabeçalhos inválidos. Use o modelo CSV mostrado na tela.')
    rows=list(reader)
    if not 1<=len(rows)<=1000:
        raise ValueError('Importe de 1 a 1.000 linhas por vez.')
    return rows
