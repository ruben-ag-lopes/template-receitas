"""Testes do template de caderno em duas folhas A5.

Garantem que todos os elementos do template sao preenchidos pelo gerador:
RECIPE, Serves, Temp, Prep time, Cook time, Recipe from, Difficulty, Rating,
as quatro caixas de curso, Ingredients, Notes e Directions.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.categories import TEMPLATE_COURSES, template_course
from src.models import Recipe
from src.renderer import INGREDIENT_ROWS, notes_text, recipe_to_html, split_ingredients

COMPLETA = Recipe(
    title="Bolo de Cenoura",
    ingredients=("3 cenouras", "2 chavenas de farinha", "3 ovos"),
    steps=("Triture as cenouras", "Leve ao forno"),
    time="15 min",
    cook_time="40 min",
    temperature="180 C",
    servings="8",
    source="@avo (instagram)",
    tags=("sobremesa", "gordice"),
)


@pytest.fixture
def html():
    return recipe_to_html(COMPLETA, contact="eu@exemplo.pt")


class TestCamposDoTemplate:
    def test_cabecalhos_das_seccoes(self, html):
        for titulo in ("Recipe", "Ingredients", "Directions", "Notes:"):
            assert titulo in html

    @pytest.mark.parametrize(
        "etiqueta", ["Serves:", "Temp:", "Prep time:", "Cook time:", "Recipe from:"]
    )
    def test_etiquetas_dos_campos(self, html, etiqueta):
        assert etiqueta in html

    @pytest.mark.parametrize(
        "valor", ["Bolo de Cenoura", "8", "180 C", "15 min", "40 min", "@avo (instagram)"]
    )
    def test_valores_preenchidos(self, html, valor):
        assert valor in html

    def test_ingredientes_e_passos(self, html):
        assert "3 cenouras" in html
        assert "Triture as cenouras" in html

    def test_contacto_no_rodape(self, html):
        assert "eu@exemplo.pt" in html


class TestEstrelas:
    def test_difficulty_e_rating_existem(self, html):
        assert "Difficulty" in html and "Rating" in html

    def test_estrelas_ficam_por_marcar(self, html):
        """Sao juizo de quem cozinha: o gerador desenha-as vazias, nunca as inventa."""
        assert html.count("&#9734;") == 10  # 5 + 5, todas vazias
        assert "&#9733;" not in html  # nenhuma estrela cheia


class TestCursos:
    def test_as_quatro_caixas_aparecem(self, html):
        for name in TEMPLATE_COURSES:
            assert name in html

    def test_marca_a_caixa_do_tipo_de_prato(self, html):
        assert 'class="radio on"' in html
        assert html.count('class="radio on"') == 1  # so uma marcada

    @pytest.mark.parametrize(
        "tipo, esperado",
        [
            ("entrada", "Starter"),
            ("prato de carne", "Main"),
            ("prato de peixe", "Main"),
            ("sobremesa", "Dessert"),
            ("doce", "Dessert"),
            ("snack", "Side/Snack"),
        ],
    )
    def test_mapeamento_das_seis_categorias_para_quatro(self, tipo, esperado):
        assert template_course(tipo) == esperado

    def test_sem_tags_nao_marca_nenhuma(self):
        sem_tags = Recipe(title="X", ingredients=("agua",), steps=("ferver",))
        assert 'class="radio on"' not in recipe_to_html(sem_tags)


class TestNotas:
    def test_leva_a_caracteristica_distintiva(self):
        assert notes_text(COMPLETA) == "gordice"

    def test_junta_as_notas_livres(self):
        from dataclasses import replace

        com_notas = replace(COMPLETA, notes="levar no domingo")
        assert "gordice" in notes_text(com_notas)
        assert "levar no domingo" in notes_text(com_notas)

    def test_sem_segunda_categoria_fica_vazio(self):
        so_tipo = Recipe(title="X", ingredients=("agua",), steps=("ferver",), tags=("snack",))
        assert notes_text(so_tipo) == ""


class TestColunasDeIngredientes:
    def test_enche_a_esquerda_antes_da_direita(self):
        left, right = split_ingredients(("a", "b", "c"))
        assert left[:3] == ["a", "b", "c"]
        assert right[0] == ""

    def test_linhas_vazias_completam_as_duas_colunas(self):
        left, right = split_ingredients(("a",))
        assert len(left) == INGREDIENT_ROWS
        assert len(right) == INGREDIENT_ROWS

    def test_passa_para_a_segunda_coluna_quando_a_primeira_enche(self):
        muitos = tuple(f"item {i}" for i in range(INGREDIENT_ROWS + 3))
        left, right = split_ingredients(muitos)
        assert left[-1] == f"item {INGREDIENT_ROWS - 1}"
        assert right[0] == f"item {INGREDIENT_ROWS}"

    def test_nunca_perde_ingredientes(self):
        muitos = tuple(f"item {i}" for i in range(INGREDIENT_ROWS * 2 + 5))
        left, right = split_ingredients(muitos)
        escritos = [i for i in left + right if i]
        assert len(escritos) == len(muitos)


class TestCamposEmFalta:
    def test_campos_sem_valor_ficam_em_branco_sem_rebentar(self):
        minima = Recipe(title="Agua", ingredients=("agua",), steps=("ferver",))
        html = recipe_to_html(minima)
        # as etiquetas continuam la, para se escrever a mao
        for etiqueta in ("Serves:", "Temp:", "Prep time:", "Cook time:", "Recipe from:"):
            assert etiqueta in html

    def test_sem_foto_nao_aparece_a_caixa_da_imagem(self):
        minima = Recipe(title="Agua", ingredients=("agua",), steps=("ferver",))
        assert 'class="photo"' not in recipe_to_html(minima)
