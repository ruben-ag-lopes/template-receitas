import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.recipe_parser import RecipeParseError, txt_to_recipe

VALID_TXT = """
TITULO: Sopa de Tomate
PORCOES: 2
TEMPO: 25 min
TAGS: sopa, vegetariano
INGREDIENTES:
- 6 tomates maduros
- 1 cebola
- 2 colheres de azeite
PASSOS:
- Refogue a cebola no azeite
- Junte os tomates e cozinhe 15 min
- Triture e sirva
"""


def test_parses_valid_recipe():
    recipe = txt_to_recipe(VALID_TXT)
    assert recipe.title == "Sopa de Tomate"
    assert recipe.servings == "2"
    assert recipe.time == "25 min"
    assert recipe.tags == ("sopa", "vegetariano")
    assert len(recipe.ingredients) == 3
    assert recipe.ingredients[0] == "6 tomates maduros"
    assert len(recipe.steps) == 3
    assert recipe.steps[-1] == "Triture e sirva"


def test_missing_title_raises():
    text = VALID_TXT.replace("TITULO: Sopa de Tomate", "")
    with pytest.raises(RecipeParseError, match="TITULO"):
        txt_to_recipe(text)


def test_missing_ingredients_raises():
    lines = [l for l in VALID_TXT.splitlines() if not l.strip().startswith("- 6") and
             not l.strip().startswith("- 1 cebola") and not l.strip().startswith("- 2 colheres")]
    text = "\n".join(lines)
    with pytest.raises(RecipeParseError, match="INGREDIENTES"):
        txt_to_recipe(text)


def test_missing_steps_raises():
    text = "TITULO: X\nPORCOES: 1\nTEMPO: 5 min\nINGREDIENTES:\n- agua\n"
    with pytest.raises(RecipeParseError, match="PASSOS"):
        txt_to_recipe(text)


def test_line_outside_section_raises():
    text = "TITULO: X\ntexto solto sem secao\n"
    with pytest.raises(RecipeParseError):
        txt_to_recipe(text)


def test_tags_optional():
    text = (
        "TITULO: Simples\nPORCOES: 1\nTEMPO: 5 min\n"
        "INGREDIENTES:\n- agua\nPASSOS:\n- ferver\n"
    )
    recipe = txt_to_recipe(text)
    assert recipe.tags == ()
