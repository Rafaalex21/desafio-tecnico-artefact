"""Simulação de compra (seção 7.3): subtotal, PIX, parcelamento e frete calculados em Decimal."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any

from emporio.domain.errors import ErroFerramenta
from emporio.domain.money import de_centavos, fmt_brl
from emporio.domain.payments import (
    calcular_frete,
    combinacao_permitida,
    frete_especial,
    opcoes_cartao,
    preco_pix,
)


def _juntar(itens: list[tuple[int, int]]) -> dict[int, int]:
    quantidades: dict[int, int] = {}
    for produto_id, quantidade in itens:
        if quantidade < 1:
            raise ErroFerramenta("quantidade_invalida", "A quantidade de cada produto deve ser de pelo menos 1.")
        quantidades[produto_id] = quantidades.get(produto_id, 0) + quantidade
    return quantidades


def simular_compra(
    conexao: sqlite3.Connection, itens: list[tuple[int, int]], cidade_entrega: str | None = None
) -> dict[str, Any]:
    if not itens:
        raise ErroFerramenta("carrinho_vazio", "Informe ao menos um produto para simular a compra.")

    linhas_itens: list[dict[str, Any]] = []
    subtotal = Decimal(0)
    total_pix = Decimal(0)
    item_especial = False
    for produto_id, quantidade in _juntar(itens).items():
        produto = conexao.execute("SELECT * FROM catalogo WHERE product_id = ?", (produto_id,)).fetchone()
        if produto is None:
            raise ErroFerramenta("produto_nao_encontrado", f"Não existe produto com id {produto_id}.")
        if produto["disponibilidade"] != "disponivel":
            raise ErroFerramenta(
                "produto_indisponivel",
                f"{produto['nome']} não está disponível para compra.",
                produto_id=produto_id,
                disponibilidade=produto["disponibilidade"],
            )
        if quantidade > produto["estoque"]:
            raise ErroFerramenta(
                "estoque_insuficiente",
                f"A quantidade pedida de {produto['nome']} é maior do que a disponível no momento.",
                produto_id=produto_id,
            )
        unitario = de_centavos(produto["preco_final_cents"])
        com_promocao = produto["promo_percent"] is not None
        unitario_pix = unitario if com_promocao else preco_pix(de_centavos(produto["price_cents"]))
        subtotal += unitario * quantidade
        total_pix += unitario_pix * quantidade
        item_especial = item_especial or frete_especial(produto["categoria"], produto["nome"])
        linhas_itens.append(
            {
                "id": produto_id,
                "nome": produto["nome"],
                "quantidade": quantidade,
                "preco_unitario": fmt_brl(unitario),
                "promocao_percentual": produto["promo_percent"],
                "preco_unitario_pix": fmt_brl(unitario_pix),
                "subtotal": fmt_brl(unitario * quantidade),
            }
        )

    opcoes = opcoes_cartao(subtotal)
    return {
        "itens": linhas_itens,
        "subtotal": fmt_brl(subtotal),
        "total_pix": fmt_brl(total_pix),
        "economia_pix": fmt_brl(subtotal - total_pix),
        "opcoes_cartao": [{"parcelas": n, "valor_parcela": fmt_brl(valor)} for n, valor in opcoes],
        "parcelas_maximas": opcoes[-1][0],
        "combinacao_permitida": combinacao_permitida(subtotal),
        "frete": calcular_frete(cidade_entrega, subtotal, item_especial),
    }
