"""`uv run emporio-etl`: recria o banco a partir dos CSVs e regenera o relatório de qualidade."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from emporio.config import RAIZ, get_settings
from emporio.etl.catalogo import construir_banco
from emporio.etl.qualidade import analisar, renderizar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrói o SQLite do catálogo e pedidos a partir dos CSVs.")
    parser.add_argument("--raw", type=Path, default=RAIZ / "data" / "raw", help="Pasta com os CSVs")
    parser.add_argument("--db", type=Path, default=None, help="Caminho do banco (padrão: DB_PATH)")
    parser.add_argument("--relatorio", type=Path, default=RAIZ / "docs" / "qualidade_dos_dados.md")
    parser.add_argument("--agora", type=datetime.fromisoformat, default=None, help="Data de referência (ISO 8601)")
    args = parser.parse_args(argv)

    config = get_settings()
    db_path = args.db or config.caminho(config.db_path)
    agora = args.agora or config.agora_referencia or datetime.now(ZoneInfo("America/Campo_Grande"))

    construir_banco(args.raw, db_path)
    with sqlite3.connect(db_path) as conexao:
        resultado = analisar(conexao, agora)
    args.relatorio.parent.mkdir(parents=True, exist_ok=True)
    args.relatorio.write_text(renderizar(resultado, agora), encoding="utf-8", newline="\n")

    contagem = ", ".join(f"{tabela}: {qtd}" for tabela, qtd in resultado["contagem"].items())
    print(f"Banco recriado em {db_path} ({contagem}).")
    print(f"Relatório em {args.relatorio}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
