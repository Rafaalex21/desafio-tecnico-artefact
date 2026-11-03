"""Busca de produtos e detalhes (seções 7.1 e 7.2): filtros em SQL e correspondência aproximada com rapidfuzz."""

from __future__ import annotations

import json
import re
import sqlite3
from decimal import Decimal
from typing import Any, Literal

from rapidfuzz import fuzz

from emporio.domain.errors import ErroFerramenta
from emporio.domain.money import de_centavos, fmt_brl, para_centavos
from emporio.domain.payments import preco_pix
from emporio.domain.texto import normalizar

CORTE_BUSCA = 70
EMPATE_NOME = 5
LIMITE_PADRAO = 15
LIMITE_MAXIMO = 30
ALTERNATIVAS_MAXIMAS = 3
INDISPONIVEIS = ("esgotado", "descontinuado", "em_breve")

Ordem = Literal["relevancia", "menor_preco", "maior_preco"]


def _variantes(termo: str) -> list[str]:
    """Termo normalizado, com hífens e pontuação como espaço e também colados (`gd-20` e `gd20`)."""
    separado = " ".join(re.sub(r"[^a-z0-9]+", " ", normalizar(termo)).split())
    colado = separado.replace(" ", "")
    return list(dict.fromkeys(v for v in (separado, colado) if v))


def pontuar(termo: str, alvo: str) -> float:
    """Maior entre `token_set_ratio` e `partial_ratio` do termo sobre o texto, já normalizado."""
    alvo_limpo = " ".join(re.sub(r"[^a-z0-9]+", " ", alvo).split())
    return max(
        max(fuzz.token_set_ratio(v, alvo_limpo), fuzz.partial_ratio(v, alvo_limpo)) for v in _variantes(termo)
    )


def _preco(centavos: int) -> str:
    return fmt_brl(de_centavos(centavos))


def _promocao(linha: sqlite3.Row) -> dict[str, Any] | None:
    if linha["promo_percent"] is None:
        return None
    return {"percentual": linha["promo_percent"], "preco_promocional": _preco(linha["preco_final_cents"])}


def categorias(conexao: sqlite3.Connection) -> list[str]:
    return [linha["name"] for linha in conexao.execute("SELECT name FROM categories ORDER BY category_id")]


def _categoria_canonica(conexao: sqlite3.Connection, informada: str) -> str:
    alvo = normalizar(informada).strip()
    nomes = categorias(conexao)
    for nome in nomes:
        if normalizar(nome) == alvo:
            return nome
    parecidas = [n for n in nomes if alvo and alvo in normalizar(n)]
    if len(parecidas) == 1:
        return parecidas[0]
    raise ErroFerramenta(
        "categoria_invalida", f"Categoria desconhecida: {informada!r}.", categorias_validas=nomes
    )


def buscar_produtos(
    conexao: sqlite3.Connection,
    termo: str | None = None,
    categoria: str | None = None,
    preco_min: Decimal | None = None,
    preco_max: Decimal | None = None,
    apenas_em_promocao: bool = False,
    incluir_indisponiveis: bool = False,
    ordenar_por: Ordem | None = None,
    limite: int = LIMITE_PADRAO,
) -> dict[str, Any]:
    termo = (termo or "").strip() or None
    limite = max(1, min(limite, LIMITE_MAXIMO))
    ordenar_por = ordenar_por or ("relevancia" if termo else "menor_preco")
    if ordenar_por == "relevancia" and not termo:
        ordenar_por = "menor_preco"

    condicoes: list[str] = []
    parametros: list[Any] = []
    categoria_sem_itens = False
    if categoria:
        categoria = _categoria_canonica(conexao, categoria)
        condicoes.append("categoria = ?")
        parametros.append(categoria)
        total_na_categoria = conexao.execute(
            "SELECT COUNT(*) FROM catalogo WHERE categoria = ?", (categoria,)
        ).fetchone()[0]
        categoria_sem_itens = total_na_categoria == 0
    if preco_min is not None:
        condicoes.append("preco_final_cents >= ?")
        parametros.append(para_centavos(preco_min))
    if preco_max is not None:
        condicoes.append("preco_final_cents <= ?")
        parametros.append(para_centavos(preco_max))
    if apenas_em_promocao:
        condicoes.append("promo_percent IS NOT NULL")
    if not incluir_indisponiveis:
        condicoes.append("disponibilidade = 'disponivel'")

    where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    linhas = conexao.execute(f"SELECT * FROM catalogo {where}", parametros).fetchall()

    pontos = {linha["product_id"]: 0.0 for linha in linhas}
    if termo:
        pontos = {linha["product_id"]: pontuar(termo, linha["texto_busca"]) for linha in linhas}
        linhas = [linha for linha in linhas if pontos[linha["product_id"]] >= CORTE_BUSCA]

    if ordenar_por == "relevancia":
        linhas.sort(key=lambda r: (-pontos[r["product_id"]], r["preco_final_cents"], r["product_id"]))
    else:
        linhas.sort(key=lambda r: (r["preco_final_cents"], r["product_id"]), reverse=ordenar_por == "maior_preco")

    exibidos = linhas[:limite]
    return {
        "total_encontrado": len(linhas),
        "exibidos": len(exibidos),
        "categoria_sem_itens": categoria_sem_itens,
        "produtos": [
            {
                "id": linha["product_id"],
                "nome": linha["nome"],
                "categoria": linha["categoria"],
                "preco": _preco(linha["price_cents"]),
                "promocao": _promocao(linha),
                "disponibilidade": linha["disponibilidade"],
            }
            for linha in exibidos
        ],
    }


