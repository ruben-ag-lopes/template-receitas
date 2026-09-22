"""Interface web local: colas o link do reel e sai a receita em PDF.

Correr com:  python -m src.web    (abre em http://127.0.0.1:5000)

Uma passagem so faz tudo: le a legenda e o primeiro comentario, le o video (texto no
ecra e fotografia do prato final), classifica a receita nas duas categorias e,
se o parser aceitar o resultado, grava o .txt e gera o PDF sem pedir nada. O
texto fica na mesma numa caixa editavel, para corrigires e voltar a gerar.
"""

import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from threading import Timer
from urllib.request import Request, urlopen

from flask import Flask, redirect, render_template, request, url_for

from . import batch, database
from .cli import IMAGES_DIR, OUTPUT_DIR, RAW_DIR, slugify
from .frames_ocr import (
    OcrError,
    OcrUnavailable,
    check_requirements,
    image_has_text,
    read_video,
)
from .link_ingest import LinkIngestError, LinkMedia, TextSource, fetch_media
from .recipe_extractor import RecipeDraft, extract_recipe
from .recipe_parser import RecipeParseError, txt_to_recipe
from .renderer import recipe_to_html, recipe_to_pdf
from .translator import LANGUAGES, TranslationError, translate_txt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"

app = Flask(__name__, template_folder=str(TEMPLATES_DIR))

_MEDIA_CACHE: dict[str, LinkMedia] = {}
_VIDEO_CACHE: dict[str, tuple[str, bytes]] = {}


@dataclass
class Analysis:
    """Tudo o que se conseguiu apurar sobre um link."""

    draft: RecipeDraft
    sources: list[TextSource] = field(default_factory=list)
    image: bytes = b""
    image_origin: str = ""
    source_label: str = ""
    warnings: list[str] = field(default_factory=list)


# -- recolha ----------------------------------------------------------------


def _load_media(url: str) -> LinkMedia:
    if url not in _MEDIA_CACHE:
        _MEDIA_CACHE[url] = fetch_media(url)
    return _MEDIA_CACHE[url]


def _read_video_cached(url: str) -> tuple[str, bytes]:
    if url not in _VIDEO_CACHE:
        reading = read_video(url)
        _VIDEO_CACHE[url] = (reading.text, reading.image)
    return _VIDEO_CACHE[url]


def _fetch_thumbnail(url: str) -> bytes:
    if not url:
        return b""
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as response:
            return response.read()
    except Exception:
        return b""


def analyse(url: str) -> Analysis:
    """Le tudo o que o link tem: texto, texto no video e foto do prato."""
    media = _load_media(url)
    sources = media.text_sources()
    warnings: list[str] = []
    image, image_origin = b"", ""

    # o video da as duas coisas que o texto nao da: passos e foto do prato
    try:
        ocr_text, frame = _read_video_cached(url)
        if ocr_text.strip():
            sources.insert(
                0,
                TextSource(
                    origin="texto no video (OCR)",
                    text=ocr_text,
                    by_author=True,
                    kind="ocr",
                ),
            )
        if frame:
            image, image_origin = frame, "fotograma do video"
    except (OcrUnavailable, OcrError) as exc:
        warnings.append(f"Nao foi possivel ler o video: {exc}")

    if not image:
        # a capa do post costuma trazer o titulo desenhado por cima; so entra
        # se estiver limpa, pela mesma razao que os fotogramas com legenda
        # ficam de fora -- a foto da receita nao leva texto
        candidate = _fetch_thumbnail(media.thumbnail)
        if candidate and not image_has_text(candidate):
            image, image_origin = candidate, "capa do post"
        elif candidate:
            warnings.append("A capa do post tem texto por cima e nao foi usada como foto.")

    return Analysis(
        draft=extract_recipe(sources),
        sources=sources,
        image=image,
        image_origin=image_origin,
        source_label=_source_label(media),
        warnings=warnings,
    )


def _source_label(media: LinkMedia) -> str:
    """O que vai no campo "Recipe from" do template: o autor e a plataforma."""
    author = (media.channel or media.uploader or "").strip()
    host = ""
    for name in ("instagram", "tiktok", "youtube"):
        if name in (media.url or "").lower():
            host = name
            break
    if author and host:
        return f"@{author.lstrip('@')} ({host})"
    if author:
        return f"@{author.lstrip('@')}"
    return media.url or ""


# -- gravacao ---------------------------------------------------------------


def _save_image(slug: str, data: bytes) -> str:
    """Grava a foto e devolve o caminho relativo a raiz do projeto."""
    if not data:
        return ""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
    path = IMAGES_DIR / f"{slug}{suffix}"
    path.write_bytes(data)
    return path.relative_to(ROOT).as_posix()


