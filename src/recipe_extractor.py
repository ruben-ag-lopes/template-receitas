"""Interpretacao de texto livre (legenda ou comentario) para o schema de receita.

A receita de um reel tanto pode estar na legenda como num comentario do autor,
escrita com emojis a fazer de marcadores, cabecalhos em varias linguas ou sem
cabecalho nenhum. Este modulo pontua cada fonte de texto, escolhe de onde vem
cada bloco (ingredientes e passos podem vir de fontes diferentes) e monta o
.txt no schema do recipe_parser.

Nao inventa conteudo: o que nao estiver no texto fica por preencher e e
devolvido em `missing`, para a interface pedir ao utilizador antes de gravar.
"""

import re
import unicodedata
from dataclasses import dataclass, field, replace

from .categories import classify
from .link_ingest import TextSource

# --- vocabulario -----------------------------------------------------------

_ING_HEADERS = (
    "ingredientes", "ingrediente", "ingredients", "ingredient",
    "lista de ingredientes", "lista de compras", "o que precisas",
    "o que vais precisar", "vais precisar", "vou precisar", "necessario",
    "necesitas", "vas a necesitar", "lo que necesitas", "you will need",
    "you'll need", "what you need", "materiais",
)

_STEP_HEADERS = (
    "passos", "passo a passo", "modo de preparo", "modo de fazer",
    "modo de preparacao", "preparo", "preparacao", "como fazer",
    "como preparar", "como se faz", "metodo", "procedimento", "confecao",
    "paso a paso", "preparacion", "modo de preparacion", "elaboracion",
    "como se hace", "instrucciones", "instrucoes", "instructions",
    "preparation", "directions", "steps", "method", "mao na massa",
)

_UNITS = (
    "g", "gr", "gramas", "gramos", "kg", "ml", "l", "lt", "litro", "litros",
    "cl", "xicara", "xicaras", "chavena", "chavenas", "taza", "tazas",
    "cup", "cups", "colher", "colheres", "cda", "cdas", "cdita", "cditas",
    "cucharada", "cucharadas", "cucharadita", "cucharaditas", "tbsp", "tsp",
    "dente", "dentes", "diente", "dientes", "unidade", "unidades",
    "lata", "latas", "pacote", "pacotes", "pitada", "pizca", "fatia", "fatias",
    "ovo", "ovos", "huevo", "huevos", "folha", "folhas", "ramo", "punhado",
    # en -- os pt/es ja cobrem estes conceitos (pitada, dente, lata...);
    # faltavam so os equivalentes em ingles
    "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "clove",
    "cloves", "can", "cans", "pinch", "splash", "slice", "slices", "egg",
    "eggs", "sprig", "sprigs", "handful", "stick", "sticks", "tablespoon",
    "tablespoons", "teaspoon", "teaspoons", "gram", "grams", "kilogram",
    "kilograms", "liter", "liters", "package", "packet",
)
# nao entram unidades ambiguas ("un", "a"): aparecem em prosa comum e fariam
# passar frases soltas por ingredientes.

_VERBS = (
    # pt
    "misture", "misturar", "mexa", "mexer", "bata", "bater", "junte", "juntar",
    "adicione", "adicionar", "acrescente", "leve", "levar", "asse", "assar",
    "coza", "cozinhe", "cozinhar", "frite", "fritar", "refogue", "tempere",
    "temperar", "corte", "cortar", "pique", "picar", "descasque", "aqueca",
    "aquecer", "deixe", "deixar", "sirva", "servir", "retire", "retirar",
    "escorra", "reserve", "coloque", "colocar", "despeje", "unte", "polvilhe",
    "triture", "triturar", "amasse", "envolva", "forre", "regue", "demolhe",
    # es
    "mezcla", "mezclar", "agrega", "agregar", "anade", "anadir", "bate",
    "batir", "hornea", "hornear", "cocina", "cocinar", "fríe", "freir",
    "corta", "pica", "calienta", "calentar", "deja", "dejar", "remoja",
    "sirve", "retira", "escurre", "coloca", "vierte", "precalienta", "licua",
    "llevar", "procesa", "integra", "salpimenta", "salpimentar", "hidrata",
    # en
    "mix", "stir", "add", "bake", "cook", "fry", "chop", "cut", "heat",
    "let", "serve", "remove", "drain", "place", "pour", "blend", "whisk",
    "season", "preheat", "combine", "fold", "simmer", "roast", "transfer",
)

