"""Fotos só para a conta que as tirou, máquinas cadastradas pelo administrador e análise da equipe."""
import io
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from pontocerto.config import carregar_config

SENHA = 'Teste@1234'
ADMIN = 'chefe@example.com'


class ContasEMaquinasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _app(self):
        from pontocerto.principal import criar_app_completo
        cfg = carregar_config()
        cfg.app.pasta_capturas = str(self.root / 'capturas')
        cfg.app.pasta_relatorios = str(self.root / 'relatorios')
        cfg.app.correcoes = str(self.root / 'correcoes.csv')
        cfg.banco['lote_ativo'] = str(self.root / 'lote_ativo.json')
        cfg.llm['ativo'] = False
        cfg.llm['leitura_ia'] = False
        for alvo in ('pontocerto.app.db.credenciais_supabase', 'pontocerto.config.credenciais_supabase'):
            p = patch(alvo, return_value={})
            p.start()
            self.addCleanup(p.stop)
        return criar_app_completo(cfg, root=self.root, admins=[ADMIN])

    @staticmethod
    def _entrar(c, email):
        c.cookies.clear()
        c.post('/api/auth/register', json={'email': email, 'password': SENHA})
        if email != ADMIN:  # contas novas esperam aprovação
            c.cookies.clear()
            c.post('/api/auth/login', json={'email': ADMIN, 'password': SENHA})
            c.post('/api/auth/aprovar', json={'email': email})
            c.cookies.clear()
        r = c.post('/api/auth/login', json={'email': email, 'password': SENHA})
        assert r.status_code == 200, r.text

    @staticmethod
    def _foto(c):
        imagem = io.BytesIO()
        Image.new('RGB', (224, 224), 'gray').save(imagem, format='PNG')
        d = c.post('/api/analisar', files={'arquivo': ('p.png', imagem.getvalue(), 'image/png')}).json()
        assert 'erro' not in d, d
        return d['evento']

    def test_fotos_por_conta_maquinas_e_analise(self):
        with TestClient(self._app()) as c:
            self._entrar(c, ADMIN)  # o administrador entra primeiro (é quem aprova)

            # --- máquinas: só o administrador cadastra
            m1 = c.post('/api/maquinas', json={'nome': 'Overloque 01', 'tipo': 'Overloque'}).json()['maquina']
            m2 = c.post('/api/maquinas', json={'nome': 'Reta 02'}).json()['maquina']
            self.assertEqual(c.post('/api/maquinas', json={'nome': 'overloque 01'}).status_code, 422)
            self.assertEqual(c.put(f'/api/maquinas/{m2["id"]}', json={'nome': 'Reta 03', 'tipo': 'Reta'}).json()['maquina']['nome'], 'Reta 03')

            self._entrar(c, 'ana@example.com')
            self.assertEqual(c.post('/api/maquinas', json={'nome': 'Intrusa'}).status_code, 403)
            self.assertEqual(c.delete(f'/api/maquinas/{m1["id"]}').status_code, 403)
            self.assertFalse(c.get('/api/perfil').json()['admin'])
            self.assertEqual(c.get('/api/analise').status_code, 403)
            c.post('/api/maquinas/ativa', json={'id': m1['id']})
            self.assertEqual(c.get('/api/maquinas').json()['ativa']['id'], m1['id'])
            ev_ana = self._foto(c)
            self.assertEqual((ev_ana['autor'], ev_ana['maquina_nome']), ('ana@example.com', 'Overloque 01'))
            self.assertEqual(c.get(ev_ana['imagem']).status_code, 200)

            # --- outra conta não vê a peça nem a foto da Ana
            self._entrar(c, 'bia@example.com')
            self.assertEqual(c.get('/api/eventos').json()['eventos'], [])
            self.assertEqual(c.get(ev_ana['imagem']).status_code, 404)
            self.assertEqual(c.post(f'/api/eventos/{ev_ana["id"]}/conferencia', json={'classe': 'normal'}).status_code, 404)
            self.assertEqual(c.delete(f'/api/eventos/{ev_ana["id"]}').status_code, 404)
            self.assertEqual(c.get('/api/status').json()['estatisticas']['total'], 0)
            self.assertEqual(c.get('/api/relatorios/resumo').json()['total'], 0)
            c.post('/api/maquinas/ativa', json={'id': m2['id']})
            ev_bia = self._foto(c)
            self._foto(c)
            ids = [e['id'] for e in c.get('/api/eventos').json()['eventos']]
            self.assertNotIn(ev_ana['id'], ids)
            self.assertEqual(len(ids), 2)

            # --- o administrador também só vê as próprias fotos, mas analisa a equipe toda
            self._entrar(c, ADMIN)
            self.assertEqual(c.get('/api/eventos').json()['eventos'], [])
            self.assertEqual(c.get(ev_bia['imagem']).status_code, 404)
            r = c.get('/api/analise').json()
            self.assertEqual(r['totais']['inspecionadas'], 3)
            por = {u['email']: u for u in r['por_usuario']}
            self.assertEqual((por['ana@example.com']['inspecionadas'], por['bia@example.com']['inspecionadas']), (1, 2))
            self.assertEqual(por['bia@example.com']['maquina_principal'], 'Reta 03')
            self.assertEqual({m['nome']: m['inspecionadas'] for m in r['por_maquina']}, {'Overloque 01': 1, 'Reta 03': 2})
            self.assertIn(ADMIN, [u['email'] for u in r['opcoes']['usuarios']])
            self.assertEqual(c.get('/api/analise', params={'usuario': 'ana@example.com'}).json()['totais']['inspecionadas'], 1)
            self.assertEqual(c.get('/api/analise', params={'maquina': m2['id']}).json()['totais']['inspecionadas'], 2)
            self.assertTrue(c.get('/api/analise/pdf').content.startswith(b'%PDF'))
            # O relatório do administrador cobre a equipe e diz quem fez e em qual máquina.
            self.assertEqual(c.get('/api/relatorios/resumo').json()['total'], 3)
            self.assertTrue(c.get('/api/relatorios/pdf').content.startswith(b'%PDF'))
            from pontocerto.app.relatorio_pdf import conteudo
            todos = c.app.state.estado.eventos_periodo('0000-01-01', '9999-12-31', todos=True)
            partes = conteudo(todos, lambda e: (e or '').split('@')[0], de=date.today(), ate=date.today())
            titulos = [s.get('titulo') for s in partes['secoes']]
            self.assertIn('Por pessoa', titulos)
            maquinas = partes['secoes'][[i for i, s in enumerate(partes['secoes']) if 'colunas' in s][0]]['colunas'][1]
            self.assertEqual({l[0] for l in maquinas['tabela']['linhas']}, {'Overloque 01', 'Reta 03'})
            pessoas = next(s for s in partes['secoes'] if s.get('titulo') == 'Por pessoa')['tabela']['linhas']
            self.assertEqual({l[0] for l in pessoas}, {'ana', 'bia'})
            defeito = next((s for s in partes['secoes'] if s.get('titulo') == 'Peças com defeito'), None)
            if defeito:  # a leitura local da foto cinza pode não achar defeito
                self.assertIn('Pessoa', defeito['tabela']['colunas'])
                self.assertIn('Máquina', defeito['tabela']['colunas'])

            # --- remover a máquina não apaga o nome dela das peças
            self.assertEqual(c.delete(f'/api/maquinas/{m1["id"]}').status_code, 200)
            self.assertEqual([m['nome'] for m in c.get('/api/maquinas').json()['maquinas']], ['Reta 03'])
            r = c.get('/api/analise').json()
            self.assertIn('Overloque 01 (removida)', [m['nome'] for m in r['por_maquina']])


