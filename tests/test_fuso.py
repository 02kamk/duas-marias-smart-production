"""Horário de Brasília: hora da peça sempre pelo instante, e a correção das datas online."""
import time
import unittest
from datetime import datetime
from unittest.mock import patch

import pontocerto
from pontocerto.app.state import Evento


class FusoTest(unittest.TestCase):
    def test_hora_vem_do_instante_e_nao_do_texto_gravado(self):
        agora = time.time()
        ev = Evento(id='x', timestamp=agora, hora='23:59:59', classe_idx=0, classe_key='normal',
                    nome='Normal', confianca=0.9, gravidade='baixa')
        self.assertEqual(ev.to_dict()['hora'], datetime.fromtimestamp(agora).strftime('%H:%M:%S'))

    def test_fuso_padrao_e_utc_menos_3(self):
        self.assertEqual(pontocerto.FUSO_PADRAO, '<-03>3')
        if hasattr(time, 'tzset'):  # Linux (Vercel): o processo roda em UTC-3
            self.assertEqual(time.timezone, 3 * 3600)

    def test_correcao_das_datas_roda_uma_vez_e_preserva_timestamp(self):
        from pontocerto import nuvem
        enviados = []

        class Db:
            def execute(self, sql, params=()):
                enviados.append(nuvem.ConexaoPostgres.traduzir(sql))
                return type('C', (), {'rowcount': 2})()

        class Ctx:
            def __enter__(self):
                return Db()

            def __exit__(self, *a):
                return False

        gravado = {}
        with patch.object(nuvem, 'conexao', lambda: Ctx()), \
                patch.object(nuvem, 'ler', lambda chave, padrao=None, cache_s=0: gravado.get(chave, padrao)), \
                patch.object(nuvem, 'gravar', lambda chave, valor: gravado.__setitem__(chave, valor)):
            self.assertEqual(nuvem.corrigir_datas_fuso(), 2)
            self.assertEqual(nuvem.corrigir_datas_fuso(), 0)  # segunda vez não mexe
        self.assertEqual(len(enviados), 1)
        self.assertIn('to_timestamp("timestamp")', enviados[0])
        self.assertNotIn('""', enviados[0])
        self.assertIn("interval '3 hours'", enviados[0])


if __name__ == '__main__':
    unittest.main()
