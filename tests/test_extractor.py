import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.link_ingest import TextSource
from src.recipe_extractor import extract_recipe
from src.recipe_parser import RecipeParseError, txt_to_recipe


def caption(text: str) -> TextSource:
    return TextSource(origin="legenda", text=text, by_author=True)


def author_comment(text: str) -> TextSource:
    return TextSource(origin="comentario de @chef (autor)", text=text, by_author=True)


def stranger_comment(text: str, likes: int = 0) -> TextSource:
    return TextSource(origin="comentario de @alguem", text=text, likes=likes)


def video_text(text: str) -> TextSource:
    return TextSource(origin="texto no video (OCR)", text=text, by_author=True, kind="ocr")


LEGENDA_COMPLETA = """
Bolo de Cenoura da Avo
Tempo: 45 min

INGREDIENTES:
- 3 cenouras medias
- 2 chavenas de farinha
- 1 chavena de acucar
- 3 ovos

MODO DE PREPARO:
1. Triture as cenouras com os ovos
2. Junte a farinha e o acucar e misture bem
3. Leve ao forno 40 minutos

#bolo #sobremesa #reels
"""


def test_legenda_com_cabecalhos_da_receita_completa():
    draft = extract_recipe([caption(LEGENDA_COMPLETA)])
    assert draft.title == "Bolo de Cenoura da Avo"
    assert draft.time == "45 min"
    assert draft.ingredients[0] == "3 cenouras medias"
    assert len(draft.ingredients) == 4
    assert len(draft.steps) == 3
    assert draft.steps[-1] == "Leve ao forno 40 minutos"
    assert draft.missing == ()
    assert draft.is_complete


def test_tags_sao_sempre_duas_categorias_fechadas():
    from src.categories import TRAITS, TYPES

    draft = extract_recipe([caption(LEGENDA_COMPLETA)])
    assert len(draft.tags) == 2
    assert draft.tags[0] in TYPES and draft.tags[1] in TRAITS
    assert draft.tags[0] == "sobremesa"
    # as hashtags do autor nao passam a tags
    assert "reels" not in draft.tags and "bolo" not in draft.tags


def test_txt_gerado_volta_a_ser_lido_pelo_parser():
    draft = extract_recipe([caption(LEGENDA_COMPLETA)])
    recipe = txt_to_recipe(draft.to_txt())
    assert recipe.title == draft.title
    assert recipe.ingredients == draft.ingredients
    assert recipe.steps == draft.steps
    assert recipe.tags == draft.tags


def test_porcoes_nao_entra_no_txt_e_tempo_so_quando_existe():
    draft = extract_recipe([caption(LEGENDA_COMPLETA)])
    assert "PORCOES" not in draft.to_txt()
    assert "TEMPO: 45 min" in draft.to_txt()

    sem_tempo = extract_recipe([caption(
        "Tosta de abacate\nINGREDIENTES:\n- 1 abacate\n- 2 fatias de pao\n"
        "PASSOS:\n- Esmague o abacate\n- Barre no pao e sirva"
    )])
    assert sem_tempo.time == ""
    assert "TEMPO" not in sem_tempo.to_txt()
    assert sem_tempo.is_complete  # o tempo e opcional: nao impede o PDF


def test_imagem_entra_no_txt_quando_ha_foto():
    draft = extract_recipe([caption(LEGENDA_COMPLETA)]).with_image("recipes/images/bolo.jpg")
    assert "IMAGEM: recipes/images/bolo.jpg" in draft.to_txt()
    assert txt_to_recipe(draft.to_txt()).image == "recipes/images/bolo.jpg"


def test_sem_passos_o_parser_recusa():
    """Os passos sao obrigatorios: sem eles nao se gera PDF."""
    draft = extract_recipe([caption("Panquecas\nINGREDIENTES:\n- 1 ovo\n- 100 g de farinha")])
    assert "PASSOS" in draft.missing
    assert not draft.is_complete
    with pytest.raises(RecipeParseError, match="PASSOS"):
        txt_to_recipe(draft.to_txt())


def test_receita_no_comentario_do_autor():
    """Legenda so com gancho; a receita esta no comentario do autor."""
    sources = [
        caption("O melhor puré de sempre! Receita nos comentarios"),
        stranger_comment("que bom, vou fazer!"),
        author_comment(
            "Ingredientes:\n"
            "- 1 kg de batata\n"
            "- 200 ml de leite\n"
            "- 50 g de manteiga\n"
            "Preparo:\n"
            "- Coza as batatas 20 minutos\n"
            "- Esmague com a manteiga e o leite\n"
        ),
    ]
    draft = extract_recipe(sources)
    assert draft.title == "O melhor puré de sempre"
    assert len(draft.ingredients) == 3
    assert len(draft.steps) == 2
    assert "autor" in draft.origins["INGREDIENTES"]
    assert "autor" in draft.origins["PASSOS"]


