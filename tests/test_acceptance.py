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
from pontocerto.management.store import Store
from pontocerto.management.api import create_router
from pontocerto.management.receiving import router as receiving_router
from pontocerto.management.experiment import DelayModel


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
        secure(app,self.root)
        with TestClient(app) as c:
            self.assertEqual(c.get('/api/private').status_code,401)
            for pwd in ['abc','abcdefgh','Abcdefgh','Abcdefg1']:
                self.assertEqual(c.post('/api/auth/register',json={'email':'test@example.com','password':pwd}).status_code,422)
            body={'email':'test@example.com','password':'Teste@1234'}
            self.assertEqual(c.post('/api/auth/register',json=body).status_code,201)
            self.assertEqual(c.post('/api/auth/register',json=body).status_code,403)
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
        restored=EstadoSessao(cfg)
        self.assertEqual(restored.evento(ev.id).origem,'upload')
        self.assertEqual(len(restored.eventos(dia=date.today().isoformat(),defeitos=True)),1)
        self.assertEqual(restored.eventos(dia=(date.today()-timedelta(days=1)).isoformat()),[])
        restored.revisar_humano(ev.id,'normal','corrigida','Revisada manualmente','test@example.com')
        again=EstadoSessao(cfg)
        self.assertEqual(again.eventos(defeitos=True),[])
        self.assertEqual(again.evento(ev.id).revisao_humana['autor'],'test@example.com')

    def test_receipt_differences_and_outlook_confirmation(self):
        store=Store(self.root/'state.json')
        app=FastAPI();app.include_router(receiving_router(store))
        with TestClient(app) as c:
            body={'day':date.today().isoformat(),'grade':[{'name':'M','expected':3000,'received':2998}],
                  'supplies':[{'name':'Botão','expected':3000,'received':2900}]}
            response=c.post('/api/gestao/orders/1/receipts',json=body)
            self.assertEqual(response.status_code,201)
            receipt=response.json()
            self.assertEqual([d['difference'] for d in receipt['differences']],[-2,-100])
            self.assertEqual(store.read()['orders'][0]['produced'],1950)
            self.assertEqual(Store(self.root/'state.json').read()['receipts'][0]['id'],receipt['id'])
            url=f'/api/gestao/receipts/{receipt["id"]}/notify'
            self.assertEqual(c.post(url,json={'recipient':'test@example.com','confirm':False}).status_code,422)
            with patch('pontocerto.management.receiving.send_outlook') as send:
                self.assertEqual(c.post(url,json={'recipient':'test@example.com','confirm':True}).status_code,200)
                self.assertEqual(c.post(url,json={'recipient':'test@example.com','confirm':True}).status_code,409)
                send.assert_called_once()
            before=store.read()
            body['grade'][0]['expected']=2999
            self.assertEqual(c.post('/api/gestao/orders/1/receipts',json=body).status_code,422)
            self.assertEqual(before,store.read())

    def test_reallocation_releases_capacity_and_is_atomic(self):
        store=Store(self.root/'state.json');app=FastAPI();app.include_router(create_router(store,DelayModel(self.root/'absent')))
        with TestClient(app) as c:
            body={'orderId':'1','employeeId':'1','operation':'Gola','minutes':180,'period':date.today().isoformat(),'decision':'accepted','reason':'Revisado manualmente'}
            original=c.post('/api/gestao/assignments',json=body).json()
            url=f'/api/gestao/assignments/{original["id"]}/reallocate'
            self.assertEqual(c.post(url,json={'employeeId':'3','minutes':180,'period':body['period'],'reason':'Destino inválido'}).status_code,422)
            self.assertEqual(store.read()['assignments'][0]['employeeId'],'1')
            result=c.post(url,json={'employeeId':'2','minutes':180,'period':body['period'],'reason':'Redistribuição revisada'})
            self.assertEqual(result.status_code,200)
            self.assertEqual(len(store.read()['assignments']),1)
            rows=c.get('/api/gestao/recommendations',params={'operation':'Gola','minutes':180,'period':body['period']}).json()
            self.assertTrue(any(e['employeeId']=='1' and e['availableMinutes']==240 for e in rows['eligible']))

    def test_full_app_real_upload_and_review(self):
        from pontocerto.app.server import criar_app
        from pontocerto.management.app import extend as management
        from pontocerto.app.operational import extend as operational
        cfg=carregar_config()
        cfg.app.pasta_capturas=str(self.root/'capturas')
        cfg.app.pasta_relatorios=str(self.root/'relatorios')
        cfg.app.correcoes=str(self.root/'correcoes.csv')
        cfg.banco['lote_ativo']=str(self.root/'lote_ativo.json')
        app=operational(management(criar_app(cfg),self.root),self.root)
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
            self.assertEqual(c.get('/api/relatorios/resumo').json()['revisadas'],1)
            # Foto da OP vai como formulário e não pode ser barrada como "Envie JSON".
            op=c.post('/api/gestao/op/read',files={'arquivo':('op.png',image.getvalue(),'image/png')})
            self.assertNotEqual(op.status_code,415)
            # A origem real da captura fica registrada.
            c.post('/api/analisar',files={'arquivo':('cam.png',image.getvalue(),'image/png')},data={'origem':'camera_aparelho'})
            self.assertEqual(c.get('/api/eventos').json()['eventos'][0]['origem'],'camera_aparelho')
            # Trocar a classe sempre grava "corrigida", mesmo que o pedido diga "confirmada".
            last=c.get('/api/eventos').json()['eventos'][0]
            other='crooked_seam' if last['classe_key']!='crooked_seam' else 'normal'
            saved=c.post(f'/api/eventos/{last["id"]}/conferencia',json={'classe':other,'decisao':'confirmada'}).json()
            self.assertEqual(saved['evento']['revisao_humana']['decisao'],'corrigida')
            self.assertFalse(any(e['id']==last['id'] for e in c.get('/api/eventos?pendentes=true').json()['eventos']))
            # Ajustes ficam gravados em disco para valer depois de reiniciar.
            c.post('/api/ajustes',json={'meta_pecas':77})
            self.assertTrue((self.root/'ajustes.json').exists())
        with TestClient(app) as c:
            c.post('/api/auth/login',json=body)
            self.assertEqual(c.get('/api/ajustes').json()['meta_pecas'],77)
        # O modelo foi executado; a imagem sintética não comprova acurácia em costura.
