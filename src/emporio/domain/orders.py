"""Pedidos: verificação de identidade, exibição de status e elegibilidade pós-venda (seções 6.8, 6.9 e 6.11)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from emporio.domain.errors import ErroFerramenta
from emporio.domain.money import de_centavos, fmt_brl

MAX_FALHAS = 3

STATUS_TEXTO = {
    "pending": "Aguardando confirmação do pagamento",
    "confirmed": "Pagamento confirmado, pedido em separação",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

_CREDITO = re.compile(r"credit_(\d+)x")

MSG_NAO_CONFERE = (
    "Não foi possível confirmar os dados informados. Confira o número do pedido e o e-mail ou telefone "
    "cadastrados na compra e tente de novo."
)

GARANTIA_FABRICANTE = (
    "A garantia do fabricante varia de 6 meses a 2 anos conforme o produto e consta no certificado que "
    "acompanha o instrumento."
)


@dataclass
class Verificacao:
    """Estado de verificação de identidade de uma sessão: tentativas falhas e clientes já confirmados."""

    falhas: int = 0
    clientes: set[int] = field(default_factory=set)

    @property
    def bloqueada(self) -> bool:
        return self.falhas >= MAX_FALHAS


def normalizar_email(email: str) -> str:
    return "".join(email.split()).lower()


def apenas_digitos(telefone: str) -> str:
    return re.sub(r"\D", "", telefone)


def _partes_telefone(digitos: str) -> tuple[str | None, str] | None:
    """(DDD ou None, últimos 8 dígitos). Aceita código do país, com ou sem DDD e com ou sem o 9 inicial."""
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) in (10, 11):
        return digitos[:2], digitos[2:][-8:]
    if len(digitos) in (8, 9):
        return None, digitos[-8:]
    return None


def telefones_coincidem(informado: str, cadastrado: str) -> bool:
    a = _partes_telefone(apenas_digitos(informado))
    b = _partes_telefone(apenas_digitos(cadastrado))
    if a is None or b is None or a[1] != b[1]:
        return False
    return a[0] is None or b[0] is None or a[0] == b[0]


def _confere(cliente: sqlite3.Row, email: str | None, telefone: str | None) -> bool:
    """Verdadeiro se o e-mail OU o telefone informado pertence ao cliente."""
    if email and normalizar_email(email) == cliente["email_norm"]:
        return True
    return bool(telefone) and telefones_coincidem(telefone, cliente["phone_digits"])


def _confere_ambos(cliente: sqlite3.Row, email: str | None, telefone: str | None) -> bool:
    return bool(
        email
        and telefone
        and normalizar_email(email) == cliente["email_norm"]
        and telefones_coincidem(telefone, cliente["phone_digits"])
    )


def forma_pagamento_texto(codigo: str) -> str:
    if codigo == "pix":
        return "PIX"
    if codigo == "debit":
        return "Cartão de débito"
    if codigo == "boleto":
        return "Boleto"
    if parcelas := _CREDITO.fullmatch(codigo):
        return f"Cartão de crédito em {parcelas.group(1)}x"
    return codigo


def _data(texto: str) -> date:
    return date.fromisoformat(texto)


def _fmt_data(valor: date | str) -> str:
    return (_data(valor) if isinstance(valor, str) else valor).strftime("%d/%m/%Y")


def _direito(marco: date, dias: int, hoje: date) -> dict[str, Any]:
    prazo = marco + timedelta(days=dias)
    elegivel = hoje <= prazo
    restantes = max(0, (prazo - hoje).days)
    if not elegivel:
        situacao = f"Prazo encerrado em {_fmt_data(prazo)}"
    elif restantes == 0:
        situacao = f"Dentro do prazo, que termina hoje ({_fmt_data(prazo)})"
    else:
        situacao = f"Dentro do prazo até {_fmt_data(prazo)} ({restantes} dias restantes)"
    return {"elegivel": elegivel, "prazo_final": _fmt_data(prazo), "dias_restantes": restantes, "situacao": situacao}


def elegibilidade(data_compra: str, recebimento: str, hoje: date) -> dict[str, Any]:
    """Prazos de arrependimento, troca e garantia legal para pedido entregue (S2 e S3)."""
    compra, recebido = _data(data_compra), _data(recebimento)
    return {
        "recebimento_considerado": _fmt_data(recebido),
        "arrependimento": _direito(recebido, 7, hoje),
        "troca_por_preferencia": _direito(recebido, 7, hoje),
        "troca_por_defeito": _direito(compra, 30, hoje),
        "garantia_legal": _direito(recebido, 90, hoje),
        "garantia_do_fabricante": GARANTIA_FABRICANTE,
    }


def _pedido(conexao: sqlite3.Connection, pedido: sqlite3.Row, cliente: sqlite3.Row, hoje: date) -> dict[str, Any]:
    itens = conexao.execute(
        "SELECT p.name AS nome, i.quantity AS quantidade FROM order_items i "
        "JOIN products p ON p.product_id = i.product_id WHERE i.order_id = ? ORDER BY p.product_id",
        (pedido["order_id"],),
    ).fetchall()
    status = pedido["status"]
    previsao = pedido["estimated_delivery"]
    saida: dict[str, Any] = {
        "numero": pedido["order_id"],
        "cliente_primeiro_nome": cliente["name"].split()[0],
        "data_compra": _fmt_data(pedido["order_date"]),
        "status": status,
        "status_texto": STATUS_TEXTO[status],
        "itens": [{"nome": item["nome"], "quantidade": item["quantidade"]} for item in itens],
        "total": fmt_brl(de_centavos(pedido["total_cents"])),
        "forma_pagamento_texto": forma_pagamento_texto(pedido["payment_method"]),
        "rastreio": pedido["tracking_code"],
        "previsao_entrega": _fmt_data(previsao) if previsao else None,
        "entrega_atrasada": status == "shipped" and previsao is not None and _data(previsao) < hoje,
        "motivo_cancelamento": pedido["notes"] if status == "cancelled" else None,
        "elegibilidade": None,
    }
    if status == "delivered" and previsao:
        saida["elegibilidade"] = elegibilidade(pedido["order_date"], previsao, hoje)
    return saida


def _resumo_pedidos(conexao: sqlite3.Connection, clientes: list[int]) -> list[dict[str, Any]]:
    marcas = ",".join("?" for _ in clientes)
    linhas = conexao.execute(
        f"SELECT order_id, order_date, status, total_cents FROM orders WHERE customer_id IN ({marcas}) "
        "ORDER BY order_date DESC, order_id DESC",
        clientes,
    ).fetchall()
    return [
        {
            "numero": linha["order_id"],
            "data_compra": _fmt_data(linha["order_date"]),
            "status_texto": STATUS_TEXTO[linha["status"]],
            "total": fmt_brl(de_centavos(linha["total_cents"])),
        }
        for linha in linhas
    ]


def _falhar(verificacao: Verificacao) -> ErroFerramenta:
    verificacao.falhas += 1
    return ErroFerramenta("dados_nao_conferem", MSG_NAO_CONFERE)


def consultar_pedido(
    conexao: sqlite3.Connection,
    verificacao: Verificacao,
    agora: datetime,
    numero_pedido: int | None = None,
    email: str | None = None,
    telefone: str | None = None,
) -> dict[str, Any]:
    """Devolve o pedido ou a lista de pedidos do cliente verificado. Falhas nunca revelam se o pedido existe."""
    if verificacao.bloqueada:
        raise ErroFerramenta(
            "tentativas_excedidas",
            "Número máximo de tentativas de verificação nesta conversa. Sugira o atendimento humano.",
        )
    email = (email or "").strip() or None
    telefone = (telefone or "").strip() or None
    hoje = agora.date()

    if numero_pedido is not None:
        linha = conexao.execute("SELECT * FROM orders WHERE order_id = ?", (numero_pedido,)).fetchone()
        ja_verificado = linha is not None and linha["customer_id"] in verificacao.clientes
        if not ja_verificado:
            if not (email or telefone):
                raise ErroFerramenta(
                    "verificacao_necessaria",
                    "Para consultar o pedido, peça ao cliente o e-mail ou o telefone cadastrados na compra.",
                )
            cliente = (
                conexao.execute("SELECT * FROM customers WHERE customer_id = ?", (linha["customer_id"],)).fetchone()
                if linha is not None
                else None
            )
            if cliente is None or not _confere(cliente, email, telefone):
                raise _falhar(verificacao)
            verificacao.clientes.add(cliente["customer_id"])
        cliente = conexao.execute("SELECT * FROM customers WHERE customer_id = ?", (linha["customer_id"],)).fetchone()
        return _pedido(conexao, linha, cliente, hoje)

    if not (email and telefone):
        if verificacao.clientes and not (email or telefone):
            return {"pedidos": _resumo_pedidos(conexao, sorted(verificacao.clientes))}
        raise ErroFerramenta(
            "verificacao_necessaria",
            "Sem o número do pedido, peça ao cliente o e-mail e o telefone cadastrados na compra, os dois juntos. "
            "Com o número do pedido, basta um dos dois.",
        )
    candidatos = conexao.execute("SELECT * FROM customers WHERE email_norm = ?", (normalizar_email(email),)).fetchall()
    cliente = next((c for c in candidatos if _confere_ambos(c, email, telefone)), None)
    if cliente is None:
        raise _falhar(verificacao)
    verificacao.clientes.add(cliente["customer_id"])
    return {"pedidos": _resumo_pedidos(conexao, [cliente["customer_id"]])}
