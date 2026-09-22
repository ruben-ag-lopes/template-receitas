"""Leitura do video: texto sobreposto (passos) e fotografia do prato final.

Muitos reels poem os passos em texto no ecra e nunca os escrevem na legenda,
e a foto do prato pronto so existe no video. As duas coisas saem da mesma
passagem: descarrega-se o video uma vez, tiram-se fotogramas com o ffmpeg e
cada fotograma serve para as duas leituras.

A foto escolhida e a mais nitida da parte final do video com menos texto por
cima -- o prato emplatado aparece quase sempre no fim, e os fotogramas com
muito texto sao os das instrucoes.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_FRAMES = 36
MIN_FRAMES = 10
FRAME_INTERVAL = 1.0  # segundos entre fotogramas -- ver _frame_budget()
FRAME_WIDTH = 900
OCR_LANGS = ("por", "spa", "eng")
JPEG_QUALITY = 88

_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

# pasta propria com os pacotes de espanhol/portugues: a instalacao do Tesseract
# fica em Program Files, sem permissao de escrita sem admin, por isso os
# idiomas extra (a maioria das receitas nao vem em ingles) ficam aqui em vez
# de dentro da instalacao
_USER_TESSDATA = Path.home() / "AppData" / "Local" / "Template_Receitas" / "tessdata"


class OcrUnavailable(RuntimeError):
    pass


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoReading:
    """Resultado de ler o video: texto do ecra e foto do prato (JPEG em bytes)."""

    text: str = ""
    image: bytes = b""


def locate_tesseract() -> str:
    """Caminho do tesseract.exe, mesmo que nao esteja no PATH."""
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in _TESSERACT_PATHS:
        if Path(candidate).is_file():
            return candidate
    return ""


def _configure_tesseract() -> bool:
    exe = locate_tesseract()
    if not exe:
        return False
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = exe
        # a pasta propria (com espanhol/portugues) tem prioridade sobre a da
        # instalacao, que normalmente so tem ingles
        if (_USER_TESSDATA / "eng.traineddata").is_file():
            os.environ["TESSDATA_PREFIX"] = str(_USER_TESSDATA)
        else:
            tessdata = Path(exe).parent / "tessdata"
            if tessdata.is_dir():
                os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
        return True
    except ImportError:
        return False


def check_requirements() -> str:
    """Devolve "" se estiver tudo pronto, ou a instrucao de instalacao em falta."""
    if not shutil.which("ffmpeg"):
        return "Falta o ffmpeg. Instala com:  winget install Gyan.FFmpeg  (e reabre o terminal)."
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return "Falta a dependencia pytesseract. Instala com: python -m pip install pytesseract"
    if not _configure_tesseract():
        return (
            "Falta o motor Tesseract OCR. Instala com:  "
            "winget install UB-Mannheim.TesseractOCR"
        )
    return ""


def read_video(url: str, max_frames: int = MAX_FRAMES) -> VideoReading:
    """Texto sobreposto (sem repeticoes) e foto do prato final, num so download."""
    problem = check_requirements()
    if problem:
        raise OcrUnavailable(problem)

    with tempfile.TemporaryDirectory(prefix="receitas-video-") as tmp:
        tmpdir = Path(tmp)
        video = _download_video(url, tmpdir)
        frames = _extract_frames(video, tmpdir, max_frames)
        if not frames:
            raise OcrError("Nao foi possivel extrair fotogramas do video.")
        per_frame = _ocr_frames(frames)
        return VideoReading(
            text=_dedupe_lines([f.lines for f in per_frame]),
            image=_pick_dish_photo(frames, per_frame),
        )


# -- video ------------------------------------------------------------------


def _download_video(url: str, tmpdir: Path) -> Path:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise OcrUnavailable(
            "Falta a dependencia yt-dlp. Instala com: python -m pip install yt-dlp"
        ) from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "format": "worst[ext=mp4]/worst",
        "outtmpl": str(tmpdir / "video.%(ext)s"),
    }
    try:
        with YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as exc:
        raise OcrError(f"Nao foi possivel descarregar o video: {exc}") from exc

    files = [p for p in tmpdir.iterdir() if p.is_file()]
    if not files:
        raise OcrError("O download do video nao produziu ficheiro.")
    return max(files, key=lambda p: p.stat().st_size)


def _frame_budget(duration: float, max_frames: int) -> tuple[int, float]:
    """Quantos fotogramas tirar e com que intervalo, conforme a duracao.

    Legendas de video costumam mudar a cada 1-2 segundos (por vezes uma
    palavra de cada vez, como em legendas ao ritmo da fala) -- um numero fixo
    de fotogramas por video (independente da duracao) deixa videos mais
    longos com intervalos grandes de mais e perde trocas de legenda inteiras.
    Aqui o intervalo e que e fixo (FRAME_INTERVAL); o numero de fotogramas
    escala com a duracao, entre MIN_FRAMES e max_frames.
    """
    if not duration:
        return MIN_FRAMES, 2.0
    count = max(MIN_FRAMES, min(max_frames, round(duration / FRAME_INTERVAL)))
    return count, duration / count


def _extract_frames(video: Path, tmpdir: Path, max_frames: int) -> list[Path]:
    frames_dir = tmpdir / "frames"
    frames_dir.mkdir(exist_ok=True)
    duration = _duration_seconds(video)
    count, interval = _frame_budget(duration, max_frames)

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", f"fps=1/{interval:.3f},scale={FRAME_WIDTH}:-1",
        "-frames:v", str(count),
        str(frames_dir / "f_%03d.png"),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise OcrError("O ffmpeg demorou demasiado a processar o video.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "ignore").strip().splitlines()
        raise OcrError(f"ffmpeg falhou: {detail[-1] if detail else 'erro desconhecido'}") from exc

    return sorted(frames_dir.glob("*.png"))


def _duration_seconds(video: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, timeout=30, check=True,
        )
        return float(out.stdout.decode().strip())
    except Exception:
        return 0.0


# -- texto ------------------------------------------------------------------


def _text_variants(grey):
    """Duas versoes da mesma imagem, para apanhar legendas sobre fotografia.

    Uma legenda de video e tipicamente texto solido (quase sempre branco,
    nestes videos), por cima de um fundo variado -- a propria fotografia. O
    OCR direto (a imagem tal como esta) falha ai porque o fundo tem demasiado
    contraste local; isolar so os pixeis quase brancos resolve a maior parte
    dos casos sem um modelo de deteccao de texto, e a imagem normal continua
    a apanhar o que a mascara falha (medido: a mascara de texto preto nunca
    trouxe nada que as outras duas ja nao tivessem lido, por isso saiu --
    e tempo que rende mais fotogramas extra do que uma terceira leitura).
    """
    import numpy as np
    from PIL import Image

    arr = np.array(grey)
    white = np.where(arr > 210, 255, 0).astype("uint8")
    return [grey, Image.fromarray(white)]


MIN_WORD_CONFIDENCE = 75  # texto que se aproveita para os passos
TEXT_PRESENCE_CONFIDENCE = 30  # suspeita de letras: chega para nao usar a foto

# so palavras alfabeticas: um digito isolado e o tipo de ruido mais comum do
# OCR sobre fotografia, e a quantidade dos ingredientes normalmente ja vem da
# legenda ou dos comentarios -- aqui o que importa e nao perder os passos
_ALPHA_WORD_RE = re.compile(r"^[A-Za-zÀ-ÿ]{3,}$")


def _read_variant(variant, langs: str) -> tuple[list[str], bool]:
    """Le uma imagem com dois criterios ao mesmo tempo, na mesma passagem.

    Os dois usos do OCR querem coisas opostas e por isso tem limiares
    diferentes:

    - os passos querem precisao: so palavras em que o Tesseract confia muito
      (MIN_WORD_CONFIDENCE), senao entra ruido de textura da fotografia;
    - a escolha da foto quer sensibilidade: basta haver suspeita de letras
      (TEXT_PRESENCE_CONFIDENCE) para o fotograma ser posto de lado, porque
      a foto que ilustra a receita nao pode ter legenda por cima.

    Devolve (linhas de confianca alta, ha sinais de texto).
    """
    import pytesseract

    try:
        data = pytesseract.image_to_data(
            variant, lang=langs, config="--psm 6", output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        raise OcrError(f"O tesseract falhou a ler um fotograma: {exc}") from exc

    lines: dict[tuple[int, int, int], list[str]] = {}
    any_text = False
    for word, conf, block, par, line in zip(
        data["text"], data["conf"], data["block_num"], data["par_num"], data["line_num"]
    ):
        word = word.strip()
        if not word or not _ALPHA_WORD_RE.match(word):
            continue
        confidence = float(conf)
        if confidence >= TEXT_PRESENCE_CONFIDENCE:
            any_text = True
        if confidence >= MIN_WORD_CONFIDENCE:
            lines.setdefault((block, par, line), []).append(word)

    return [" ".join(w) for w in lines.values() if len(" ".join(w)) >= 4], any_text


def _confident_lines(variant, langs: str) -> list[str]:
    """So as linhas de confianca alta (usado por image_has_text e testes)."""
    return _read_variant(variant, langs)[0]


@dataclass(frozen=True)
class FrameText:
    """O que se leu num fotograma, pelos dois criterios."""

    lines: list[str]  # confianca alta -> serve para os passos
    has_text: bool  # qualquer suspeita -> chega para rejeitar a foto


def _ocr_frames(frames: list[Path]) -> list[FrameText]:
    """Texto lido em cada fotograma, pela ordem dos fotogramas."""
    from PIL import Image

    langs = _available_langs()
    out: list[FrameText] = []
    for frame in frames:
        lines: list[str] = []
        has_text = False
        with Image.open(frame) as image:
            grey = image.convert("L")
            for variant in _text_variants(grey):
                variant_lines, variant_text = _read_variant(variant, langs)
                lines.extend(variant_lines)
                has_text = has_text or variant_text
        out.append(
            FrameText(
                lines=_dedupe_frame(l for l in lines if _is_useful(l)),
                has_text=has_text,
            )
        )
    return out


def _dedupe_key(text: str) -> str:
    """Chave de deduplicacao sem acentos nem pontuacao.

    Sem isto, "dejalos" e "déjalos" -- a mesma palavra lida em dois
    fotogramas ou variantes diferentes -- contam como coisas distintas e
    duplicam-se no resultado final.
    """
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def _accent_score(text: str) -> int:
    """Quantos acentos tem a linha -- para preferir "déjalos" a "dejalos"."""
    return sum(1 for c in unicodedata.normalize("NFKD", text) if unicodedata.combining(c))


def _dedupe(lines) -> list[str]:
    """Remove repeticoes (por chave sem acentos), mantendo a leitura mais
    completa de cada palavra quando aparece com e sem acento."""
    best: dict[str, str] = {}
    order: list[str] = []
    for line in lines:
        key = _dedupe_key(line)
        if len(key) < 4:
            continue
        if key not in best:
            best[key] = line
            order.append(key)
        elif _accent_score(line) > _accent_score(best[key]):
            best[key] = line
    return [best[key] for key in order]


def _dedupe_frame(lines) -> list[str]:
    """Remove repeticoes dentro do mesmo fotograma (as variantes leem o mesmo texto)."""
    return _dedupe(lines)


def _available_langs() -> str:
    """Usa por/spa se os pacotes existirem; caso contrario fica-se pelo ingles."""
    try:
        import pytesseract

        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    wanted = [lang for lang in OCR_LANGS if lang in installed]
    return "+".join(wanted) if wanted else "eng"


def _dedupe_lines(per_frame: list[list[str]]) -> str:
    """Junta as linhas de todos os fotogramas sem repetir (o texto fica no ecra)."""
    flat = (line for frame_lines in per_frame for line in frame_lines)
    return "\n".join(_dedupe(flat))


def _is_useful(line: str) -> bool:
    """Filtra lixo tipico do OCR: linhas curtas, sem letras ou so simbolos.

    As mascaras de texto branco/preto (ver _text_variants) tendem a deixar
    passar fragmentos de contorno como "y Ss 5" -- por isso o limiar e mais
    apertado do que bastaria para uma imagem limpa.
    """
    if len(line) < 4:
        return False
    letters = sum(1 for c in line if c.isalpha())
    return letters >= 4 and letters / len(line) >= 0.6


# -- fotografia -------------------------------------------------------------


def image_has_text(data: bytes) -> bool:
    """Ha texto legivel nesta imagem?

    Serve para nao deixar passar uma capa de post com titulo grafico por cima
    quando ela e usada como foto da receita -- a foto do PDF tem de ser limpa,
    tal como a que se escolhe dos fotogramas.
    """
    import io

    from PIL import Image

    if not data or check_requirements():
        return False
    try:
        with Image.open(io.BytesIO(data)) as image:
            grey = image.convert("L")
            langs = _available_langs()
            return any(_read_variant(v, langs)[1] for v in _text_variants(grey))
    except Exception:
        return False


def _sharpness(frame: Path) -> float:
    """Nitidez aproximada: desvio-padrao dos contornos da imagem."""
    from PIL import Image, ImageFilter, ImageStat

    try:
        with Image.open(frame) as image:
            grey = image.convert("L")
            return ImageStat.Stat(grey.filter(ImageFilter.FIND_EDGES)).stddev[0]
    except Exception:
        return -1.0


def _pick_dish_photo(frames: list[Path], per_frame: list["FrameText"]) -> bytes:
    """A foto do prato: fotograma limpo, sem legenda sobreposta.

    A imagem vai ilustrar a receita no PDF, por isso nao pode ter texto do
    video por cima. So entram fotogramas onde o OCR nao leu nada -- e a
    mesma leitura que ja se fez para os passos, aproveitada ao contrario:
    onde ela encontrou texto, ha legenda na imagem.

    Procura-se primeiro na segunda metade do video (e onde o prato pronto
    aparece) e so depois no resto. Se o video tiver legenda do principio ao
    fim, nao ha fotograma limpo e devolve-se vazio -- mais vale nenhuma foto
    do que uma com letras atravessadas.
    """
    import io

    from PIL import Image

    clean = [
        index
        for index in range(len(frames))
        if index < len(per_frame) and not per_frame[index].has_text
    ]
    if not clean:
        return b""

    half = len(frames) // 2
    preferred = [i for i in clean if i >= half] or clean
    best = max(preferred, key=lambda i: _sharpness(frames[i]))

    with Image.open(frames[best]) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()
