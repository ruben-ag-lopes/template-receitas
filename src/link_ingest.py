"""Leitura de metadados publicos de um link de video (Instagram Reels, TikTok, YouTube...).

Usa o yt-dlp em modo metadados: nao descarrega o video, so a ficha publica do
post -- legenda, titulo, autor e comentarios. E o caminho mais barato em
computacao e nao precisa de sessao iniciada para posts publicos.

A receita tanto pode estar na legenda como num comentario do proprio autor
(pratica comum quando a legenda fica curta), por isso recolhem-se as duas
coisas e deixa-se a decisao de onde esta a receita para o recipe_extractor.
So se usa o primeiro comentario (o que aparece primeiro no post) -- o
Instagram devolve-os todos numa unica chamada, mas nao ha vantagem em
processar 10+ comentarios quando normalmente so o primeiro, ou nenhum, tem
a receita.
"""

from dataclasses import dataclass, field


class LinkIngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextSource:
    """Um bloco de texto candidato a conter a receita."""

    origin: str  # descricao legivel, ex: "legenda" ou "comentario de @autor"
    text: str
    by_author: bool = False
    likes: int = 0
    kind: str = "text"  # "text" (escrito) ou "ocr" (lido do ecra do video)

    @property
    def priority(self) -> int:
        """Legenda e comentarios do autor valem mais do que comentarios de terceiros."""
        if self.origin == "legenda":
            return 3
        if self.by_author:
            return 2
        return 1


@dataclass(frozen=True)
class LinkMedia:
    url: str
    title: str
    description: str
    uploader: str
    channel: str = ""
    thumbnail: str = ""
    duration: float | None = None
    comments: tuple[TextSource, ...] = field(default_factory=tuple)

    @property
    def caption(self) -> str:
        """Legenda do post, com o titulo a abrir se acrescentar informacao."""
        desc = (self.description or "").strip()
        title = (self.title or "").strip()
        if title and not title.lower().startswith("video by") and title not in desc:
            return f"{title}\n{desc}".strip()
        return desc

    def text_sources(self) -> list[TextSource]:
        """Todos os textos candidatos, dos mais fiaveis para os menos."""
        sources: list[TextSource] = []
        if self.caption.strip():
            sources.append(TextSource(origin="legenda", text=self.caption, by_author=True))
        sources.extend(self.comments)
        return sorted(sources, key=lambda s: (-s.priority, -s.likes))


def fetch_media(url: str, with_comments: bool = True) -> LinkMedia:
    """Devolve os metadados publicos do link. Levanta LinkIngestError se falhar."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise LinkIngestError("Indica um link completo, comecado por https://")

    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise LinkIngestError(
            "Falta a dependencia yt-dlp. Instala com: python -m pip install yt-dlp"
        ) from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "getcomments": with_comments,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # yt-dlp levanta varios tipos de erro
        raise LinkIngestError(_friendly_error(exc)) from exc

    if not info:
        raise LinkIngestError("O link nao devolveu qualquer conteudo.")
    if info.get("entries"):
        info = info["entries"][0]

    channel = info.get("channel") or info.get("uploader_id") or ""
    media = LinkMedia(
        url=info.get("webpage_url") or url,
        title=info.get("title") or "",
        description=info.get("description") or "",
        uploader=info.get("uploader") or channel,
        channel=channel,
        thumbnail=info.get("thumbnail") or "",
        duration=info.get("duration"),
        comments=_comment_sources(info),
    )

    if not media.text_sources():
        raise LinkIngestError(
            "O post nao tem legenda nem comentarios publicos utilizaveis. "
            "Se a receita so aparece no video, usa a leitura das imagens (OCR)."
        )
    return media


def _comment_sources(info: dict) -> tuple[TextSource, ...]:
    """So o primeiro comentario do post, convertido em candidato a receita."""
    comments = [c for c in (info.get("comments") or []) if (c.get("text") or "").strip()]
    if not comments:
        return ()
    comment = comments[0]

    channel = (info.get("channel") or "").lower()
    uploader_id = str(info.get("uploader_id") or "")
    author = (comment.get("author") or "").lstrip("@")
    by_author = bool(comment.get("author_is_uploader")) or (
        author.lower() == channel and channel != ""
    ) or (str(comment.get("author_id") or "") == uploader_id and uploader_id != "")
    label = f"primeiro comentario (@{author})" if author else "primeiro comentario"
    if by_author:
        label += " (autor)"

    return (
        TextSource(
            origin=label,
            text=comment["text"].strip(),
            by_author=by_author,
            likes=int(comment.get("like_count") or 0),
        ),
    )


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "login" in low or "rate-limit" in low or "restricted" in low or "cookies" in low:
        return (
            "O Instagram bloqueou o acesso a este post (privado ou limite de pedidos). "
            "Tenta novamente daqui a uns minutos ou usa um post publico."
        )
    if "unsupported url" in low:
        return "Link nao reconhecido. Usa o endereco publico do reel/post."
    if "not exist" in low or "404" in low:
        return "O post nao existe ou foi removido."
    return f"Nao foi possivel ler o link: {text.splitlines()[0]}"
