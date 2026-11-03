"""Políticas da loja: mapa de tópicos para seções do manual e leitura do `politicas.json` (seção 7.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Tópicos aceitos pela ferramenta `consultar_politicas`. As seções 7 e 10 do manual (procedimentos internos de
# atendimento e disposições finais) ficam fora: o conteúdo delas entra no prompt de sistema como regra de comportamento.
TOPICOS: dict[str, tuple[str, ...]] = {
    "sobre_a_loja": ("1", "1.1", "1.2"),
    "horario_funcionamento": ("2",),
    "formas_de_pagamento": ("3", "3.1"),
    "trocas_e_devolucoes": ("4", "4.1", "4.2", "4.3", "4.4"),
    "frete_e_entregas": ("5", "5.1", "5.2", "5.3"),
    "promocoes": ("6", "6.1", "6.2"),
    "garantia": ("8", "8.1", "8.2", "8.3"),
    "privacidade": ("9",),
}


def carregar_politicas(caminho: Path) -> dict[str, Any]:
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def secoes_do_topico(politicas: dict[str, Any], topico: str) -> list[dict[str, str]]:
    """Seções do manual de um tópico, na ordem do documento."""
    if topico not in TOPICOS:
        raise KeyError(f"Tópico desconhecido: {topico!r}")
    return [politicas["secoes"][numero] for numero in politicas["topicos"][topico]]
