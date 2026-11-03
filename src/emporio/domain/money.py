"""Dinheiro: Decimal em todo o cálculo, arredondamento ROUND_HALF_UP e formatação brasileira (seção 6.1)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENTAVO = Decimal("0.01")


def para_decimal(valor: Any) -> Decimal:
    """Converte int, str ou Decimal em Decimal sem passar por float."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        raise TypeError("Use str, int ou Decimal para valores monetários, nunca float")
    return Decimal(str(valor).strip())


def arredondar(valor: Decimal) -> Decimal:
    """Arredonda para duas casas, metade para cima."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def para_centavos(valor: Any) -> int:
    """Valor em reais para centavos inteiros; recusa valores com mais de duas casas decimais."""
    centavos = para_decimal(valor) * 100
    if centavos != centavos.to_integral_value():
        raise ValueError(f"Valor com mais de duas casas decimais: {valor!r}")
    return int(centavos)


def de_centavos(centavos: int) -> Decimal:
    return (Decimal(centavos) / 100).quantize(CENTAVO)


def fmt_brl(valor: Any) -> str:
    """Formata no padrão brasileiro: `R$ 1.234,56`."""
    texto = f"{arredondar(para_decimal(valor)):.2f}"
    inteiro, fracao = texto.split(".")
    sinal = "-" if inteiro.startswith("-") else ""
    inteiro = f"{int(inteiro.lstrip('-')):,}".replace(",", ".")
    return f"{sinal}R$ {inteiro},{fracao}"