# formas curtas, tipicas de legendas de video (uma palavra por fotograma) em
# vez de frases completas -- sem estas, "CONGELA" ou "TAPA" sozinhas no ecra
# nao batem em nenhum verbo da lista principal
_SHORT_VERBS = (
    "congela", "congele", "descongela", "descongele", "derrite", "derreta",
    "funde", "funda", "tapa", "tape", "cubra", "cubre", "gira", "vire",
    "voltea", "aplana", "rellena", "recheie", "decora", "decore", "espera",
    "repite", "repita", "reserva", "saca", "tire", "vuelca", "desmolda",
    "desenforme", "enfria", "enfrie", "resfrie",
    # "poner" (colocar) -- muito comum em legendas de video e sem acento no
    # imperativo com pronome ("ponlo"), por isso nao bate no padrao ortografico
    # de _has_command_word e tem de estar aqui explicitamente
    "pon", "ponlo", "ponla", "ponlos", "ponlas", "ponle", "ponles",
    "ponga", "pongan", "ponte",
)

_CTA = (
    # pt/es
    "segue", "segui", "sigue", "siguenos", "guarda este", "guarda o",
    "guardar esta", "salva este", "salvar", "comenta", "comentario abaixo",
    "link na bio", "link en bio", "linkbio", "compartilha", "comparte",
    "etiqueta", "marca a", "manda para", "envia para", "deixa o teu like",
    "dale like", "curte", "ativa as notificacoes", "receita completa no",
    "mais receitas", "mas recetas", "eu te conto", "me cuenta", "me cuentan",
    "espero que gostem", "espero que les guste", "haganlo",
    "receita nos comentarios", "receita no comentario",
    "receta en comentarios", "receta en los comentarios",
    # en
    "follow", "save this", "save it", "link in bio", "share this",
    "share with", "comment below", "tag a friend", "tag someone",
    "double tap", "turn on notifications", "let me know", "full recipe on",
    "more recipes", "drop a", "hit follow", "smash that", "for more recipes",
)

_BULLET_CHARS = "-*•·▪▫◦‣∙+>»→▶●○☑✔✓□▢◾◽➖–—"

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U00002190-\U000021FF"
    "\U00002460-\U000024FF"
    "\U0001F1E6-\U0001F1FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200B-\U0000200D"
    "\U00002022"
    "\U000025A0-\U000025FF"
    "]+",
    flags=re.UNICODE,
)

_NUMBERED_RE = re.compile(r"^\s*\(?\d{1,2}\s*[\).:\-–]\s+")
_QTY_RE = re.compile(
    r"^\s*(\d+([.,/]\d+)?|[½¼¾⅓⅔]|meia|meio|media|medio|um|uma|un|una|dois|duas|tres)\b",
    re.IGNORECASE,
)
_HASHTAG_RE = re.compile(r"#([\wÀ-ſ]+)")


def _deaccent(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _key(text: str) -> str:
    """Forma normalizada de uma linha, para comparar com o vocabulario."""
    stripped = _EMOJI_RE.sub(" ", text)
    stripped = _deaccent(stripped).lower()
    return re.sub(r"\s+", " ", stripped.strip(" \t:.-–—*#•·|")).strip()


def _clean(text: str) -> str:
    """Limpa uma linha de conteudo: emojis, marcadores e espacos a mais."""
    out = _EMOJI_RE.sub(" ", text)
    out = out.lstrip(_BULLET_CHARS + " \t")
    out = _NUMBERED_RE.sub("", out)
    out = _HASHTAG_RE.sub("", out)
    out = out.replace("...", " ").replace("…", " ")
    out = re.sub(r"\s+", " ", out).strip(" \t-–—*:;,")
    return out


def _is_bullet(line: str) -> bool:
    raw = line.strip()
    if not raw:
        return False
    if raw[0] in _BULLET_CHARS:
        return True
    if _NUMBERED_RE.match(raw):
        return True
    return bool(_EMOJI_RE.match(raw))


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-ZÀ-ſ]+", _deaccent(text).lower()))


