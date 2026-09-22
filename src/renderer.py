import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .categories import TEMPLATE_COURSES, template_course
from .models import Recipe

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

# quantas linhas cabem em cada bloco da folha, para o resto ficar em branco
# como no caderno impresso (medido no A5 do template)
INGREDIENT_ROWS = 24  # por coluna
DIRECTION_ROWS = 15  # abaixo da fotografia
FIRST_FOLIO = 1

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def image_data_uri(image_path: str) -> str:
    """Foto do prato embebida no HTML.

    Vai como data URI para o ficheiro gerado ser autonomo: o PDF do WeasyPrint
    e o HTML de impressao levam a imagem dentro, sem depender de caminhos.
    """
    if not image_path:
        return ""
    path = Path(image_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return ""
    mime = _MIME.get(path.suffix.lower(), "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def split_ingredients(
    ingredients: tuple[str, ...], rows: int = INGREDIENT_ROWS
) -> tuple[list[str], list[str]]:
    """Reparte os ingredientes pelas duas colunas do template.

    Enche-se a coluna da esquerda antes de passar a direita, como se escreve
    no caderno, e o que sobra fica em linhas vazias para se acrescentar a mao.
    """
    left = list(ingredients[:rows])
    right = list(ingredients[rows : rows * 2])
    overflow = list(ingredients[rows * 2 :])
    right.extend(overflow)  # se nao couber, adensa-se a direita em vez de cortar

    left += [""] * max(0, rows - len(left))
    right += [""] * max(0, rows - len(right))
    return left, right


def notes_text(recipe: Recipe) -> str:
    """O que vai para a faixa NOTES: a caracteristica distintiva e as notas."""
    parts = []
    if len(recipe.tags) > 1 and recipe.tags[1]:
        parts.append(recipe.tags[1])
    if recipe.notes:
        parts.append(recipe.notes)
    return " · ".join(parts)


def recipe_to_html(recipe: Recipe, contact: str = "") -> str:
    template = _env.get_template("recipe.html")
    left, right = split_ingredients(recipe.ingredients)
    return template.render(
        recipe=recipe,
        contact=contact,
        image_src=image_data_uri(recipe.image),
        courses=TEMPLATE_COURSES,
        course=template_course(recipe.tags[0]) if recipe.tags else "",
        notes=notes_text(recipe),
        ingredients_left=left,
        ingredients_right=right,
        blank_lines=max(0, DIRECTION_ROWS - len(recipe.steps)),
        folio=FIRST_FOLIO,
    )


def html_to_pdf(html: str, output_path: Path) -> None:
    from weasyprint import HTML

    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(output_path))


def recipe_to_pdf(recipe: Recipe, output_path: Path, contact: str = "") -> None:
    html_to_pdf(recipe_to_html(recipe, contact=contact), output_path)
