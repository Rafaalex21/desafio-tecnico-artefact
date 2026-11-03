"""Memória das conversas em SQLite (seção 10): mensagens no formato OpenAI, estado de verificação e corte por tokens."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from emporio.domain.orders import Verificacao

CARACTERES_POR_TOKEN = 3.5

DDL = """
CREATE TABLE IF NOT EXISTS sessoes (
    session_id             TEXT PRIMARY KEY,
    criado_em              TEXT NOT NULL,
    clientes_verificados   TEXT NOT NULL DEFAULT '[]',
    tentativas_verificacao INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mensagens (
    session_id      TEXT NOT NULL REFERENCES sessoes (session_id),
    seq             INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT,
    tool_calls_json TEXT,
    tool_call_id    TEXT,
    criado_em       TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
"""


def estimar_tokens(mensagem: dict[str, Any]) -> int:
    tamanho = len(str(mensagem.get("content") or "")) + len(json.dumps(mensagem.get("tool_calls") or []))
    return int(tamanho / CARACTERES_POR_TOKEN) + 4


def recortar(mensagens: list[dict[str, Any]], orcamento: int) -> list[dict[str, Any]]:
    """Remove os turnos completos mais antigos até caber no orçamento. O último turno nunca sai."""
    inicios = [i for i, m in enumerate(mensagens) if m["role"] == "user"]
    if not inicios:
        return mensagens
    turnos = [mensagens[a:b] for a, b in zip(inicios, [*inicios[1:], len(mensagens)], strict=True)]
    while len(turnos) > 1 and sum(estimar_tokens(m) for turno in turnos for m in turno) > orcamento:
        turnos.pop(0)
    return [m for turno in turnos for m in turno]


@dataclass
class Memoria:
    caminho: Path

    def __post_init__(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conexao()) as conexao:
            conexao.executescript(DDL)

    def _conexao(self) -> sqlite3.Connection:
        conexao = sqlite3.connect(self.caminho, timeout=10)
        conexao.row_factory = sqlite3.Row
        return conexao

    def existe(self, session_id: str) -> bool:
        with closing(self._conexao()) as conexao:
            return conexao.execute("SELECT 1 FROM sessoes WHERE session_id = ?", (session_id,)).fetchone() is not None

    def carregar(self, session_id: str) -> list[dict[str, Any]]:
        with closing(self._conexao()) as conexao:
            linhas = conexao.execute(
                "SELECT role, content, tool_calls_json, tool_call_id FROM mensagens WHERE session_id = ? ORDER BY seq",
                (session_id,),
            ).fetchall()
        mensagens = []
        for linha in linhas:
            mensagem: dict[str, Any] = {"role": linha["role"], "content": linha["content"] or ""}
            if linha["tool_calls_json"]:
                mensagem["tool_calls"] = json.loads(linha["tool_calls_json"])
            if linha["tool_call_id"]:
                mensagem["tool_call_id"] = linha["tool_call_id"]
            mensagens.append(mensagem)
        return mensagens

    def anexar(self, session_id: str, mensagens: list[dict[str, Any]], agora: datetime) -> None:
        with closing(self._conexao()) as conexao, conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO sessoes (session_id, criado_em) VALUES (?, ?)", (session_id, agora.isoformat())
            )
            proximo = conexao.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM mensagens WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            for deslocamento, mensagem in enumerate(mensagens, start=1):
                tool_calls = mensagem.get("tool_calls")
                conexao.execute(
                    "INSERT INTO mensagens VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        proximo + deslocamento,
                        mensagem["role"],
                        mensagem.get("content"),
                        json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                        mensagem.get("tool_call_id"),
                        agora.isoformat(),
                    ),
                )

    def verificacao(self, session_id: str) -> Verificacao:
        with closing(self._conexao()) as conexao:
            linha = conexao.execute(
                "SELECT clientes_verificados, tentativas_verificacao FROM sessoes WHERE session_id = ?", (session_id,)
            ).fetchone()
        if linha is None:
            return Verificacao()
        return Verificacao(linha["tentativas_verificacao"], set(json.loads(linha["clientes_verificados"])))

    def salvar_verificacao(self, session_id: str, verificacao: Verificacao, agora: datetime) -> None:
        with closing(self._conexao()) as conexao, conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO sessoes (session_id, criado_em) VALUES (?, ?)", (session_id, agora.isoformat())
            )
            conexao.execute(
                "UPDATE sessoes SET clientes_verificados = ?, tentativas_verificacao = ? WHERE session_id = ?",
                (json.dumps(sorted(verificacao.clientes)), verificacao.falhas, session_id),
            )

    def mensagens_visiveis(self, session_id: str) -> list[dict[str, str]]:
        """Só o que o cliente vê: suas mensagens e as respostas finais do assistente."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.carregar(session_id)
            if m["role"] in ("user", "assistant") and not m.get("tool_calls") and m["content"]
        ]
