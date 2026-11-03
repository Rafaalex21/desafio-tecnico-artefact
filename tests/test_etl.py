"""Testes da E1: ETL, inconsistências T1 a T10 (seção 5.3), vista `catalogo` e regras de preço."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from emporio.config import RAIZ
from emporio.domain.catalog import (
    descricao_confiavel,
    disponibilidade,
    marca_do_nome,
    marcas_citadas,
    preco_final,
)
from emporio.domain.money import fmt_brl, para_centavos
from emporio.etl.catalogo import construir_banco
from emporio.etl.qualidade import analisar, renderizar

AGORA = datetime.fromisoformat("2026-03-25T10:30:00-04:00")


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    caminho = tmp_path_factory.mktemp("etl") / "emporio.db"
    construir_banco(RAIZ / "data" / "raw", caminho)
    return caminho


@pytest.fixture()
def conexao(db_path: Path):
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        yield con


@pytest.fixture(scope="module")
def qualidade(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as con:
        return analisar(con, AGORA)


def ids(linhas: list[dict], campo: str = "product_id") -> set[int]:
    return {linha[campo] for linha in linhas}


# Carga


def test_contagem_de_linhas(qualidade):
    assert qualidade["contagem"] == {
        "categories": 9, "products": 65, "promotions": 25, "customers": 50, "orders": 20, "order_items": 22,
    }


def test_todos_os_produtos_tem_marca_e_texto_de_busca(conexao):
    linhas = conexao.execute("SELECT marca, texto_busca FROM products").fetchall()
    assert all(linha["marca"] and linha["texto_busca"] for linha in linhas)


def _catalogo(db: Path) -> list[tuple]:
    with closing(sqlite3.connect(db)) as con:
        return con.execute("SELECT * FROM catalogo ORDER BY product_id").fetchall()


def test_etl_e_idempotente(tmp_path):
    db = tmp_path / "emporio.db"
    construir_banco(RAIZ / "data" / "raw", db)
    primeiro = _catalogo(db)
    construir_banco(RAIZ / "data" / "raw", db)
    segundo = _catalogo(db)
    assert primeiro == segundo and len(primeiro) == 65
    assert not db.with_name(db.name + ".tmp").exists()


def test_relatorio_e_deterministico(db_path):
    with sqlite3.connect(db_path) as con:
        a = renderizar(analisar(con, AGORA), AGORA)
        b = renderizar(analisar(con, AGORA), AGORA)
    assert a == b
    for codigo in (f"T{n}" for n in range(1, 11)):
        assert f"### {codigo}." in a


# Inconsistências


def test_t1_categorias_sem_produtos(qualidade):
    assert ids(qualidade["T1"], "category_id") == {6, 7, 8}


def test_t2_ativo_com_estoque_zero(qualidade, conexao):
    assert ids(qualidade["T2"]) == {96}
    assert conexao.execute("SELECT disponibilidade FROM products WHERE product_id = 96").fetchone()[0] == "esgotado"


def test_t3_descontinuado_prevalece_sobre_o_estoque(conexao):
    linhas = dict(conexao.execute("SELECT product_id, disponibilidade FROM products WHERE product_id IN (113, 136)"))
    assert linhas == {113: "descontinuado", 136: "descontinuado"}
    assert conexao.execute("SELECT stock_quantity FROM products WHERE product_id = 136").fetchone()[0] == 13


def test_t4_em_breve_nao_e_vendavel(qualidade, conexao):
    assert ids(qualidade["T4"]) == {130}
    assert qualidade["T4"][0]["pedidos"] == "3,14"
    assert conexao.execute("SELECT disponibilidade FROM products WHERE product_id = 130").fetchone()[0] == "em_breve"


def test_t5_descricao_de_outra_marca(qualidade, conexao):
    assert ids(qualidade["T5"]) == {135, 137, 139, 142, 144}
    confiaveis = dict(conexao.execute("SELECT product_id, descricao_confiavel FROM products"))
    assert [i for i, v in confiaveis.items() if not v] == [135, 137, 139, 142, 144]
    texto = conexao.execute("SELECT texto_busca FROM products WHERE product_id = 135").fetchone()[0]
    assert "fender" not in texto and "jazz bass" not in texto


def test_t6_somente_promocoes_ativas(qualidade, conexao):
    assert ids(qualidade["T6"]["ativas"]) == {127, 121, 90, 94}
    assert ids(qualidade["T6"]["produtos_repetidos"]) == {93, 96, 99}
    assert qualidade["T6"]["produtos_com_varias_ativas"] == []
    com_promocao = {r[0] for r in conexao.execute("SELECT product_id FROM catalogo WHERE promo_percent IS NOT NULL")}
    assert com_promocao == {127, 121, 90, 94}


def test_t6_maior_desconto_prevalece_e_promocao_exige_disponibilidade(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for arquivo in (RAIZ / "data" / "raw").glob("*.csv"):
        raw.joinpath(arquivo.name).write_bytes(arquivo.read_bytes())
    promocoes = raw / "desafio_tecnico_ai_eng - promotions.csv"
    promocoes.write_text(
        promocoes.read_text(encoding="utf-8").rstrip("\n")
        + "\n26,127,25,Teste maior desconto,1\n27,96,30,Teste esgotado,1\n",
        encoding="utf-8",
    )
    db = tmp_path / "emporio.db"
    construir_banco(raw, db)
    with closing(sqlite3.connect(db)) as con:
        kalani = con.execute("SELECT promo_percent, preco_final_cents FROM catalogo WHERE product_id = 127").fetchone()
        esgotado = con.execute("SELECT promo_percent FROM catalogo WHERE product_id = 96").fetchone()[0]
    assert kalani == (25, 26925)
    assert esgotado is None


def test_t7_total_do_pedido_diverge_da_soma_dos_itens(qualidade):
    assert {x["order_id"]: (x["total_cents"], x["total_itens_cents"]) for x in qualidade["T7"]} == {
        3: (345000, 349800),
        20: (140000, 148800),
    }


def test_t8_email_compartilhado(qualidade):
    assert [(x["email"], x["clientes"]) for x in qualidade["T8"]] == [("bruno.martins@jmail.com", "11,43")]


def test_t9_parcelamento_abaixo_do_minimo(qualidade):
    assert ids(qualidade["T9"], "order_id") == {9, 16, 18}
    pedido9 = next(x for x in qualidade["T9"] if x["order_id"] == 9)
    assert pedido9["parcelas"] == 6 and fmt_brl(pedido9["valor_parcela"]) == "R$ 58,32"


def test_t10_entrega_atrasada_depende_da_data_de_referencia(db_path):
    with sqlite3.connect(db_path) as con:
        assert ids(analisar(con, AGORA)["T10"], "order_id") == {8}
        assert analisar(con, datetime.fromisoformat("2026-02-20T10:00:00-04:00"))["T10"] == []


# Vista `catalogo` e regras de preço


@pytest.mark.parametrize(
    ("produto", "percentual", "centavos"),
    [(127, 10, 32310), (94, 8, 551908), (121, 20, 43920), (90, 18, 196718)],
)
def test_preco_final_na_vista(conexao, produto, percentual, centavos):
    linha = conexao.execute(
        "SELECT price_cents, promo_percent, preco_final_cents FROM catalogo WHERE product_id = ?", (produto,)
    ).fetchone()
    assert linha["promo_percent"] == percentual and linha["preco_final_cents"] == centavos
    assert para_centavos(preco_final(Decimal(linha["price_cents"]) / 100, percentual)) == centavos


def test_vista_e_codigo_python_concordam_em_todos_os_produtos(conexao):
    for linha in conexao.execute("SELECT price_cents, promo_percent, preco_final_cents FROM catalogo"):
        esperado = preco_final(Decimal(linha["price_cents"]) / 100, linha["promo_percent"])
        assert linha["preco_final_cents"] == para_centavos(esperado)


def test_produto_sem_promocao_mantem_preco_de_tabela(conexao):
    linha = conexao.execute("SELECT price_cents, preco_final_cents FROM catalogo WHERE product_id = 95").fetchone()
    assert linha["price_cents"] == linha["preco_final_cents"] == 219900


# Regras de domínio


@pytest.mark.parametrize(
    ("status", "estoque", "esperado"),
    [
        ("active", 5, "disponivel"), ("active", 0, "esgotado"), ("discontinued", 13, "descontinuado"),
        ("discontinued", 0, "descontinuado"), ("coming_soon", 2, "em_breve"),
    ],
)
def test_disponibilidade(status, estoque, esperado):
    assert disponibilidade(status, estoque) == esperado


def test_disponibilidade_recusa_status_desconhecido():
    with pytest.raises(ValueError):
        disponibilidade("archived", 1)


def test_marcas_respeitam_limites_de_palavra():
    assert marca_do_nome("Kalani KAL-700T Tenor Natural") == "Kalani"
    assert marca_do_nome("Kala KA-15S Soprano Mogno") == "Kala"
    assert marca_do_nome("Music Man Bass 1X Electric Bass") == "Music Man"
    assert marca_do_nome("Bateria Acústica Pearl Kit 2 Studio") == "Pearl"
    assert marcas_citadas("Contrabaixo Fender com captadores Yamaha") == ["Fender", "Yamaha"]


def test_descricao_confiavel():
    assert descricao_confiavel("Takamine GD20 Dreadnought", "Violão Takamine com tampo sólido.")
    assert not descricao_confiavel("Korg Synth 1 Pro", "Sintetizador workstation Roland com 88 teclas.")
    assert descricao_confiavel("Yamaha C40", "Violão clássico para estudantes.")


def test_preco_final_arredonda_metade_para_cima():
    assert preco_final("0.05", 10) == Decimal("0.05")
    assert preco_final("10.05", 50) == Decimal("5.03")
    assert preco_final("599.9") == Decimal("599.90")


@pytest.mark.parametrize(
    ("valor", "texto"),
    [("1234.5", "R$ 1.234,50"), ("159.9", "R$ 159,90"), ("11499", "R$ 11.499,00"), ("-48", "-R$ 48,00"),
     ("0.5", "R$ 0,50")],
)
def test_fmt_brl(valor, texto):
    assert fmt_brl(valor) == texto


def test_para_centavos_recusa_mais_de_duas_casas():
    assert para_centavos("599.9") == 59990
    with pytest.raises(ValueError):
        para_centavos("10.005")
    with pytest.raises(TypeError):
        fmt_brl(10.5)
