"""Guardrails de entrada e saída (seção 9.2): G2 valores rastreáveis, G4 entrada e G5 raciocínio vazado."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any

from emporio.domain.money import fmt_brl

MAX_ENTRADA = 2000
TOLERANCIA = Decimal("0.01")

RESPOSTA_SEGURA = (
    "Opa, me enrolei aqui pra confirmar essa informação. Pode reformular a pergunta, "
    "ou prefere que eu chame alguém da equipe?"
)

_VALOR = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_RACIOCINIO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_RACIOCINIO_ABERTO = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def limpar_entrada(texto: str) -> str:
    """G4: tira caracteres de controle (menos quebra de linha e tabulação), apara e limita a 2.000 caracteres."""
    limpo = "".join(c for c in texto if c in "\n\t" or unicodedata.category(c) != "Cc")
    return limpo.strip()[:MAX_ENTRADA].strip()


def remover_raciocinio(texto: str) -> str:
    """G5: remove blocos `<think>...</think>`, inclusive o bloco que ficou aberto ou sem a tag de abertura."""
    if "</think>" in texto.lower() and "<think>" not in texto.lower():
        texto = re.split(r"</think>", texto, flags=re.IGNORECASE)[-1]
    texto = _RACIOCINIO.sub("", texto)
    return _RACIOCINIO_ABERTO.sub("", texto).strip()


def valores_em_reais(texto: str) -> list[Decimal]:
    """Todos os valores `R$` do texto, em Decimal."""
    valores = []
    for inteiro, centavos in _VALOR.findall(texto):
        fracao = (centavos or "0").ljust(2, "0")
        valores.append(Decimal(f"{inteiro.replace('.', '')}.{fracao}"))
    return valores


def valores_permitidos(mensagens: list[dict[str, Any]]) -> list[Decimal]:
    """Valores `R$` que o agente pode citar: resultados de ferramenta e mensagens do próprio cliente."""
    permitidos: list[Decimal] = []
    for mensagem in mensagens:
        if mensagem.get("role") in ("tool", "user"):
            permitidos.extend(valores_em_reais(str(mensagem.get("content") or "")))
    return permitidos


def valores_nao_rastreaveis(texto: str, permitidos: list[Decimal]) -> list[Decimal]:
    """G2: valores da resposta sem correspondente (tolerância de 1 centavo) entre os permitidos."""
    return [
        valor
        for valor in dict.fromkeys(valores_em_reais(texto))
        if not any(abs(valor - p) <= TOLERANCIA for p in permitidos)
    ]


def aviso_de_correcao(invalidos: list[Decimal], permitidos: list[Decimal]) -> str:
    citados = ", ".join(fmt_brl(v) for v in invalidos)
    disponiveis = ", ".join(fmt_brl(v) for v in dict.fromkeys(permitidos)) or "nenhum"
    return (
        f"[aviso do sistema] Sua resposta citou valores que não vieram das ferramentas: {citados}. "
        f"Os únicos valores que você pode citar são: {disponiveis}. Se faltar algum valor, chame a ferramenta "
        "adequada. Reescreva a resposta ao cliente sem mencionar este aviso."
    )
