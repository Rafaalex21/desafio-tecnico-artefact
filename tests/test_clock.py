"""Testes da E2: relógio do sistema e estado da loja (seção 6.10)."""

from __future__ import annotations

from datetime import datetime

import pytest

from emporio.clock import FUSO, agora, estado_loja
from emporio.config import Settings, get_settings


def em(texto: str) -> datetime:
    return datetime.fromisoformat(texto).replace(tzinfo=FUSO)


def test_quarta_de_manha_esta_aberta_ate_as_18h():
    estado = estado_loja(em("2026-03-25T10:30"))
    assert estado.aberta and estado.fecha_as.strftime("%H:%M") == "18:00" and estado.proxima_abertura is None
    assert estado.texto == "Aberta agora; hoje fechamos às 18:00."


def test_sabado_apos_as_13h_reabre_na_segunda():
    estado = estado_loja(em("2026-03-28T13:01"))
    assert not estado.aberta and estado.fecha_as is None
    assert estado.proxima_abertura == em("2026-03-30T09:00")
    assert estado.texto == "Fechada agora; reabrimos segunda-feira (30/03) às 09:00."


def test_domingo_reabre_na_segunda():
    estado = estado_loja(em("2026-03-29T15:00"))
    assert not estado.aberta and estado.proxima_abertura == em("2026-03-30T09:00")


@pytest.mark.parametrize(
    ("momento", "aberta"),
    [
        ("2026-03-25T08:59", False), ("2026-03-25T09:00", True), ("2026-03-25T17:59", True),
        ("2026-03-25T18:00", False), ("2026-03-28T09:00", True), ("2026-03-28T12:59", True),
        ("2026-03-28T13:00", False), ("2026-03-29T10:00", False), ("2026-03-30T00:00", False),
    ],
)
def test_limites_do_horario(momento, aberta):
    assert estado_loja(em(momento)).aberta is aberta


def test_antes_de_abrir_o_texto_diz_hoje():
    estado = estado_loja(em("2026-03-25T08:00"))
    assert estado.proxima_abertura == em("2026-03-25T09:00")
    assert estado.texto == "Fechada agora; reabrimos hoje às 09:00."


def test_depois_de_fechar_o_texto_diz_amanha():
    texto = estado_loja(em("2026-03-25T19:00")).texto
    assert texto == "Fechada agora; reabrimos amanhã (quinta-feira, 26/03) às 09:00."


def test_sexta_apos_fechar_reabre_no_sabado():
    estado = estado_loja(em("2026-03-27T18:30"))
    assert estado.proxima_abertura == em("2026-03-28T09:00")
    assert "amanhã (sábado, 28/03)" in estado.texto


def test_horario_com_outro_fuso_e_convertido():
    estado = estado_loja(datetime.fromisoformat("2026-03-25T14:30:00+00:00"))  # 10h30 em Campo Grande
    assert estado.aberta


def test_como_dict_e_serializavel():
    dados = estado_loja(em("2026-03-28T13:01")).como_dict()
    assert dados["aberta"] is False and dados["fecha_as"] is None
    assert dados["proxima_abertura"] == "2026-03-30T09:00:00-04:00"


def test_agora_usa_a_referencia_configurada():
    config = Settings(agora_referencia=datetime.fromisoformat("2026-03-25T10:30:00-04:00"))
    assert agora(config) == em("2026-03-25T10:30") and agora(config).utcoffset().total_seconds() == -4 * 3600


def test_agora_converte_referencia_de_outro_fuso():
    config = Settings(agora_referencia=datetime.fromisoformat("2026-03-25T14:30:00+00:00"))
    assert agora(config).hour == 10


def test_agora_sem_referencia_usa_o_relogio_real():
    config = Settings(agora_referencia=None)
    assert abs((agora(config) - datetime.now(FUSO)).total_seconds()) < 5


def test_variavel_de_ambiente_altera_o_relogio_de_todo_o_sistema(monkeypatch):
    monkeypatch.setenv("AGORA_REFERENCIA", "2026-03-28T13:01:00-04:00")
    get_settings.cache_clear()
    try:
        assert agora() == em("2026-03-28T13:01")
        assert not estado_loja().aberta
    finally:
        monkeypatch.delenv("AGORA_REFERENCIA")
        get_settings.cache_clear()