class LotePorContaTest(unittest.TestCase):
    def test_cada_conta_tem_o_proprio_lote(self):
        from pontocerto.app.state import EstadoSessao
        with tempfile.TemporaryDirectory() as pasta:
            cfg = carregar_config()
            cfg.app.pasta_capturas = str(Path(pasta) / 'capturas')
            cfg.app.correcoes = str(Path(pasta) / 'correcoes.csv')
            estado = EstadoSessao(cfg)
            estado.definir_lote('ana@x.com', {'id': 1, 'codigo': 'OP-1'})
            estado.definir_lote('BIA@x.com', {'id': 2, 'codigo': 'OP-2'})
            pred = {'classe_idx': 0, 'confianca': 0.9}
            self.assertEqual(estado.registrar_evento(pred, autor='ana@x.com').lote_codigo, 'OP-1')
            self.assertEqual(estado.registrar_evento(pred, autor='bia@x.com').lote_codigo, 'OP-2')
            self.assertIsNone(estado.registrar_evento(pred, autor='carla@x.com').lote_codigo)
            estado.definir_lote('ana@x.com', None)
            self.assertIsNone(estado.lote_de('ana@x.com'))
            self.assertEqual(estado.lote_de('bia@x.com')['codigo'], 'OP-2')
            estado.soltar_lote(2)  # lote concluído sai de todas as contas
            self.assertEqual(estado.lotes_ativos(), {})


class RitmoTest(unittest.TestCase):
    def test_pausas_longas_nao_contam_como_trabalho(self):
        from pontocerto.app.analise import analisar
        base = time.mktime((2026, 11, 20, 8, 0, 0, 0, 0, -1))
        # 11 peças a cada 2 min, almoço de 1 h, mais 10 peças a cada 3 min.
        instantes = [base + i * 120 for i in range(11)] + [base + 20 * 60 + 3600 + i * 180 for i in range(10)]
        eventos = [SimpleNamespace(timestamp=t, autor='ana@x.com', maquina_id=None, maquina_nome=None,
                                   classe_final='normal', precisa_revisao=False, revisao_humana=None) for t in instantes]
        r = analisar(eventos, perfis={}, contas=[], maquinas=[], de=date(2026, 11, 20), ate=date(2026, 11, 20))
        # Ativo: 20 min + 27 min + 1 min por sequência = 49 min -> 21 peças / 0,8167 h
        self.assertEqual(r['totais']['horas_ativas'], round(49 / 60, 2))
        self.assertEqual(r['totais']['pecas_por_hora'], round(21 / (49 / 60), 1))
        self.assertEqual(r['por_usuario'][0]['horario'], {'inicio': '08:00', 'fim': '09:47'})


if __name__ == '__main__':
    unittest.main()
