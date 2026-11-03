"""Troca o nome do usuário do sistema operacional por `usuario` nos relatórios dos testes end-to-end.

O pytest grava caminhos absolutos (a raiz do projeto e os arquivos de teste) no HTML e no JSON; como esses
relatórios são versionados, o nome da conta local não deve seguir junto.

Uso:
    python scripts/anonimizar_relatorio_e2e.py
"""

from __future__ import annotations

import getpass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RELATORIOS = ("e2e-report/index.html", "e2e-report/results.json")


def main() -> int:
    usuario = getpass.getuser()
    for caminho in RELATORIOS:
        arquivo = RAIZ / caminho
        if arquivo.exists():
            texto = arquivo.read_text(encoding="utf-8")
            arquivo.write_text(texto.replace(usuario, "usuario"), encoding="utf-8")
            print(f"{caminho}: {texto.count(usuario)} ocorrência(s) trocada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
