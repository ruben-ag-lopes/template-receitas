"""Arquivo das receitas em SQLite (recipes/receitas.db).

Porque SQLite: vem com o Python, nao precisa de servidor nem de dependencias
novas, e um ficheiro so que se copia ou se abre em qualquer visualizador, e
guarda texto e imagem na mesma linha -- o .txt completo em TEXT e a fotografia
em BLOB. Os ficheiros em recipes/ continuam a existir; a base de dados e o
arquivo pesquisavel por cima deles.

As duas categorias ficam em colunas proprias (tag_type e tag_trait) para se
poder pesquisar "todos os snacks" ou "tudo o que e assado" sem partir strings.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Recipe

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "recipes" / "receitas.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    slug         TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    time         TEXT NOT NULL DEFAULT '',
    servings     TEXT NOT NULL DEFAULT '',
    tag_type     TEXT NOT NULL DEFAULT '',
    tag_trait    TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '',
    ingredients  TEXT NOT NULL DEFAULT '',
    steps        TEXT NOT NULL DEFAULT '',
    txt          TEXT NOT NULL,
    source_url   TEXT NOT NULL DEFAULT '',
    source_text  TEXT NOT NULL DEFAULT '',
    image        BLOB,
    image_mime   TEXT NOT NULL DEFAULT '',
    pdf_path     TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recipes_type ON recipes(tag_type);
CREATE INDEX IF NOT EXISTS idx_recipes_trait ON recipes(tag_trait);
"""

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


@dataclass(frozen=True)
class StoredRecipe:
    slug: str
    title: str
    time: str
    tag_type: str
    tag_trait: str
    txt: str
    source_url: str
    source_text: str
    created_at: str
    updated_at: str
    has_image: bool

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(t for t in (self.tag_type, self.tag_trait) if t)


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _read_image(relative: str) -> bytes:
    """Bytes da foto referida em IMAGEM:, para ficar tambem dentro da base."""
    path = Path(relative)
    if not path.is_absolute():
        path = ROOT / path
    return path.read_bytes() if path.is_file() else b""


def _now() -> str:
    # microssegundos: duas gravacoes no mesmo segundo (comum em testes e em
    # correcoes rapidas na caixa) nao podem empatar a ordenacao de list_all
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def save(
    recipe: Recipe,
    txt: str,
    slug: str,
    image: bytes = b"",
    source_url: str = "",
    source_text: str = "",
    pdf_path: str = "",
    db_path: Path | None = None,
) -> str:
    """Grava (ou atualiza) uma receita. Devolve o slug.

    Reescrever a mesma receita mantem a data de criacao e nao apaga a imagem
    que ja la estava se desta vez nao vier nenhuma.
    """
    now = _now()
    tags = ", ".join(recipe.tags)
    if not image and recipe.image:
        image = _read_image(recipe.image)
    # o mime sai do caminho em IMAGEM: quando existe; bytes passados diretamente
    # (ex: foto extraida do video, ainda sem ficheiro) vao sempre como jpeg
    mime = _MIME.get(Path(recipe.image).suffix.lower(), "image/jpeg") if recipe.image else (
        "image/jpeg" if image else ""
    )

    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT created_at, image, image_mime, source_url, source_text "
            "FROM recipes WHERE slug = ?",
            (slug,),
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        if existing:
            # gravar de novo depois de uma correcao a mao nao pode apagar o que
            # so se apurou na primeira leitura do link
            if not image:
                image, mime = existing["image"], existing["image_mime"]
            source_url = source_url or existing["source_url"]
            source_text = source_text or existing["source_text"]

        conn.execute(
            """
            INSERT INTO recipes (
                slug, title, time, servings, tag_type, tag_trait, tags,
                ingredients, steps, txt, source_url, source_text,
                image, image_mime, pdf_path, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET
                title=excluded.title, time=excluded.time, servings=excluded.servings,
                tag_type=excluded.tag_type, tag_trait=excluded.tag_trait,
                tags=excluded.tags, ingredients=excluded.ingredients,
                steps=excluded.steps, txt=excluded.txt,
                source_url=excluded.source_url, source_text=excluded.source_text,
                image=excluded.image, image_mime=excluded.image_mime,
                pdf_path=excluded.pdf_path, updated_at=excluded.updated_at
            """,
            (
                slug, recipe.title, recipe.time, recipe.servings,
                recipe.tags[0] if len(recipe.tags) > 0 else "",
                recipe.tags[1] if len(recipe.tags) > 1 else "",
                tags,
                "\n".join(recipe.ingredients), "\n".join(recipe.steps), txt,
                source_url, source_text, image, mime, pdf_path, created_at, now,
            ),
        )
    return slug


def _row_to_stored(row: sqlite3.Row) -> StoredRecipe:
    return StoredRecipe(
        slug=row["slug"],
        title=row["title"],
        time=row["time"],
        tag_type=row["tag_type"],
        tag_trait=row["tag_trait"],
        txt=row["txt"],
        source_url=row["source_url"],
        source_text=row["source_text"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        has_image=row["image"] is not None and len(row["image"]) > 0,
    )


def get(slug: str, db_path: Path | None = None) -> StoredRecipe | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE slug = ?", (slug,)).fetchone()
    return _row_to_stored(row) if row else None


def get_image(slug: str, db_path: Path | None = None) -> tuple[bytes, str]:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT image, image_mime FROM recipes WHERE slug = ?", (slug,)
        ).fetchone()
    if not row or not row["image"]:
        return b"", ""
    return bytes(row["image"]), row["image_mime"]


def list_all(
    tag: str = "", search: str = "", db_path: Path | None = None
) -> list[StoredRecipe]:
    """Receitas guardadas, das mais recentes para as mais antigas."""
    query = "SELECT * FROM recipes"
    where, params = [], []
    if tag:
        where.append("(tag_type = ? OR tag_trait = ?)")
        params += [tag, tag]
    if search:
        where.append("(title LIKE ? OR ingredients LIKE ? OR steps LIKE ?)")
        params += [f"%{search}%"] * 3
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY updated_at DESC"

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_stored(r) for r in rows]


def delete(slug: str, db_path: Path | None = None) -> bool:
    with connect(db_path) as conn:
        changed = conn.execute("DELETE FROM recipes WHERE slug = ?", (slug,)).rowcount
    return changed > 0
