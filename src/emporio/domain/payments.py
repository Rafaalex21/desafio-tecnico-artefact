"""Regras de pagamento (seção 3.1 do manual, seção 6 da especificação)."""

from __future__ import annotations

from decimal import Decimal


def parcela_minima(parcelas: int) -> Decimal:
    """Valor mínimo de cada parcela no cartão de crédito, sem juros (manual 3.1, suposição S7)."""
    if parcelas < 1 or parcelas > 12:
        raise ValueError(f"Número de parcelas fora do intervalo de 1 a 12: {parcelas}")
    if parcelas == 1:
        return Decimal(0)
    if parcelas <= 3:
        return Decimal(50)
    if parcelas <= 6:
        return Decimal(80)
    return Decimal(100)
