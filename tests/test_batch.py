import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import batch


@pytest.fixture(autouse=True)
def fila_limpa():
    """Cada teste comeca com a fila vazia (o estado e global ao modulo)."""
    batch._state.running = False
    batch.clear()
    yield
    batch._state.running = False
    batch.clear()


def esperar_fim(timeout: float = 5.0) -> batch.BatchState:
    limite = time.time() + timeout
    while time.time() < limite:
        estado = batch.snapshot()
        if estado.total and not estado.running:
            return estado
        time.sleep(0.02)
    raise AssertionError("a fila nao terminou a tempo")


class TestParseLinks:
    def test_um_link_por_linha(self):
        assert batch.parse_links("https://a.com\nhttps://b.com") == [
            "https://a.com",
            "https://b.com",
        ]

    def test_aceita_virgulas_e_espacos(self):
        """E como saem de uma folha de calculo ou de uma nota do telemovel."""
        assert batch.parse_links("https://a.com, https://b.com") == [
            "https://a.com",
            "https://b.com",
        ]

    def test_ignora_linhas_que_nao_sao_links(self):
        raw = "as minhas receitas:\nhttps://a.com\nver depois\n"
        assert batch.parse_links(raw) == ["https://a.com"]

    def test_remove_repetidos_mantendo_a_ordem(self):
        raw = "https://b.com\nhttps://a.com\nhttps://b.com"
        assert batch.parse_links(raw) == ["https://b.com", "https://a.com"]

    def test_limita_o_tamanho_da_lista(self):
        raw = "\n".join(f"https://exemplo.com/{i}" for i in range(batch.MAX_LINKS + 20))
        assert len(batch.parse_links(raw)) == batch.MAX_LINKS

    def test_texto_vazio(self):
        assert batch.parse_links("") == []


class TestFila:
    def test_processa_todos_os_links_por_ordem(self):
        vistos = []

        def processa(url, contact):
            vistos.append(url)
            return batch.LinkResult(url=url, state="pronta", title=url[-1])

        assert batch.start(["https://a.com", "https://b.com"], processa)
        estado = esperar_fim()

        assert vistos == ["https://a.com", "https://b.com"]
        assert estado.done_count == 2
        assert len(estado.ready) == 2

    def test_um_link_com_erro_nao_para_a_fila(self):
        def processa(url, contact):
            if "mau" in url:
                raise RuntimeError("link partido")
            return batch.LinkResult(url=url, state="pronta")

        batch.start(["https://mau.com", "https://bom.com"], processa)
        estado = esperar_fim()

        assert len(estado.failed) == 1
        assert len(estado.ready) == 1
        assert "link partido" in estado.failed[0].message

    def test_separa_prontas_de_incompletas(self):
        def processa(url, contact):
            if "meia" in url:
                return batch.LinkResult(url=url, state="incompleta", missing=("PASSOS",))
            return batch.LinkResult(url=url, state="pronta")

        batch.start(["https://meia.com", "https://boa.com"], processa)
        estado = esperar_fim()

        assert [r.url for r in estado.incomplete] == ["https://meia.com"]
        assert [r.url for r in estado.ready] == ["https://boa.com"]

    def test_o_contacto_chega_ao_processador(self):
        recebidos = []

        def processa(url, contact):
            recebidos.append(contact)
            return batch.LinkResult(url=url, state="pronta")

        batch.start(["https://a.com"], processa, contact="eu@exemplo.pt")
        esperar_fim()
        assert recebidos == ["eu@exemplo.pt"]

    def test_nao_arranca_uma_segunda_fila_em_simultaneo(self):
        """Duas filas ao mesmo tempo disputavam o Tesseract e a base de dados."""
        batch._state.running = True
        assert batch.start(["https://a.com"], lambda u, c: None) is False

    def test_lista_vazia_nao_arranca(self):
        assert batch.start([], lambda u, c: None) is False

    def test_guarda_o_rascunho_das_incompletas(self):
        """Para se poder completar a mao sem repetir a leitura do video."""

        def processa(url, contact):
            return batch.LinkResult(
                url=url, state="incompleta", txt="TITULO: X\n", missing=("PASSOS",)
            )

        batch.start(["https://a.com"], processa)
        esperar_fim()
        assert batch.result_for("https://a.com").txt == "TITULO: X\n"

    def test_snapshot_nao_partilha_objetos_com_a_fila(self):
        def processa(url, contact):
            return batch.LinkResult(url=url, state="pronta", title="original")

        batch.start(["https://a.com"], processa)
        esperar_fim()

        copia = batch.snapshot()
        copia.results[0].title = "alterado"
        assert batch.snapshot().results[0].title == "original"
