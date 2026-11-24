"""Máquinas (equipamentos) da facção e a máquina que cada pessoa está usando.

O administrador cadastra, edita e remove as máquinas em Perfil › Ajustes. Na tela
Inspecionar cada pessoa escolhe a sua, e cada peça registrada guarda o id e o
nome da máquina daquele momento (remover a máquina não apaga o histórico).

Guardado em um JSON ao lado dos ajustes; online (Vercel) em `pc_config`.
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

TIPOS_SUGERIDOS = ("Reta", "Overloque", "Galoneira", "Interloque", "Caseadeira", "Travete", "Botoneira")


def _limpar(valor, limite: int) -> str:
    return " ".join(str(valor or "").split())[:limite]


class Maquinas:
    def __init__(self, arquivo: Path, nuvem: bool = False) -> None:
        self._arquivo = Path(arquivo)
        self._nuvem = nuvem
        self._trava = threading.RLock()

    # ------------------------------------------------------------ guardar
    def _ler(self) -> dict:
        if self._nuvem:
            from pontocerto import nuvem
            return {"maquinas": nuvem.ler("maquinas", [], cache_s=0) or [],
                    "ativas": nuvem.ler("maquinas_ativas", {}, cache_s=0) or {}}
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
        except Exception:
            dados = {}
        return {"maquinas": list(dados.get("maquinas") or []), "ativas": dict(dados.get("ativas") or {})}

    def _gravar(self, dados: dict) -> None:
        if self._nuvem:
            from pontocerto import nuvem
            nuvem.gravar("maquinas", dados["maquinas"])
            nuvem.gravar("maquinas_ativas", dados["ativas"])
            return
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        temp = self._arquivo.with_suffix(".tmp")
        temp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        temp.replace(self._arquivo)

    # ------------------------------------------------------------ cadastro
    def listar(self) -> list[dict]:
        with self._trava:
            return sorted(self._ler()["maquinas"], key=lambda m: m["nome"].casefold())

    def obter(self, maquina_id: str | None) -> dict | None:
        if not maquina_id:
            return None
        return next((m for m in self.listar() if m["id"] == str(maquina_id)), None)

    def _validar(self, dados: dict, nome: str, ignorar: str | None = None) -> None:
        if not nome:
            raise ValueError("Dê um nome para a máquina.")
        if any(m["nome"].casefold() == nome.casefold() and m["id"] != ignorar for m in dados["maquinas"]):
            raise ValueError(f"Já existe uma máquina chamada {nome}.")

    def criar(self, nome: str, tipo: str = "", setor: str = "") -> dict:
        nome, tipo, setor = _limpar(nome, 60), _limpar(tipo, 40), _limpar(setor, 40)
        with self._trava:
            dados = self._ler()
            self._validar(dados, nome)
            maquina = {"id": uuid.uuid4().hex[:10], "nome": nome, "tipo": tipo or None, "setor": setor or None}
            dados["maquinas"].append(maquina)
            self._gravar(dados)
            return maquina

    def atualizar(self, maquina_id: str, nome: str, tipo: str = "", setor: str = "") -> dict | None:
        nome, tipo, setor = _limpar(nome, 60), _limpar(tipo, 40), _limpar(setor, 40)
        with self._trava:
            dados = self._ler()
            maquina = next((m for m in dados["maquinas"] if m["id"] == maquina_id), None)
            if maquina is None:
                return None
            self._validar(dados, nome, ignorar=maquina_id)
            maquina.update(nome=nome, tipo=tipo or None, setor=setor or None)
            self._gravar(dados)
            return maquina

    def remover(self, maquina_id: str) -> bool:
        with self._trava:
            dados = self._ler()
            antes = len(dados["maquinas"])
            dados["maquinas"] = [m for m in dados["maquinas"] if m["id"] != maquina_id]
            if len(dados["maquinas"]) == antes:
                return False
            dados["ativas"] = {k: v for k, v in dados["ativas"].items() if v != maquina_id}
            self._gravar(dados)
            return True

    # ------------------------------------------------- máquina de cada pessoa
    def ativa(self, email: str | None) -> dict | None:
        chave = (email or "").casefold()
        with self._trava:
            dados = self._ler()
            mid = dados["ativas"].get(chave)
            return next((m for m in dados["maquinas"] if m["id"] == mid), None) if mid else None

    def definir_ativa(self, email: str | None, maquina_id: str | None) -> dict | None:
        chave = (email or "").casefold()
        with self._trava:
            dados = self._ler()
            maquina = None
            if maquina_id:
                maquina = next((m for m in dados["maquinas"] if m["id"] == str(maquina_id)), None)
                if maquina is None:
                    raise LookupError("Máquina não encontrada. Ela pode ter sido removida.")
                dados["ativas"][chave] = maquina["id"]
            else:
                dados["ativas"].pop(chave, None)
            self._gravar(dados)
            return maquina


def quem(app: FastAPI, request: Request) -> tuple[str | None, bool]:
    """(e-mail da conta logada ou None sem login, é administrador?)."""
    email = getattr(request.state, "user", None)
    email = str(email).casefold() if email else None
    contas = getattr(app.state, "accounts", None)
    if contas is None or email is None:
        return email, True
    return email, bool(contas.eh_admin(email))


def registrar(app: FastAPI, maquinas: Maquinas) -> None:
    def erro(status: int, texto: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"erro": texto})

    def exigir_admin(request: Request):
        _, admin = quem(app, request)
        return None if admin else erro(403, "Só um administrador pode mexer nas máquinas.")

    @app.get("/api/maquinas")
    def listar(request: Request):
        email, admin = quem(app, request)
        return {"maquinas": maquinas.listar(), "ativa": maquinas.ativa(email), "admin": admin,
                "tipos": list(TIPOS_SUGERIDOS)}

    @app.post("/api/maquinas", status_code=201)
    def criar(request: Request, corpo: dict = Body(default={})):
        if (negado := exigir_admin(request)) is not None:
            return negado
        try:
            return {"maquina": maquinas.criar(corpo.get("nome"), corpo.get("tipo"), corpo.get("setor"))}
        except ValueError as exc:
            return erro(422, str(exc))

    @app.put("/api/maquinas/{maquina_id}")
    def atualizar(maquina_id: str, request: Request, corpo: dict = Body(default={})):
        if (negado := exigir_admin(request)) is not None:
            return negado
        try:
            maquina = maquinas.atualizar(maquina_id, corpo.get("nome"), corpo.get("tipo"), corpo.get("setor"))
        except ValueError as exc:
            return erro(422, str(exc))
        return {"maquina": maquina} if maquina else erro(404, "Máquina não encontrada.")

    @app.delete("/api/maquinas/{maquina_id}")
    def remover(maquina_id: str, request: Request):
        if (negado := exigir_admin(request)) is not None:
            return negado
        if not maquinas.remover(maquina_id):
            return erro(404, "Máquina não encontrada.")
        return {"ok": True}

    @app.post("/api/maquinas/ativa")
    def escolher(request: Request, corpo: dict = Body(default={})):
        email, _ = quem(app, request)
        try:
            return {"maquina": maquinas.definir_ativa(email, (corpo or {}).get("id"))}
        except LookupError as exc:
            return erro(404, str(exc))
