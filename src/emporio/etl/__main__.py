"""`uv run emporio-etl`: recria o banco a partir dos CSVs e regenera o relatório de qualidade."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from emporio.clock import agora as agora_do_sistema
from emporio.config import RAIZ, get_settings
from emporio.etl.catalogo import construir_banco
from emporio.etl.politicas import gerar_politicas
from emporio.etl.qualidade import analisar, renderizar

PDF_POLITICAS = "políticas_da_loja.pdf"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constrói o SQLite de catálogo e pedidos e as seções do manual de políticas."
    )
    parser.add_argument("--raw", type=Path, default=RAIZ / "data" / "raw", help="Pasta com os CSVs e o PDF do manual")
    parser.add_argument("--db", type=Path, default=None, help="Caminho do banco (padrão: DB_PATH)")
    parser.add_argument("--politicas", type=Path, default=None, help="Saída das seções (padrão: POLITICAS_PATH)")
    parser.add_argument("--relatorio", type=Path, default=RAIZ / "docs" / "qualidade_dos_dados.md")
    parser.add_argument("--agora", type=datetime.fromisoformat, default=None, help="Data de referência (ISO 8601)")
    args = parser.parse_args(argv)

    config = get_settings()
    db_path = args.db or config.caminho(config.db_path)
    politicas_path = args.politicas or config.caminho(config.politicas_path)
    agora = args.agora or agora_do_sistema(config)

    construir_banco(args.raw, db_path)
    with closing(sqlite3.connect(db_path)) as conexao:
        resultado = analisar(conexao, agora)
    args.relatorio.parent.mkdir(parents=True, exist_ok=True)
    args.relatorio.write_text(renderizar(resultado, agora), encoding="utf-8", newline="\n")
    politicas = gerar_politicas(args.raw / PDF_POLITICAS, politicas_path)

    contagem = ", ".join(f"{tabela}: {qtd}" for tabela, qtd in resultado["contagem"].items())
    print(f"Banco recriado em {db_path} ({contagem}).")
    print(f"Políticas em {politicas_path} ({len(politicas['secoes'])} seções).")
    print(f"Relatório em {args.relatorio}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
