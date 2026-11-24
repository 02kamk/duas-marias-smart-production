"""Leitura das peças pela IA de visão, com um OpenRouter falso (sem rede e sem gasto)."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from pontocerto.config import carregar_config
from pontocerto.llm.openrouter import RespostaLLM


class OpenRouterFalso:
    configurado = True
    modelo_visao = 'anthropic/claude-haiku-5.5'

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def chat(self, mensagens, modelo=None, json_schema=None, max_tokens=None, temperatura=None):
        self.pedidos.append(mensagens)
        texto = json.dumps(self.respostas.pop(0))
        return RespostaLLM(texto=texto, modelo=modelo, tokens_entrada=1500, tokens_saida=60, ms=900,
                           bruto={'usage': {'cost': 0.0005}})


DEFEITO = {'veredito': 'defeito', 'classe': 'stain_damage', 'confianca': 0.9,
           'onde': {'x': 0.2, 'y': 0.1, 'largura': 0.1, 'altura': 0.05}, 'explicacao': 'Fio solto rosa sobre o tecido.'}
NORMAL = {'veredito': 'aprovada', 'classe': 'normal', 'confianca': 0.95, 'onde': None, 'explicacao': 'Costura certa.'}
INCERTA = {'veredito': 'incerta', 'classe': 'normal', 'confianca': 0.8, 'onde': None, 'explicacao': 'Pode ser sombra.'}


class LeituraIATest(unittest.TestCase):
    def test_foto_lida_pela_ia_limite_e_volta_para_local(self):
        from pontocerto.principal import criar_app_completo
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = carregar_config()
            cfg.app.pasta_capturas = str(root / 'capturas')
            cfg.app.pasta_relatorios = str(root / 'relatorios')
            cfg.app.correcoes = str(root / 'correcoes.csv')
            cfg.banco['lote_ativo'] = str(root / 'lote_ativo.json')
            cfg.llm['leitura_limite_diario'] = 3
            with patch('pontocerto.app.db.credenciais_supabase', return_value={}), \
                 patch('pontocerto.config.credenciais_supabase', return_value={}):
                app = criar_app_completo(cfg, root=root, admins=[])
                falso = OpenRouterFalso([DEFEITO, NORMAL, INCERTA])
                with TestClient(app) as c:
                    app.state.leitura_ia._cliente = lambda: falso
                    body = {'email': 'ana@example.com', 'password': 'Senha@123'}
                    c.post('/api/auth/register', json=body); c.post('/api/auth/login', json=body)
                    self.assertEqual(c.get('/api/status').json()['leitura']['modo'], 'ia')
                    foto = io.BytesIO(); Image.new('RGB', (800, 600), 'white').save(foto, format='JPEG')

                    def enviar():
                        return c.post('/api/analisar', files={'arquivo': ('p.jpg', foto.getvalue(), 'image/jpeg')}).json()

                    d = enviar()
                    self.assertEqual((d['fonte'], d['predicao']['classe_key']), ('ia', 'stain_damage'))
                    self.assertTrue(d['heatmap'].startswith('data:image/'))
                    self.assertEqual(d['evento']['revisao_llm']['explicacao'], 'Fio solto rosa sobre o tecido.')
                    self.assertTrue(d['evento']['precisa_revisao'])
                    # Foto da peça vai junto com o quadro de referência (quando existe).
                    self.assertGreaterEqual(sum(b.get('type') == 'image_url' for b in falso.pedidos[0][0]['content']), 1)

                    d = enviar()
                    self.assertEqual(d['predicao']['classe_key'], 'normal')
                    self.assertIsNone(d['heatmap'])
                    self.assertFalse(d['evento']['precisa_revisao'])

                    d = enviar()  # incerta: parece normal, mas vai para Conferir
                    self.assertEqual(d['predicao']['classe_key'], 'normal')
                    self.assertTrue(d['evento']['precisa_revisao'])

                    uso = c.get('/api/status').json()['leitura']
                    self.assertEqual((uso['modo'], uso['chamadas'], uso['restantes']), ('local', 3, 0))
                    self.assertAlmostEqual(uso['custo_usd'], 0.0015)
                    d = enviar()  # passou do limite: lê no local e avisa
                    self.assertEqual(d['fonte'], 'local')
                    self.assertIn('Limite de 3 leituras', d['aviso'])


if __name__ == '__main__':
    unittest.main()