def test_comentario_de_terceiros_nao_define_tempo():
    sources = [
        caption("Tarte de maca\nINGREDIENTES:\n- 4 macas\n- 1 massa folhada"),
        stranger_comment("comi isto em 15 min, dava para 12 pessoas", likes=99),
    ]
    draft = extract_recipe(sources)
    assert draft.time == ""


def test_prosa_a_seguir_a_lista_nao_entra_nos_ingredientes():
    text = (
        "Snack facil\n"
        "INGREDIENTES:\n"
        "- 200 g de lentilhas\n"
        "- 2 colheres de azeite\n"
        "Ideal para ter um snack em casa ou para juntar a uma entrada, facam e depois contem-me\n"
    )
    draft = extract_recipe([caption(text)])
    assert len(draft.ingredients) == 2
    assert all("snack em casa" not in i for i in draft.ingredients)


def test_marcadores_em_emoji_sem_cabecalho():
    text = (
        "Molho verde rapido\n"
        "\U0001F7E2 1 abacate\n"
        "\U0001F7E2 2 colheres de sumo de limao\n"
        "\U0001F7E2 1 dente de alho\n"
        "\U0001F7E2 sal q.b.\n"
    )
    draft = extract_recipe([caption(text)])
    assert len(draft.ingredients) == 4
    assert draft.ingredients[0] == "1 abacate"


def test_texto_do_video_fornece_os_passos_que_faltam():
    """O OCR vem sem marcadores: cada frase com verbo de cozinha vale um passo."""
    sources = [
        caption("CHIPS DE LENTILHAS\nINGREDIENTES:\n- 200 g de lentilhas\n- 150 ml de agua"),
        video_text(
            "chips de lentilhas\n"
            "Demolhe as lentilhas durante 8 horas\n"
            "Triture com a agua ate ficar um pure\n"
            "Leve ao forno 25 minutos a 180 graus\n"
            "SEGUE PARA MAIS RECEITAS\n"
        ),
    ]
    draft = extract_recipe(sources)
    assert len(draft.steps) == 3
    assert draft.steps[0].startswith("Demolhe")
    assert draft.origins["PASSOS"] == "texto no video (OCR)"
    assert draft.origins["INGREDIENTES"] == "legenda"
    assert all("SEGUE" not in s for s in draft.steps)
    assert draft.is_complete


def test_video_so_com_legendas_de_uma_palavra_em_maiusculas():
    """Caso real: cada fotograma so mostra uma palavra, um imperativo com
    pronome colado ("SACATELOS") tipico de reels em espanhol -- nao bate em
    nenhum verbo da lista fixa, tem de se reconhecer pelo padrao ortografico."""
    sources = [
        caption(
            "Bombones de chocolate\nINGREDIENTES:\n- 200 g de chocolate\n- 100 g de mani"
        ),
        video_text("DERRITE\nMÉZCLALO\nCONGELA\nSÁCATELOS\n"),
    ]
    draft = extract_recipe(sources)
    assert "Sácatelos" in draft.steps
    assert draft.is_complete
    # legenda em maiusculas vira frase normal, para nao destoar no PDF
    assert all(not s.isupper() for s in draft.steps)


def test_video_reconhece_imperativos_de_poner_sem_acento():
    """"ponlo"/"pongan" nao levam acento (a silaba tonica nao muda) e por isso
    nao batem no padrao ortografico de _has_command_word -- tem de estar na
    lista de verbos. Caso real: legenda de video so com "PONGAN"."""
    sources = [
        caption("Bombones\nINGREDIENTES:\n- 200 g de chocolate\n- 100 g de cacahuetes"),
        video_text("PONGAN\nSÁCATELOS\n"),
    ]
    draft = extract_recipe(sources)
    assert "Pongan" in draft.steps
    assert "Sácatelos" in draft.steps


def test_comando_com_pronome_colado_reconhecido_por_padrao():
    from src.recipe_extractor import _has_command_word

    for word in ("sácalo", "sácatelos", "mézclalo", "congélalo", "tritúralo", "déjalo"):
        assert _has_command_word(word), word
    # palavras comuns com o mesmo sufixo mas sem acento nao devem disparar
    for word in ("chocolate", "aceite", "parte", "gente"):
        assert not _has_command_word(word), word


LEGENDA_REAL = (
    "CHIPS CROCANTES... \U0001F7E1¿DE LENTEJAS? \n"
    "Si pensaban que las lentejas eran solo para guisos o ensaladas... tienen que probar esto.\n"
    "Quedan finitas, bien crocantes y son perfectas para comer solas.\n"
    "➖\n"
    " INGREDIENTES:\n"
    " • 200 g de lentejas \n"
    " • 150 ml de agua \n"
    " • 2 cucharadas de aceite de oliva \n"
    " • Sal y pimienta \n"
    " • Especias a gusto \n"
    "➖\n"
    "Ideal para tener un snack casero o para sumar a una picada, haganlo y despues me cuenta \n"
    "➖\n"
    "#recetas #recetasfaciles #healthy #saludable #food"
)


