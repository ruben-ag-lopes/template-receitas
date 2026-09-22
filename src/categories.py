"""Atribuicao das duas categorias de uma receita.

Cada receita leva exatamente duas tags: o tipo de prato e a caracteristica
distintiva. Os vocabularios sao fechados -- nada de hashtags do autor -- para
as receitas ficarem todas comparaveis entre si.

As tags de alergenios ("sem gluten", "sem lactose") so se atribuem quando o
texto de origem o diz por palavras: nunca se deduzem da ausencia de um
ingrediente, porque uma receita pode levar farinha sem a listar.
"""

import re
import unicodedata

TYPES = ("entrada", "prato de carne", "prato de peixe", "sobremesa", "doce", "snack")
TRAITS = ("sem gluten", "sem lactose", "ocasiao especial", "saudavel", "gordice", "assado")

DEFAULT_TYPE = "entrada"

# O template de caderno so tem quatro caixas (Starter/Main/Side-Snack/Dessert)
# e as categorias daqui sao seis -- este e o mapeamento de uma para a outra.
# "doce" cai em Dessert e "snack" em Side/Snack; os pratos de carne e de peixe
# juntam-se em Main, que e a unica caixa para prato principal.
TEMPLATE_COURSES = ("Starter", "Main", "Side/Snack", "Dessert")

_COURSE_BY_TYPE = {
    "entrada": "Starter",
    "prato de carne": "Main",
    "prato de peixe": "Main",
    "sobremesa": "Dessert",
    "doce": "Dessert",
    "snack": "Side/Snack",
}


def template_course(kind: str) -> str:
    """A caixa do template que corresponde a um tipo de prato."""
    return _COURSE_BY_TYPE.get(kind, "")

# ordem de desempate: o que e mais distintivo primeiro
_TRAIT_PRIORITY = {name: len(TRAITS) - i for i, name in enumerate(TRAITS)}

_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "prato de peixe": (
        "peixe", "peixes", "bacalhau", "salmao", "atum", "sardinha", "sardinhas",
        "polvo", "lulas", "camarao", "camaroes", "gambas", "marisco", "mariscos",
        "ameijoas", "pescada", "robalo", "dourada", "truta", "pescado", "merluza",
        "langostinos", "fish", "shrimp", "tuna", "salmon", "cod", "seafood",
    ),
    "prato de carne": (
        "carne", "frango", "galinha", "peru", "vaca", "novilho", "porco",
        "entrecosto", "bife", "costeleta", "costeletas", "lombo", "picanha",
        "alheira", "chourico", "linguica", "salsicha", "salsichas", "bacon",
        "presunto", "fiambre", "cordeiro", "borrego", "coelho", "almondegas",
        "pollo", "cerdo", "ternera", "chicken", "beef", "pork", "turkey",
        "lamb", "sausage", "ham", "steak", "albondigas",
    ),
    "sobremesa": (
        "bolo", "tarte", "torta", "mousse", "gelado", "pudim", "cheesecake",
        "tiramisu", "crumble", "semifrio", "sobremesa", "postre", "dessert",
        "cake", "pavlova", "flan", "arroz doce", "leite creme", "pastel",
    ),
    "doce": (
        "chocolate", "acucar", "mel", "caramelo", "geleia", "compota", "bolacha",
        "bolachas", "biscoito", "biscoitos", "cookie", "cookies", "donut",
        "muffin", "muffins", "panqueca", "panquecas", "crepe", "crepes",
        "waffle", "brownie", "brownies", "alfajor", "brigadeiro", "chantilly",
        "dulce", "candy", "azucar",
    ),
    "snack": (
        "snack", "snacks", "chips", "pipoca", "popcorn", "barrinha", "barritas",
        "granola", "crackers", "palitos", "nachos", "tostas", "lanche",
        "picada", "merienda", "aperitivo", "petisco", "petiscos",
    ),
    "entrada": (
        "entrada", "entradas", "tapa", "tapas", "bruschetta", "pate", "dip",
        "hummus", "humus", "guacamole", "sopa", "sopas", "salada", "saladas",
        "starter", "appetizer", "entrante", "ensalada", "caldo",
    ),
    # "creme de"/"crema de" ficaram de fora: foram pensados para sopas
    # ("crema de calabaza") mas apanhavam "crema de cacahuete", que e o
    # oposto de uma entrada. "sopa" e "caldo" ja cobrem o caso.
}

