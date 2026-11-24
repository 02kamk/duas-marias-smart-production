"""Ponto Certo: inspeção de costura com IA.

O sistema inteiro trabalha no horário de Brasília (UTC-3). Na Vercel o servidor
roda em UTC: sem isto, uma peça das 22h caía no dia seguinte e as horas
apareciam 3 horas adiantadas. "<-03>3" é a forma POSIX de UTC-3 e não depende
dos arquivos de fuso do sistema (o Brasil não tem horário de verão desde 2019).
PONTOCERTO_FUSO troca o fuso, se um dia for preciso.

No Windows o Python não troca o fuso do processo (time.tzset não existe): ali
vale o relógio do computador, que já está no horário de Brasília.
"""
import os as _os
import time as _time

FUSO_PADRAO = "<-03>3"


def _ajustar_fuso() -> None:
    if not hasattr(_time, "tzset"):
        return
    _os.environ["TZ"] = _os.environ.get("PONTOCERTO_FUSO") or FUSO_PADRAO
    _time.tzset()


_ajustar_fuso()