def _has_unit(text: str) -> bool:
    return bool(_words(text) & {_deaccent(u) for u in _UNITS})


def _has_verb(text: str) -> bool:
    return bool(_words(text) & {_deaccent(v) for v in _VERBS + _SHORT_VERBS})


_COMMAND_WORD_RE = re.compile(
    r"^[A-Za-zÀ-ÿ]*[áéíóúÁÉÍÓÚ][A-Za-zÀ-ÿ]*(lo|la|los|las|le|les|se|te)$",
    re.IGNORECASE,
)


def _has_command_word(text: str) -> bool:
    """Imperativo com pronome preso ("sácalo", "mézclalos", "congélalo").

    Comum em legendas de video em espanhol latino-americano e impossivel de
    cobrir com uma lista fixa de verbos (cada verbo combina com varios
    pronomes). Reconhece-se pelo padrao ortografico: o acento que o espanhol
    obriga a marcar quando um pronome fica colado ao imperativo.
    """
    return any(_COMMAND_WORD_RE.match(w.strip(".,!?")) for w in text.split())


def _is_quantity_line(text: str) -> bool:
    body = _clean(text)
    return bool(_QTY_RE.match(body)) or _has_unit(body)


def _is_cta(text: str) -> bool:
    """Chamada a acao ("segue-me", "guarda este reel") -- nao faz parte da receita."""
    k = _key(text)
    if not k:
        return False
    # fronteiras de palavra para "comenta" nao apanhar "comentarios" de uma frase normal
    return any(re.search(rf"\b{re.escape(c)}\b", k) for c in _CTA)


def _is_hashtags_only(text: str) -> bool:
    without = _HASHTAG_RE.sub("", _EMOJI_RE.sub("", text)).strip()
    return bool(_HASHTAG_RE.search(text)) and not without


def _match_header(line: str, headers: tuple[str, ...]) -> str | None:
    """Se a linha for um cabecalho de seccao, devolve o texto que vem a seguir."""
    k = _key(line)
    if not k or len(k) > 60:
        return None
    for header in headers:
        if k == header or k.startswith(header + " ") or k.startswith(header + ":"):
            inline = line.split(":", 1)[1].strip() if ":" in line else ""
            return inline if inline else k[len(header):].strip(" :-–—")
    return None


# --- leitura de uma fonte --------------------------------------------------


@dataclass
class SourceParse:
    origin: str
    priority: int = 1
    title: str = ""
    time: str = ""
    cook_time: str = ""
    temperature: str = ""
    servings: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    ingredients: tuple[str, ...] = field(default_factory=tuple)
    steps: tuple[str, ...] = field(default_factory=tuple)
    ing_headed: bool = False
    step_headed: bool = False

    @property
    def ing_score(self) -> float:
        if len(self.ingredients) < 2:
            return 0.0
        qty = sum(1 for i in self.ingredients if _is_quantity_line(i))
        score = len(self.ingredients) + qty
        if self.ing_headed:
            score *= 2
        return score + self.priority

    @property
    def step_score(self) -> float:
        if not self.steps:
            return 0.0
        verbs = sum(1 for s in self.steps if _has_verb(s))
        score = len(self.steps) + verbs
        if self.step_headed:
            score *= 2
        return score + self.priority


