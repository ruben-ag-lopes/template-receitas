"""Testes do translator.py.

Fazem pedidos reais a API do MyMemory (gratuita, sem chave) -- sao pulados
automaticamente se nao houver ligacao a internet, para nao partir o resto
da suite num ambiente offline.
"""

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.translator import _is_detection_risky, translate_txt


def _has_internet() -> bool:
    try:
        socket.create_connection(("api.mymemory.translated.net", 443), timeout=3).close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _has_internet(), reason="sem ligacao a internet")


TXT = """TITULO: Chips Crocantes de Lentejas
TEMPO: 25 min
TAGS: snack, saudavel
IMAGEM: recipes/images/chips.jpg
INGREDIENTES:
- 200 g de lentejas
- 150 ml de agua
PASSOS:
- Remoja las lentejas durante 8 horas
- Hornea 25 minutos
"""


def test_so_os_valores_traduziveis_mudam():
    result = translate_txt(TXT, "en")
    lines = result.txt.splitlines()
    assert lines[0].startswith("TITULO: ")
    assert lines[0] != "TITULO: Chips Crocantes de Lentejas"  # foi traduzido
    # cabecalhos e valores fechados ficam exatamente iguais
    assert "TEMPO: 25 min" in result.txt
    assert "TAGS: snack, saudavel" in result.txt
    assert "IMAGEM: recipes/images/chips.jpg" in result.txt
    assert "INGREDIENTES:" in result.txt
    assert "PASSOS:" in result.txt


def test_ingredientes_e_passos_traduzidos():
    result = translate_txt(TXT, "en")
    assert "- 200 g" in result.txt  # a quantidade fica, a unidade pode mudar
    # nenhuma linha de conteudo ficou por traduzir (region espanhola original)
    assert "lentejas" not in result.txt.lower()
    assert "hornea" not in result.txt.lower()


def test_deteta_a_lingua_de_origem():
    result = translate_txt(TXT, "en")
    assert result.detected_lang == "es"


def test_texto_incompleto_traduz_o_que_existe():
    """Funciona mesmo sem PASSOS, para traduzir antes de completar a receita."""
    incompleto = "TITULO: Sopa de Tomate\nINGREDIENTES:\n- 4 tomates\nPASSOS:\n"
    result = translate_txt(incompleto, "en")
    lines = result.txt.splitlines()
    assert lines[0].startswith("TITULO: ") and "Tomato" in lines[0]
    assert lines[-1] == "PASSOS:"  # seccao vazia sobrevive, nada rebenta


def test_texto_vazio_nao_rebenta():
    result = translate_txt("", "en")
    assert result.txt == "\n"


class TestDetectionRisk:
    def test_linha_com_quantidade_e_arriscada(self):
        assert _is_detection_risky("200 g de lentejas")
        assert _is_detection_risky("150 ml de agua")

    def test_frase_normal_nao_e_arriscada(self):
        assert not _is_detection_risky("Triture com a agua")
        assert not _is_detection_risky("Leve ao forno 25 minutos")

    def test_linha_vazia_nao_e_arriscada(self):
        assert not _is_detection_risky("")
