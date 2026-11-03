"""Testes da E3: regras de pagamento, frete, telefone e prazos pós-venda, sem banco nem LLM."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from emporio.domain.handoff import registrar_encaminhamento
from emporio.domain.orders import elegibilidade, forma_pagamento_texto, telefones_coincidem
from emporio.domain.payments import (
    calcular_frete,
    combinacao_permitida,
    eh_campo_grande,
    frete_especial,
    opcoes_cartao,
    preco_pix,
)

AGORA = datetime.fromisoformat("2026-03-25T10:30:00-04:00")


# Parcelamento (6.5)


@pytest.mark.parametrize(
    ("total", "maximo", "parcela", "primeira_invalida"),
    [
        ("323.10", 4, "80.78", 5),
        ("699.90", 6, "116.65", 7),
        ("2199.00", 12, "183.25", None),
    ],
)
def test_parcelamento_maximo_dos_exemplos(total: str, maximo: int, parcela: str, primeira_invalida: int | None):
    opcoes = dict(opcoes_cartao(total))
    assert max(opcoes) == maximo
    assert opcoes[maximo] == Decimal(parcela)
    if primeira_invalida:
        assert primeira_invalida not in opcoes


def test_parcelamento_usa_divisao_exata_na_validacao():
    # 699,90 / 7 = 99,9857: a parcela exibida seria 99,99, mas a validade usa o valor exato, então 7x não vale.
    assert 7 not in dict(opcoes_cartao("699.90"))
    assert 7 in dict(opcoes_cartao("700.00"))


def test_total_pequeno_so_aceita_a_vista():
    assert [n for n, _ in opcoes_cartao("49.99")] == [1]
    assert [n for n, _ in opcoes_cartao("100.00")] == [1, 2]


def test_combinacao_so_acima_de_dois_mil():
    assert not combinacao_permitida("2000.00")
    assert combinacao_permitida("2000.01")


def test_pix_cinco_por_cento_sobre_a_tabela():
    assert preco_pix("699.90") == Decimal("664.91")  # 664,905 arredonda para cima
    assert preco_pix("100.00") == Decimal("95.00")


# Frete (6.7)


@pytest.mark.parametrize(
    "cidade", ["Campo Grande", "campo grande", "  CAMPO   GRANDE ", "Campo Grande - MS", "Campo Grande/MS"]
)
def test_campo_grande_em_variacoes_de_escrita(cidade: str):
    assert eh_campo_grande(cidade)


@pytest.mark.parametrize("cidade", ["Campinas", "Campo Grande do Sul", "Dourados", "Grande Campo"])
def test_outras_cidades_nao_sao_campo_grande(cidade: str):
    assert not eh_campo_grande(cidade)


def test_frete_em_campo_grande_gratis_a_partir_de_500():
    abaixo = calcular_frete("Campo Grande", "499.99")
    limite = calcular_frete("Campo Grande", "500.00")
    assert abaixo["valor"] == "R$ 35,00"
    assert limite["valor"] == "R$ 0,00"
    assert abaixo["prazo"] == "1 a 3 dias úteis"


def test_frete_para_outras_cidades_nao_inventa_valor():
    frete = calcular_frete("Dourados", "900.00")
    assert frete["valor"] is None
    assert all(modalidade in frete["observacao"] for modalidade in ("PAC", "SEDEX", "Jadlog"))


def test_frete_sem_cidade_fica_a_definir():
    assert calcular_frete(None, "900.00")["tipo"] == "a_definir"


def test_item_de_grande_porte_exige_cotacao_mesmo_em_campo_grande():
    frete = calcular_frete("Campo Grande", "9000.00", com_item_especial=True)
    assert frete["tipo"] == "cotacao_individual"
    assert frete["valor"] is None


def test_frete_especial_so_para_bateria_acustica_e_contrabaixo_acustico():
    assert frete_especial("Baterias e Percussão", "Bateria Acústica Yamaha Kit 1 Studio")
    assert frete_especial("Cordas Orquestrais", "Contrabaixo Acústico 3/4")
    assert not frete_especial("Baixos", "Fender Precision Bass")
    assert not frete_especial("Guitarras", "Fender Stratocaster")


# Telefone (6.11)


@pytest.mark.parametrize(
    "informado",
    ["(67) 99789-0123", "67997890123", "99789-0123", "997890123", "97890123", "+55 67 99789-0123", "6797890123"],
)
def test_telefone_aceita_com_ou_sem_ddd_e_com_ou_sem_nono_digito(informado: str):
    assert telefones_coincidem(informado, "67997890123")


@pytest.mark.parametrize("informado", ["(11) 99789-0123", "99789-0124", "123", "", "abc"])
def test_telefone_recusa_numero_diferente_ou_incompleto(informado: str):
    assert not telefones_coincidem(informado, "67997890123")


# Elegibilidade (6.9)


def test_pedido_7_em_25_de_marco():
    resultado = elegibilidade("2026-02-03", "2026-02-17", date(2026, 3, 25))
    assert resultado["arrependimento"] == {"elegivel": False, "prazo_final": "24/02/2026", "dias_restantes": 0}
    assert resultado["troca_por_preferencia"]["elegivel"] is False
    assert resultado["troca_por_defeito"] == {"elegivel": False, "prazo_final": "05/03/2026", "dias_restantes": 0}
    assert resultado["garantia_legal"] == {"elegivel": True, "prazo_final": "18/05/2026", "dias_restantes": 54}


def test_prazo_vale_ate_o_ultimo_dia_inclusive():
    no_ultimo_dia = elegibilidade("2026-03-01", "2026-03-10", date(2026, 3, 17))
    um_dia_depois = elegibilidade("2026-03-01", "2026-03-10", date(2026, 3, 18))
    assert no_ultimo_dia["arrependimento"] == {"elegivel": True, "prazo_final": "17/03/2026", "dias_restantes": 0}
    assert um_dia_depois["arrependimento"]["elegivel"] is False


def test_troca_por_defeito_conta_da_compra_e_nao_do_recebimento():
    resultado = elegibilidade("2026-01-01", "2026-01-20", date(2026, 1, 31))
    assert resultado["troca_por_defeito"]["prazo_final"] == "31/01/2026"
    assert resultado["troca_por_defeito"]["elegivel"] is True


@pytest.mark.parametrize(
    ("codigo", "texto"),
    [
        ("pix", "PIX"),
        ("debit", "Cartão de débito"),
        ("boleto", "Boleto"),
        ("credit_6x", "Cartão de crédito em 6x"),
        ("credit_12x", "Cartão de crédito em 12x"),
    ],
)
def test_forma_de_pagamento_em_texto(codigo: str, texto: str):
    assert forma_pagamento_texto(codigo) == texto


# Encaminhamento (7.6)


def test_protocolos_sao_sequenciais_por_dia_e_ficam_no_arquivo(tmp_path):
    arquivo = tmp_path / "handoff.jsonl"
    primeiro = registrar_encaminhamento(arquivo, AGORA, "s1", "reclamacao", "Cliente reclama do atraso")
    segundo = registrar_encaminhamento(arquivo, AGORA, "s2", "outro", "Dúvida fora das regras", 7, "67 99999-0000")
    assert primeiro["protocolo"] == "ATD-20260325-0001"
    assert segundo["protocolo"] == "ATD-20260325-0002"
    amanha = datetime.fromisoformat("2026-03-26T09:00:00-04:00")
    assert registrar_encaminhamento(arquivo, amanha, "s3", "outro", "x")["protocolo"] == "ATD-20260326-0001"
    linhas = [json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines()]
    assert [linha["session_id"] for linha in linhas] == ["s1", "s2", "s3"]
    assert linhas[1]["numero_pedido"] == 7 and linhas[1]["contato"] == "67 99999-0000"


def test_prazo_de_retorno_e_situacao_da_loja(tmp_path):
    arquivo = tmp_path / "handoff.jsonl"
    reclamacao = registrar_encaminhamento(arquivo, AGORA, "s", "reclamacao", "r")
    comum = registrar_encaminhamento(arquivo, AGORA, "s", "solicitacao_do_cliente", "r")
    assert reclamacao["prazo_retorno"] == "até 24 horas úteis"
    assert comum["prazo_retorno"] == "no próximo horário de atendimento"
    assert comum["equipe_disponivel_agora"] is True  # quarta-feira, 10:30

    domingo = datetime.fromisoformat("2026-03-29T15:00:00-04:00")
    fechada = registrar_encaminhamento(arquivo, domingo, "s", "outro", "r")
    assert fechada["equipe_disponivel_agora"] is False
    assert fechada["proxima_abertura"].startswith("2026-03-30T09:00")