def test_legenda_real_do_reel():
    """Caso real: a legenda tem ingredientes mas os passos so existem no video."""
    draft = extract_recipe([caption(LEGENDA_REAL)])
    assert draft.title == "Chips Crocantes de Lentejas"
    assert draft.ingredients == (
        "200 g de lentejas",
        "150 ml de agua",
        "2 cucharadas de aceite de oliva",
        "Sal y pimienta",
        "Especias a gusto",
    )
    assert draft.steps == ()
    assert draft.missing == ("PASSOS",)
    assert draft.tags == ("snack", "saudavel")
    assert draft.origins["INGREDIENTES"] == "legenda"


def test_sem_fontes_devolve_rascunho_vazio():
    draft = extract_recipe([])
    assert set(draft.missing) == {"TITULO", "INGREDIENTES", "PASSOS"}


# --- cobertura em ingles: o sistema tem de funcionar tao bem em pt/es/en ---


def test_legenda_em_ingles_completa():
    text = (
        "Crispy Baked Chicken Thighs\n"
        "Ready in 35 min\n"
        "INGREDIENTS:\n"
        "- 4 chicken thighs\n"
        "- 2 tbsp olive oil\n"
        "DIRECTIONS:\n"
        "1. Preheat the oven to 200C\n"
        "2. Bake for 30 minutes until crispy\n"
        "#chicken #dinner #easyrecipe\n"
    )
    draft = extract_recipe([caption(text)])
    assert draft.title == "Crispy Baked Chicken Thighs"
    assert draft.time == "35 min"
    assert len(draft.ingredients) == 2
    assert len(draft.steps) == 2
    assert draft.is_complete


def test_cta_em_ingles_nao_vira_titulo():
    text = (
        "Save this for later! You need this easy pasta recipe\n"
        "INGREDIENTS:\n"
        "- 200g pasta\n"
        "- 2 cloves garlic\n"
        "PASSOS:\n"
        "- Cook pasta\n"
        "- Add garlic\n"
        "Follow for more recipes like this\n"
    )
    draft = extract_recipe([caption(text)])
    assert draft.title == "You need this easy pasta recipe"
    assert "Follow" not in draft.title and "Save" not in draft.title


def test_unidades_em_ingles_sem_marcador():
    """Sem bullet nem numero a abrir, so a palavra da unidade identifica a linha."""
    text = "Steak\nINGREDIENTS:\nPinch of salt\nClove of garlic\nSplash of oil\nPASSOS:\n- Cook it\n"
    draft = extract_recipe([caption(text)])
    assert draft.ingredients == ("Pinch of salt", "Clove of garlic", "Splash of oil")


# --- campos do template de caderno (Serves, Temp, Prep/Cook time) ----------


def test_extrai_todos_os_campos_do_template():
    text = (
        "Bolo de Cenoura da Avo\n"
        "Rende 8 porcoes | Prep: 15 min\n"
        "INGREDIENTES:\n"
        "- 3 cenouras\n"
        "- 2 chavenas de farinha\n"
        "PASSOS:\n"
        "- Triture as cenouras\n"
        "- Leve ao forno a 180 graus durante 40 minutos\n"
    )
    draft = extract_recipe([caption(text)])
    assert draft.servings == "8"
    assert draft.time == "15 min"
    assert draft.cook_time == "40 min"
    assert draft.temperature == "180 C"


def test_campos_do_template_entram_no_txt():
    draft = extract_recipe([caption(
        "Tarte\nServes 4\nINGREDIENTES:\n- 1 massa\nPASSOS:\n- Hornea 25 minutos a 200C\n"
    )])
    txt = draft.to_txt()
    assert "PORCOES: 4" in txt
    assert "COZEDURA: 25 min" in txt
    assert "TEMPERATURA: 200 C" in txt


def test_origem_preenche_o_recipe_from():
    draft = extract_recipe([caption("X\nINGREDIENTES:\n- agua\nPASSOS:\n- ferver\n")])
    assert draft.with_source("@chef (instagram)").to_txt().count("ORIGEM: @chef (instagram)") == 1


def test_campos_do_template_sao_opcionais():
    """Sem indicacao nenhuma ficam vazios -- e o PDF imprime a linha em branco."""
    draft = extract_recipe([caption(
        "Agua com gas\nINGREDIENTES:\n- 1 l de agua\n- 1 limao\nPASSOS:\n- Misture tudo\n"
    )])
    assert draft.servings == "" and draft.temperature == "" and draft.cook_time == ""
    assert draft.is_complete  # nenhum deles impede a geracao do PDF


def test_nao_confunde_quantidade_com_temperatura():
    draft = extract_recipe([caption(
        "Pao\nINGREDIENTES:\n- 500 g de farinha\n- 300 ml de agua\nPASSOS:\n- Amasse bem\n"
    )])
    assert draft.temperature == ""
