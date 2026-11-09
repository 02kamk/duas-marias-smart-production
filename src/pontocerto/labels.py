"""Taxonomia canonica do projeto Ponto Certo.

Unico lugar do sistema onde classes, tecidos e seus nomes em portugues sao
definidos. Qualquer modulo que precise converter indice <-> nome deve importar
daqui, nunca redefinir listas locais.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassInfo:
    index: int          # indice usado pelo modelo (0..10)
    key: str            # identificador estavel em snake_case
    folder: str         # nome exato da pasta no dataset
    pt: str             # nome curto em portugues (UI)
    descricao: str      # explicacao curta para o operador
    gravidade: str      # "ok" | "leve" | "media" | "alta"


CLASSES: tuple[ClassInfo, ...] = (
    ClassInfo(0, "normal", "0. Normal", "Costura normal",
              "Pontos uniformes, tensao equilibrada e alinhamento correto.", "ok"),
    ClassInfo(1, "skipped_stitch", "1. Skipped stitch", "Ponto falhado",
              "A agulha nao prendeu a linha da bobina e deixou um vao na carreira.", "alta"),
    ClassInfo(2, "broken_stitch", "2. Broken stitch", "Ponto quebrado",
              "A linha rompeu durante a costura, interrompendo a carreira de pontos.", "alta"),
    ClassInfo(3, "pinched_fabric", "3. Pinched fabric", "Tecido beliscado",
              "Uma dobra do tecido foi presa sob o calcador e costurada junto.", "alta"),
    ClassInfo(4, "crooked_seam", "4. Crooked seam", "Costura torta",
              "A carreira fugiu da linha de referencia da peca.", "media"),
    ClassInfo(5, "thread_sagging", "5. Thread sagging", "Linha frouxa",
              "Lacadas soltas por tensao insuficiente na linha superior ou da bobina.", "media"),
    ClassInfo(6, "puckering", "6. Puckering", "Franzimento",
              "O tecido enrugou ao longo da costura por tensao ou arraste desigual.", "media"),
    ClassInfo(7, "stain_damage", "7. Stain and damage", "Mancha ou dano",
              "Sujeira, oleo, furo ou rasgo no tecido na regiao da costura.", "alta"),
    ClassInfo(8, "needle_mark", "8. Needle mark", "Marca de agulha",
              "Furos visiveis deixados pela agulha, geralmente por agulha grossa ou cega.", "leve"),
    ClassInfo(9, "bobbin_pullup", "9. Bobbin thread pulling up", "Linha da bobina subindo",
              "A linha da bobina aparece na face superior por desequilibrio de tensao.", "media"),
    ClassInfo(10, "overlapped_stitch", "10. Overlapped stitch", "Ponto sobreposto",
              "Duas carreiras de pontos se sobrepoem no mesmo trecho.", "leve"),
)

NUM_CLASSES: int = len(CLASSES)
OK_INDEX: int = 0

CLASS_KEYS: tuple[str, ...] = tuple(c.key for c in CLASSES)
CLASS_FOLDERS: tuple[str, ...] = tuple(c.folder for c in CLASSES)
CLASS_NAMES_PT: tuple[str, ...] = tuple(c.pt for c in CLASSES)

_BY_INDEX = {c.index: c for c in CLASSES}
_BY_KEY = {c.key: c for c in CLASSES}
_BY_FOLDER = {c.folder: c for c in CLASSES}


@dataclass(frozen=True)
class FabricInfo:
    letter: str         # prefixo usado nos nomes de arquivo (A..K)
    folder: str         # nome exato da pasta
    pt: str             # nome em portugues
    familia: str        # "Poly" | "Core"


FABRICS: tuple[FabricInfo, ...] = (
    FabricInfo("A", "A. Cotton-Poly", "Algodao", "Poly"),
    FabricInfo("B", "B. Linen-Poly", "Linho", "Poly"),
    FabricInfo("C", "C. Denim-Poly", "Jeans", "Poly"),
    FabricInfo("D", "D. Velveteen-Poly", "Veludo cotele", "Poly"),
    FabricInfo("E", "E. Polyester-Poly", "Poliester", "Poly"),
    FabricInfo("F", "F. Satin-Core", "Cetim", "Core"),
    FabricInfo("G", "G. Chiffon-Poly", "Chiffon", "Poly"),
    FabricInfo("H", "H. Nylon-Core", "Nylon", "Core"),
    FabricInfo("I", "I. Jacquard-Poly", "Jacquard", "Poly"),
    FabricInfo("J", "J. Oxford-Core", "Oxford", "Core"),
    FabricInfo("K", "K. Polyester (coated)-Core", "Poliester revestido", "Core"),
)

NUM_FABRICS: int = len(FABRICS)
FABRIC_LETTERS: tuple[str, ...] = tuple(f.letter for f in FABRICS)
FABRIC_FOLDERS: tuple[str, ...] = tuple(f.folder for f in FABRICS)

_FAB_BY_LETTER = {f.letter: f for f in FABRICS}
_FAB_BY_FOLDER = {f.folder: f for f in FABRICS}


def class_by_index(index: int) -> ClassInfo:
    return _BY_INDEX[int(index)]


def class_by_key(key: str) -> ClassInfo:
    return _BY_KEY[key]


def class_by_folder(folder: str) -> ClassInfo:
    return _BY_FOLDER[folder]


def fabric_by_letter(letter: str) -> FabricInfo:
    return _FAB_BY_LETTER[letter.upper()]


def fabric_by_folder(folder: str) -> FabricInfo:
    return _FAB_BY_FOLDER[folder]


def is_defect(index: int) -> bool:
    """True quando o indice previsto representa uma falha (tudo que nao e Normal)."""
    return int(index) != OK_INDEX


def taxonomy_payload() -> list[dict]:
    """Serializacao usada pela API e pelo front-end."""
    return [
        {
            "index": c.index,
            "key": c.key,
            "nome": c.pt,
            "descricao": c.descricao,
            "gravidade": c.gravidade,
            "ok": c.index == OK_INDEX,
        }
        for c in CLASSES
    ]


def fabrics_payload() -> list[dict]:
    return [
        {"letra": f.letter, "nome": f.pt, "familia": f.familia, "pasta": f.folder}
        for f in FABRICS
    ]
