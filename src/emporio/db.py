"""Abertura do banco de dados do catálogo: as ferramentas só leem, então a conexão é somente leitura."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def abrir_banco(caminho: Path) -> sqlite3.Connection:
    if not caminho.exists():
        raise FileNotFoundError(f"Banco não encontrado em {caminho}. Rode `uv run emporio-etl` antes.")
    conexao = sqlite3.connect(f"{caminho.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
    conexao.row_factory = sqlite3.Row
    return conexao
