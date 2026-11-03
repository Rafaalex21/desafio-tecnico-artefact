"""Fixtures compartilhadas: banco e políticas gerados a partir de `data/raw`, relógio fixo em 25/03/2026."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from emporio.agent.tools import Ferramentas
from emporio.config import RAIZ, Settings
from emporio.db import abrir_banco
from emporio.etl.catalogo import construir_banco
from emporio.etl.politicas import gerar_politicas

AGORA = datetime.fromisoformat("2026-03-25T10:30:00-04:00")


@pytest.fixture(scope="session")
def banco(tmp_path_factory: pytest.TempPathFactory) -> Path:
    caminho = tmp_path_factory.mktemp("banco") / "emporio.db"
    construir_banco(RAIZ / "data" / "raw", caminho)
    return caminho


@pytest.fixture(scope="session")
def politicas_geradas(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    pdf = RAIZ / "data" / "raw" / "políticas_da_loja.pdf"
    return gerar_politicas(pdf, tmp_path_factory.mktemp("politicas") / "politicas.json")


@pytest.fixture()
def ferramentas(banco: Path, politicas_geradas: dict[str, Any], tmp_path: Path):
    """Ferramentas de uma sessão nova, com verificação zerada e arquivo de encaminhamentos próprio."""
    conexao = abrir_banco(banco)
    yield Ferramentas(
        conexao, politicas_geradas, tmp_path / "handoff.jsonl", "sessao-teste", Settings(agora_referencia=AGORA)
    )
    conexao.close()
