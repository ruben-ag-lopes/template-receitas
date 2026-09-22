"""Traducao do .txt final para outra lingua, via MyMemory (grátis, sem chave).

So os VALORES dos campos sao traduzidos -- os nomes dos campos (TITULO,
INGREDIENTES, PASSOS...) sao vocabulario fixo do schema e tem de ficar
exatamente como estao, senao o recipe_parser deixa de reconhecer o ficheiro.
TAGS tambem fica intocado: e vocabulario fechado usado para pesquisa na base
de dados (ver categories.py), traduzi-lo quebrava esse contrato.

Porque MyMemory: e gratuito, nao pede chave, deteta a lingua de origem
sozinho (langpair=autodetect|<destino>) e e so um pedido HTTP simples --
sem dependencias novas, so a biblioteca padrao.
"""

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

_API = "https://api.mymemory.translated.net/get"
_TIMEOUT = 10

LANGUAGES = {
    "pt": "Português",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "de": "Deutsch",
}

# so os valores destas linhas se traduzem -- o cabecalho fica igual
_TRANSLATABLE_HEADERS = {"TITULO"}
_LIST_HEADERS = {"INGREDIENTES", "PASSOS"}
_UNTRANSLATED_HEADERS = {"TEMPO", "TAGS", "IMAGEM", "PORCOES"}
_ALL_HEADERS = _TRANSLATABLE_HEADERS | _LIST_HEADERS | _UNTRANSLATED_HEADERS


class TranslationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranslationResult:
    txt: str
    detected_lang: str = ""


def _is_detection_risky(text: str) -> bool:
    """Uma quantidade ("200 g de lentejas") engana a autodeteccao -- ja saiu
    identificada como dinamarques. Uma frase curta mas sem numeros ("Triture
    com a agua") deteta-se bem sozinha; o risco esta especificamente nas
    linhas curtas com um numero a abrir, tipicas de um ingrediente.
    """
    words = text.split()
    if not words:
        return False
    has_digit = any(c.isdigit() for c in words[0]) or any(
        any(c.isdigit() for c in w) for w in words[:2]
    )
    return has_digit and len(words) <= 6


def _translate_text(text: str, target: str, source: str = "") -> tuple[str, str]:
    """Um pedido a API. Devolve (traducao, lingua detetada). Vazio devolve vazio.

    `source` so se usa quando a propria linha e curta/numerica de mais para
    se detetar sozinha (ver _is_detection_risky) -- uma frase normal deteta-se
    melhor por si so do que forcando a lingua de outra linha, porque uma
    receita pode legitimamente juntar campos vindos de fontes em linguas
    diferentes (legenda numa lingua, passos lidos do video noutra).
    """
    if not text.strip():
        return text, ""
    pair = f"{source}|{target}" if source else f"autodetect|{target}"
    url = f"{_API}?q={quote(text)}&langpair={pair}"
    try:
        with urlopen(url, timeout=_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError) as exc:
        raise TranslationError(f"Sem ligacao ao serviço de tradução: {exc}") from exc
    except (json.JSONDecodeError, KeyError) as exc:
        raise TranslationError("O serviço de tradução devolveu uma resposta inesperada.") from exc

    if payload.get("responseStatus") not in (200, "200"):
        raise TranslationError(
            payload.get("responseDetails") or "O serviço de tradução recusou o pedido."
        )
    data = payload.get("responseData") or {}
    translated = data.get("translatedText") or text
    detected = data.get("detectedLanguage") or ""
    return translated, detected


def translate_txt(txt: str, target_lang: str) -> TranslationResult:
    """Traduz os valores do .txt para target_lang, preservando o schema.

    Funciona sobre o texto tal como esta na caixa, mesmo que ainda esteja
    incompleto -- traduz o que ja la estiver e deixa o resto como esta, para
    poderes traduzir antes ou depois de completares os campos em falta.
    """
    lines = txt.splitlines()
    out: list[str] = []
    current_list: str | None = None
    reported = ""  # primeira deteccao fiavel, so para a mensagem ao utilizador
    fallback = ""  # deteccao mais recente de uma linha normal, para emprestar
    # as linhas curtas/numericas que nao se deteta sozinhas com confianca

    def _translate_value(content: str) -> str:
        nonlocal reported, fallback
        risky = _is_detection_risky(content)
        translated, lang = _translate_text(content, target_lang, source=fallback if risky else "")
        reported = reported or lang
        if lang and not risky:
            fallback = lang
        return translated

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue

        header, sep, rest = stripped.partition(":")
        header_key = header.strip().upper()

        if sep and header_key in _ALL_HEADERS:
            current_list = header_key if header_key in _LIST_HEADERS else None
            if header_key in _TRANSLATABLE_HEADERS and rest.strip():
                out.append(f"{header_key}: {_translate_value(rest.strip())}")
            else:
                out.append(line)
            continue

        if current_list is not None and stripped[:1] in ("-", "*"):
            bullet, content = stripped[0], stripped[1:].strip()
            if content:
                translated = _translate_value(content)
                out.append(f"{bullet} {translated}")
            else:
                out.append(line)
            continue

        out.append(line)

    return TranslationResult(txt="\n".join(out) + "\n", detected_lang=reported)
