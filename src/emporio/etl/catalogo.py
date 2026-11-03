"""ETL dos CSVs do desafio para o SQLite `emporio.db` (seção 5.2 da especificação)."""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from pathlib import Path

from emporio.domain.catalog import descricao_confiavel, disponibilidade, marca_do_nome, montar_texto_busca
from emporio.domain.money import para_centavos

PREFIXO_CSV = "desafio_tecnico_ai_eng - "

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE products (
    product_id          INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    category_id         INTEGER NOT NULL REFERENCES categories (category_id),
    price_cents         INTEGER NOT NULL CHECK (price_cents > 0),
    description         TEXT NOT NULL,
    stock_quantity      INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status              TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    specs               TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    marca               TEXT NOT NULL,
    disponibilidade     TEXT NOT NULL
        CHECK (disponibilidade IN ('disponivel', 'esgotado', 'descontinuado', 'em_breve')),
    descricao_confiavel INTEGER NOT NULL CHECK (descricao_confiavel IN (0, 1)),
    texto_busca         TEXT NOT NULL
);
CREATE INDEX idx_products_category ON products (category_id);

CREATE TABLE promotions (
    promotion_id     INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products (product_id),
    discount_percent INTEGER NOT NULL CHECK (discount_percent > 0 AND discount_percent < 100),
    description      TEXT NOT NULL,
    is_active        INTEGER NOT NULL CHECK (is_active IN (0, 1))
);
CREATE INDEX idx_promotions_product ON promotions (product_id, is_active);

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    phone         TEXT NOT NULL,
    email         TEXT NOT NULL,
    city          TEXT NOT NULL,
    email_norm    TEXT NOT NULL,
    phone_digits  TEXT NOT NULL
);

CREATE TABLE orders (
    order_id            INTEGER PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date          TEXT NOT NULL,
    status              TEXT NOT NULL
        CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')),
    total_cents         INTEGER NOT NULL,
    payment_method      TEXT NOT NULL,
    tracking_code       TEXT,
    estimated_delivery  TEXT,
    notes               TEXT,
    total_itens_cents   INTEGER NOT NULL,
    total_divergente    INTEGER NOT NULL CHECK (total_divergente IN (0, 1))
);
CREATE INDEX idx_orders_customer ON orders (customer_id);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders (order_id),
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

-- Promoção ativa de maior desconto por produto (T6); só vale para produto disponível (seção 6.3).
-- A conta em centavos inteiros, com metade para cima, repete a regra de `domain.catalog.preco_final`.
CREATE VIEW catalogo AS
WITH promo_ativa AS (
    SELECT product_id, discount_percent AS percentual, description AS descricao
    FROM (
        SELECT promotions.*,
               ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY discount_percent DESC, promotion_id) AS ordem
        FROM promotions
        WHERE is_active = 1
    )
    WHERE ordem = 1
)
SELECT p.product_id,
       p.name                   AS nome,
       p.marca,
       p.category_id,
       c.name                   AS categoria,
       p.description            AS descricao,
       p.descricao_confiavel,
       p.specs,
       p.price_cents,
       p.stock_quantity         AS estoque,
       p.status,
       p.disponibilidade,
       p.texto_busca,
       p.created_at,
       pa.percentual            AS promo_percent,
       pa.descricao             AS promo_descricao,
       CASE WHEN pa.percentual IS NULL THEN p.price_cents
            ELSE (p.price_cents * (100 - pa.percentual) + 50) / 100 END AS preco_final_cents
