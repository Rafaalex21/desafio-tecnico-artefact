"""Servidor real da tela de chat para os testes end-to-end, em porta livre.

O sistema testado é o de produção (FastAPI, ferramentas, banco, guardrails e a tela). Só o servidor de modelos é
trocado, por `LLMDeRoteiro`, e o modelo real fica para os testes marcados com `real`."""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from tests.conftest import AGORA
from tests.e2e.roteiro import LLMDeRoteiro

from emporio.agent.loop import Agente
from emporio.agent.memory import Memoria
from emporio.agent.tools import Ferramentas
from emporio.config import Settings, get_settings
from emporio.db import abrir_banco
from emporio.web.app import criar_app


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


def _porta_livre() -> int:
    with socket.socket() as soquete:
        soquete.bind(("127.0.0.1", 0))
        return soquete.getsockname()[1]


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict[str, Any]) -> dict[str, Any]:
    """Usa o navegador já instalado (Edge por padrão no Windows), sem baixar o Chromium do Playwright."""
    canal = os.environ.get("E2E_CANAL", "msedge")
    return {**browser_type_launch_args, **({"channel": canal} if canal else {})}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    return {**browser_context_args, "locale": "pt-BR"}


def _subir(app: Any) -> Iterator[str]:
    porta = _porta_livre()
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    fio = threading.Thread(target=servidor.run, daemon=True)
    fio.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("O servidor de teste não subiu.")
    yield f"http://127.0.0.1:{porta}"
    servidor.should_exit = True
    fio.join(timeout=10)


@pytest.fixture(scope="session")
def base_url(banco: Path, politicas_geradas: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    pasta = tmp_path_factory.mktemp("e2e")
    config = Settings(agora_referencia=AGORA)
    agente = Agente(
        llm=LLMDeRoteiro(),
        memoria=Memoria(pasta / "conversas.db"),
        config=config,
        fabrica_ferramentas=lambda sid: Ferramentas(
            abrir_banco(banco), politicas_geradas, pasta / "handoff.jsonl", sid, config
        ),
    )
    yield from _subir(criar_app(agente=agente, config=config))


@pytest.fixture(scope="session")
def url_modelo_real(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Mesma tela, com o modelo local de verdade; só roda com `E2E_MODELO_REAL=1` e o servidor de modelos ligado."""
    if os.environ.get("E2E_MODELO_REAL") != "1":
        pytest.skip("defina E2E_MODELO_REAL=1 e ligue o LM Studio para rodar contra o modelo real")
    pasta = tmp_path_factory.mktemp("e2e-real")
    config = get_settings().model_copy(
        update={
            "agora_referencia": AGORA,
            "conversas_db_path": pasta / "c.db",
            "handoff_path": pasta / "handoff.jsonl",
        }
    )
    yield from _subir(criar_app(agente=Agente(config=config, memoria=Memoria(pasta / "c.db")), config=config))
