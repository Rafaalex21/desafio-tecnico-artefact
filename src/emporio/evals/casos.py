"""Leitura dos casos e verificação das asserções (seção 13.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from emporio.domain.texto import normalizar


@dataclass(frozen=True)
class Espera:
    ferramentas: tuple[str, ...] = ()
    ferramentas_alguma: tuple[str, ...] = ()
    ferramentas_proibidas: tuple[str, ...] = ()
    contem_todos: tuple[str, ...] = ()
    contem_algum: tuple[tuple[str, ...], ...] = ()
    nao_contem: tuple[str, ...] = ()

    @property
    def verifica_roteamento(self) -> bool:
        return bool(self.ferramentas or self.ferramentas_alguma or self.ferramentas_proibidas)


@dataclass(frozen=True)
class Caso:
    id: str
    categoria: str
    turnos: tuple[str, ...]
    espera: Espera
    agora: datetime | None = None


@dataclass
class Falha:
    tipo: str  # "roteamento" ou "texto"
    descricao: str


@dataclass
class Verificacao:
    total: int = 0
    falhas: list[Falha] = field(default_factory=list)

    @property
    def roteamento_ok(self) -> bool:
        return not any(f.tipo == "roteamento" for f in self.falhas)


def comparavel(texto: str) -> str:
    """Minúsculas, sem acentos, hífens tipográficos como `-`, sem markdown e com `R$` colado ao número."""
    limpo = re.sub("[‐-―−]", "-", normalizar(texto)).replace("*", "").replace("_", " ")
    limpo = re.sub(r"r\$\s*", "r$", limpo)
    return " ".join(limpo.split())


def _grupos(valor: Any) -> tuple[tuple[str, ...], ...]:
    if not valor:
        return ()
    if all(isinstance(item, str) for item in valor):
        return (tuple(valor),)
    return tuple(tuple(grupo) for grupo in valor)


def ler_casos(caminho: Path) -> list[Caso]:
    with open(caminho, encoding="utf-8") as arquivo:
        brutos = yaml.safe_load(arquivo)
    casos = []
    for bruto in brutos:
        espera = bruto.get("espera", {})
        agora = bruto.get("agora")
        if isinstance(agora, str):
            agora = datetime.fromisoformat(agora)
        casos.append(
            Caso(
                id=bruto["id"],
                categoria=bruto["categoria"],
                turnos=tuple(bruto["turnos"]),
                agora=agora,
                espera=Espera(
                    ferramentas=tuple(espera.get("ferramentas", ())),
                    ferramentas_alguma=tuple(espera.get("ferramentas_alguma", ())),
                    ferramentas_proibidas=tuple(espera.get("ferramentas_proibidas", ())),
                    contem_todos=tuple(espera.get("contem_todos", ())),
                    contem_algum=_grupos(espera.get("contem_algum")),
                    nao_contem=tuple(espera.get("nao_contem", ())),
                ),
            )
        )
    return casos


def verificar(espera: Espera, texto: str, ferramentas: list[str]) -> Verificacao:
    """Confere as asserções do caso contra a resposta e as ferramentas chamadas no último turno."""
    resultado = Verificacao()
    alvo = comparavel(texto)

    def checar(ok: bool, tipo: str, descricao: str) -> None:
        resultado.total += 1
        if not ok:
            resultado.falhas.append(Falha(tipo, descricao))

    for nome in espera.ferramentas:
        checar(nome in ferramentas, "roteamento", f"não chamou {nome}")
    if espera.ferramentas_alguma:
        checar(
            any(nome in ferramentas for nome in espera.ferramentas_alguma),
            "roteamento",
            f"não chamou nenhuma de {', '.join(espera.ferramentas_alguma)}",
        )
    for nome in espera.ferramentas_proibidas:
        checar(nome not in ferramentas, "roteamento", f"chamou {nome}, proibida no caso")
    for trecho in espera.contem_todos:
        checar(comparavel(trecho) in alvo, "texto", f"faltou {trecho!r}")
    for grupo in espera.contem_algum:
        checar(any(comparavel(t) in alvo for t in grupo), "texto", f"faltou algum de {list(grupo)!r}")
    for trecho in espera.nao_contem:
        checar(comparavel(trecho) not in alvo, "texto", f"não deveria conter {trecho!r}")
    return resultado