FROM products p
JOIN categories c ON c.category_id = p.category_id
LEFT JOIN promo_ativa pa ON pa.product_id = p.product_id AND p.disponibilidade = 'disponivel';
"""


def ler_csv(raw_dir: Path, nome: str) -> list[dict[str, str]]:
    with open(raw_dir / f"{PREFIXO_CSV}{nome}.csv", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _vazio_como_none(valor: str) -> str | None:
    valor = valor.strip()
    return valor or None


def construir_banco(raw_dir: Path, db_path: Path) -> dict[str, int]:
    """Recria o banco do zero a partir dos CSVs e devolve a contagem de linhas por tabela."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temporario = db_path.with_name(db_path.name + ".tmp")
    temporario.unlink(missing_ok=True)

    categorias = ler_csv(raw_dir, "categories")
    produtos = ler_csv(raw_dir, "products")
    promocoes = ler_csv(raw_dir, "promotions")
    clientes = ler_csv(raw_dir, "customers")
    pedidos = ler_csv(raw_dir, "orders")
    itens = ler_csv(raw_dir, "order_items")

    nome_categoria = {c["category_id"]: c["name"] for c in categorias}
    preco_por_produto = {p["product_id"]: para_centavos(p["price_brl"]) for p in produtos}
    soma_itens: dict[str, int] = {}
    for item in itens:
        subtotal = preco_por_produto[item["product_id"]] * int(item["quantity"])
        soma_itens[item["order_id"]] = soma_itens.get(item["order_id"], 0) + subtotal

    conexao = sqlite3.connect(temporario)
    try:
        conexao.executescript(DDL)
        conexao.executemany(
            "INSERT INTO categories VALUES (?, ?, ?)",
            [(int(c["category_id"]), c["name"], c["description"]) for c in categorias],
        )
        for p in produtos:
            specs = json.loads(p["specs"])
            marca = marca_do_nome(p["name"])
            if marca is None:
                raise ValueError(f"Marca não identificada no nome do produto {p['product_id']}: {p['name']!r}")
            estoque = int(p["stock_quantity"])
            confiavel = descricao_confiavel(p["name"], p["description"])
            conexao.execute(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(p["product_id"]), p["name"], int(p["category_id"]), para_centavos(p["price_brl"]),
                    p["description"], estoque, p["status"], json.dumps(specs, ensure_ascii=False), p["created_at"],
                    marca, disponibilidade(p["status"], estoque), int(confiavel),
                    montar_texto_busca(p["name"], nome_categoria[p["category_id"]], specs, p["description"], confiavel),
                ),
            )
        conexao.executemany(
            "INSERT INTO promotions VALUES (?, ?, ?, ?, ?)",
            [
                (int(x["promotion_id"]), int(x["product_id"]), int(x["discount_percent"]), x["description"],
                 int(x["is_active"]))
                for x in promocoes
            ],
        )
        conexao.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (int(c["customer_id"]), c["name"], c["phone"], c["email"], c["city"],
                 c["email"].strip().lower(), re.sub(r"\D", "", c["phone"]))
                for c in clientes
            ],
        )
        for o in pedidos:
            total = para_centavos(o["total_brl"])
            soma = soma_itens.get(o["order_id"], 0)
            conexao.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(o["order_id"]), int(o["customer_id"]), o["order_date"], o["status"], total,
                    o["payment_method"], _vazio_como_none(o["tracking_code"]),
                    _vazio_como_none(o["estimated_delivery"]), _vazio_como_none(o["notes"]), soma, int(total != soma),
                ),
            )
        conexao.executemany(
            "INSERT INTO order_items VALUES (?, ?, ?)",
            [(int(i["order_id"]), int(i["product_id"]), int(i["quantity"])) for i in itens],
        )
        conexao.commit()
        contagem = {
            tabela: conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            for tabela in ("categories", "products", "promotions", "customers", "orders", "order_items")
        }
        violacoes = conexao.execute("PRAGMA foreign_key_check").fetchall()
        if violacoes:
            raise ValueError(f"Chaves estrangeiras inválidas nos CSVs: {violacoes[:5]}")
    finally:
        conexao.close()

    try:
        os.replace(temporario, db_path)
    except PermissionError as erro:
        temporario.unlink(missing_ok=True)
        raise PermissionError(
            f"Não foi possível substituir {db_path}; feche quem a estiver usando (ex.: emporio-web)"
        ) from erro
    return contagem