def _resolver_produto(conexao: sqlite3.Connection, produto: int | str) -> sqlite3.Row:
    """Id exato ou melhor correspondência por nome; empate próximo vira `produto_ambiguo` com candidatos."""
    texto = str(produto).strip()
    if texto.isdigit():
        linha = conexao.execute("SELECT * FROM catalogo WHERE product_id = ?", (int(texto),)).fetchone()
        if linha is None:
            raise ErroFerramenta("produto_nao_encontrado", f"Não existe produto com id {texto}.")
        return linha

    linhas = conexao.execute("SELECT * FROM catalogo").fetchall()
    alvo = normalizar(texto)
    exatos = [linha for linha in linhas if normalizar(linha["nome"]) == alvo]
    if len(exatos) == 1:
        return exatos[0]
    pontuados = sorted(
        ((pontuar(texto, normalizar(linha["nome"])), linha) for linha in linhas),
        key=lambda par: (-par[0], par[1]["product_id"]),
    )
    melhor = pontuados[0][0] if pontuados else 0
    if melhor < CORTE_BUSCA:
        raise ErroFerramenta("produto_nao_encontrado", f"Nenhum produto parecido com {texto!r}.")
    proximos = [linha for pontos, linha in pontuados if melhor - pontos < EMPATE_NOME]
    if len(proximos) > 1:
        raise ErroFerramenta(
            "produto_ambiguo",
            "Mais de um produto combina com o nome; pergunte ao cliente qual deles.",
            candidatos=[{"id": linha["product_id"], "nome": linha["nome"]} for linha in proximos[:5]],
        )
    return pontuados[0][1]


def _alternativas(conexao: sqlite3.Connection, produto: sqlite3.Row) -> list[dict[str, Any]]:
    candidatas = conexao.execute(
        "SELECT * FROM catalogo WHERE category_id = ? AND disponibilidade = 'disponivel' AND product_id != ?",
        (produto["category_id"], produto["product_id"]),
    ).fetchall()
    nome_base = normalizar(produto["nome"])
    base = produto["price_cents"]

    def nota(linha: sqlite3.Row) -> float:
        similaridade = fuzz.token_set_ratio(nome_base, normalizar(linha["nome"])) / 100
        proximidade = 1 - abs(linha["preco_final_cents"] - base) / max(linha["preco_final_cents"], base)
        return 0.6 * similaridade + 0.4 * proximidade

    melhores = sorted(candidatas, key=lambda r: (-nota(r), r["product_id"]))[:ALTERNATIVAS_MAXIMAS]
    return [
        {
            "id": linha["product_id"],
            "nome": linha["nome"],
            "preco": _preco(linha["price_cents"]),
            "promocao": _promocao(linha),
        }
        for linha in melhores
    ]


def detalhes_produto(conexao: sqlite3.Connection, produto: int | str) -> dict[str, Any]:
    linha = _resolver_produto(conexao, produto)
    disponivel = linha["disponibilidade"] == "disponivel"
    com_promocao = linha["promo_percent"] is not None
    pix = None
    if disponivel and not com_promocao:
        pix = fmt_brl(preco_pix(de_centavos(linha["price_cents"])))
    return {
        "id": linha["product_id"],
        "nome": linha["nome"],
        "marca": linha["marca"],
        "categoria": linha["categoria"],
        "preco": _preco(linha["price_cents"]),
        "promocao": _promocao(linha),
        "preco_pix": pix,
        "disponibilidade": linha["disponibilidade"],
        "ultimas_unidades": disponivel and linha["estoque"] <= 2,
        "especificacoes": json.loads(linha["specs"]),
        "descricao": linha["descricao"] if linha["descricao_confiavel"] else None,
        "alternativas": [] if disponivel else _alternativas(conexao, linha),
    }
