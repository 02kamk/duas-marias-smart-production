"""Persistência JSON de demonstração, processo único; PostgreSQL continua planejado."""
import copy
import json
import os
from datetime import date, timedelta
from pathlib import Path
from threading import RLock
from .domain import now

OPERATIONS = ['Gola', 'Manga', 'Barra', 'Costura lateral', 'Etiqueta', 'Acabamento', 'Revisão final']


def seed():
    today = date.today()
    orders = []
    for i, (quantity, produced, days, rate) in enumerate([(3000,1950,3,220),(1500,1280,5,90),(2000,1900,6,120),(1200,420,2,180)]):
        orders.append({'id': str(i+1), 'code': f'OP-{i+1:03}', 'client': f'Cliente demo {i+1}',
                       'model': ['Camiseta', 'Calça', 'Blusa', 'Camisa'][i], 'quantity': quantity,
                       'produced': produced, 'dueDate': (today+timedelta(days=days)).isoformat(),
                       'capacityPerDay': rate*1.3, 'recentRate': rate, 'reworkRate': .05,
                       'dataOrigin': 'mock', 'status': 'Em andamento'})
    return {'schemaVersion': 1, 'dataOrigin': 'mock', 'createdAt': now(),
            'orders': orders, 'records': [], 'audit': [], 'assignments': [], 'decisions': [],
            'employees': [{'id': str(i+1), 'name': name, 'active': True, 'availableMinutes': 240,
                           'skills': {op: {'rate': 40+i*7, 'quality': .94+i*.01, 'experience': 2+i}
                                      for op in OPERATIONS if not(i==2 and op=='Gola')}}
                          for i,name in enumerate(['Ana Demo','Bia Demo','Clara Demo'])]}


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()
        self.state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else seed()
        if self.state.get('schemaVersion') != 1 or self.state.get('dataOrigin') != 'mock':
            raise ValueError('Arquivo de gestão não é a demonstração v1; não será sobrescrito.')

    def read(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def update(self, action, reason, callback):
        with self.lock:
            draft = copy.deepcopy(self.state)
            result = callback(draft)
            draft['audit'].append({'at': now(), 'actor': 'operador-local-demo', 'action': action, 'reason': reason})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, self.path)
            self.state = draft
            return result