def parse_source(source: TextSource) -> SourceParse:
    """Le um bloco de texto e separa o que parecem ingredientes e passos."""
    result = SourceParse(origin=source.origin, priority=source.priority)
    if source.kind == "ocr":
        return _parse_ocr(source, result)
    lines = source.text.splitlines()

    ingredients: list[str] = []
    steps: list[str] = []
    loose: list[str] = []
    mode: str | None = None
    steps_bulleted = False

    for raw in lines:
        if not raw.strip():
            continue
        if _is_hashtags_only(raw):
            mode = None
            continue

        step_rest = _match_header(raw, _STEP_HEADERS)
        if step_rest is not None:
            mode = "step"
            result.step_headed = True
            cleaned = _clean(step_rest)
            if cleaned:
                steps.append(cleaned)
            continue

        ing_rest = _match_header(raw, _ING_HEADERS)
        if ing_rest is not None:
            mode = "ing"
            result.ing_headed = True
            cleaned = _clean(ing_rest)
            if cleaned:
                ingredients.append(cleaned)
            continue

        cleaned = _clean(raw)
        if not cleaned:
            continue

        if mode == "ing":
            # a lista termina quando aparece prosa que ja nao parece ingrediente:
            # sem marcador, so continua se for curta e comecar por quantidade
            if _is_bullet(raw) or (len(cleaned) <= 60 and _is_quantity_line(raw)):
                ingredients.append(cleaned)
                continue
            mode = None

        if mode == "step":
            bulleted = _is_bullet(raw)
            # se os passos vinham com marcadores, prosa a seguir ja e outra coisa
            # ("Serve 4 pessoas", despedidas, hashtags soltas)
            if _is_cta(raw) or (steps_bulleted and not bulleted):
                mode = None
            else:
                if bulleted and not steps:
                    steps_bulleted = True
                steps.append(cleaned)
                continue

        # entra tudo: o _guess_title filtra por frase, para nao perder o nome do
        # prato em linhas como "O melhor pure de sempre! Receita nos comentarios"
        loose.append(cleaned)

    # sem cabecalhos, procuram-se blocos de marcadores seguidos
    if not ingredients or not steps:
        for run in _bullet_runs(lines):
            cleaned_run = tuple(_clean(l) for l in run if _clean(l))
            if len(cleaned_run) < 2:
                continue
            qty_ratio = sum(1 for l in cleaned_run if _is_quantity_line(l)) / len(cleaned_run)
            verb_ratio = sum(1 for l in cleaned_run if _has_verb(l)) / len(cleaned_run)
            if not ingredients and qty_ratio >= 0.5 and qty_ratio >= verb_ratio:
                ingredients = list(cleaned_run)
            elif not steps and verb_ratio >= 0.4:
                steps = list(cleaned_run)

    result.ingredients = tuple(ingredients)
    result.steps = tuple(steps)
    result.title = _guess_title(loose)
    result.time = _guess_time(source.text, list(result.steps))
    result.cook_time = _guess_cook_time(source.text)
    result.temperature = _guess_temperature(source.text)
    result.servings = _guess_servings(source.text)
    return result


def _parse_ocr(source: TextSource, result: SourceParse) -> SourceParse:
    """Texto lido do ecra do video: sem marcadores nem cabecalhos.

    Cada linha vale por si -- uma frase com verbo de cozinha e um passo, uma
    linha com quantidade e um ingrediente. O resto e legenda de marca ou ruido.
    """
    ingredients: list[str] = []
    steps: list[str] = []

    for raw in source.text.splitlines():
        line = _clean(raw)
        if len(line) < 4 or _is_cta(line):
            continue
        if _match_header(line, _ING_HEADERS + _STEP_HEADERS) is not None:
            continue
        if _has_verb(line) or _has_command_word(line):
            steps.append(_sentence_case(line))
        elif _is_quantity_line(line) and len(line) <= 60:
            ingredients.append(_sentence_case(line))

    result.ingredients = tuple(ingredients)
    result.steps = tuple(steps)
    result.step_headed = False
    result.time = _guess_time(source.text, steps)
    result.cook_time = _guess_cook_time(source.text)
    result.temperature = _guess_temperature(source.text)
    result.servings = _guess_servings(source.text)
    return result


def _bullet_runs(lines: list[str]) -> list[list[str]]:
    runs: list[list[str]] = []
    current: list[str] = []
    for raw in lines:
        if raw.strip() and _is_bullet(raw) and not _is_hashtags_only(raw):
            current.append(raw)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