def _generate(
    txt: str, contact: str = "", source_url: str = "", source_text: str = ""
) -> tuple[dict, str, str]:
    """Grava o .txt, gera o PDF e arquiva tudo na base de dados."""
    recipe = txt_to_recipe(txt)  # levanta RecipeParseError
    slug = slugify(recipe.title)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{slug}.txt"
    raw_path.write_text(txt if txt.endswith("\n") else txt + "\n", encoding="utf-8")

    saved = {"slug": slug, "raw": str(raw_path), "pdf": "", "html": "", "image": recipe.image}
    notice = f"Guardado em recipes/raw/{slug}.txt"
    error = ""
    try:
        pdf_path = OUTPUT_DIR / f"{slug}.pdf"
        recipe_to_pdf(recipe, pdf_path, contact=contact)
        saved["pdf"] = str(pdf_path)
        notice += f" e PDF gerado em recipes/output/{slug}.pdf"
    except Exception as exc:  # WeasyPrint precisa do GTK3; sem ele fica o HTML
        html_path = OUTPUT_DIR / f"{slug}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(recipe_to_html(recipe, contact=contact), encoding="utf-8")
        saved["html"] = str(html_path)
        error = (
            f"O PDF nao foi gerado ({type(exc).__name__}: {exc}). "
            f"Ficou o HTML em recipes/output/{slug}.html -- abre-o e usa Ctrl+P."
        )

    database.save(
        recipe,
        txt=txt,
        slug=slug,
        source_url=source_url,
        source_text=source_text,
        pdf_path=saved["pdf"] or saved["html"],
    )
    notice += ". Arquivada na base de dados"
    return saved, notice, error


# -- paginas ----------------------------------------------------------------


def _page(**context):
    base = {
        "url": "",
        "txt": "",
        "missing": (),
        "origins": {},
        "sources": [],
        "error": "",
        "notice": "",
        "warnings": [],
        "saved": None,
        "image_url": "",
        "image_origin": "",
        "arquivo": [],
        "lote": None,
        "languages": LANGUAGES,
    }
    base.update(context)
    return render_template("web.html", **base)


def _join_sources(sources) -> str:
    """Texto integral de todas as fontes lidas, para ficar no arquivo."""
    blocks = [f"[{s.origin}]\n{s.text.strip()}" for s in sources if s.text.strip()]
    return "\n\n".join(blocks)


def _source_preview(sources) -> list[dict]:
    return [
        {"origin": s.origin, "text": s.text.strip(), "likes": s.likes}
        for s in sources
        if s.text.strip()
    ]


@app.get("/")
def home():
    hint = check_requirements()
    warnings = [f"{hint} Sem isso nao se leem os passos que so aparecem no video."] if hint else []
    return _page(warnings=warnings, arquivo=database.list_all(), lote=batch.snapshot())


# -- lista de links ---------------------------------------------------------


def process_link(url: str, contact: str) -> batch.LinkResult:
    """Trata de um link da fila: le, monta a receita e grava se estiver completa."""
    try:
        result = analyse(url)
    except LinkIngestError as exc:
        return batch.LinkResult(url=url, state="erro", message=str(exc))

    draft = result.draft
    if result.source_label:
        draft = draft.with_source(result.source_label)
    slug = slugify(draft.title or "receita")
    image_path = _save_image(slug, result.image)
    if image_path:
        draft = draft.with_image(image_path)

    txt = draft.to_txt()
    if not draft.is_complete:
        return batch.LinkResult(
            url=url,
            state="incompleta",
            title=draft.title,
            slug=slug,
            txt=txt,
            missing=draft.missing,
            message="Falta: " + ", ".join(draft.missing),
        )

    try:
        saved, notice, error = _generate(
            txt,
            contact=contact,
            source_url=url,
            source_text=_join_sources(result.sources),
        )
    except RecipeParseError as exc:
        return batch.LinkResult(
            url=url, state="erro", title=draft.title, txt=txt, message=str(exc)
        )

    return batch.LinkResult(
        url=url,
        state="pronta",
        title=draft.title,
        slug=saved["slug"],
        txt=txt,
        message=error or notice,
    )


@app.post("/lote")
def lote():
    """Recebe a lista de links (caixa de texto ou ficheiro) e arranca a fila."""
    raw = request.form.get("links") or ""
    upload = request.files.get("ficheiro")
    if upload and upload.filename:
        raw += "\n" + upload.read().decode("utf-8", "ignore")

    links = batch.parse_links(raw)
    if not links:
        return _page(
            error="Nenhum link valido na lista. Cola um link por linha, comecados por https://",
            arquivo=database.list_all(),
            lote=batch.snapshot(),
        )

    contact = (request.form.get("contact") or "").strip()
    if not batch.start(links, process_link, contact=contact):
        return _page(
            error="Ja ha uma lista a ser processada. Espera que termine.",
            arquivo=database.list_all(),
            lote=batch.snapshot(),
        )
    return redirect(url_for("lote_estado"))


@app.get("/lote")
def lote_estado():
    state = batch.snapshot()
    notice = ""
    if state.total and not state.running:
        notice = (
            f"Lista terminada: {len(state.ready)} receita(s) pronta(s), "
            f"{len(state.incomplete)} por completar, {len(state.failed)} com erro."
        )
    return _page(notice=notice, arquivo=database.list_all(), lote=state)


@app.post("/lote/limpar")
def lote_limpar():
    batch.clear()
    return redirect(url_for("home"))


