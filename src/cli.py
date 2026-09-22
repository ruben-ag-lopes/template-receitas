import argparse
import re
import sys
import unicodedata
from pathlib import Path

from . import database
from .recipe_parser import RecipeParseError, txt_to_recipe
from .renderer import recipe_to_html, recipe_to_pdf

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "recipes" / "raw"
OUTPUT_DIR = ROOT / "recipes" / "output"
IMAGES_DIR = ROOT / "recipes" / "images"


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "receita"


def cmd_add(args: argparse.Namespace) -> int:
    src = Path(args.file)
    text = src.read_text(encoding="utf-8")
    try:
        recipe = txt_to_recipe(text, source_file=str(src))
    except RecipeParseError as e:
        print(f"Erro ao interpretar {src}: {e}", file=sys.stderr)
        return 1

    slug = slugify(recipe.title)
    raw_dest = RAW_DIR / f"{slug}.txt"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_dest.write_text(text, encoding="utf-8")

    pdf_dest = OUTPUT_DIR / f"{slug}.pdf"
    recipe_to_pdf(recipe, pdf_dest, contact=args.contact or "")
    database.save(recipe, txt=text, slug=slug, pdf_path=str(pdf_dest))
    print(f"Guardado: {raw_dest}")
    print(f"PDF gerado: {pdf_dest}")
    print("Arquivada em: recipes/receitas.db")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.txt")):
        print("Nenhuma receita guardada.")
        return 0
    for f in sorted(RAW_DIR.glob("*.txt")):
        print(f.stem)
    return 0


def cmd_regenerate(args: argparse.Namespace) -> int:
    targets = [RAW_DIR / f"{args.slug}.txt"] if args.slug else sorted(RAW_DIR.glob("*.txt"))
    if not targets:
        print("Nenhuma receita para regenerar.")
        return 0
    for raw in targets:
        if not raw.exists():
            print(f"Nao encontrada: {raw}", file=sys.stderr)
            continue
        text = raw.read_text(encoding="utf-8")
        try:
            recipe = txt_to_recipe(text, source_file=str(raw))
        except RecipeParseError as e:
            print(f"Erro ao interpretar {raw}: {e}", file=sys.stderr)
            continue
        pdf_dest = OUTPUT_DIR / f"{raw.stem}.pdf"
        recipe_to_pdf(recipe, pdf_dest, contact=args.contact or "")
        print(f"PDF regenerado: {pdf_dest}")
    return 0


def cmd_print(args: argparse.Namespace) -> int:
    raw = RAW_DIR / f"{args.slug}.txt"
    if not raw.exists():
        print(f"Nao encontrada: {raw}", file=sys.stderr)
        return 1
    text = raw.read_text(encoding="utf-8")
    try:
        recipe = txt_to_recipe(text, source_file=str(raw))
    except RecipeParseError as e:
        print(f"Erro ao interpretar {raw}: {e}", file=sys.stderr)
        return 1
    html_dest = OUTPUT_DIR / f"{raw.stem}.html"
    html_dest.parent.mkdir(parents=True, exist_ok=True)
    html_dest.write_text(recipe_to_html(recipe, contact=args.contact or ""), encoding="utf-8")
    print(f"HTML para impressao: {html_dest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="receitas", description="Gestor de receitas em PDF")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Interpreta um .txt e gera o PDF")
    p_add.add_argument("file", help="Caminho para o ficheiro .txt de origem")
    p_add.add_argument("--contact", default="", help="Texto de rodape (email/site)")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="Lista as receitas guardadas")
    p_list.set_defaults(func=cmd_list)

    p_regen = sub.add_parser("regenerate", help="Regenera PDFs a partir dos .txt guardados")
    p_regen.add_argument("slug", nargs="?", help="Slug especifico (omitir para todas)")
    p_regen.add_argument("--contact", default="", help="Texto de rodape (email/site)")
    p_regen.set_defaults(func=cmd_regenerate)

    p_print = sub.add_parser("print", help="Gera HTML pronto para imprimir/exportar via browser")
    p_print.add_argument("slug", help="Slug da receita guardada")
    p_print.add_argument("--contact", default="", help="Texto de rodape (email/site)")
    p_print.set_defaults(func=cmd_print)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
