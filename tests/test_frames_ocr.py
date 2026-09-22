"""Testes da parte pura do frames_ocr.py -- sem ffmpeg/Tesseract/rede.

O resto do modulo (download, extracao de fotogramas, OCR) precisa do
ambiente instalado e e validado manualmente; estas funcoes sao logica pura
e valem a pena cobrir sem essa dependencia.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.frames_ocr import MAX_FRAMES, MIN_FRAMES, _dedupe, _dedupe_key, _frame_budget, _is_useful


def test_chave_ignora_acentos_e_pontuacao():
    assert _dedupe_key("Déjalos") == _dedupe_key("Dejalos") == "dejalos"


def test_dedupe_prefere_a_variante_acentuada():
    """Caso real: um fotograma le "SACATELOS", outro le "SÁCATELOS" -- so a
    segunda deve sobreviver, em vez de aparecerem os dois passos repetidos."""
    result = _dedupe(["SACATELOS", "SÁCATELOS"])
    assert result == ["SÁCATELOS"]


def test_dedupe_mantem_a_ordem_de_primeira_aparicao():
    result = _dedupe(["Horno", "Chocolate", "horno", "Negro"])
    assert result == ["Horno", "Chocolate", "Negro"]


def test_dedupe_ignora_fragmentos_demasiado_curtos():
    assert _dedupe(["ab", "abc", "Chocolate"]) == ["Chocolate"]


class TestFrameBudget:
    def test_video_curto_usa_o_minimo(self):
        count, interval = _frame_budget(5.0, MAX_FRAMES)
        assert count == MIN_FRAMES

    def test_video_longo_fica_limitado_ao_maximo(self):
        count, interval = _frame_budget(300.0, MAX_FRAMES)
        assert count == MAX_FRAMES
        assert interval == 300.0 / MAX_FRAMES

    def test_sem_duracao_nao_rebenta(self):
        count, interval = _frame_budget(0.0, MAX_FRAMES)
        assert count == MIN_FRAMES
        assert interval > 0

    def test_video_medio_fica_entre_os_limites(self):
        count, interval = _frame_budget(36.0, MAX_FRAMES)
        assert MIN_FRAMES <= count <= MAX_FRAMES
        assert 0.9 <= interval <= 1.1  # perto do FRAME_INTERVAL alvo


def test_is_useful_filtra_fragmentos_de_ruido():
    assert not _is_useful("y Ss 5")
    assert not _is_useful("ab")
    assert _is_useful("SÁCATELOS")
    assert _is_useful("Chocolate")
