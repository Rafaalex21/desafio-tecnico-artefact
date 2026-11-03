"""Regras determinísticas do catálogo: disponibilidade, preço promocional e marca (seções 5.2, 6.2 e 6.3)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from emporio.domain.money import arredondar, para_decimal
from emporio.domain.texto import normalizar

MARCAS = (
    "Yamaha", "Tagima", "Giannini", "Rozini", "Shelby", "Crafter", "Martin", "Taylor", "Takamine", "Kala",
    "Ohana", "Kalani", "Fender", "Gibson", "Ibanez", "PRS", "Music Man", "Pearl", "Korg", "Nord", "Roland",
)


_PADROES_MARCA = {marca: re.compile(rf"\b{re.escape(normalizar(marca))}\b") for marca in MARCAS}


def marcas_citadas(texto: str) -> list[str]:
    """Marcas da lista citadas no texto, na ordem em que aparecem. `Kala` não casa com `Kalani`."""
    alvo = normalizar(texto)
    achadas = [(m.start(), marca) for marca, padrao in _PADROES_MARCA.items() if (m := padrao.search(alvo))]
    return [marca for _, marca in sorted(achadas)]


def marca_do_nome(nome: str) -> str | None:
    citadas = marcas_citadas(nome)
    return citadas[0] if citadas else None


def descricao_confiavel(nome: str, descricao: str) -> bool:
    """Falso quando a descrição cita uma marca diferente da marca do nome (T5)."""
    marca = marca_do_nome(nome)
    return all(citada == marca for citada in marcas_citadas(descricao))


def disponibilidade(status: str, estoque: int) -> str:
    """Estado comercial do produto. `descontinuado` e `em_breve` prevalecem sobre o estoque (T3 e T4)."""
    if status == "discontinued":
        return "descontinuado"
    if status == "coming_soon":
        return "em_breve"
    if status == "active":
        return "disponivel" if estoque > 0 else "esgotado"
    raise ValueError(f"Status de produto desconhecido: {status!r}")


def preco_final(preco: Any, desconto_percent: Any = None) -> Decimal:
    """Preço com a promoção ativa aplicada; sem promoção, devolve o preço de tabela."""
    preco = para_decimal(preco)
    if not desconto_percent:
        return arredondar(preco)
    return arredondar(preco * (Decimal(100) - para_decimal(desconto_percent)) / 100)


_TRADUCAO_VALOR = {"steel": "aço"}


def traduzir_spec(chave: str, valor: Any) -> str:
    """Valor de uma especificação em palavras que o cliente usaria na busca."""
    texto = str(valor)
    if chave == "electronics":
        return "elétrico eletroacústico" if texto.lower() == "yes" else ""
    return _TRADUCAO_VALOR.get(texto.lower(), texto)


_SINONIMOS_CATEGORIA = {
    "Guitarras": "guitarra",
    "Baixos": "baixo contrabaixo",
    "Baterias e Percussão": "bateria percussão",
    "Teclados e Pianos": "teclado piano sintetizador",
    "Violões": "violão",
    "Ukuleles": "ukulele",
}


def montar_texto_busca(nome: str, categoria: str, specs: dict[str, Any], descricao: str, confiavel: bool) -> str:
    """Texto normalizado usado na busca aproximada: nome, categoria, especificações e descrição confiável."""
    partes = [nome, categoria, _SINONIMOS_CATEGORIA.get(categoria, "")]
    partes += [traduzir_spec(chave, valor) for chave, valor in specs.items()]
    if confiavel:
        partes.append(descricao)
    return normalizar(" ".join(p for p in partes if p))
