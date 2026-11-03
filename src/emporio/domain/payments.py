"""Regras de pagamento e frete (seções 6.4 a 6.7 da especificação; manual 3.1, 5.1 e 5.2)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from emporio.domain.money import arredondar, fmt_brl, para_decimal
from emporio.domain.texto import normalizar

DESCONTO_PIX = Decimal(5)
LIMITE_COMBINACAO = Decimal(2000)
FRETE_GRATIS_A_PARTIR_DE = Decimal(500)
FRETE_LOCAL = Decimal(35)
PARCELAS_MAXIMAS = 12

_CAMPO_GRANDE = re.compile(r"campo grande(\s*[-/,]\s*(ms|mato grosso do sul))?")

_MODALIDADES = (
    "PAC (5 a 12 dias úteis), SEDEX (2 a 5 dias úteis) ou Jadlog (3 a 8 dias úteis), "
    "todas com código de rastreio e seguro"
)


def parcela_minima(parcelas: int) -> Decimal:
    """Valor mínimo de cada parcela no cartão de crédito, sem juros (manual 3.1, suposição S7)."""
    if parcelas < 1 or parcelas > PARCELAS_MAXIMAS:
        raise ValueError(f"Número de parcelas fora do intervalo de 1 a 12: {parcelas}")
    if parcelas == 1:
        return Decimal(0)
    if parcelas <= 3:
        return Decimal(50)
    if parcelas <= 6:
        return Decimal(80)
    return Decimal(100)


def preco_pix(preco_tabela: Any) -> Decimal:
    """Preço no PIX: 5% sobre o preço de tabela, só para item sem promoção ativa (manual 6.2)."""
    return arredondar(para_decimal(preco_tabela) * (Decimal(100) - DESCONTO_PIX) / 100)


def opcoes_cartao(total: Any) -> list[tuple[int, Decimal]]:
    """Parcelamentos sem juros válidos para o total, como pares (parcelas, valor da parcela).

    A validade usa a divisão exata; só o valor exibido é arredondado.
    """
    total = para_decimal(total)
    return [
        (n, arredondar(total / n))
        for n in range(1, PARCELAS_MAXIMAS + 1)
        if total / n >= parcela_minima(n)
    ]


def combinacao_permitida(total: Any) -> bool:
    """Combinar formas de pagamento só vale para compras acima de R$ 2.000,00 (manual 3.1)."""
    return para_decimal(total) > LIMITE_COMBINACAO


def eh_campo_grande(cidade: str) -> bool:
    return bool(_CAMPO_GRANDE.fullmatch(" ".join(normalizar(cidade).split())))


def frete_especial(categoria: str, nome: str) -> bool:
    """Baterias acústicas e contrabaixos acústicos exigem cotação individual (S6)."""
    nome_normalizado = normalizar(nome)
    if categoria == "Baterias e Percussão":
        return "bateria acustica" in nome_normalizado
    return categoria == "Cordas Orquestrais" and "contrabaixo" in nome_normalizado


def calcular_frete(cidade: str | None, subtotal: Any, com_item_especial: bool = False) -> dict[str, Any]:
    """Frete da compra: regra de Campo Grande ou modalidades dos Correios e da Jadlog para as demais cidades."""
    subtotal = para_decimal(subtotal)
    if com_item_especial:
        return {
            "tipo": "cotacao_individual",
            "valor": None,
            "prazo": None,
            "observacao": "Há item de grande porte no carrinho; o frete é cotado individualmente pela equipe.",
        }
    if not cidade or not cidade.strip():
        return {
            "tipo": "a_definir",
            "valor": None,
            "prazo": None,
            "observacao": "Informe a cidade de entrega para calcular o frete.",
        }
    if eh_campo_grande(cidade):
        if subtotal >= FRETE_GRATIS_A_PARTIR_DE:
            return {
                "tipo": "entrega_local",
                "valor": fmt_brl(0),
                "prazo": "1 a 3 dias úteis",
                "observacao": "Frete grátis em Campo Grande para compras a partir de R$ 500,00.",
            }
        return {
            "tipo": "entrega_local",
            "valor": fmt_brl(FRETE_LOCAL),
            "prazo": "1 a 3 dias úteis",
            "observacao": "Frete de R$ 35,00 em Campo Grande para compras abaixo de R$ 500,00.",
        }
    return {
        "tipo": "correios_ou_transportadora",
        "valor": None,
        "prazo": "de 2 a 12 dias úteis, conforme a modalidade",
        "observacao": f"O valor é calculado pelo CEP no fechamento do pedido. Modalidades: {_MODALIDADES}.",
    }
