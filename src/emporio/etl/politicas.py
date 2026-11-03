"""Converte o manual de políticas (PDF) em seções numeradas, em `politicas.json` (seção 15, etapa E2).

O texto bruto sai de `pymupdf4llm`. Três limpezas e três correções explícitas, todas registradas em `correcoes`
no próprio arquivo gerado:

1. cabeçalhos e rodapés de página são removidos;
2. tabelas com coluna vazia deslocada (horário de funcionamento) são realinhadas;
3. o espaço perdido em telefones, como `(67)3341-4444`, é restaurado;
4. T11: o e-mail com acento da ficha cadastral passa para a forma sem acento;
5. T12: a parcela mínima fixa da tabela de pagamentos remete às regras escalonadas da seção 3.1.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any

from emporio.domain.policies import TOPICOS

VERSAO_MANUAL = "2.1"

_CABECALHO_SECAO = re.compile(r"^#{2,4}\s+(?:\*\*)?(\d+(?:\.\d+)?)\.?\s+(.+?)(?:\*\*)?\s*$")
_RUIDO_DE_PAGINA = (
    re.compile(r"^\*\*Empório da Música\*\* Manual de Políticas e Procedimentos\s*$"),
    re.compile(r"^Página \d+\s*$"),
)
_TELEFONE_SEM_ESPACO = re.compile(r"\((\d{2})\)(\d)")

CORRECOES_DE_TEXTO: tuple[tuple[str, str, str], ...] = (
    (
        "contato@empóriodamusica.com.br",
        "contato@emporiodamusica.com.br",
        "T11: e-mail da ficha cadastral sem acento, como na capa do manual",
    ),
    (
        "Parcela mínima de R$ 100,00",
        "Parcela mínima conforme as regras de parcelamento (seção 3.1)",
        "T12: a tabela de pagamentos fixa R$ 100,00, mas a seção 3.1, mais específica, escalona o mínimo",
    ),
)


def markdown_do_pdf(pdf: Path) -> str:
    # O pymupdf4llm imprime avisos sobre OCR opcional ao ser importado e ao converter; o ETL não precisa de OCR.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import pymupdf4llm

        return pymupdf4llm.to_markdown(str(pdf))


def _celulas(linha: str) -> list[str]:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def _tabela(linhas: list[str]) -> list[str]:
    """Realinha uma tabela cujo cabeçalho tem células vazias e remove marcação de negrito do cabeçalho."""
    celulas = [_celulas(linha.replace("<br>", " ")) for linha in linhas]
    cabecalho = [c.replace("**", "").strip() for c in celulas[0]]
    vazias = sum(1 for c in cabecalho if not c)
    cabecalho = [c for c in cabecalho if c]
    corpo = []
    for linha in celulas[2:]:
        for _ in range(vazias):
            if linha and not linha[-1]:
                linha = linha[:-1]
        corpo.append(linha)
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(linha) + " |" for linha in corpo]
    return saida


def _limpar(linhas: list[str]) -> str:
    saida: list[str] = []
    bloco: list[str] = []
    for linha in linhas + [""]:
        if linha.lstrip().startswith("|"):
            bloco.append(linha)
            continue
        if bloco:
            saida.extend(_tabela(bloco))
            bloco = []
        saida.append(linha.rstrip())
    texto = "\n".join(saida)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return _TELEFONE_SEM_ESPACO.sub(r"(\1) \2", texto)


def extrair_secoes(markdown: str) -> dict[str, dict[str, str]]:
    """Divide o manual em seções e subseções; o texto de cada uma exclui as subseções."""
    linhas = [x for x in markdown.splitlines() if not any(r.match(x) for r in _RUIDO_DE_PAGINA)]
    secoes: dict[str, dict[str, str]] = {}
    atual: tuple[str, str] | None = None
    corpo: list[str] = []

    def fechar() -> None:
        if atual:
            numero, titulo = atual
            secoes[numero] = {"numero": numero, "titulo": titulo, "texto": _limpar(corpo)}

    for linha in linhas:
        cabecalho = _CABECALHO_SECAO.match(linha)
        if cabecalho:
            fechar()
            atual, corpo = (cabecalho.group(1), cabecalho.group(2).replace("**", "").strip()), []
        elif atual:
            corpo.append(linha)
    fechar()
    return secoes


def gerar_politicas(pdf: Path, saida: Path) -> dict[str, Any]:
    secoes = extrair_secoes(markdown_do_pdf(pdf))
    correcoes = []
    for antes, depois, motivo in CORRECOES_DE_TEXTO:
        ocorrencias = [n for n, s in secoes.items() if antes in s["texto"]]
        for numero in ocorrencias:
            secoes[numero]["texto"] = secoes[numero]["texto"].replace(antes, depois)
        correcoes.append({"motivo": motivo, "secoes": ocorrencias})
    ausentes = [n for numeros in TOPICOS.values() for n in numeros if n not in secoes]
    if ausentes:
        raise ValueError(f"Seções do manual não encontradas: {ausentes}")
    documento = {
        "versao_manual": VERSAO_MANUAL,
        "secoes": secoes,
        "topicos": {topico: list(numeros) for topico, numeros in TOPICOS.items()},
        "correcoes": correcoes,
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return documento