_SMALL_WORDS = {
    "de", "da", "do", "das", "dos", "e", "com", "sem", "na", "no", "nas", "nos",
    "a", "o", "as", "os", "ao", "aos", "y", "con", "sin", "la", "el", "los",
    "las", "del", "al", "of", "the", "and", "with", "in", "para", "por", "em",
}


def _titlecase(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio < 0.7:
        return text
    words = []
    for i, word in enumerate(text.split()):
        low = word.lower()
        words.append(low if i and low in _SMALL_WORDS else low.capitalize())
    return " ".join(words)


def _sentence_case(text: str) -> str:
    """Legendas de video vem quase sempre em maiusculas (estilo grafico); para
    nao destoar dos ingredientes/passos vindos de texto normal, so a primeira
    letra fica maiuscula quando a linha inteira estava em maiusculas."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio < 0.7:
        return text
    return text[0].upper() + text[1:].lower()


def _guess_title(loose: list[str]) -> str:
    """Primeira frase aproveitavel do texto: o titulo e quase sempre a abrir.

    So se olha para as linhas soltas: se a fonte for so lista de ingredientes e
    passos (tipico de um comentario com a receita), nao tem titulo nenhum -- e
    melhor deixar vazio do que promover "1 kg de batata" a nome do prato.
    """
    for candidate in loose:
        text = candidate.replace("¿", "").replace("¡", "")
        text = re.sub(r"\s+", " ", text)
        # so a primeira frase: "O melhor pure! Receita nos comentarios" -> "O melhor pure"
        for part in re.split(r"[.!?]+", text):
            part = part.strip(" .!?:;-")
            if len(part) < 4:
                continue
            if _is_cta(part):
                continue
            if _match_header(part, _ING_HEADERS + _STEP_HEADERS) is not None:
                continue
            return _titlecase(part[:80].strip())
    return ""


_TIME_LABEL_RE = re.compile(
    r"(?:tempo|tiempo|preparo|prep|total|demora|leva|listo en|lista en|pronto em|"
    r"pronta em|em apenas|en solo|ready in)"
    r"[^\d\n]{0,18}(\d+)\s*(min|mins|minutos|minutes|h|hs|hrs|horas|hours)\b",
    re.IGNORECASE,
)
_TIME_ANY_RE = re.compile(
    r"\b(\d+)\s*(min|mins|minutos|minutes|h|hs|hrs|horas|hours)\b", re.IGNORECASE
)


def _fmt_time(number: str, unit: str) -> str:
    return f"{number} h" if unit.lower().startswith("h") else f"{number} min"


def _guess_time(text: str, steps: list[str]) -> str:
    flat = _deaccent(text)
    labelled = _TIME_LABEL_RE.search(flat)
    if labelled:
        return _fmt_time(labelled.group(1), labelled.group(2))
    # sem etiqueta, so vale se houver um unico tempo no texto e fora dos passos
    steps_blob = _deaccent(" ".join(steps)).lower()
    matches = [m for m in _TIME_ANY_RE.finditer(flat) if m.group(0).lower() not in steps_blob]
    if len(matches) == 1:
        return _fmt_time(matches[0].group(1), matches[0].group(2))
    return ""


# -- campos do template: Serves, Temp, Cook time ----------------------------

_SERVING_UNITS = (
    "porcoes|porcao|porciones|porcion|pessoas|personas|doses|servings|serving"
    "|unidades|unidad|fatias|bolinhos|pancakes|muffins|people"
)
_SERVINGS_RE = re.compile(
    r"(?:(?:rende|rinde|serve|servem|sirve|sirven|para|da para|rendimento|"
    r"rendimiento|yields?|makes|serves)\s*(?:cerca de\s*|aprox\.?\s*|about\s*)?)?"
    r"(\d+\s*(?:a|-|ate|hasta|to)\s*\d+|\d+)\s*(" + _SERVING_UNITS + r")\b",
    re.IGNORECASE,
)


# "Serves 4" / "Rende 12": o verbo de rendimento dispensa a unidade a seguir.
# So verbos explicitos -- um "para 4" solto tanto pode ser porcoes como
# "corta para 4 partes".
_SERVINGS_VERB_RE = re.compile(
    r"\b(?:serves|serve|servem|sirve|sirven|rende|rinde|makes|yields?)\s*:?\s*(\d+)\b",
    re.IGNORECASE,
)


def _guess_servings(text: str) -> str:
    """Serves: "rende 4 porcoes", "serves 2", "para 6 pessoas"."""
    flat = re.sub(r"\s+", " ", _deaccent(text).lower())
    match = _SERVINGS_RE.search(flat)
    if match:
        number, unit = match.group(1).strip(), match.group(2)
        number = re.sub(r"\s*(a|-|ate|hasta|to)\s*", " a ", number)
        if unit.startswith(("porcao", "porcoes", "porcion", "porciones", "dose", "serving")):
            return number
        return f"{number} {unit}"

    verb_match = _SERVINGS_VERB_RE.search(flat)
    return verb_match.group(1) if verb_match else ""


# graus so contam com a unidade a seguir: um "200" solto e quase sempre outra
# coisa (gramas, ml, um ano), e um forno abaixo de 80 graus nao existe
_TEMP_RE = re.compile(
    r"\b(\d{2,3})\s*(?:º|°|graus|grados|degrees)?\s*(C|F)\b|"
    r"\b(\d{2,3})\s*(?:º|°)(?!\w)|"
    r"\b(\d{2,3})\s*(?:graus|grados|degrees)\b",
    re.IGNORECASE,
)


def _guess_temperature(text: str) -> str:
    """Temp: "180 graus", "200C", "180º" -- so valores plausiveis de forno.

    Le o texto original de proposito: o º (indicador ordinal) decompoe-se
    num "o" normal quando se tiram os acentos, e o simbolo perder-se-ia.
    """
    for match in _TEMP_RE.finditer(text):
        number = next(g for g in (match.group(1), match.group(3), match.group(4)) if g)
        scale = (match.group(2) or "C").upper()
        value = int(number)
        if scale == "C" and not 80 <= value <= 300:
            continue
        if scale == "F" and not 175 <= value <= 550:
            continue
        return f"{value} {scale}"
    return ""


_COOK_VERBS = (
    "forno", "assar", "asse", "assa", "horno", "hornea", "hornear", "oven",
    "bake", "baked", "cozinhe", "cozinhar", "coza", "cocina", "cocinar",
    "frite", "fritar", "freir", "fry", "air fryer", "airfryer", "cook",
    "congela", "congelar", "freezer", "freeze", "geladeira", "frigorifico",
    "nevera", "fridge", "repousar", "reposar", "rest",
)
# o tempo de cozedura aparece perto do verbo: "ao forno 25 minutos",
# "hornea 25 min", "bake for 30 minutes". Entre os dois pode aparecer a
# temperatura ("ao forno a 180 graus durante 40 minutos"), por isso o meio
# aceita digitos -- e nao-guloso e curto para nao colar a frase seguinte.
_COOK_TIME_RE = re.compile(
    r"(?:" + "|".join(_COOK_VERBS) + r")"
    r"[^\n]{0,40}?(\d+)\s*(min|mins|minutos|minutes|h|hs|hrs|horas|hours)\b",
    re.IGNORECASE,
)


def _guess_cook_time(text: str) -> str:
    """Cook time: o tempo que aparece junto de um verbo de cozedura."""
    match = _COOK_TIME_RE.search(_deaccent(text))
    return _fmt_time(match.group(1), match.group(2)) if match else ""


# --- juncao das fontes -----------------------------------------------------


@dataclass(frozen=True)
class RecipeDraft:
    title: str = ""
    time: str = ""  # Prep time
    cook_time: str = ""  # Cook time
    temperature: str = ""  # Temp
    servings: str = ""  # Serves
    source: str = ""  # Recipe from
    tags: tuple[str, ...] = field(default_factory=tuple)
    ingredients: tuple[str, ...] = field(default_factory=tuple)
    steps: tuple[str, ...] = field(default_factory=tuple)
    image: str = ""
    origins: dict[str, str] = field(default_factory=dict)

    @property
    def missing(self) -> tuple[str, ...]:
        """Campos obrigatorios ainda por preencher (o tempo e opcional)."""
        gaps = []
        if not self.title:
            gaps.append("TITULO")
        if not self.ingredients:
            gaps.append("INGREDIENTES")
        if not self.steps:
            gaps.append("PASSOS")
        return tuple(gaps)

    @property
    def is_complete(self) -> bool:
        return not self.missing

    def with_image(self, path: str) -> "RecipeDraft":
        return replace(self, image=path)

    def with_source(self, source: str) -> "RecipeDraft":
        return replace(self, source=source)

    def to_txt(self) -> str:
        """Schema final. Campos opcionais so aparecem quando ha valor.

        A ordem segue a da folha 1 do template (RECIPE, Serves, Temp, Prep
        time, Cook time, Recipe from), para o .txt se ler ao lado do PDF.
        """
        lines = [f"TITULO: {self.title}"]
        if self.servings:
            lines.append(f"PORCOES: {self.servings}")
        if self.temperature:
            lines.append(f"TEMPERATURA: {self.temperature}")
        if self.time:
            lines.append(f"TEMPO: {self.time}")
        if self.cook_time:
            lines.append(f"COZEDURA: {self.cook_time}")
        if self.source:
            lines.append(f"ORIGEM: {self.source}")
        if self.tags:
            lines.append(f"TAGS: {', '.join(self.tags)}")
        if self.image:
            lines.append(f"IMAGEM: {self.image}")
        lines.append("INGREDIENTES:")
        lines.extend(f"- {item}" for item in self.ingredients)
        lines.append("PASSOS:")
        lines.extend(f"- {item}" for item in self.steps)
        return "\n".join(lines) + "\n"


def extract_recipe(sources: list[TextSource]) -> RecipeDraft:
    """Escolhe de onde vem cada bloco da receita entre varias fontes de texto."""
    parses = [parse_source(s) for s in sources if s.text.strip()]
    if not parses:
        return RecipeDraft()

    origins: dict[str, str] = {}

    best_ing = max(parses, key=lambda p: p.ing_score)
    ingredients = best_ing.ingredients if best_ing.ing_score > 0 else ()
    if ingredients:
        origins["INGREDIENTES"] = best_ing.origin

    best_step = max(parses, key=lambda p: p.step_score)
    steps = best_step.steps if best_step.step_score > 0 else ()
    if steps:
        origins["PASSOS"] = best_step.origin

    def pick(attr: str) -> tuple[str, str]:
        """Primeiro valor nao vazio, comecando pelas fontes que trazem a receita.

        Titulo, porcoes e tempo so se aceitam da legenda, de comentarios do autor
        ou da fonte que deu a receita -- um comentario de terceiros a dizer
        "como isto em 15 min" nao e o tempo da receita.
        """
        trusted = [p for p in parses if p.priority >= 2]
        candidates = [p for p in (best_ing, best_step) if p.ingredients or p.steps]
        ordered = candidates + sorted(trusted, key=lambda p: -p.priority)
        for parse in ordered:
            value = getattr(parse, attr)
            if value:
                return value, parse.origin
        return "", ""

    title, title_origin = pick("title")
    time_value, time_origin = pick("time")
    cook_time, cook_origin = pick("cook_time")
    temperature, temp_origin = pick("temperature")
    servings, servings_origin = pick("servings")

    for name, origin in (
        ("TITULO", title_origin),
        ("TEMPO", time_origin),
        ("COZEDURA", cook_origin),
        ("TEMPERATURA", temp_origin),
        ("PORCOES", servings_origin),
    ):
        if origin:
            origins[name] = origin

    # as duas categorias saem do conteudo da receita mais o texto de origem
    # (as hashtags do autor entram aqui como pista, nao como tags)
    extra = " ".join(s.text for s in sources if s.priority >= 2)
    tags = classify(title, ingredients, steps, extra=extra)
    origins["TAGS"] = "categorias automaticas"

    return RecipeDraft(
        title=title,
        time=time_value,
        cook_time=cook_time,
        temperature=temperature,
        servings=servings,
        tags=tags,
        ingredients=ingredients,
        steps=steps,
        origins=origins,
    )
