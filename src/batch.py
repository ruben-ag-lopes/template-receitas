"""Processamento de uma lista de links, um a um, em segundo plano.

Cada link leva um a dois minutos (o video e a parte lenta), por isso uma
lista de dez seria um pedido HTTP de vinte minutos. Aqui a fila corre numa
thread e a pagina vai buscar o estado, o que tambem deixa acompanhar o
progresso em vez de ficar a olhar para o browser parado.

Guarda-se o rascunho de cada receita mesmo quando fica incompleta, para se
poder abrir no editor e acabar a mao sem repetir a leitura do video.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_LINKS = 50


@dataclass
class LinkResult:
    """O que aconteceu a um link da lista."""

    url: str
    state: str = "em espera"  # em espera | a processar | pronta | incompleta | erro
    title: str = ""
    slug: str = ""
    txt: str = ""
    missing: tuple[str, ...] = field(default_factory=tuple)
    message: str = ""

    @property
    def done(self) -> bool:
        return self.state in ("pronta", "incompleta", "erro")


@dataclass
class BatchState:
    """Estado da fila inteira, partilhado entre a thread e as paginas."""

    results: list[LinkResult] = field(default_factory=list)
    running: bool = False
    started_at: str = ""
    finished_at: str = ""
    contact: str = ""

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def done_count(self) -> int:
        return sum(1 for r in self.results if r.done)

    @property
    def ready(self) -> list[LinkResult]:
        return [r for r in self.results if r.state == "pronta"]

    @property
    def incomplete(self) -> list[LinkResult]:
        return [r for r in self.results if r.state == "incompleta"]

    @property
    def failed(self) -> list[LinkResult]:
        return [r for r in self.results if r.state == "erro"]


_state = BatchState()
_lock = threading.Lock()


def parse_links(raw: str) -> list[str]:
    """Extrai os links de um texto colado ou de um ficheiro carregado.

    Aceita um link por linha, e tambem listas separadas por virgulas ou
    espacos -- e como saem de uma folha de calculo ou de uma nota do
    telemovel. Repetidos ficam pelo primeiro, mantendo a ordem.
    """
    seen: set[str] = set()
    links: list[str] = []
    for chunk in raw.replace(",", " ").split():
        link = chunk.strip().strip("<>\"'")
        if not link.startswith(("http://", "https://")) or link in seen:
            continue
        seen.add(link)
        links.append(link)
    return links[:MAX_LINKS]


def snapshot() -> BatchState:
    """Copia do estado atual, para a pagina nao ler enquanto a thread escreve."""
    with _lock:
        return BatchState(
            results=[LinkResult(**vars(r)) for r in _state.results],
            running=_state.running,
            started_at=_state.started_at,
            finished_at=_state.finished_at,
            contact=_state.contact,
        )


def result_for(url: str) -> LinkResult | None:
    with _lock:
        for r in _state.results:
            if r.url == url:
                return LinkResult(**vars(r))
    return None


def clear() -> None:
    with _lock:
        if _state.running:
            return
        _state.results = []
        _state.started_at = ""
        _state.finished_at = ""


def start(links: list[str], process, contact: str = "") -> bool:
    """Arranca a fila. `process(url, contact)` trata de um link e devolve LinkResult.

    Devolve False se ja houver uma fila a correr -- duas em simultaneo iam
    disputar o mesmo Tesseract e o mesmo ficheiro de base de dados.
    """
    with _lock:
        if _state.running or not links:
            return False
        _state.results = [LinkResult(url=u) for u in links]
        _state.running = True
        _state.contact = contact
        _state.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _state.finished_at = ""

    thread = threading.Thread(target=_run, args=(process, contact), daemon=True)
    thread.start()
    return True


def _run(process, contact: str) -> None:
    try:
        index = 0
        while True:
            with _lock:
                if index >= len(_state.results):
                    break
                url = _state.results[index].url
                _state.results[index].state = "a processar"

            try:
                outcome = process(url, contact)
            except Exception as exc:  # um link mau nao pode parar a fila toda
                outcome = LinkResult(
                    url=url, state="erro", message=f"{type(exc).__name__}: {exc}"
                )

            with _lock:
                _state.results[index] = outcome
            index += 1
    finally:
        with _lock:
            _state.running = False
            _state.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
