"""Análise de qualidade dos dados (T1 a T10 da seção 5.3) e geração de `docs/qualidade_dos_dados.md`."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from emporio.domain.catalog import marcas_citadas
from emporio.domain.money import de_centavos, fmt_brl
from emporio.domain.payments import parcela_minima

Linha = dict[str, Any]


def _consultar(conexao: sqlite3.Connection, sql: str, parametros: tuple[Any, ...] = ()) -> list[Linha]:
    cursor = conexao.execute(sql, parametros)
    colunas = [c[0] for c in cursor.description]
    return [dict(zip(colunas, linha, strict=True)) for linha in cursor.fetchall()]


def analisar(conexao: sqlite3.Connection, agora: datetime) -> dict[str, Any]:
    """Executa as verificações sobre o banco já construído. A data de referência só afeta T10 e T13."""
    hoje = agora.date()
    resultado: dict[str, Any] = {}

    resultado["T1"] = _consultar(
        conexao,
        "SELECT c.category_id, c.name FROM categories c "
        "WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.category_id = c.category_id) ORDER BY c.category_id",
    )
    resultado["T2"] = _consultar(
        conexao,
        "SELECT product_id, name FROM products WHERE status = 'active' AND stock_quantity = 0 ORDER BY product_id",
    )
    resultado["T3"] = _consultar(
        conexao,
        "SELECT product_id, name, stock_quantity FROM products WHERE status = 'discontinued' ORDER BY product_id",
    )
    resultado["T4"] = _consultar(
        conexao,
        "SELECT p.product_id, p.name, p.stock_quantity, "
        "(SELECT group_concat(order_id) FROM (SELECT order_id FROM order_items i WHERE i.product_id = p.product_id "
        " ORDER BY order_id)) AS pedidos "
        "FROM products p WHERE p.status = 'coming_soon' ORDER BY p.product_id",
    )
    nao_confiaveis = _consultar(
        conexao,
        "SELECT product_id, name, marca, description FROM products WHERE descricao_confiavel = 0 ORDER BY product_id",
    )
    resultado["T5"] = [
        {"product_id": p["product_id"], "name": p["name"], "marca": p["marca"],
         "marcas_na_descricao": ", ".join(marcas_citadas(p["description"]))}
        for p in nao_confiaveis
    ]
    resultado["T6"] = {
        "total": conexao.execute("SELECT COUNT(*) FROM promotions").fetchone()[0],
        "ativas": _consultar(
            conexao,
            "SELECT promotion_id, product_id, discount_percent, description FROM promotions "
            "WHERE is_active = 1 ORDER BY promotion_id",
        ),
        "produtos_repetidos": _consultar(
            conexao,
            "SELECT product_id, COUNT(*) AS entradas, group_concat(promotion_id) AS promocoes FROM promotions "
            "GROUP BY product_id HAVING COUNT(*) > 1 ORDER BY product_id",
        ),
        "produtos_com_varias_ativas": _consultar(
            conexao,
            "SELECT product_id, COUNT(*) AS ativas FROM promotions WHERE is_active = 1 "
            "GROUP BY product_id HAVING COUNT(*) > 1",
        ),
    }
    resultado["T7"] = _consultar(
        conexao,
        "SELECT order_id, total_cents, total_itens_cents FROM orders WHERE total_divergente = 1 ORDER BY order_id",
    )

    t9 = []
    for pedido in _consultar(
        conexao,
        "SELECT order_id, status, total_cents, payment_method FROM orders WHERE payment_method LIKE 'credit_%x' "
        "ORDER BY order_id",
    ):
        parcelas = int(re.fullmatch(r"credit_(\d+)x", pedido["payment_method"]).group(1))
        valor_parcela = de_centavos(pedido["total_cents"]) / parcelas
        minimo = parcela_minima(parcelas)
        if valor_parcela < minimo:
            t9.append({**pedido, "parcelas": parcelas, "valor_parcela": valor_parcela, "minimo": minimo})
    resultado["T8"] = _consultar(
        conexao,
        "SELECT email_norm AS email, group_concat(customer_id) AS clientes, COUNT(*) AS ocorrencias FROM customers "
        "GROUP BY email_norm HAVING COUNT(*) > 1",
    )
    resultado["T9"] = t9
    resultado["T10"] = _consultar(
        conexao,
        "SELECT order_id, tracking_code, estimated_delivery FROM orders "
        "WHERE status = 'shipped' AND estimated_delivery < ? ORDER BY order_id",
        (hoje.isoformat(),),
    )
    ultimo = conexao.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]
    resultado["T13"] = {"ultimo_pedido": ultimo, "dias": (hoje - date.fromisoformat(ultimo)).days}
    resultado["contagem"] = {
        tabela: conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        for tabela in ("categories", "products", "promotions", "customers", "orders", "order_items")
    }
    return resultado


def _tabela(cabecalho: list[str], linhas: list[list[Any]]) -> str:
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(str(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(saida)


def _ids(linhas: list[Linha], campo: str) -> str:
    return ", ".join(str(linha[campo]) for linha in linhas) or "nenhum"


def renderizar(resultado: dict[str, Any], agora: datetime) -> str:
    r = resultado
    t3_com_estoque = [x for x in r["T3"] if x["stock_quantity"] > 0]
    t6 = r["T6"]
    resumo = [
        ["T1", "Categorias sem nenhum produto", len(r["T1"]),
         "Busca devolve `categoria_sem_itens`; o agente não inventa itens"],
        ["T2", "Produto ativo com estoque zero", len(r["T2"]), "Classificado como esgotado; sugere alternativas"],
        ["T3", "Produto descontinuado com estoque positivo", len(t3_com_estoque),
         "Descontinuado prevalece sobre o estoque"],
        ["T4", "Produto em breve, com estoque e já vendido", len(r["T4"]), "Não é oferecido; pedidos históricos valem"],
        ["T5", "Descrição que cita outra marca", len(r["T5"]),
         "Nome é canônico; descrição fora da busca e das respostas"],
        ["T6", "Promoções repetidas e inativas", len(t6["produtos_repetidos"]),
         f"Só as {len(t6['ativas'])} ativas valem; havendo mais de uma, a de maior desconto"],
        ["T7", "Total do pedido diferente da soma dos itens", len(r["T7"]), "Prevalece o total do pedido"],
        ["T8", "E-mail compartilhado por clientes", len(r["T8"]), "Consulta sem pedido exige e-mail e telefone"],
        ["T9", "Parcela abaixo do mínimo vigente", len(r["T9"]), "Registro histórico, sem questionamento"],
        ["T10", "Pedido enviado com previsão vencida", len(r["T10"]), "Sinalizado como atrasado"],
    ]

    partes = [
        "# Qualidade dos dados",
        "Relatório gerado por `uv run emporio-etl`. Não edite à mão: a próxima execução o sobrescreve.",
        f"Data de referência usada nas verificações temporais (T10 e T13): {agora.strftime('%d/%m/%Y %H:%M')} "
        f"(UTC{agora.strftime('%z')[:3]}).",
        "## Volume carregado",
        _tabela(["Tabela", "Linhas"], [[nome, qtd] for nome, qtd in r["contagem"].items()]),
        "## Resumo",
        _tabela(["ID", "Inconsistência", "Ocorrências", "Tratamento"], resumo),
        "## Detalhes",
        "### T1. Categorias sem produtos",
        _tabela(["Categoria", "Nome"], [[x["category_id"], x["name"]] for x in r["T1"]]),
        "O manual afirma comercializar esses instrumentos, mas o catálogo não tem nenhum item neles.",
        "### T2. Ativo com estoque zero",
        _tabela(["Produto", "Nome"], [[x["product_id"], x["name"]] for x in r["T2"]]),
        "### T3. Descontinuados",
        _tabela(["Produto", "Nome", "Estoque"], [[x["product_id"], x["name"], x["stock_quantity"]] for x in r["T3"]]),
        "O descontinuado com estoque positivo é tratado como fora do catálogo, conforme o manual (7.3).",
        "### T4. Em breve",
        _tabela(
            ["Produto", "Nome", "Estoque", "Pedidos que o incluem"],
            [[x["product_id"], x["name"], x["stock_quantity"], x["pedidos"] or "nenhum"] for x in r["T4"]],
        ),
        "### T5. Descrição de outra marca",
        _tabela(
            ["Produto", "Nome", "Marca do nome", "Marca na descrição"],
            [[x["product_id"], x["name"], x["marca"], x["marcas_na_descricao"]] for x in r["T5"]],
        ),
        "### T6. Promoções",
        f"São {t6['total']} entradas, das quais {len(t6['ativas'])} ativas.",
        _tabela(
            ["Promoção", "Produto", "Desconto", "Descrição"],
            [[x["promotion_id"], x["product_id"], f"{x['discount_percent']}%", x["description"]] for x in t6["ativas"]],
        ),
        "Produtos com mais de uma entrada: "
        + (", ".join(f"{x['product_id']} (promoções {x['promocoes']})" for x in t6["produtos_repetidos"]) or "nenhum")
        + ". Produtos com mais de uma promoção ativa: "
        + (", ".join(str(x["product_id"]) for x in t6["produtos_com_varias_ativas"]) or "nenhum")
        + ".",
        "### T7. Total do pedido",
        _tabela(
            ["Pedido", "Total do pedido", "Soma dos itens", "Diferença"],
            [
                [x["order_id"], fmt_brl(de_centavos(x["total_cents"])), fmt_brl(de_centavos(x["total_itens_cents"])),
                 fmt_brl(de_centavos(x["total_cents"] - x["total_itens_cents"]))]
                for x in r["T7"]
            ],
        ),
        "A soma dos itens usa os preços de tabela atuais.",
        "### T8. E-mail compartilhado",
        _tabela(["E-mail", "Clientes"], [[x["email"], x["clientes"]] for x in r["T8"]]),
        "### T9. Parcelamento abaixo do mínimo",
        _tabela(
            ["Pedido", "Situação", "Total", "Parcelas", "Valor da parcela", "Mínimo vigente"],
            [
                [x["order_id"], x["status"], fmt_brl(de_centavos(x["total_cents"])), f"{x['parcelas']}x",
                 fmt_brl(x["valor_parcela"]), fmt_brl(Decimal(x["minimo"]))]
                for x in r["T9"]
            ],
        ),
        "### T10. Entrega atrasada",
        _tabela(
            ["Pedido", "Rastreio", "Previsão"],
            [[x["order_id"], x["tracking_code"], x["estimated_delivery"]] for x in r["T10"]],
        ),
        "## Inconsistências fora do alcance do ETL",
        f"T11 e T12 estão no manual (contatos divergentes e parcela mínima contraditória) e são resolvidas nas regras "
        f"de domínio. T13: o último pedido é de {r['T13']['ultimo_pedido']}, {r['T13']['dias']} dias antes da data de "
        f"referência; por isso o relógio do sistema é configurável.",
    ]
    return "\n\n".join(partes) + "\n"
