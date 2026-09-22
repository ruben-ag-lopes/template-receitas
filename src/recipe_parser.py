"""Parser de receitas em formato .txt delimitado por campos.

Os campos correspondem ao template de caderno em duas folhas A5:

    TITULO: Nome da receita        -> RECIPE
    PORCOES: 4                     -> Serves
    TEMPERATURA: 180 C             -> Temp
    TEMPO: 15 min                  -> Prep time
    COZEDURA: 25 min               -> Cook time
    ORIGEM: @autor (instagram)     -> Recipe from
    TAGS: snack, saudavel          -> categoria do template + Notes
    NOTAS: texto livre             -> Notes
    IMAGEM: recipes/images/x.jpg   -> foto na folha das Directions
    INGREDIENTES:                  -> Ingredients
    - item 1
    PASSOS:                        -> Directions
    - passo 1

So TITULO, INGREDIENTES e PASSOS sao obrigatorios. Tudo o resto fica em
branco no PDF quando a origem nao o refere -- como no caderno impresso, para
se escrever a mao. Difficulty e Rating nao tem campo: sao juizos de quem
cozinha e ficam sempre por preencher.
"""

from .models import Recipe

_SINGLE_FIELDS = {
    "TITULO", "PORCOES", "TEMPERATURA", "TEMPO", "COZEDURA",
    "ORIGEM", "TAGS", "NOTAS", "IMAGEM",
}
_LIST_FIELDS = {"INGREDIENTES", "PASSOS"}
_ALL_HEADERS = _SINGLE_FIELDS | _LIST_FIELDS


class RecipeParseError(ValueError):
    pass


def _strip_bullet(line: str) -> str:
    line = line.strip()
    if line.startswith(("-", "*")):
        line = line[1:].strip()
    return line


def txt_to_recipe(text: str, source_file: str = "") -> Recipe:
    fields: dict[str, str] = {}
    lists: dict[str, list[str]] = {"INGREDIENTES": [], "PASSOS": []}

    current_list: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header, sep, rest = line.partition(":")
        header_key = header.strip().upper()

        if sep and header_key in _ALL_HEADERS:
            current_list = None
            if header_key in _LIST_FIELDS:
                current_list = header_key
                rest = rest.strip()
                if rest:
                    lists[current_list].append(_strip_bullet(rest))
            else:
                fields[header_key] = rest.strip()
            continue

        if current_list is not None:
            lists[current_list].append(_strip_bullet(line))
        else:
            raise RecipeParseError(
                f"Linha fora de qualquer secao conhecida: {raw_line!r}"
            )

    if not fields.get("TITULO"):
        raise RecipeParseError("Campo obrigatorio em falta: TITULO")
    if not lists["INGREDIENTES"]:
        raise RecipeParseError("Secao INGREDIENTES vazia ou em falta")
    if not lists["PASSOS"]:
        raise RecipeParseError("Secao PASSOS vazia ou em falta")

    tags_raw = fields.get("TAGS", "")
    tags = tuple(t.strip() for t in tags_raw.split(",") if t.strip())

    return Recipe(
        title=fields["TITULO"],
        ingredients=tuple(lists["INGREDIENTES"]),
        steps=tuple(lists["PASSOS"]),
        time=fields.get("TEMPO", ""),
        cook_time=fields.get("COZEDURA", ""),
        temperature=fields.get("TEMPERATURA", ""),
        servings=fields.get("PORCOES", ""),
        source=fields.get("ORIGEM", ""),
        notes=fields.get("NOTAS", ""),
        tags=tags,
        image=fields.get("IMAGEM", ""),
        source_file=source_file,
    )
