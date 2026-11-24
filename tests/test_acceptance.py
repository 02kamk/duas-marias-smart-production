"""Aceite local em bases temporárias, sem câmera, e-mail ou credenciais externas."""
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pontocerto.config import carregar_config
from pontocerto.app.auth import secure
from pontocerto.app.state import EstadoSessao


class BancoFalso:
    """Faz o papel do Supabase nas rotas de lotes, em memória."""
    configurado=True
    def __init__(self):
        self.clientes=[];self.lotes={}
    def mascarar(self,texto): return texto
    def listar_clientes(self): return list(self.clientes)
    def criar_cliente(self,nome):
        c={'id':len(self.clientes)+1,'nome':nome};self.clientes.append(c);return c
    def criar_lote(self,d):
        i=len(self.lotes)+1
        nome=next(c['nome'] for c in self.clientes if c['id']==d['cliente_id'])
        self.lotes[i]={'id':i,'codigo':d['codigo'],'cliente':nome,'modelo_peca':d.get('modelo_peca'),
                       'quantidade':d['quantidade'],'status':'aberto','inspecionadas':0,'aprovadas':0,'reprovadas':0}
        return {'id':i}
    def listar_lotes(self): return [dict(l) for l in self.lotes.values()]
    def obter_lote(self,i): return dict(self.lotes[i]) if i in self.lotes else None
    def atualizar_status_lote(self,i,status):
        if i not in self.lotes: return False
        self.lotes[i]['status']=status;return True
    def defeitos_por_classe(self,i): return [{'classe_final':'crooked_seam','quantidade':2},{'classe_final':'normal','quantidade':5}]
    def ultimas_inspecoes(self,i,limite=30): return []


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_auth_policy_session_access_and_logout(self):
        app=FastAPI()
        @app.get('/api/private')
        def private(): return {'ok':True}
        secure(app,self.root,admins=[])
        with TestClient(app) as c:
            self.assertEqual(c.get('/api/private').status_code,401)
            for pwd in ['abc','abcdefgh','Abcdefgh','Abcdefg1']:
                self.assertEqual(c.post('/api/auth/register',json={'email':'test@example.com','password':pwd}).status_code,422)
            body={'email':'test@example.com','password':'Teste@1234'}
            self.assertEqual(c.post('/api/auth/register',json=body).status_code,201)
            # Cadastro aberto, mas o mesmo e-mail não entra duas vezes e criar conta não abre sessão.
            self.assertEqual(c.post('/api/auth/register',json=body).status_code,409)
            self.assertEqual(c.get('/api/private').status_code,401)
            self.assertEqual(c.post('/api/auth/login',json={**body,'password':'errada'}).status_code,401)
            login=c.post('/api/auth/login',json=body)
            self.assertEqual(login.status_code,200)
            self.assertIn('HttpOnly',login.headers['set-cookie'])
            self.assertEqual(c.get('/api/private').status_code,200)
            self.assertEqual(c.post('/api/auth/logout',headers={'origin':'https://outro.site'}).status_code,403)
            self.assertEqual(c.post('/api/auth/logout').status_code,200)
            self.assertEqual(c.get('/api/private').status_code,401)
        raw=(self.root/'artifacts/local/accounts.sqlite3').read_bytes()
        self.assertNotIn(b'Teste@1234',raw)

    def test_persistent_photo_history_and_human_review(self):
        import numpy as np
        cfg=carregar_config()
        cfg.app.pasta_capturas=str(self.root/'capturas')
        cfg.app.correcoes=str(self.root/'correcoes.csv')
        state=EstadoSessao(cfg)
        ev=state.registrar_evento({'classe_idx':4,'classe_key':'crooked_seam','confianca':.8},np.zeros((32,32,3),dtype=np.uint8),origem='upload')
        self.assertTrue(state.caminho_captura(ev).exists())
        from pontocerto.app.sincronizador import Sincronizador
        ev.lote_id=1
        self.assertEqual(Sincronizador.instantaneo(ev)['origem'],'upload')
        # Origens novas viram as duas que o banco aceita.
        ev.origem='camera_aparelho';self.assertEqual(Sincronizador.instantaneo(ev)['origem'],'upload')
        ev.origem='camera_servidor';self.assertEqual(Sincronizador.instantaneo(ev)['origem'],'ao_vivo')
        ev.origem='upload'
        restored=EstadoSessao(cfg)
        self.assertEqual(restored.evento(ev.id).origem,'upload')
        self.assertEqual(len(restored.eventos(dia=date.today().isoformat(),defeitos=True)),1)
        self.assertEqual(restored.eventos(dia=(date.today()-timedelta(days=1)).isoformat()),[])
        restored.revisar_humano(ev.id,'normal','corrigida','Revisada manualmente','test@example.com')
        again=EstadoSessao(cfg)
        self.assertEqual(again.eventos(defeitos=True),[])
        self.assertEqual(again.evento(ev.id).revisao_humana['autor'],'test@example.com')

    def test_full_app_real_upload_and_review(self):
        from pontocerto.principal import criar_app_completo
        cfg=carregar_config()
        cfg.app.pasta_capturas=str(self.root/'capturas')
        cfg.app.pasta_relatorios=str(self.root/'relatorios')
        cfg.app.correcoes=str(self.root/'correcoes.csv')
        cfg.banco['lote_ativo']=str(self.root/'lote_ativo.json')
        # Sem OpenRouter de verdade: este teste exercita a leitura local.
        cfg.llm['ativo']=False;cfg.llm['leitura_ia']=False
        # Nunca usa o Supabase do .env: o teste não pode gravar no banco de verdade.
        sem_supabase=patch('pontocerto.app.db.credenciais_supabase',return_value={})
        sem_auth=patch('pontocerto.config.credenciais_supabase',return_value={})
        sem_supabase.start();sem_auth.start()
        self.addCleanup(sem_supabase.stop);self.addCleanup(sem_auth.stop)
        app=criar_app_completo(cfg,root=self.root,admins=[])
        with TestClient(app) as c:
            self.assertEqual(c.get('/',follow_redirects=False).status_code,303)
            body={'email':'test@example.com','password':'Teste@1234'}
            c.post('/api/auth/register',json=body);c.post('/api/auth/login',json=body)
            self.assertTrue(c.get('/api/saude').json()['modelo']['carregado'])
            self.assertEqual(c.get('/financeiro').status_code,404)
            html=c.get('/').text
            self.assertNotIn('data-pagina="treinamento"',html)
            self.assertNotIn('data-pagina="testar"',html)
            self.assertIn('historico-dia',html)
            self.assertIn('data-pagina="lotes"',html)
            self.assertNotIn('/gestao#equipe',html)
            self.assertEqual(c.get('/gestao',follow_redirects=False).headers['location'],'/#lotes')
            self.assertIn('id="foto-camera"',html)
            self.assertEqual(c.get('/manifest.webmanifest').status_code,200)
            image=io.BytesIO();Image.new('RGB',(224,224),'gray').save(image,format='PNG')
            response=c.post('/api/analisar',files={'arquivo':('teste.png',image.getvalue(),'image/png')})
            data=response.json()
            self.assertNotIn('erro',data)
            self.assertTrue(data['heatmap'].startswith('data:image/'))
            self.assertTrue(data['evento_id'])
            event=c.get('/api/eventos').json()['eventos'][0]
            self.assertEqual(event['origem'],'upload')
            self.assertEqual(c.get(event['imagem']).status_code,200)
            review=c.post(f'/api/eventos/{event["id"]}/conferencia',json={'classe':event['classe_key'],'decisao':'confirmada','observacao':'Ensaio com imagem sintética, sem avaliar acurácia'})
            self.assertEqual(review.status_code,200)
            self.assertEqual(review.json()['evento']['revisao_humana']['autor'],'test@example.com')
            corrected=c.post(f'/api/eventos/{event["id"]}/conferencia',json={'classe':'crooked_seam','decisao':'corrigida','observacao':'Conferência da classe real'})
            self.assertEqual(corrected.json()['evento']['nome_final'],'Costura torta')
            diagnosis=c.post(f'/api/eventos/{event["id"]}/diagnostico',json={'usar_llm':False}).json()
            self.assertEqual(diagnosis['diagnostico']['classe_key'],'crooked_seam')
            self.assertEqual(c.get('/api/eventos?classe=crooked_seam').json()['eventos'][0]['id'],event['id'])
            pdf=c.get('/api/relatorios/pdf')
            self.assertTrue(pdf.content.startswith(b'%PDF'))
            resumo=c.get('/api/relatorios/resumo').json()
            self.assertEqual((resumo['total'],resumo['conferidas'],resumo['corrigidas']),(1,1,1))
            # A peça corrigida conta como "Costura torta" nos números de hoje e no relatório.
            self.assertEqual(resumo['defeitos_por_tipo'][0]['nome'],'Costura torta')
            self.assertEqual(c.get('/api/status').json()['estatisticas']['por_classe']['crooked_seam'],1)
            semana=c.get('/api/relatorios/resumo',params={'de':'2020-01-01','ate':'2020-01-07'}).json()
            self.assertEqual((semana['de'],semana['total']),('2020-01-01',0))
            self.assertTrue(c.get('/api/relatorios/pdf',params={'de':'2020-01-01','ate':'2099-01-01'}).content.startswith(b'%PDF'))
            minha=c.get('/api/perfil/atividade').json()
            self.assertEqual((minha['hoje'],minha['total'],minha['corrigidas']),(1,1,1))
            self.assertEqual(minha['ultimas'][0]['nome'],'Costura torta')
            inicio=c.get('/api/inicio').json()
            self.assertEqual((inicio['hoje']['total'],inicio['lotes']),(1,[]))
            # A origem real da captura fica registrada.
            c.post('/api/analisar',files={'arquivo':('cam.png',image.getvalue(),'image/png')},data={'origem':'camera_aparelho'})
            self.assertEqual(c.get('/api/eventos').json()['eventos'][0]['origem'],'camera_aparelho')
            # Trocar a classe sempre grava "corrigida", mesmo que o pedido diga "confirmada".
            last=c.get('/api/eventos').json()['eventos'][0]
            other='crooked_seam' if last['classe_key']!='crooked_seam' else 'normal'
            saved=c.post(f'/api/eventos/{last["id"]}/conferencia',json={'classe':other,'decisao':'confirmada'}).json()
            self.assertEqual(saved['evento']['revisao_humana']['decisao'],'corrigida')
            self.assertFalse(any(e['id']==last['id'] for e in c.get('/api/eventos?pendentes=true').json()['eventos']))
            # Excluir a peça tira do histórico, dos números e apaga a foto.
            antes=c.get('/api/relatorios/resumo').json()['total']
            foto_peca=self.root/'capturas'/(last['id']+'.jpg')
            self.assertEqual(c.delete(f'/api/eventos/{last["id"]}').status_code,200)
            self.assertFalse(any(e['id']==last['id'] for e in c.get('/api/eventos').json()['eventos']))
            self.assertEqual(c.get('/api/relatorios/resumo').json()['total'],antes-1)
            self.assertFalse(foto_peca.exists())
            self.assertEqual(c.delete(f'/api/eventos/{last["id"]}').status_code,404)
            # Ajustes ficam gravados em disco para valer depois de reiniciar.
            c.post('/api/ajustes',json={'meta_pecas':77})
            self.assertTrue((self.root/'ajustes.json').exists())
        with TestClient(app) as c:
            c.post('/api/auth/login',json=body)
            self.assertEqual(c.get('/api/ajustes').json()['meta_pecas'],77)
            # Sem Supabase, os lotes avisam o que falta em vez de quebrar.
            sem_banco=c.get('/api/lotes').json()
            self.assertFalse(sem_banco['disponivel']);self.assertIn('Supabase',sem_banco['erro'])
            self.assertEqual(c.post('/api/lotes',json={'codigo':'OP-1','cliente':'X','quantidade':1}).status_code,503)
            # Com o banco (aqui, um falso em memória): criar, inspecionar, concluir e baixar o PDF.
            app.state.banco=BancoFalso()
            self.assertEqual(c.post('/api/lotes',json={'codigo':'','cliente':'X','quantidade':1}).status_code,422)
            criado=c.post('/api/lotes',json={'codigo':'OP-900','cliente':'Cliente A','quantidade':100})
            self.assertEqual(criado.status_code,201,criado.text)
            lote=criado.json()['lote']
            self.assertEqual((lote['codigo'],lote['cliente'],lote['quantidade'],lote['inspecionadas']),('OP-900','Cliente A',100,0))
            self.assertEqual(c.post('/api/lotes',json={'codigo':'op-900','cliente':'B','quantidade':5}).status_code,409)
            self.assertEqual(c.get('/api/lotes/clientes').json()['clientes'],['Cliente A'])
            ativo=c.post(f'/api/lotes/{lote["id"]}/inspecionar',json={}).json()['lote']
            self.assertEqual((ativo['id'],ativo['codigo']),(lote['id'],'OP-900'))
            c.post('/api/analisar',files={'arquivo':('lote.png',image.getvalue(),'image/png')})
            self.assertEqual(c.get('/api/eventos').json()['eventos'][0]['lote_codigo'],'OP-900')
            detalhe=c.get(f'/api/lotes/{lote["id"]}').json()
            self.assertTrue(detalhe['lote']['ativo'])
            self.assertEqual(detalhe['defeitos'],[{'classe':'crooked_seam','nome':'Costura torta','quantidade':2}])
            self.assertTrue(c.get(f'/api/lotes/{lote["id"]}/pdf').content.startswith(b'%PDF'))
            # Concluir tira o lote da lista em aberto e para de gravar nele.
            self.assertTrue(c.post(f'/api/lotes/{lote["id"]}/concluir',json={}).json()['lote']['concluido'])
            self.assertIsNone(c.get('/api/lotes/ativo').json()['lote'])
            self.assertEqual(c.get('/api/lotes').json()['lotes'],[])
            self.assertEqual(len(c.get('/api/lotes?todos=true').json()['lotes']),1)
            self.assertEqual(c.post(f'/api/lotes/{lote["id"]}/inspecionar',json={}).status_code,409)
            c.post(f'/api/lotes/{lote["id"]}/reabrir',json={})
            c.post(f'/api/lotes/{lote["id"]}/inspecionar',json={})
            c.post('/api/lotes/ativo',json={})
            self.assertIsNone(c.get('/api/lotes/ativo').json()['lote'])
        # O modelo foi executado; a imagem sintética não comprova acurácia em costura.