# Ordem de desempate quando duas categorias pontuam igual: da mais especifica
# para a mais generica. "entrada" fica no fim de proposito -- e tambem o valor
# por omissao, e a ganhar empates roubava as sobremesas ("Postre ... crema de
# cacahuete" empatava 1-1 e saia entrada).
_TIEBREAK_ORDER = (
    "prato de peixe",
    "prato de carne",
    "sobremesa",
    "doce",
    "snack",
    "entrada",
)

_TRAIT_WORDS: dict[str, tuple[str, ...]] = {
    # so por mencao explicita
    "sem gluten": (
        "sem gluten", "sin gluten", "gluten free", "glutenfree", "libre de gluten",
    ),
    "sem lactose": (
        "sem lactose", "sin lactosa", "lactose free", "dairy free", "sem leite",
        "vegano", "vegana", "vegan", "plant based",
    ),
    "ocasiao especial": (
        "natal", "pascoa", "aniversario", "festa", "celebracao", "casamento",
        "navidad", "pascua", "cumpleanos", "fiesta", "christmas", "easter",
        "thanksgiving", "birthday", "party", "comemorar", "ceia", "consoada",
    ),
    "saudavel": (
        "saudavel", "saludable", "healthy", "fit", "light", "low carb", "lowcarb",
        "proteico", "proteina", "nutritivo", "integral", "detox", "sem acucar",
        "sin azucar", "sugar free", "dieta",
    ),
    "gordice": (
        "frito", "fritos", "fritura", "freir", "fried", "bacon", "natas",
        "manteiga", "mantequilla", "queijo", "cheddar", "mozzarella", "creme",
        "cremoso", "caramelo", "chocolate", "condensado", "mascarpone",
        "indulgente", "nutella", "acucar",
    ),
    "assado": (
        "forno", "assado", "assada", "assar", "asado", "horno", "hornear",
        "baked", "bake", "roast", "roasted", "air fryer", "airfryer",
    ),
}


def _deaccent(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", _deaccent(text).lower())


def _count(haystack: str, words: tuple[str, ...]) -> int:
    """Conta quantas palavras/frases do vocabulario aparecem no texto.

    Uma frase com espaco ("sem lactose") tambem conta se aparecer colada
    ("semlactose") -- e assim que as hashtags costumam escrever-se em pt/es
    (#semgluten, #sinazucar), e sem isto essas pistas explicitas perdiam-se.
    """
    total = 0
    for word in words:
        if re.search(rf"\b{re.escape(word)}\b", haystack):
            total += 1
        elif " " in word and re.search(rf"\b{re.escape(word.replace(' ', ''))}\b", haystack):
            total += 1
    return total


def classify(
    title: str,
    ingredients: tuple[str, ...] = (),
    steps: tuple[str, ...] = (),
    extra: str = "",
) -> tuple[str, str]:
    """Devolve sempre (tipo de prato, caracteristica distintiva)."""
    blob = _normalize(" ".join((title, " ".join(ingredients), " ".join(steps), extra)))
    # o titulo pesa mais: e o que diz que prato e este
    weighted = blob + " " + (_normalize(title) + " ") * 2

    kind = _best_type(weighted)
    trait = _best_trait(blob)
    return kind, trait


def _best_type(text: str) -> str:
    scores = {name: _count(text, words) for name, words in _TYPE_WORDS.items()}
    best = max(scores.values())
    if best == 0:
        return DEFAULT_TYPE
    for name in _TIEBREAK_ORDER:
        if scores.get(name, 0) == best:
            return name
    return DEFAULT_TYPE


def _best_trait(text: str) -> str:
    scores = {name: _count(text, words) for name, words in _TRAIT_WORDS.items()}
    if any(scores.values()):
        return max(scores, key=lambda name: (scores[name], _TRAIT_PRIORITY[name]))
    # sem sinais nenhuns, decide-se pelo metodo de confecao
    return "assado" if _count(text, _TRAIT_WORDS["assado"]) else "saudavel"
