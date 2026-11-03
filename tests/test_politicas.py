"""Testes da E2: seções do manual, tópicos da ferramenta `consultar_politicas` e ficha da loja."""

from __future__ import annotations

import re

import pytest

from emporio.config import RAIZ
from emporio.domain.loja import FICHA, HORARIO_TEXTO
from emporio.domain.policies import TOPICOS, secoes_do_topico
from emporio.etl.politicas import extrair_secoes, gerar_politicas, markdown_do_pdf

PDF = RAIZ / "data" / "raw" / "políticas_da_loja.pdf"
NUMEROS_ESPERADOS = (
    "1 1.1 1.2 2 3 3.1 4 4.1 4.2 4.3 4.4 5 5.1 5.2 5.3 6 6.1 6.2 7 7.1 7.2 7.3 8 8.1 8.2 8.3 9 10".split()
)


@pytest.fixture(scope="module")
def politicas(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return gerar_politicas(PDF, tmp_path_factory.mktemp("politicas") / "politicas.json")


def texto(politicas: dict, numero: str) -> str:
    return politicas["secoes"][numero]["texto"]


def linhas_de_tabela(conteudo: str) -> list[list[str]]:
    linhas = [linha for linha in conteudo.splitlines() if linha.startswith("|")]
    return [[c.strip() for c in linha.strip("|").split("|")] for linha in linhas]


def test_todas_as_secoes_do_manual_estao_presentes(politicas):
    assert list(politicas["secoes"]) == NUMEROS_ESPERADOS
    assert politicas["secoes"]["4.1"]["titulo"] == "Direito de Arrependimento (Compras Online)"
    assert politicas["secoes"]["8"]["titulo"] == "Garantia"
    assert all(s["texto"] for n, s in politicas["secoes"].items() if n not in {"1", "4", "5", "6", "7", "8"})


def test_o_texto_da_secao_exclui_as_subsecoes(politicas):
    assert "Missão" not in texto(politicas, "1").split("não comercializamos")[-1]
    assert "Democratizar" in texto(politicas, "1.1")
    assert "Democratizar" not in texto(politicas, "1")


def test_cabecalhos_e_rodapes_de_pagina_foram_removidos(politicas):
    todo = "\n".join(s["texto"] for s in politicas["secoes"].values())
    assert not re.search(r"^Página \d+$", todo, flags=re.MULTILINE)
    assert "Manual de Políticas e Procedimentos" not in todo
    assert "**Campo**" not in todo


def test_tabela_de_horario_esta_alinhada(politicas):
    linhas = linhas_de_tabela(texto(politicas, "2"))
    assert linhas[0] == ["Dia", "Horário"]
    assert linhas[2:] == [
        ["Segunda a Sexta-feira", "09:00 às 18:00"],
        ["Sábado", "09:00 às 13:00"],
        ["Domingo e Feriados", "Fechado"],
    ]


def test_tabela_de_pagamento_esta_legivel(politicas):
    linhas = {linha[0]: linha for linha in linhas_de_tabela(texto(politicas, "3"))}
    assert linhas["PIX"][2] == "5% de desconto sobre o preço de tabela"
    assert linhas["Cartão de Crédito"][1] == "Até 12x sem juros"
    assert linhas["Boleto Bancário"][2] == "Compensação em até 3 dias úteis"
    assert all(len(linha) == 3 for linha in linhas.values())


def test_t12_parcela_minima_da_tabela_remete_a_secao_3_1(politicas):
    assert "R$ 100,00" not in texto(politicas, "3")
    assert "seção 3.1" in texto(politicas, "3")
    regras = texto(politicas, "3.1")
    assert "R$ 50,00" in regras and "R$ 80,00" in regras and "R$ 100,00" in regras


def test_tabela_de_frete_esta_legivel(politicas):
    linhas = {linha[0]: linha for linha in linhas_de_tabela(texto(politicas, "5.2"))}
    assert linhas["PAC (Correios)"][1] == "5 a 12 dias úteis"
    assert linhas["SEDEX (Correios)"][1] == "2 a 5 dias úteis"
    assert linhas["Jadlog (.package)"][1] == "3 a 8 dias úteis"
    assert "Frete grátis para pedidos acima de R$ 500,00" in texto(politicas, "5.1")
    assert "taxa fixa de R$ 35,00" in texto(politicas, "5.1")


def test_prazos_de_troca_e_garantia(politicas):
    assert "7 (sete) dias corridos" in texto(politicas, "4.1")
    assert "30 (trinta) dias" in texto(politicas, "4.2")
    assert "90 (noventa) dias" in texto(politicas, "8.1")


def test_t11_ficha_cadastral_corrigida(politicas):
    ficha = texto(politicas, "1.2")
    assert "(67) 3341-4444" in ficha
    assert "(67)3341" not in ficha
    assert "contato@emporiodamusica.com.br" in ficha
    assert "empóriodamusica" not in ficha
    assert [c["secoes"] for c in politicas["correcoes"]] == [["1.2"], ["3"]]


def test_ficha_da_loja_concorda_com_o_manual(politicas):
    ficha = texto(politicas, "1.2")
    assert FICHA["telefone_whatsapp"] in ficha
    assert FICHA["email"] in ficha
    assert FICHA["cnpj"] in ficha
    assert "Rua 14 de Maio, 3200" in ficha and "Rua 14 de Maio, 3200" in FICHA["endereco"]
    assert "79202-333" in ficha and "79202-333" in FICHA["endereco"]
    horarios = texto(politicas, "2")
    for faixa in ("09:00 às 18:00", "09:00 às 13:00"):
        assert faixa in horarios and faixa in HORARIO_TEXTO


def test_todo_topico_aponta_para_secoes_existentes(politicas):
    assert set(politicas["topicos"]) == set(TOPICOS)
    for topico, numeros in politicas["topicos"].items():
        assert numeros and all(n in politicas["secoes"] for n in numeros), topico
        assert [s["numero"] for s in secoes_do_topico(politicas, topico)] == numeros


def test_secoes_internas_nao_sao_expostas_por_topico(politicas):
    expostas = {n for numeros in politicas["topicos"].values() for n in numeros}
    assert not expostas & {"7", "7.1", "7.2", "7.3", "10"}
    assert expostas == set(NUMEROS_ESPERADOS) - {"7", "7.1", "7.2", "7.3", "10"}


def test_topico_desconhecido_e_recusado(politicas):
    with pytest.raises(KeyError):
        secoes_do_topico(politicas, "fofocas")


def test_extracao_ignora_o_que_vem_antes_da_primeira_secao():
    markdown = "# capa\n\n## **1. Primeira**\n\ncorpo\n\n### **1.1 Filha**\n\nfilha\n\nPágina 2\n"
    assert extrair_secoes(markdown) == {
        "1": {"numero": "1", "titulo": "Primeira", "texto": "corpo"},
        "1.1": {"numero": "1.1", "titulo": "Filha", "texto": "filha"},
    }


def test_conversao_do_pdf_nao_depende_de_ocr():
    assert "Manual de Políticas" in markdown_do_pdf(PDF)
