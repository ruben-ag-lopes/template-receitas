import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database
from src.models import Recipe


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "receitas.db"


def make_recipe(**overrides) -> Recipe:
    fields = dict(
        title="Chips de Lentilhas",
        ingredients=("200 g de lentilhas", "150 ml de agua"),
        steps=("Demolhe as lentilhas", "Leve ao forno 25 minutos"),
        time="25 min",
        tags=("snack", "saudavel"),
        image="",
    )
    fields.update(overrides)
    return Recipe(**fields)


def test_save_e_get_roundtrip(db_path):
    recipe = make_recipe()
    slug = database.save(recipe, txt=recipe.title, slug="chips-de-lentilhas", db_path=db_path)
    assert slug == "chips-de-lentilhas"

    stored = database.get(slug, db_path=db_path)
    assert stored is not None
    assert stored.title == "Chips de Lentilhas"
    assert stored.time == "25 min"
    assert stored.tags == ("snack", "saudavel")
    assert stored.has_image is False


def test_imagem_fica_gravada_como_blob(db_path):
    recipe = make_recipe()
    fake_jpeg = b"\xff\xd8\xff\xe0fake-image-bytes"
    database.save(recipe, txt="x", slug="chips", image=fake_jpeg, db_path=db_path)

    stored = database.get("chips", db_path=db_path)
    assert stored.has_image is True

    data, mime = database.get_image("chips", db_path=db_path)
    assert data == fake_jpeg
    assert mime == "image/jpeg"


def test_gravar_de_novo_sem_imagem_mantem_a_anterior(db_path):
    recipe = make_recipe()
    fake_jpeg = b"\xff\xd8\xff\xe0original"
    database.save(recipe, txt="v1", slug="chips", image=fake_jpeg, db_path=db_path)

    # segunda gravacao (ex: depois de corrigir o texto na caixa) sem nova imagem
    database.save(recipe, txt="v2 corrigido", slug="chips", db_path=db_path)

    data, _ = database.get_image("chips", db_path=db_path)
    assert data == fake_jpeg
    stored = database.get("chips", db_path=db_path)
    assert stored.txt == "v2 corrigido"


def test_gravar_de_novo_mantem_data_de_criacao(db_path):
    recipe = make_recipe()
    database.save(recipe, txt="v1", slug="chips", db_path=db_path)
    first = database.get("chips", db_path=db_path)

    database.save(recipe, txt="v2", slug="chips", db_path=db_path)
    second = database.get("chips", db_path=db_path)

    assert second.created_at == first.created_at
    assert second.txt == "v2"


def test_list_all_ordena_por_mais_recente(db_path):
    database.save(make_recipe(title="A"), txt="a", slug="a", db_path=db_path)
    database.save(make_recipe(title="B"), txt="b", slug="b", db_path=db_path)

    slugs = [r.slug for r in database.list_all(db_path=db_path)]
    assert slugs == ["b", "a"]


def test_list_all_filtra_por_categoria(db_path):
    database.save(make_recipe(title="Snack", tags=("snack", "saudavel")), txt="s", slug="snack", db_path=db_path)
    database.save(make_recipe(title="Bolo", tags=("sobremesa", "gordice")), txt="b", slug="bolo", db_path=db_path)

    snacks = database.list_all(tag="snack", db_path=db_path)
    assert [r.slug for r in snacks] == ["snack"]

    saudaveis = database.list_all(tag="saudavel", db_path=db_path)
    assert [r.slug for r in saudaveis] == ["snack"]


def test_list_all_filtra_por_pesquisa_de_texto(db_path):
    database.save(make_recipe(title="Chips de Lentilhas"), txt="x", slug="chips", db_path=db_path)
    database.save(make_recipe(title="Bolo de Cenoura", ingredients=("cenoura",), steps=("asse",)),
                   txt="y", slug="bolo", db_path=db_path)

    found = database.list_all(search="lentilhas", db_path=db_path)
    assert [r.slug for r in found] == ["chips"]


def test_delete_remove_a_receita(db_path):
    database.save(make_recipe(), txt="x", slug="chips", db_path=db_path)
    assert database.delete("chips", db_path=db_path) is True
    assert database.get("chips", db_path=db_path) is None
    assert database.delete("chips", db_path=db_path) is False


def test_imagem_referida_por_ficheiro_e_lida_automaticamente(tmp_path, db_path):
    img_path = tmp_path / "prato.jpg"
    img_path.write_bytes(b"\xff\xd8\xff\xe0from-disk")
    recipe = make_recipe(image=str(img_path))

    database.save(recipe, txt="x", slug="chips", db_path=db_path)
    data, _ = database.get_image("chips", db_path=db_path)
    assert data == b"\xff\xd8\xff\xe0from-disk"
