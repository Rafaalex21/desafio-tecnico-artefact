"""Guardrails de entrada e saída (seção 9.2): G2 valores rastreáveis, G4 entrada, G5 raciocínio vazado,
G6 promoção completa e G7 parcelamento simulado."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
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
_PARCELAMENTO = re.compile(r"parcel|prest[aã]|\b\d{1,2}\s*x\b|\bvezes\b|cart[aã]o", re.IGNORECASE)


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


@dataclass(frozen=True)
class Promocao:
    original: Decimal
    percentual: Decimal
    final: Decimal


def _percentual(valor: Any) -> Decimal | None:
    try:
        return Decimal(str(valor))
    except ArithmeticError:
        return None


def _promocoes_em(dado: Any) -> list[Promocao]:
    """Promoções de um resultado: `promocao` na busca e nos detalhes, `promocao_percentual` na simulação."""
    achadas: list[Promocao] = []
    if isinstance(dado, dict):
        promocao = dado.get("promocao")
        if isinstance(promocao, dict) and dado.get("preco") and promocao.get("preco_promocional"):
            original = valores_em_reais(str(dado["preco"]))
            final = valores_em_reais(str(promocao["preco_promocional"]))
            percentual = _percentual(promocao.get("percentual"))
            if original and final and percentual is not None:
                achadas.append(Promocao(original[0], percentual, final[0]))
        if dado.get("promocao_percentual") is not None and dado.get("preco_tabela") and dado.get("preco_unitario"):
            original = valores_em_reais(str(dado["preco_tabela"]))
            final = valores_em_reais(str(dado["preco_unitario"]))
            percentual = _percentual(dado["promocao_percentual"])
            if original and final and percentual is not None:
                achadas.append(Promocao(original[0], percentual, final[0]))
        for valor in dado.values():
            achadas.extend(_promocoes_em(valor))
    elif isinstance(dado, list):
        for valor in dado:
            achadas.extend(_promocoes_em(valor))
    return achadas


def promocoes_nas_ferramentas(mensagens: list[dict[str, Any]]) -> list[Promocao]:
    achadas: list[Promocao] = []
    for mensagem in mensagens:
        if mensagem.get("role") != "tool":
            continue
        try:
            achadas.extend(_promocoes_em(json.loads(str(mensagem.get("content") or ""))))
        except json.JSONDecodeError:
            continue
    return achadas


def _cita_percentual(texto: str, percentual: Decimal) -> bool:
    exato = percentual == percentual.to_integral_value()
    inteiro = str(int(percentual)) if exato else str(percentual).replace(".", ",")
    return bool(re.search(rf"(?<![\d,.]){re.escape(inteiro)}(?:[.,]0+)?\s*%", texto))


def promocao_incompleta(texto: str, promocoes: list[Promocao]) -> list[str]:
    """G6: para cada promoção cujo preço final aparece na resposta, o que falta citar (preço original e percentual)."""
    citados = valores_em_reais(texto)
    faltas: list[str] = []
    for promocao in promocoes:
        if not any(abs(valor - promocao.final) <= TOLERANCIA for valor in citados):
            continue
        if not any(abs(valor - promocao.original) <= TOLERANCIA for valor in citados):
            faltas.append(f"o preço original {fmt_brl(promocao.original)} (promocional {fmt_brl(promocao.final)})")
        if not _cita_percentual(texto, promocao.percentual):
            desconto = f"{promocao.percentual.normalize():f}%"
            faltas.append(f"o percentual de desconto {desconto} (promocional {fmt_brl(promocao.final)})")
    return list(dict.fromkeys(faltas))


def aviso_de_promocao(faltas: list[str]) -> str:
    return (
        "[aviso do sistema] Ao citar um produto em promoção, a resposta precisa trazer juntos o preço original, "
        f"o percentual de desconto e o preço promocional. Faltou citar: {'; '.join(faltas)}. "
        "Reescreva a resposta ao cliente sem mencionar este aviso."
    )


def parcelamento_sem_simulacao(turno: list[dict[str, Any]]) -> bool:
    """G7: o cliente falou de parcelas ou cartão, o agente consultou um produto e não chamou `simular_compra`."""
    if not turno or not _PARCELAMENTO.search(str(turno[0].get("content") or "")):
        return False
    chamadas = {c["function"]["name"] for m in turno for c in m.get("tool_calls") or []}
    return bool(chamadas & {"detalhes_produto", "buscar_produtos"}) and "simular_compra" not in chamadas


AVISO_DE_PARCELAMENTO = (
    "[aviso do sistema] O cliente perguntou sobre parcelas ou cartão. Chame `simular_compra` com o produto de que "
    "ele falou (sem pedir cidade nem CEP) e responda com o número de parcelas e o valor de cada uma. "
    "Não mencione este aviso."
)


def reforco_de_resposta(texto: str, mensagens: list[dict[str, Any]], inicio_turno: int) -> str | None:
    """G6 e G7: devolve o aviso de correção quando a resposta é válida mas incompleta, ou None se está boa."""
    if parcelamento_sem_simulacao(mensagens[inicio_turno:]):
        return AVISO_DE_PARCELAMENTO
    faltas = promocao_incompleta(texto, promocoes_nas_ferramentas(mensagens))
    return aviso_de_promocao(faltas) if faltas else None
