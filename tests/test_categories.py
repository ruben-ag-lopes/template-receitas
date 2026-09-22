import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.categories import TRAITS, TYPES, classify


def test_devolve_sempre_duas_categorias_do_vocabulario():
    kind, trait = classify("Qualquer coisa", ("agua",), ("mexa",))
    assert kind in TYPES
    assert trait in TRAITS


@pytest.mark.parametrize(
    "title, ingredients, esperado",
    [
        ("Bacalhau a Bras", ("bacalhau", "batata"), "prato de peixe"),
        ("Frango assado com limao", ("frango", "limao"), "prato de carne"),
        ("Bolo de chocolate", ("chocolate", "farinha"), "sobremesa"),
        ("Cookies de aveia", ("aveia", "mel"), "doce"),
        ("Chips de lentilhas", ("lentilhas",), "snack"),
        ("Hummus caseiro", ("grao",), "entrada"),
    ],
)
def test_tipo_de_prato(title, ingredients, esperado):
    assert classify(title, ingredients)[0] == esperado


def test_empate_nao_e_ganho_pela_categoria_generica():
    """Caso real: "Postre ... crema de cacahuete" empatava sobremesa com
    entrada e saia entrada, por ser a primeira da lista. A ordem de desempate
    vai da categoria mais especifica para a mais generica."""
    kind, _ = classify(
        "Postre Fit Sabor Snickers",
        ("Masa filo", "Crema de cacahuete", "Chocolate"),
    )
    assert kind == "sobremesa"


def test_creme_de_nao_conta_como_entrada():
    """"crema de cacahuete" e manteiga de amendoim, nao uma sopa -- por isso
    "creme de"/"crema de" sairam do vocabulario, que ja tem "sopa" e "caldo"."""
    from src.categories import _TYPE_WORDS, _count, _normalize

    assert _count(_normalize("crema de cacahuete"), _TYPE_WORDS["entrada"]) == 0
    # uma sopa a serio continua a ser reconhecida
    assert _count(_normalize("sopa de tomate"), _TYPE_WORDS["entrada"]) == 1


def test_tipo_por_omissao_quando_nada_encaixa():
    assert classify("Mistura da casa", ("agua",))[0] == "entrada"


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("receita sem gluten para todos", "sem gluten"),
        ("bolo vegano de banana", "sem lactose"),
        ("sobremesa de Natal", "ocasiao especial"),
        ("snack saudavel e proteico", "saudavel"),
        ("batatas fritas com bacon", "gordice"),
    ],
)
def test_caracteristica_distintiva(texto, esperado):
    assert classify(texto, (), (), extra=texto)[1] == esperado


@pytest.mark.parametrize(
    "hashtags, esperado",
    [
        ("#semgluten", "sem gluten"),
        ("#singluten", "sem gluten"),
        ("#semlactose", "sem lactose"),
        ("#sinlactosa", "sem lactose"),
        ("#dairyfree", "sem lactose"),
        ("#sinazucar", "saudavel"),
        ("#sugarfree", "saudavel"),
    ],
)
def test_hashtag_colada_reconhece_frase_com_espaco(hashtags, esperado):
    """Hashtags escrevem-se sem espacos (#semlactose); o vocabulario tem as
    frases com espaco ("sem lactose") -- tem de reconhecer as duas formas."""
    assert classify("Receita", (), (), extra=hashtags)[1] == esperado


def test_alergenios_nunca_se_deduzem_da_ausencia():
    """Sem farinha na lista nao basta: a tag so sai se o texto o disser."""
    kind, trait = classify("Mousse de chocolate", ("chocolate", "ovos", "natas"))
    assert trait != "sem gluten"


def test_forno_decide_quando_nao_ha_outro_sinal():
    assert classify("Legumes no forno", ("curgete",), ("leve ao forno",))[1] == "assado"
