"""Ponto Certo - etapa 00: verificacao do ambiente.

Roda ANTES de qualquer outra coisa e responde a uma pergunta so:
"esta maquina consegue rodar o Ponto Certo agora?".

Nada aqui altera o projeto. O script apenas olha e relata:

  * versao do Python;
  * pacotes do requirements.txt instalados / faltando / abaixo da versao minima;
  * dataset no lugar (11 tecidos x 11 classes) e quantas imagens tem;
  * placa de video (se houver) e quantos nucleos de CPU o treino vai usar;
  * arquivo .env com a chave do OpenRouter;
  * manifesto artifacts/splits.csv gerado;
  * checkpoint artifacts/modelo.pt treinado;
  * webcam respondendo (tentativa curta, com release garantido).

No fim imprime o proximo comando recomendado.

Uso:
    python scripts/00_verificar_ambiente.py
    python scripts/00_verificar_ambiente.py --sem-camera     # pula o teste de webcam
    python scripts/00_verificar_ambiente.py --camera 1       # testa outro indice
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

# O OpenCV imprime avisos do backend de video direto do C++ (fora do stdout do
# Python), o que embaralha o relatorio. Silencia tudo abaixo de ERROR.
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_MSMF", "0")

PYTHON_MINIMO = (3, 10)

# Nome da distribuicao no requirements.txt -> nome do modulo a importar.
MODULO_DA_DISTRIBUICAO = {
    "torch": "torch",
    "torchvision": "torchvision",
    "opencv-python": "cv2",
    "numpy": "numpy",
    "pillow": "PIL",
    "pandas": "pandas",
    "scikit-learn": "sklearn",
    "matplotlib": "matplotlib",
    "tqdm": "tqdm",
    "pyyaml": "yaml",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "python-multipart": "multipart",
    "jinja2": "jinja2",
    "httpx": "httpx",
}

LARGURA = 78


# ---------------------------------------------------------------------------
# Impressao
# ---------------------------------------------------------------------------
class Relatorio:
    """Acumula os itens verificados e o estado geral do ambiente."""

    def __init__(self) -> None:
        self.problemas: list[str] = []
        self.avisos: list[str] = []

    def ok(self, titulo: str, detalhe: str = "") -> None:
        print(f"  [ok] {titulo}" + (f" - {detalhe}" if detalhe else ""))

    def falta(self, titulo: str, detalhe: str = "", bloqueia: bool = True) -> None:
        print(f"  [!]  {titulo}" + (f" - {detalhe}" if detalhe else ""))
        if bloqueia:
            self.problemas.append(titulo)
        else:
            self.avisos.append(titulo)


def cabecalho(texto: str) -> None:
    print()
    print("-" * LARGURA)
    print(texto)
    print("-" * LARGURA)


def banner() -> None:
    print("=" * LARGURA)
    print("  ____              _          ____          _        ")
    print(" |  _ \\ ___  _ __ | |_ ___   / ___|___ _ __| |_ ___  ")
    print(" | |_) / _ \\| '_ \\| __/ _ \\ | |   / _ \\ '__| __/ _ \\ ")
    print(" |  __/ (_) | | | | || (_) || |__|  __/ |  | || (_) |")
    print(" |_|   \\___/|_| |_|\\__\\___/  \\____\\___|_|   \\__\\___/ ")
    print()
    print("  ETAPA 00 - VERIFICACAO DO AMBIENTE")
    print("=" * LARGURA)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _versao_tupla(texto: str) -> tuple[int, ...]:
    partes: list[int] = []
    for pedaco in str(texto).split("."):
        digitos = ""
        for ch in pedaco:
            if ch.isdigit():
                digitos += ch
            else:
                break
        if not digitos:
            break
        partes.append(int(digitos))
    return tuple(partes) if partes else (0,)


def _humano(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def ler_requirements(caminho: Path) -> list[tuple[str, str]]:
    """Devolve [(distribuicao, versao_minima_ou_vazio), ...]."""
    itens: list[tuple[str, str]] = []
    if not caminho.exists():
        return itens
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        nome, _, resto = linha.partition(">=")
        nome = nome.split("==")[0].split("[")[0].strip().lower()
        if nome:
            itens.append((nome, resto.strip()))
    return itens


# ---------------------------------------------------------------------------
# Verificacoes
# ---------------------------------------------------------------------------
def checar_python(rel: Relatorio) -> None:
    cabecalho("1. Python")
    atual = sys.version_info[:3]
    texto = ".".join(str(v) for v in atual)
    if atual >= PYTHON_MINIMO:
        rel.ok(f"Python {texto}", f"{platform.system()} {platform.release()}")
    else:
        rel.falta(
            f"Python {texto} e antigo demais",
            f"o projeto pede {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} ou mais novo",
        )
    print(f"       executavel : {sys.executable}")
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        rel.ok("Ambiente virtual ativo", venv)
    else:
        rel.falta(
            "Nenhum ambiente virtual ativo",
            "recomendado: python -m venv .venv && .venv\\Scripts\\activate",
            bloqueia=False,
        )


def checar_pacotes(rel: Relatorio) -> list[str]:
    """Compara o que esta instalado com o requirements.txt."""
    cabecalho("2. Pacotes (comparando com requirements.txt)")
    from importlib import metadata as md
    from importlib.util import find_spec

    req = RAIZ / "requirements.txt"
    exigidos = ler_requirements(req)
    if not exigidos:
        rel.falta("requirements.txt nao encontrado ou vazio", str(req))
        return []

    faltando: list[str] = []
    for dist, minima in exigidos:
        modulo = MODULO_DA_DISTRIBUICAO.get(dist, dist.replace("-", "_"))
        instalada = ""
        try:
            instalada = md.version(dist)
        except Exception:
            instalada = ""

        presente = False
        try:
            presente = find_spec(modulo) is not None
        except Exception:
            presente = False

        if not instalada and not presente:
            rel.falta(f"{dist:<18} nao instalado", f"import '{modulo}' falhou")
            faltando.append(dist)
            continue

        rotulo = instalada or "versao desconhecida"
        if minima and instalada and _versao_tupla(instalada) < _versao_tupla(minima):
            rel.falta(
                f"{dist:<18} {rotulo}",
                f"abaixo do minimo {minima}",
                bloqueia=False,
            )
        else:
            extra = f"minimo {minima}" if minima else ""
            rel.ok(f"{dist:<18} {rotulo}", extra)

    if faltando:
        print()
        print("       Para instalar tudo de uma vez:")
        print("         pip install -r requirements.txt")
    return faltando


def checar_torch(rel: Relatorio) -> None:
    cabecalho("3. Torch, CPU e GPU")
    try:
        import torch
    except Exception as exc:
        rel.falta("torch nao pode ser importado", f"{type(exc).__name__}: {exc}")
        print("       Instale com: pip install -r requirements.txt")
        return

    rel.ok(f"torch {torch.__version__}")
    nucleos = os.cpu_count() or 1
    usados = max(1, nucleos - 2)
    rel.ok(f"{nucleos} nucleos de CPU", f"o treino vai usar {usados} threads")

    tem_cuda = False
    try:
        tem_cuda = bool(torch.cuda.is_available())
    except Exception:
        tem_cuda = False

    if tem_cuda:
        try:
            nome = torch.cuda.get_device_name(0)
        except Exception:
            nome = "GPU CUDA"
        rel.ok("GPU CUDA disponivel", nome)
    else:
        rel.falta(
            "Sem GPU CUDA",
            "o treino roda em CPU (mais lento, porem funciona)",
            bloqueia=False,
        )


def checar_config(rel: Relatorio):
    cabecalho("4. Configuracao")
    try:
        from pontocerto.config import carregar_config
    except Exception as exc:
        rel.falta("Nao consegui importar pontocerto.config", f"{type(exc).__name__}: {exc}")
        print("       Confira se a pasta src/pontocerto existe e se pyyaml esta instalado.")
        return None
    try:
        cfg = carregar_config()
    except Exception as exc:
        rel.falta("Falha ao ler o config.yaml", f"{type(exc).__name__}: {exc}")
        return None
    rel.ok("config.yaml lido", str(cfg["_arquivo"]))
    try:
        from pontocerto.labels import NUM_CLASSES, NUM_FABRICS

        rel.ok("Taxonomia carregada", f"{NUM_CLASSES} classes, {NUM_FABRICS} tecidos")
    except Exception as exc:
        rel.falta("Nao consegui importar pontocerto.labels", f"{type(exc).__name__}: {exc}")
    return cfg


def checar_dataset(rel: Relatorio, cfg) -> int:
    cabecalho("5. Dataset bruto")
    if cfg is None:
        rel.falta("Sem config.yaml, nao da para localizar o dataset")
        return 0
    try:
        from pontocerto.labels import CLASS_FOLDERS, FABRIC_FOLDERS
    except Exception as exc:
        rel.falta("Taxonomia indisponivel", f"{type(exc).__name__}: {exc}")
        return 0

    raiz = Path(cfg["dados"]["raiz"])
    print(f"       raiz : {raiz}")
    if not raiz.is_dir():
        rel.falta(
            "Pasta do dataset nao encontrada",
            "ajuste a chave 'dados.raiz' no config.yaml",
        )
        return 0

    total = 0
    tecidos_ok = 0
    pastas_faltando: list[str] = []
    extensoes = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    for tecido in FABRIC_FOLDERS:
        pasta_tecido = raiz / tecido
        if not pasta_tecido.is_dir():
            pastas_faltando.append(tecido)
            continue
        tecidos_ok += 1
        for classe in CLASS_FOLDERS:
            pasta_classe = pasta_tecido / classe
            if not pasta_classe.is_dir():
                pastas_faltando.append(f"{tecido}/{classe}")
                continue
            try:
                with os.scandir(pasta_classe) as entradas:
                    for entrada in entradas:
                        if entrada.is_file() and Path(entrada.name).suffix.lower() in extensoes:
                            total += 1
            except OSError as exc:
                rel.falta(f"Nao consegui ler {pasta_classe}", str(exc), bloqueia=False)

    if tecidos_ok == len(FABRIC_FOLDERS) and not pastas_faltando:
        rel.ok(
            f"{tecidos_ok} pastas de tecido, {len(CLASS_FOLDERS)} classes em cada",
            "estrutura completa",
        )
    else:
        rel.falta(
            f"{len(pastas_faltando)} pasta(s) esperada(s) nao foram encontradas",
            "; ".join(pastas_faltando[:3]) + ("..." if len(pastas_faltando) > 3 else ""),
        )

    if total:
        rel.ok(f"{_humano(total)} imagens encontradas")
    else:
        rel.falta("Nenhuma imagem encontrada no dataset")
    return total


def checar_chave(rel: Relatorio) -> bool:
    cabecalho("6. Chave do OpenRouter (opcional)")
    env = RAIZ / ".env"
    if env.exists():
        rel.ok("Arquivo .env encontrado", str(env))
    else:
        rel.falta(
            "Arquivo .env nao existe",
            "copie o .env.example para .env se quiser usar o LLM",
            bloqueia=False,
        )
    try:
        from pontocerto.config import chave_openrouter

        chave = chave_openrouter()
    except Exception as exc:
        rel.falta("Falha ao ler a chave", f"{type(exc).__name__}: {exc}", bloqueia=False)
        return False

    if chave and chave.startswith("sk-or-") and "troque" not in chave:
        rel.ok("OPENROUTER_API_KEY carregada", f"comeca com {chave[:10]}...")
        return True
    if chave:
        rel.falta(
            "OPENROUTER_API_KEY parece ser o valor de exemplo",
            "gere a sua em https://openrouter.ai/keys",
            bloqueia=False,
        )
        return False
    rel.falta(
        "Sem OPENROUTER_API_KEY",
        "o sistema funciona assim mesmo, sem diagnostico generativo, "
        "segunda opiniao e auditoria de rotulos",
        bloqueia=False,
    )
    return False


def checar_manifesto(rel: Relatorio, cfg) -> bool:
    cabecalho("7. Manifesto de divisao (artifacts/splits.csv)")
    if cfg is None:
        rel.falta("Sem config.yaml, nao da para localizar o manifesto")
        return False
    destino = Path(cfg["dados"]["manifesto"])
    if not destino.exists():
        rel.falta(
            "Manifesto ainda nao foi gerado",
            "rode: python scripts/01_preparar_dados.py",
            bloqueia=False,
        )
        return False
    try:
        with open(destino, "r", encoding="utf-8") as fh:
            cabecalho_csv = fh.readline().strip()
            linhas = sum(1 for _ in fh)
    except OSError as exc:
        rel.falta("Manifesto ilegivel", str(exc))
        return False

    rel.ok(f"{_humano(linhas)} linhas", str(destino))
    print(f"       colunas : {cabecalho_csv}")

    try:
        import pandas as pd

        df = pd.read_csv(destino, encoding="utf-8")
        contagem = df["split"].value_counts().to_dict()
        partes = "  ".join(
            f"{s}={_humano(int(contagem.get(s, 0)))}"
            for s in ("treino", "validacao", "teste")
        )
        rel.ok("Divisao", partes)
    except Exception as exc:
        rel.falta("Nao consegui resumir o manifesto", f"{type(exc).__name__}: {exc}", bloqueia=False)
    return True


def checar_modelo(rel: Relatorio, cfg) -> bool:
    cabecalho("8. Modelo treinado")
    if cfg is None:
        rel.falta("Sem config.yaml, nao da para localizar o checkpoint")
        return False
    destino = Path(cfg["treino"]["saida"])
    if not destino.exists():
        rel.falta(
            "Checkpoint ainda nao existe",
            "rode: python scripts/02_treinar.py",
            bloqueia=False,
        )
        return False

    mb = destino.stat().st_size / (1024 * 1024)
    rel.ok(f"{destino.name} ({mb:.1f} MB)", str(destino))

    try:
        import torch

        bruto = torch.load(destino, map_location="cpu", weights_only=False)
        backbone = bruto.get("backbone", "?")
        classes = len(bruto.get("classes", []) or [])
        criado = bruto.get("criado_em", "?")
        metricas = bruto.get("metricas") or {}
        rel.ok("Checkpoint valido", f"backbone={backbone}, classes={classes}, criado_em={criado}")
        if metricas:
            resumo = "  ".join(
                f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                for k, v in list(metricas.items())[:4]
            )
            print(f"       metricas: {resumo}")
    except Exception as exc:
        rel.falta("Nao consegui abrir o checkpoint", f"{type(exc).__name__}: {exc}", bloqueia=False)

    saida_avaliacao = Path(cfg["avaliacao"]["saida_dir"]) / "metricas.json"
    if saida_avaliacao.exists():
        rel.ok("Avaliacao ja executada", str(saida_avaliacao))
    else:
        rel.falta(
            "Avaliacao ainda nao executada",
            "rode: python scripts/03_avaliar.py",
            bloqueia=False,
        )
    return True


def checar_interface(rel: Relatorio) -> None:
    cabecalho("9. Interface web")
    index = RAIZ / "src" / "pontocerto" / "app" / "static" / "index.html"
    if index.exists():
        kb = index.stat().st_size / 1024
        rel.ok(f"index.html presente ({kb:.0f} KB)", str(index.parent))
    else:
        rel.falta("index.html nao encontrado", str(index), bloqueia=False)
    for modulo in ("fastapi", "uvicorn"):
        try:
            __import__(modulo)
            rel.ok(f"{modulo} importavel")
        except Exception as exc:
            rel.falta(f"{modulo} indisponivel", f"{type(exc).__name__}: {exc}")


def checar_camera(rel: Relatorio, indice: int, pular: bool) -> None:
    cabecalho("10. Camera")
    if pular:
        print("       teste pulado (--sem-camera)")
        return
    try:
        import cv2
    except Exception as exc:
        rel.falta("opencv-python indisponivel", f"{type(exc).__name__}: {exc}")
        return

    if os.name == "nt":
        backends = [("DSHOW", int(getattr(cv2, "CAP_DSHOW", 0))),
                    ("MSMF", int(getattr(cv2, "CAP_MSMF", 0))),
                    ("ANY", int(getattr(cv2, "CAP_ANY", 0)))]
    else:
        backends = [("ANY", int(getattr(cv2, "CAP_ANY", 0)))]

    print(f"       testando o indice {indice} (pode levar alguns segundos)...")
    sys.stdout.flush()
    for nome, codigo in backends:
        cap = None
        try:
            inicio = time.perf_counter()
            cap = cv2.VideoCapture(indice, codigo)
            if not cap.isOpened():
                print(f"       [..] backend {nome}: nao abriu")
                continue
            ok, quadro = cap.read()
            gasto = time.perf_counter() - inicio
            if ok and quadro is not None:
                altura, largura = quadro.shape[:2]
                rel.ok(
                    f"Camera {indice} respondeu pelo backend {nome}",
                    f"{largura}x{altura} em {gasto:.1f}s",
                )
                return
            print(f"       [..] backend {nome}: abriu mas nao entregou quadro")
        except Exception as exc:
            print(f"       [..] backend {nome}: {type(exc).__name__}: {exc}")
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    rel.falta(
        f"Nenhum backend conseguiu ler a camera {indice}",
        "feche Teams/Zoom/Camera do Windows, confira o cabo e as permissoes "
        "em Privacidade > Camera",
        bloqueia=False,
    )


# ---------------------------------------------------------------------------
# Conclusao
# ---------------------------------------------------------------------------
def proximo_comando(
    faltando: list[str],
    total_imagens: int,
    tem_manifesto: bool,
    tem_modelo: bool,
    cfg,
) -> str:
    if faltando:
        return "pip install -r requirements.txt"
    if total_imagens <= 0:
        return "ajuste a chave 'dados.raiz' no config.yaml e rode este verificador de novo"
    if not tem_manifesto:
        return "python scripts/01_preparar_dados.py"
    if not tem_modelo:
        return "python scripts/02_treinar.py"
    if cfg is not None:
        try:
            if not (Path(cfg["avaliacao"]["saida_dir"]) / "metricas.json").exists():
                return "python scripts/03_avaliar.py"
        except Exception:
            pass
    return "python scripts/05_rodar_app.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="00_verificar_ambiente",
        description="Confere se esta maquina esta pronta para rodar o Ponto Certo.",
    )
    parser.add_argument("--sem-camera", action="store_true",
                        help="pula o teste de webcam (mais rapido)")
    parser.add_argument("--camera", type=int, default=None,
                        help="indice da camera a testar (padrao: camera.indice do config.yaml)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    banner()
    rel = Relatorio()

    checar_python(rel)
    faltando = checar_pacotes(rel)
    checar_torch(rel)
    cfg = checar_config(rel)
    total_imagens = checar_dataset(rel, cfg)
    checar_chave(rel)
    tem_manifesto = checar_manifesto(rel, cfg)
    tem_modelo = checar_modelo(rel, cfg)
    checar_interface(rel)

    indice = args.camera
    if indice is None:
        try:
            indice = int(cfg["camera"]["indice"]) if cfg is not None else 0
        except Exception:
            indice = 0
    checar_camera(rel, indice, args.sem_camera)

    print()
    print("=" * LARGURA)
    print("RESUMO")
    print("=" * LARGURA)
    if rel.problemas:
        print(f"  {len(rel.problemas)} item(ns) bloqueando:")
        for item in rel.problemas:
            print(f"    - {item}")
    else:
        print("  Nenhum bloqueio: o ambiente esta pronto.")
    if rel.avisos:
        print(f"  {len(rel.avisos)} aviso(s) (nao impedem o uso):")
        for item in rel.avisos:
            print(f"    - {item}")

    comando = proximo_comando(faltando, total_imagens, tem_manifesto, tem_modelo, cfg)
    print()
    print("  PROXIMO COMANDO RECOMENDADO:")
    print(f"    {comando}")
    print("=" * LARGURA)
    return 1 if rel.problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
