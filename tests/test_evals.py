"""Testes da E5: leitura dos casos, asserções, métricas e relatório do runner, sem chamar o modelo."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.conftest import AGORA
from tests.test_agente import LLMRoteirizado, chama, fala

from emporio.config import RAIZ, Settings
from emporio.evals.casos import Espera, comparavel, ler_casos, verificar
from emporio.evals.run import (
    ResultadoCaso,
    Turno,
    executar_caso,
    nome_de_arquivo,
    percentil,
    relatorio_md,
    resumir,
)

CASOS = RAIZ / "evals" / "cases.yaml"
IDS_DA_ESPECIFICACAO = (
    [f"cat-{i:02d}" for i in range(1, 12)]
    + [f"pag-{i:02d}" for i in range(1, 4)]
    + [f"pol-{i:02d}" for i in range(1, 7)]
    + [f"ped-{i:02d}" for i in range(1, 7)]
    + [f"esc-{i:02d}" for i in range(1, 5)]
)


# Casos


def test_arquivo_de_casos_cobre_todos_os_ids_da_especificacao():
    ids = [caso.id for caso in ler_casos(CASOS)]
    assert len(ids) == len(set(ids))
    assert set(IDS_DA_ESPECIFICACAO) <= set(ids)


def test_todo_caso_tem_turnos_e_alguma_asercao():
    for caso in ler_casos(CASOS):
        assert caso.turnos, caso.id
        e = caso.espera
        assert any(
            [e.ferramentas, e.ferramentas_alguma, e.ferramentas_proibidas, e.contem_todos, e.contem_algum, e.nao_contem]
        ), caso.id


def test_data_de_referencia_do_caso_e_lida():
    pol06 = next(c for c in ler_casos(CASOS) if c.id == "pol-06")
    assert pol06.agora is not None and pol06.agora.isoformat() == "2026-03-29T15:00:00-04:00"


def test_contem_algum_aceita_lista_simples_e_lista_de_listas():
    casos = {c.id: c for c in ler_casos(CASOS)}
    assert casos["cat-06"].espera.contem_algum == (("descontinuad", "não faz mais parte", "fora de linha"),)
    assert len(casos["cat-04"].espera.contem_algum) == 2


def test_cada_caso_de_exemplo_da_especificacao_tem_resposta_aceitavel():
    """Respostas escritas à mão com os fatos corretos precisam passar: protege contra caso impossível."""
    casos = {c.id: c for c in ler_casos(CASOS)}
    ok = {
        "cat-02": ("O Takamine GD20 custa **R$ 2.199,00**.", ["detalhes_produto"]),
        "cat-03": ("Taylor 110e: R$5.999,00 com 8% de desconto, por R$ 5.519,08.", ["detalhes_produto"]),
        "pol-04": ("O SEDEX leva de 2 a 5 dias úteis.", ["consultar_politicas"]),
        "pol-06": ("Estamos fechados, voltamos segunda às 09:00.", []),
        "esc-04": ("Sinto muito. Seu protocolo é ATD-1 e o retorno é em até 24 horas úteis.", ["encaminhar_atendente"]),
    }
    for id_, (texto, ferramentas) in ok.items():
        assert verificar(casos[id_].espera, texto, ferramentas).falhas == [], id_


# Asserções


def test_comparacao_ignora_caixa_acento_markdown_e_espaco_apos_rs():
    assert comparavel("**R$2.199,00** é o preço") == comparavel("r$ 2.199,00 E O PREÇO")
    assert comparavel("Descontinuado") == "descontinuado"


def test_comparacao_trata_hifens_tipograficos_como_hifen():
    assert comparavel("Crafter HT‑100 e GF–1R") == comparavel("crafter ht-100 e gf-1r")


def test_asercoes_de_roteamento_e_de_texto_sao_classificadas():
    espera = Espera(
        ferramentas=("consultar_pedido",),
        ferramentas_alguma=("buscar_produtos", "detalhes_produto"),
        ferramentas_proibidas=("encaminhar_atendente",),
        contem_todos=("R$ 10,00",),
        contem_algum=(("sim", "claro"), ("hoje",)),
        nao_contem=("Fender",),
    )
    certo = verificar(espera, "Claro, sai por R$10,00 hoje", ["consultar_pedido", "buscar_produtos"])
    assert certo.falhas == [] and certo.total == 7 and certo.roteamento_ok

    errado = verificar(espera, "Talvez, custa R$ 11,00. É uma Fender.", ["encaminhar_atendente"])
    tipos = sorted(f.tipo for f in errado.falhas)
    assert tipos == ["roteamento"] * 3 + ["texto"] * 4
    assert not errado.roteamento_ok


def test_caso_sem_ferramentas_esperadas_nao_entra_no_roteamento():
    assert not Espera(contem_todos=("x",)).verifica_roteamento
    assert Espera(ferramentas_proibidas=("buscar_produtos",)).verifica_roteamento


# Execução com LLM roteirizado


def test_executar_caso_aplica_asercoes_ao_ultimo_turno(politicas_geradas):
    casos = {c.id: c for c in ler_casos(CASOS)}
    config = Settings(agora_referencia=AGORA)
    llm = LLMRoteirizado(
        chama("detalhes_produto", {"produto": "Takamine GD20"}),
        fala("O Takamine GD20 custa R$ 2.199,00."),
    )
    resultado = executar_caso(casos["cat-02"], config, politicas_geradas, llm)
    assert resultado.aprovado and resultado.roteamento_ok
    assert resultado.turnos[-1].ferramentas == ["detalhes_produto"]


def test_resposta_segura_reprova_o_caso_mesmo_com_texto_aceitavel(politicas_geradas):
    casos = {c.id: c for c in ler_casos(CASOS)}
    config = Settings(agora_referencia=AGORA)
    llm = LLMRoteirizado(fala("Custa R$ 1,00"), fala("Custa R$ 2,00"))
    resultado = executar_caso(casos["cat-02"], config, politicas_geradas, llm)
    assert resultado.resposta_segura and not resultado.aprovado


def test_caso_com_data_propria_usa_o_relogio_do_caso(politicas_geradas):
    casos = {c.id: c for c in ler_casos(CASOS)}
    llm = LLMRoteirizado(fala("Estamos fechados; voltamos segunda às 09:00."))
    executar_caso(casos["pol-06"], Settings(agora_referencia=AGORA), politicas_geradas, llm)
    sistema = llm.chamadas[0][0]["content"]
    assert "domingo, 29 de março de 2026, 15:00" in sistema


# Métricas e relatório


def resultado(id_: str, categoria: str, falhas: list[Any], latencia: int, roteamento: bool = True) -> ResultadoCaso:
    turno = Turno("pergunta", "resposta", ["buscar_produtos"], latencia, 0, False)
    return ResultadoCaso(id_, categoria, [turno], 3, falhas, roteamento)


def test_percentis():
    assert percentil([], 0.5) == 0
    assert percentil([10], 0.95) == 10
    valores = list(range(1, 101))
    assert percentil(valores, 0.5) in (50, 51) and percentil(valores, 0.95) in (95, 96)


def test_resumo_conta_roteamento_asercoes_e_categorias():
    from emporio.evals.casos import Falha

    resultados = [
        resultado("a", "catalogo", [], 1000),
        resultado("b", "catalogo", [Falha("texto", "faltou x")], 3000),
        resultado("c", "pedidos", [Falha("roteamento", "não chamou y")], 2000),
        resultado("d", "politicas", [], 500, roteamento=False),
    ]
    resumo = resumir(resultados)
    assert resumo["casos"] == 4 and resumo["casos_aprovados"] == 2
    assert resumo["casos_com_roteamento"] == 3 and resumo["roteamento_ok"] == 2
    assert resumo["asercoes"] == 12 and resumo["asercoes_ok"] == 10
    assert resumo["por_categoria"]["catalogo"] == {"casos": 2, "aprovados": 1}


def test_relatorio_lista_falhas_com_a_resposta_obtida():
    from emporio.evals.casos import Falha

    meta = {
        "executado_em": "03/11/2026 15:00",
        "modelo": "qwen3-14b",
        "extra_body": '{"reasoning_effort": "none"}',
        "temperatura": 0.3,
        "agora_referencia": "2026-03-25T10:30:00-04:00",
    }
    resultados = [resultado("cat-01", "catalogo", [Falha("texto", "faltou 'Yamaha C40'")], 2000)]
    texto = relatorio_md("qwen3-14b", meta, resumir(resultados), resultados)
    assert texto.startswith("# Avaliação: qwen3-14b")
    assert "### cat-01" in texto and "faltou 'Yamaha C40'" in texto and "Resposta obtida: resposta" in texto
    assert "p95" in texto and "Acerto de roteamento | 1/1" in texto
    assert "—" not in texto  # sem travessões (ARCHITECTURE.md 0.3)


def test_relatorio_sem_falhas():
    meta = dict.fromkeys(["executado_em", "modelo", "extra_body", "agora_referencia"], "x") | {"temperatura": 0}
    resultados = [resultado("cat-01", "catalogo", [], 1000)]
    assert "Nenhum caso reprovado." in relatorio_md("m", meta, resumir(resultados), resultados)


@pytest.mark.parametrize(("rotulo", "arquivo"), [("qwen/qwen3-14b", "qwen-qwen3-14b"), ("gpt oss:20b", "gpt-oss-20b")])
def test_nome_de_arquivo_seguro(rotulo: str, arquivo: str):
    assert nome_de_arquivo(rotulo) == arquivo
    json.dumps(arquivo)