@app.post("/lote/editar")
def lote_editar():
    """Abre no editor o rascunho de um link que ficou incompleto."""
    url = (request.form.get("url") or "").strip()
    result = batch.result_for(url)
    if not result or not result.txt:
        return _page(error="Esse rascunho ja nao esta disponivel.", lote=batch.snapshot())
    return _page(
        url=url,
        txt=result.txt,
        missing=result.missing,
        notice=f"Rascunho de {result.title or url}. Completa o que falta e grava.",
    )


@app.post("/extrair")
def extrair():
    url = (request.form.get("url") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    try:
        result = analyse(url)
    except LinkIngestError as exc:
        return _page(url=url, error=str(exc))

    draft = result.draft
    if result.source_label:
        draft = draft.with_source(result.source_label)
    slug = slugify(draft.title or "receita")
    image_path = _save_image(slug, result.image)
    if image_path:
        draft = draft.with_image(image_path)

    txt = draft.to_txt()
    common = {
        "url": url,
        "txt": txt,
        "missing": draft.missing,
        "origins": draft.origins,
        "sources": _source_preview(result.sources),
        "warnings": result.warnings,
        "image_url": url_for("imagem", nome=Path(image_path).name) if image_path else "",
        "image_origin": result.image_origin,
    }

    if not draft.is_complete:
        return _page(
            notice="",
            error=(
                "Falta o que o post nao diz em lado nenhum: "
                + ", ".join(draft.missing)
                + ". Escreve na caixa e carrega em Guardar e gerar PDF."
            ),
            **common,
        )

    # completo: grava e gera o PDF sem pedir mais nada
    try:
        saved, notice, error = _generate(
            txt,
            contact=contact,
            source_url=url,
            source_text=_join_sources(result.sources),
        )
    except RecipeParseError as exc:
        return _page(error=f"O parser recusou o texto: {exc}", **common)
    return _page(notice=notice, error=error, saved=saved, **common)


@app.post("/validar")
def validar():
    url = (request.form.get("url") or "").strip()
    txt = request.form.get("txt") or ""
    try:
        recipe = txt_to_recipe(txt)
    except RecipeParseError as exc:
        return _page(url=url, txt=txt, error=f"O parser recusou o texto: {exc}")
    return _page(
        url=url,
        txt=txt,
        notice=f"Texto valido: {recipe.title} ({len(recipe.ingredients)} ingredientes, "
        f"{len(recipe.steps)} passos).",
    )


@app.post("/traduzir")
def traduzir():
    """Traduz o texto que esta agora na caixa (mesmo que ainda esteja incompleto)."""
    url = (request.form.get("url") or "").strip()
    txt = request.form.get("txt") or ""
    target = (request.form.get("target_lang") or "").strip()
    if target not in LANGUAGES:
        return _page(url=url, txt=txt, error="Escolhe uma lingua da lista.")
    try:
        result = translate_txt(txt, target)
    except TranslationError as exc:
        return _page(url=url, txt=txt, error=f"Falhou a traducao: {exc}")

    notice = f"Traduzido para {LANGUAGES[target]}"
    if result.detected_lang:
        notice += f" (detetado: {result.detected_lang})"
    notice += ". Os nomes dos campos e as TAGS nao mudam -- fazem parte do schema."
    try:
        txt_to_recipe(result.txt)
    except RecipeParseError as exc:
        notice += f" Ainda falta completar antes de gravar: {exc}."
    return _page(url=url, txt=result.txt, notice=notice)


def _cached_source_text(url: str) -> str:
    """Texto das fontes ja lidas nesta sessao para este link, sem voltar a rede.

    O caso comum e extrair, faltar so os PASSOS, e o utilizador completa-los na
    caixa antes de carregar em Guardar -- as fontes ja estao em cache do
    /extrair e o arquivo nao fica sem o texto de onde a receita veio.
    """
    if url not in _MEDIA_CACHE:
        return ""
    sources = _MEDIA_CACHE[url].text_sources()
    if url in _VIDEO_CACHE:
        ocr_text, _ = _VIDEO_CACHE[url]
        if ocr_text.strip():
            sources.insert(
                0, TextSource(origin="texto no video (OCR)", text=ocr_text, by_author=True, kind="ocr")
            )
    return _join_sources(sources)


@app.post("/guardar")
def guardar():
    url = (request.form.get("url") or "").strip()
    txt = request.form.get("txt") or ""
    contact = (request.form.get("contact") or "").strip()
    try:
        saved, notice, error = _generate(
            txt, contact=contact, source_url=url, source_text=_cached_source_text(url)
        )
    except RecipeParseError as exc:
        return _page(url=url, txt=txt, error=f"O parser recusou o texto: {exc}")
    return _page(url=url, txt=txt, notice=notice, error=error, saved=saved, arquivo=database.list_all())


@app.get("/imagem/<nome>")
def imagem(nome: str):
    """Serve a foto guardada, so para a pre-visualizacao na pagina."""
    from flask import send_from_directory

    return send_from_directory(IMAGES_DIR, nome)


@app.post("/limpar")
def limpar():
    return redirect(url_for("home"))


def main() -> None:
    host, port = "127.0.0.1", 5000
    Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
