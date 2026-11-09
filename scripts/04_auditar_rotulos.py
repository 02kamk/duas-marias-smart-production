"""Ponto Certo - etapa 04: auditoria de rotulos com o LLM multimodal (opcional).

Sorteia imagens do conjunto de TREINO, envia cada uma ao modelo de visao do
OpenRouter junto com o rotulo original e pergunta se o rotulo faz sentido. O
resultado vai para artifacts/auditoria_rotulos.csv, com as imagens suspeitas
ordenadas para revisao humana.

Este e o papel (1) do LLM no projeto: melhorar o DADO que alimenta a CNN antes
do treino. O LLM nao treina a rede e nao decide nada em producao.

Etapa OPCIONAL: precisa de OPENROUTER_API_KEY no arquivo .env e consome
creditos. Sem chave, o resto do sistema funciona normalmente.

Este arquivo e so o atalho de linha de comando. A logica de verdade esta em
src/pontocerto/llm/auditoria.py.

Uso:
    python scripts/04_auditar_rotulos.py --dry-run     # plano e custo, sem gastar
    python scripts/04_auditar_rotulos.py
    python scripts/04_auditar_rotulos.py --amostras 20
    python scripts/04_auditar_rotulos.py --saida artifacts/auditoria_rotulos.csv
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

CABECALHO = """
================================================================================
  PONTO CERTO  |  ETAPA 04 - AUDITAR ROTULOS (opcional, usa o LLM)
  O modelo de visao revisa amostras do conjunto de treino e aponta suspeitas
================================================================================
"""

AJUDA_IMPORT = """
Nao consegui importar 'pontocerto.llm.auditoria'.

Possiveis causas e solucoes:

  1. Dependencias faltando (httpx, pandas, tqdm):
         pip install -r requirements.txt

  2. O manifesto ainda nao foi gerado (a auditoria sorteia do split 'treino'):
         python scripts/01_preparar_dados.py

  3. Voce esta fora da pasta do projeto. Entre na pasta 'pontocerto'
     (a que contem o config.yaml) e rode de novo.

Lembrete: esta etapa e opcional. Ela so funciona com OPENROUTER_API_KEY
configurada no arquivo .env (copie o .env.example). Sem chave, pule direto
para 'python scripts/02_treinar.py'.
"""


def main() -> int:
    print(CABECALHO)
    try:
        from pontocerto.llm.auditoria import main as etapa
    except ImportError as exc:
        print(f"[erro] {type(exc).__name__}: {exc}")
        print(AJUDA_IMPORT)
        return 1

    try:
        from pontocerto.config import chave_openrouter

        if not chave_openrouter() and "--dry-run" not in sys.argv[1:]:
            print("[!] OPENROUTER_API_KEY nao encontrada.")
            print("    Copie o .env.example para .env e coloque a sua chave")
            print("    (gere em https://openrouter.ai/keys).")
            print("    Para so ver o plano sem chamar o LLM, use --dry-run.")
            print()
    except Exception:
        pass

    etapa(sys.argv[1:])
    print()
    print("[ok] Etapa 04 concluida. Revise o CSV antes de retreinar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
