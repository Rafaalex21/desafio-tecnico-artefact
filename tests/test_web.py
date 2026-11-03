"""Testes da E6: rotas da API, fluxo SSE e entrega da tela, com o agente alimentado por um LLM roteirizado."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.conftest import AGORA
from tests.test_agente import LLMRoteirizado, chama, fala

from emporio.agent.llm import ErroLLM
from emporio.agent.loop import RESPOSTA_SEM_MODELO, Agente
from emporio.agent.memory import Memoria
from emporio.agent.tools import Ferramentas
from emporio.config import Settings
from emporio.db import abrir_banco
from emporio.web.app import criar_app

SESSAO = "sessao-web-1"


def montar(llm: Any, banco: Path, politicas: dict[str, Any], tmp_path: Path) -> TestClient:
    config = Settings(agora_referencia=AGORA)
    agente = Agente(
        llm=llm,
        memoria=Memoria(tmp_path / "conversas.db"),
        config=config,
        fabrica_ferramentas=lambda sid: Ferramentas(
            abrir_banco(banco), politicas, tmp_path / "handoff.jsonl", sid, config
        ),
    )
    return TestClient(criar_app(agente=agente, config=config))


def eventos(corpo: str) -> list[tuple[str, dict[str, Any]]]:
    saida = []
    for bloco in corpo.strip().split("\n\n"):
        linhas = dict(linha.split(": ", 1) for linha in bloco.split("\n"))
        saida.append((linhas["event"], json.loads(linhas["data"])))
    return saida


def test_tela_e_estaticos_sao_servidos(banco, politicas_geradas, tmp_path):
    cliente = montar(LLMRoteirizado(), banco, politicas_geradas, tmp_path)
    pagina = cliente.get("/")
    assert pagina.status_code == 200
    assert "Empório da Música" in pagina.text and "Riff" in pagina.text
    for caminho in ("/static/app.js", "/static/styles.css", "/static/riff.svg"):
        assert cliente.get(caminho).status_code == 200


def test_chat_emite_status_mensagem_e_fim_em_ordem(banco, politicas_geradas, tmp_path):
    llm = LLMRoteirizado(chama("consultar_politicas", {"topicos": ["sobre_a_loja"]}), fala("Ficamos em Campo Grande."))
    cliente = montar(llm, banco, politicas_geradas, tmp_path)
    resposta = cliente.post("/api/chat", json={"session_id": SESSAO, "message": "Onde vocês ficam?"})
    assert resposta.headers["content-type"].startswith("text/event-stream")
    lista = eventos(resposta.text)
    assert [nome for nome, _ in lista] == ["status", "message", "done"]
    assert lista[0][1] == {"ferramenta": "consultar_politicas", "rotulo": "Consultando as políticas da loja"}
    mensagem = lista[1][1]
    assert mensagem["content"] == "Ficamos em Campo Grande."
    assert mensagem["ferramentas"] == [{"nome": "consultar_politicas", "argumentos": {"topicos": ["sobre_a_loja"]}}]
    assert mensagem["latencia_ms"] >= 0 and mensagem["erro"] is False


def test_historico_restaura_so_o_que_o_cliente_ve(banco, politicas_geradas, tmp_path):
    llm = LLMRoteirizado(chama("consultar_politicas", {"topicos": ["sobre_a_loja"]}), fala("Ficamos em Campo Grande."))
    cliente = montar(llm, banco, politicas_geradas, tmp_path)
    cliente.post("/api/chat", json={"session_id": SESSAO, "message": "Onde vocês ficam?"})
    restaurado = cliente.get(f"/api/sessions/{SESSAO}/messages").json()["messages"]
    assert restaurado == [
        {"role": "user", "content": "Onde vocês ficam?"},
        {"role": "assistant", "content": "Ficamos em Campo Grande."},
    ]
    assert cliente.get("/api/sessions/outra-sessao/messages").json() == {"messages": [], "em_curso": None}


@pytest.mark.parametrize(
    "corpo",
    [
        {"session_id": "x", "message": "oi"},
        {"session_id": "sessao com espaço", "message": "oi"},
        {"session_id": SESSAO, "message": ""},
        {"session_id": SESSAO, "message": "a" * 4001},
        {"message": "oi"},
    ],
)
def test_entrada_invalida_e_recusada(corpo, banco, politicas_geradas, tmp_path):
    cliente = montar(LLMRoteirizado(), banco, politicas_geradas, tmp_path)
    assert cliente.post("/api/chat", json=corpo).status_code == 422


def test_id_de_sessao_invalido_na_leitura(banco, politicas_geradas, tmp_path):
    cliente = montar(LLMRoteirizado(), banco, politicas_geradas, tmp_path)
    assert cliente.get("/api/sessions/a b/messages").status_code in (404, 422)
    assert cliente.get("/api/sessions/x/messages").status_code == 422


def test_modelo_fora_do_ar_vira_mensagem_com_erro(banco, politicas_geradas, tmp_path):
    llm = LLMRoteirizado(ErroLLM("sem conexão"))
    cliente = montar(llm, banco, politicas_geradas, tmp_path)
    lista = eventos(cliente.post("/api/chat", json={"session_id": SESSAO, "message": "oi"}).text)
    assert [nome for nome, _ in lista] == ["message", "done"]
    assert lista[0][1]["content"] == RESPOSTA_SEM_MODELO and lista[0][1]["erro"] is True


def test_falha_inesperada_vira_evento_de_erro_sem_vazar_detalhes(banco, politicas_geradas, tmp_path):
    class Quebrado:
        config = Settings(agora_referencia=AGORA)
        memoria = Memoria(tmp_path / "x.db")

        def responder(self, *args: Any, **kwargs: Any):
            raise RuntimeError("detalhe interno secreto")

    cliente = TestClient(criar_app(agente=Quebrado(), config=Quebrado.config))  # type: ignore[arg-type]
    corpo = cliente.post("/api/chat", json={"session_id": SESSAO, "message": "oi"}).text
    lista = eventos(corpo)
    assert [nome for nome, _ in lista] == ["error", "done"]
    assert "secreto" not in corpo


def test_loja_e_saude(banco, politicas_geradas, tmp_path):
    cliente = montar(LLMRoteirizado(), banco, politicas_geradas, tmp_path)
    loja = cliente.get("/api/loja").json()
    assert loja["aberta"] is True and "Aberta" in loja["texto"]
    saude = cliente.get("/api/health").json()
    assert saude == {"llm": "erro", "modelo": "qwen3-14b"}
