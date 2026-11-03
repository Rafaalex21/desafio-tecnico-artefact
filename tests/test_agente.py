"""Testes da E4: guardrails, memória, montagem do prompt e loop do agente com um LLM roteirizado."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import AGORA

from emporio.agent import guardrails
from emporio.agent.llm import ErroLLM
from emporio.agent.loop import MAX_ITERACOES, RESPOSTA_SEM_MODELO, RESPOSTA_VAZIA, Agente
from emporio.agent.memory import Memoria, estimar_tokens, recortar
from emporio.agent.prompt import data_por_extenso, montar_system
from emporio.agent.tools import Ferramentas
from emporio.clock import agora, estado_loja
from emporio.config import Settings
from emporio.db import abrir_banco
from emporio.domain.orders import Verificacao


class LLMRoteirizado:
    """Devolve as respostas na ordem; um `ErroLLM` no roteiro é levantado em vez de devolvido."""

    def __init__(self, *respostas: dict[str, Any] | Exception) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[list[dict[str, Any]]] = []

    def completar(self, mensagens: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.chamadas.append(copy.deepcopy(mensagens))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def fala(texto: str) -> dict[str, Any]:
    return {"role": "assistant", "content": texto}


def chama(nome: str, argumentos: dict[str, Any] | str, identificador: str = "c1") -> dict[str, Any]:
    texto = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": identificador, "type": "function", "function": {"name": nome, "arguments": texto}}],
    }


@pytest.fixture()
def config() -> Settings:
    return Settings(agora_referencia=AGORA, history_max_tokens=6000)


@pytest.fixture()
def memoria(tmp_path: Path) -> Memoria:
    return Memoria(tmp_path / "conversas.db")


@pytest.fixture()
def fabrica(banco: Path, politicas_geradas: dict[str, Any], tmp_path: Path, config: Settings):
    def criar(session_id: str) -> Ferramentas:
        return Ferramentas(abrir_banco(banco), politicas_geradas, tmp_path / "handoff.jsonl", session_id, config)

    return criar


def agente(llm: LLMRoteirizado, memoria: Memoria, config: Settings, fabrica) -> Agente:
    return Agente(llm=llm, memoria=memoria, config=config, fabrica_ferramentas=fabrica)


# G4 e G5


def test_entrada_sem_controle_e_limitada():
    assert guardrails.limpar_entrada("  oi\x00\x07 tudo\nbem\x1b?  ") == "oi tudo\nbem?"
    assert len(guardrails.limpar_entrada("a" * 5000)) == guardrails.MAX_ENTRADA
    assert guardrails.limpar_entrada("\x00\x01 \n") == ""


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("<think>penso aqui</think>Olá!", "Olá!"),
        ("<think>\nlinhas\nvárias\n</think>\n\nOlá!", "Olá!"),
        ("penso sem abrir</think>Olá!", "Olá!"),
        ("Olá!<think>cortado no meio", "Olá!"),
        ("<THINK>x</THINK>Olá!", "Olá!"),
        ("Olá sem raciocínio", "Olá sem raciocínio"),
    ],
)
def test_raciocinio_nao_vaza(bruto: str, esperado: str):
    assert guardrails.remover_raciocinio(bruto) == esperado


# G2


@pytest.mark.parametrize(
    ("texto", "valores"),
    [
        ("custa R$ 2.199,00 no cartão", ["2199.00"]),
        ("R$2.199,00 e R$ 5,5", ["2199.00", "5.50"]),
        ("até R$ 1000 ou R$1.000", ["1000.00", "1000.00"]),
        ("R$ 35,00 de frete", ["35.00"]),
        ("sem valores, só 12x e 5%", []),
    ],
)
def test_extracao_de_valores_em_reais(texto: str, valores: list[str]):
    assert guardrails.valores_em_reais(texto) == [Decimal(v) for v in valores]


def test_g2_aceita_valores_de_ferramenta_e_do_cliente_com_tolerancia_de_um_centavo():
    historico = [
        {"role": "user", "content": "tenho R$ 1.500 para gastar"},
        {"role": "tool", "content": '{"preco":"R$ 2.199,00"}'},
        {"role": "assistant", "content": "R$ 9.999,00 (a fala do próprio agente não conta)"},
    ]
    permitidos = guardrails.valores_permitidos(historico)
    assert guardrails.valores_nao_rastreaveis("R$ 2.199,00 e R$ 1.500,00", permitidos) == []
    assert guardrails.valores_nao_rastreaveis("R$ 2.199,01", permitidos) == []
    assert guardrails.valores_nao_rastreaveis("R$ 2.199,02", permitidos) == [Decimal("2199.02")]
    assert guardrails.valores_nao_rastreaveis("R$ 9.999,00", permitidos) == [Decimal("9999.00")]


def test_g2_nao_repete_valor_invalido_no_aviso():
    aviso = guardrails.aviso_de_correcao([Decimal("10")], [Decimal("2199"), Decimal("2199")])
    assert aviso.count("R$ 2.199,00") == 1 and "R$ 10,00" in aviso


# Memória


def test_historico_volta_no_formato_openai_com_ferramentas(memoria: Memoria):
    chamada = chama("buscar_produtos", {"termo": "violão"})
    memoria.anexar(
        "s1",
        [
            {"role": "user", "content": "oi"},
            chamada,
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
            fala("pronto"),
        ],
        AGORA,
    )
    carregado = memoria.carregar("s1")
    assert [m["role"] for m in carregado] == ["user", "assistant", "tool", "assistant"]
    assert carregado[1]["tool_calls"] == chamada["tool_calls"]
    assert carregado[2]["tool_call_id"] == "c1"
    assert memoria.mensagens_visiveis("s1") == [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "pronto"},
    ]


def test_sessoes_sao_independentes_e_a_sequencia_continua(memoria: Memoria):
    memoria.anexar("a", [{"role": "user", "content": "1"}], AGORA)
    memoria.anexar("a", [{"role": "user", "content": "2"}], AGORA)
    memoria.anexar("b", [{"role": "user", "content": "x"}], AGORA)
    assert [m["content"] for m in memoria.carregar("a")] == ["1", "2"]
    assert [m["content"] for m in memoria.carregar("b")] == ["x"]
    assert memoria.existe("a") and not memoria.existe("c")


def test_verificacao_persiste_na_sessao(memoria: Memoria):
    assert memoria.verificacao("s") == Verificacao()
    memoria.salvar_verificacao("s", Verificacao(2, {14, 3}), AGORA)
    assert memoria.verificacao("s") == Verificacao(2, {3, 14})
    assert memoria.verificacao("outra") == Verificacao()


def turno(i: int, tamanho: int = 700) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"pergunta {i}"}, fala("r" * tamanho)]


def test_corte_remove_turnos_inteiros_dos_mais_antigos():
    mensagens = [m for i in range(10) for m in turno(i)]
    cortado = recortar(mensagens, orcamento=sum(estimar_tokens(m) for m in mensagens[-6:]))
    assert cortado == mensagens[-6:]
    assert cortado[0]["role"] == "user"


def test_corte_nunca_remove_o_ultimo_turno_nem_separa_ferramentas():
    longo = [
        {"role": "user", "content": "busca"},
        chama("buscar_produtos", {}),
        {"role": "tool", "tool_call_id": "c1", "content": "x" * 30000},
        fala("ok"),
    ]
    assert recortar([*turno(0), *longo], orcamento=10) == longo
    assert recortar([], orcamento=10) == []


# Prompt


def test_system_traz_data_estado_da_loja_e_ficha(config: Settings):
    momento = agora(config)
    texto = montar_system(momento, estado_loja(momento))
    assert "quarta-feira, 25 de março de 2026, 10:30" in texto
    assert "Aberta agora; hoje fechamos às 18:00" in texto
    assert "(67) 3341-4444" in texto and "contato@emporiodamusica.com.br" in texto
    assert "Rua 14 de Maio, 3200" in texto
    assert "{{" not in texto


def test_system_fechado_informa_reabertura():
    domingo = AGORA.replace(day=29, hour=15, minute=0)
    assert "reabrimos" in montar_system(domingo, estado_loja(domingo))
    assert data_por_extenso(domingo) == "domingo, 29 de março de 2026, 15:00"


# Loop


def test_pergunta_de_preco_chama_ferramenta_e_persiste_a_conversa(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("detalhes_produto", {"produto": "Takamine GD20"}),
        fala("O Takamine GD20 sai por R$ 2.199,00. No PIX, R$ 2.089,05."),
    )
    status: list[dict[str, str]] = []
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Quanto custa o Takamine GD20?", status.append)

    assert resultado.texto.startswith("O Takamine GD20 sai por R$ 2.199,00")
    assert [c.nome for c in resultado.ferramentas] == ["detalhes_produto"]
    assert json.loads(resultado.ferramentas[0].resultado)["preco"] == "R$ 2.199,00"
    assert status == [{"ferramenta": "detalhes_produto", "rotulo": "Conferindo o produto"}]
    assert resultado.iteracoes == 2 and resultado.correcoes_g2 == 0 and not resultado.resposta_segura

    primeira = llm.chamadas[0]
    assert primeira[0]["role"] == "system" and primeira[-1] == {
        "role": "user",
        "content": "Quanto custa o Takamine GD20?",
    }
    assert [m["role"] for m in memoria.carregar("s1")] == ["user", "assistant", "tool", "assistant"]


def test_historico_e_reenviado_no_turno_seguinte(memoria, config, fabrica):
    llm = LLMRoteirizado(fala("Fala! Sou o Riff."), fala("Posso ajudar com o quê?"))
    ag = agente(llm, memoria, config, fabrica)
    ag.responder("s1", "Oi")
    ag.responder("s1", "Quem é você?")
    roles = [m["role"] for m in llm.chamadas[1]]
    assert roles == ["system", "user", "assistant", "user"]


def test_g2_pede_correcao_uma_vez_e_nao_guarda_a_resposta_ruim(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("detalhes_produto", {"produto": 95}),
        fala("Sai por R$ 1.999,00!"),
        fala("Sai por R$ 2.199,00."),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Quanto custa o GD20?")
    assert resultado.texto == "Sai por R$ 2.199,00." and resultado.correcoes_g2 == 1
    aviso = llm.chamadas[2][-1]
    assert aviso["role"] == "user" and "R$ 1.999,00" in aviso["content"] and "R$ 2.199,00" in aviso["content"]
    guardado = json.dumps(memoria.carregar("s1"), ensure_ascii=False)
    assert "1.999" not in guardado and "aviso do sistema" not in guardado


def test_g2_persistente_vira_resposta_segura(memoria, config, fabrica):
    llm = LLMRoteirizado(fala("Custa R$ 111,00"), fala("Custa R$ 222,00"))
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Quanto custa o baixo?")
    assert resultado.resposta_segura and resultado.texto == guardrails.RESPOSTA_SEGURA
    assert memoria.mensagens_visiveis("s1")[-1]["content"] == guardrails.RESPOSTA_SEGURA


def test_valor_dito_pelo_cliente_pode_ser_repetido(memoria, config, fabrica):
    llm = LLMRoteirizado(fala("Entendi, seu limite é de R$ 800,00."))
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Posso gastar até R$ 800,00")
    assert resultado.correcoes_g2 == 0 and not resultado.resposta_segura


def test_resposta_vazia_ganha_uma_nova_chance(memoria, config, fabrica):
    llm = LLMRoteirizado(fala("<think>só pensei</think>"), fala("Agora sim!"))
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Oi")
    assert resultado.texto == "Agora sim!" and resultado.correcoes_g2 == 1


def test_raciocinio_e_removido_da_resposta_final(memoria, config, fabrica):
    llm = LLMRoteirizado(fala("<think>hmm, saudação</think>Fala! Sou o Riff 🤘"))
    assert agente(llm, memoria, config, fabrica).responder("s1", "Oi").texto == "Fala! Sou o Riff 🤘"


def test_limite_de_seis_chamadas_ao_modelo(memoria, config, fabrica):
    llm = LLMRoteirizado(*[chama("buscar_produtos", {"termo": "violão"}, f"c{i}") for i in range(10)])
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Violões?")
    assert resultado.resposta_segura and len(llm.chamadas) == MAX_ITERACOES
    assert len(resultado.ferramentas) == MAX_ITERACOES


def test_argumentos_invalidos_voltam_ao_modelo_como_erro_de_ferramenta(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("buscar_produtos", "{não é json"),
        chama("buscar_produtos", {"termo": "ukulele"}, "c2"),
        fala("Achei uns ukuleles, quer ver?"),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Tem ukulele?")
    assert json.loads(resultado.ferramentas[0].resultado)["erro"] == "argumentos_invalidos"
    assert "erro" not in json.loads(resultado.ferramentas[1].resultado)
    assert resultado.texto == "Achei uns ukuleles, quer ver?"


def test_servidor_do_modelo_fora_do_ar_nao_grava_nada(memoria, config, fabrica):
    llm = LLMRoteirizado(ErroLLM("conexão recusada"))
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Oi")
    assert resultado.erro and resultado.texto == RESPOSTA_SEM_MODELO
    assert memoria.carregar("s1") == []


def test_entrada_vazia_nao_chama_o_modelo(memoria, config, fabrica):
    llm = LLMRoteirizado()
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "  \x00 ")
    assert resultado.texto == RESPOSTA_VAZIA and llm.chamadas == []


def test_verificacao_de_pedido_sobrevive_a_novas_execucoes(memoria, config, fabrica):
    email = "leticia.rocha@jmail.com"
    primeiro = LLMRoteirizado(
        chama("consultar_pedido", {"numero_pedido": 7, "email": email}), fala("Achei o pedido 7, Letícia.")
    )
    agente(primeiro, memoria, config, fabrica).responder("s1", f"Pedido 7, {email}")
    assert memoria.verificacao("s1").clientes

    segundo = LLMRoteirizado(chama("consultar_pedido", {"numero_pedido": 7}), fala("Segue o status."))
    resultado = agente(segundo, memoria, config, fabrica).responder("s1", "E o status de novo?")
    assert json.loads(resultado.ferramentas[0].resultado)["numero"] == 7

    outra_sessao = LLMRoteirizado(chama("consultar_pedido", {"numero_pedido": 7}), fala("Preciso confirmar os dados."))
    resultado = agente(outra_sessao, memoria, config, fabrica).responder("s2", "Status do pedido 7?")
    assert json.loads(resultado.ferramentas[0].resultado)["erro"] == "verificacao_necessaria"


def test_tentativas_falhas_tambem_persistem(memoria, config, fabrica):
    for i in range(3):
        llm = LLMRoteirizado(
            chama("consultar_pedido", {"numero_pedido": 7, "email": "errado@jmail.com"}), fala("Não confere.")
        )
        agente(llm, memoria, config, fabrica).responder("s1", f"tentativa {i}")
    llm = LLMRoteirizado(
        chama("consultar_pedido", {"numero_pedido": 7, "email": "leticia.rocha@jmail.com"}), fala("Vou chamar alguém.")
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "agora com o certo")
    assert json.loads(resultado.ferramentas[0].resultado)["erro"] == "tentativas_excedidas"


def test_historico_longo_e_cortado_antes_de_ir_ao_modelo(memoria, config, fabrica):
    cfg = config.model_copy(update={"history_max_tokens": 600})
    memoria.anexar("s1", [m for i in range(20) for m in turno(i)], AGORA)
    llm = LLMRoteirizado(fala("Fechou."))
    agente(llm, memoria, cfg, fabrica).responder("s1", "e agora?")
    enviadas = llm.chamadas[0]
    assert len(enviadas) < 15 and enviadas[0]["role"] == "system" and enviadas[1]["role"] == "user"
    assert len(memoria.carregar("s1")) == 42


# G6 e G7


def _resultado_de_ferramenta(fabrica, nome: str, argumentos: dict[str, Any]) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": "t", "content": fabrica("sessao-g6").executar(nome, json.dumps(argumentos))}


def test_g6_promocao_sem_preco_original_e_percentual_e_apontada(fabrica):
    ferramenta = _resultado_de_ferramenta(fabrica, "detalhes_produto", {"produto": "Kalani KAL-700T"})
    promocoes = guardrails.promocoes_nas_ferramentas([ferramenta])
    esperado = [(Decimal("359.00"), Decimal(10), Decimal("323.10"))]
    assert [(p.original, p.percentual, p.final) for p in promocoes] == esperado

    faltas = guardrails.promocao_incompleta("Sai por R$ 323,10 em até 4x.", promocoes)
    assert len(faltas) == 2 and "R$ 359,00" in faltas[0] and "10%" in faltas[1]
    assert guardrails.promocao_incompleta("De R$ 359,00 por R$ 323,10, 10% de desconto.", promocoes) == []
    assert guardrails.promocao_incompleta("A loja abre às 9h.", promocoes) == []


def test_g6_simulacao_tambem_traz_a_promocao(fabrica):
    detalhes = json.loads(fabrica("s").executar("detalhes_produto", json.dumps({"produto": "Kalani KAL-700T"})))
    carrinho = {"produtos": [{"id": detalhes["id"], "quantidade": 1}]}
    simulacao = _resultado_de_ferramenta(fabrica, "simular_compra", carrinho)
    promocoes = guardrails.promocoes_nas_ferramentas([simulacao])
    assert [(p.original, p.final) for p in promocoes] == [(Decimal("359.00"), Decimal("323.10"))]


def test_g6_corrige_uma_vez_e_nao_persiste_o_rascunho(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("detalhes_produto", {"produto": "Kalani KAL-700T"}),
        fala("Ele sai por R$ 323,10."),
        fala("De R$ 359,00 por R$ 323,10, com 10% de desconto."),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s1", "Quanto custa o Kalani KAL-700T?")
    assert resultado.texto == "De R$ 359,00 por R$ 323,10, com 10% de desconto."
    assert resultado.reforcos == 1 and not resultado.resposta_segura
    assert "preço original" in llm.chamadas[-1][-1]["content"]
    assert all("Ele sai por" not in str(m["content"]) for m in memoria.carregar("s1"))


def test_g6_nao_insiste_se_o_modelo_repete_a_resposta(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("detalhes_produto", {"produto": "Kalani KAL-700T"}),
        fala("Ele sai por R$ 323,10."),
        fala("Ele sai por R$ 323,10."),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s2", "Quanto custa o Kalani KAL-700T?")
    assert resultado.texto == "Ele sai por R$ 323,10." and resultado.reforcos == 1


def test_g7_parcelamento_sem_simulacao_pede_simular_compra(memoria, config, fabrica):
    detalhes = json.loads(fabrica("s").executar("detalhes_produto", json.dumps({"produto": "Takamine GD20"})))
    llm = LLMRoteirizado(
        chama("detalhes_produto", {"produto": "Takamine GD20"}),
        fala("Posso simular, em qual cidade você está?"),
        chama("simular_compra", {"produtos": [{"id": detalhes["id"], "quantidade": 1}]}, "c2"),
        fala("Dá para parcelar o Takamine GD20 em 12x de R$ 183,25."),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s3", "Em quantas vezes parcela o Takamine GD20?")
    assert resultado.texto == "Dá para parcelar o Takamine GD20 em 12x de R$ 183,25."
    assert [c.nome for c in resultado.ferramentas] == ["detalhes_produto", "simular_compra"]
    assert resultado.reforcos == 1


def test_g7_nao_age_sem_conversa_de_parcelas(memoria, config, fabrica):
    llm = LLMRoteirizado(chama("detalhes_produto", {"produto": "Takamine GD20"}), fala("Ele custa R$ 2.199,00."))
    resultado = agente(llm, memoria, config, fabrica).responder("s4", "Quanto custa o Takamine GD20?")
    assert resultado.reforcos == 0 and resultado.texto == "Ele custa R$ 2.199,00."


def test_g8_pedido_sem_consulta_pede_consultar_pedido(memoria, config, fabrica):
    email = "anacarol.ferreira@coldmail.com"
    llm = LLMRoteirizado(
        fala("Preciso do telefone cadastrado na compra."),
        chama("consultar_pedido", {"numero_pedido": 8, "email": email}),
        fala("Seu pedido saiu para entrega."),
    )
    pergunta = f"Qual o status do pedido 8? Meu e-mail é {email}"
    resultado = agente(llm, memoria, config, fabrica).responder("s5", pergunta)
    assert [c.nome for c in resultado.ferramentas] == ["consultar_pedido"]
    assert resultado.texto == "Seu pedido saiu para entrega." and resultado.reforcos == 1
    assert "consultar_pedido" in llm.chamadas[1][-1]["content"]


@pytest.mark.parametrize(
    "fala_do_cliente",
    [
        "Qual o status do pedido 8?",
        "Quero ver meu pedido, meu e-mail é anacarol.ferreira@coldmail.com",
        "Quanto custa o Takamine GD20? Meu e-mail é anacarol.ferreira@coldmail.com",
        "Pedido 8, telefone (67) 98765-4321",
    ],
)
def test_g8_so_age_com_numero_do_pedido_e_contato(fala_do_cliente):
    turno = [{"role": "user", "content": fala_do_cliente}]
    assert guardrails.pedido_sem_consulta(turno) is (fala_do_cliente == "Pedido 8, telefone (67) 98765-4321")


def test_g8_nao_age_quando_a_ferramenta_foi_chamada():
    turno = [
        {"role": "user", "content": "Status do pedido 8, a.b@jmail.com"},
        {"role": "assistant", "tool_calls": [{"id": "c", "function": {"name": "consultar_pedido", "arguments": "{}"}}]},
    ]
    assert guardrails.pedido_sem_consulta(turno) is False


def test_g7_nao_confunde_nome_de_produto_com_parcelas():
    turno = [
        {"role": "user", "content": "Quero o baixo Ibanez Bass 2X"},
        {"role": "assistant", "tool_calls": [{"id": "c", "function": {"name": "buscar_produtos", "arguments": "{}"}}]},
    ]
    assert guardrails.parcelamento_sem_simulacao(turno) is False
    turno[0]["content"] = "Quero o Takamine GD20 em 12x"
    assert guardrails.parcelamento_sem_simulacao(turno) is True


def test_g9_atraso_sem_oferta_pede_encaminhamento(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("consultar_pedido", {"numero_pedido": 8, "email": "anacarol.ferreira@coldmail.com"}),
        fala("Sinto muito pelo atraso. O rastreio é BRJL5544332BR."),
        fala("Sinto muito pelo atraso. O rastreio é BRJL5544332BR. Quer que eu encaminhe o caso à equipe?"),
    )
    pergunta = "Qual o status do pedido 8? Meu e-mail é anacarol.ferreira@coldmail.com"
    resultado = agente(llm, memoria, config, fabrica).responder("s6", pergunta)
    assert resultado.texto.endswith("à equipe?") and resultado.reforcos == 1
    assert "encaminhe o caso" in llm.chamadas[-1][-1]["content"]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Prazo encerrado em 24/02/2026.", {(24, 2)}),
        ("Até 5 de março e 18/05.", {(5, 3), (18, 5)}),
        ("Funciona das 09:00 às 18:00, 3x sem juros, 1/2 dúzia.", set()),
    ],
)
def test_g11_reconhece_datas_nos_tres_formatos(texto, esperado):
    assert guardrails.datas_em(texto) == esperado


def test_g11_data_inventada_pede_reescrita(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("consultar_pedido", {"numero_pedido": 7, "email": "leticia.rocha@jmail.com"}),
        fala("O prazo de arrependimento encerrou em 24 de fevereiro, mas a troca vai até 17 de março."),
        fala("O prazo de arrependimento encerrou em 24/02/2026."),
    )
    pergunta = "Quero devolver, pedido 7, leticia.rocha@jmail.com"
    resultado = agente(llm, memoria, config, fabrica).responder("s7", pergunta)
    assert resultado.texto == "O prazo de arrependimento encerrou em 24/02/2026." and resultado.reforcos == 1
    assert "17/03" in llm.chamadas[-1][-1]["content"]


def test_g11_data_do_ferramenta_ou_do_cliente_nao_dispara():
    mensagens = [
        {"role": "user", "content": "Comprei dia 03/02"},
        {"role": "tool", "content": json.dumps({"prazo_final": "24/02/2026"})},
    ]
    assert guardrails.datas_nao_rastreaveis("Comprou em 3 de fevereiro; prazo até 24/02/2026.", mensagens) == []


def test_g10_situacao_vaga_pede_o_estado_exato(memoria, config, fabrica):
    llm = LLMRoteirizado(
        chama("buscar_produtos", {"consulta": "Shelby SN-7C"}),
        fala("O Shelby SN-7C não está disponível no momento, talvez esgotado."),
        fala("O Shelby SN-7C foi descontinuado e não faz mais parte do catálogo."),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s8", "Vocês têm o Shelby SN-7C?")
    assert resultado.texto.startswith("O Shelby SN-7C foi descontinuado") and resultado.reforcos == 1
    assert "descontinuado" in llm.chamadas[-1][-1]["content"]


def test_g10_nao_age_se_o_produto_nao_e_citado():
    produto = {"nome": "Shelby SN-7C 7 Cordas Nylon Natural", "disponibilidade": "descontinuado"}
    mensagens = [{"role": "tool", "content": json.dumps({"indisponiveis_correspondentes": [produto]})}]
    assert guardrails.situacao_imprecisa("Temos o Yamaha C40 por R$ 599,90.", mensagens) == []
    assert guardrails.situacao_imprecisa("O SN-7C está descontinuado.", mensagens) == []
    assert guardrails.situacao_imprecisa("O SN‑7C está fora de estoque.", mensagens) != []


def test_g10_hesitacao_sobre_produto_descontinuado_tambem_e_corrigida():
    produto = {"nome": "Shelby SN-7C 7 Cordas Nylon Natural", "disponibilidade": "descontinuado"}
    mensagens = [{"role": "tool", "content": json.dumps({"indisponiveis_correspondentes": [produto]})}]
    vago = "O SN-7C está temporariamente indisponível e foi descontinuado."
    assert guardrails.situacao_imprecisa(vago, mensagens) != []
    assert guardrails.situacao_imprecisa("O SN-7C saiu de linha, descontinuado.", mensagens) == []


def test_g12_protocolo_inventado_manda_chamar_encaminhar_atendente(memoria, config, fabrica):
    llm = LLMRoteirizado(
        fala("Sinto muito. Já enviamos um protocolo (nº 20261103-001) e a equipe retorna em 24 horas."),
        chama("encaminhar_atendente", {"motivo": "reclamacao", "resumo": "violão chegou riscado"}),
        fala("Sinto muito pelo transtorno. Seu protocolo está registrado, a equipe retorna em até 24 horas."),
    )
    resultado = agente(llm, memoria, config, fabrica).responder("s9", "O violão chegou riscado, quero reclamar")
    assert [c.nome for c in resultado.ferramentas] == ["encaminhar_atendente"] and resultado.reforcos == 1
    assert "encaminhar_atendente" in llm.chamadas[1][-1]["content"]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Vou encaminhar seu caso à equipe.", True),
        ("Quer que eu encaminhe o caso à equipe?", False),
        ("Nosso protocolo de troca tem 30 dias.", False),
        ("Seu protocolo é ATD-20261103-0001.", True),
    ],
)
def test_g12_sem_chamada_da_ferramenta(texto, esperado):
    assert guardrails.encaminhamento_sem_registro(texto, []) is esperado


def test_g12_protocolo_devolvido_pela_ferramenta_e_aceito():
    mensagens = [
        {"role": "assistant", "tool_calls": [{"id": "c", "function": {"name": "encaminhar_atendente"}}]},
        {"role": "tool", "content": json.dumps({"protocolo": "ATD-20261103-0001"})},
    ]
    certo = "Protocolo ATD-20261103-0001, retorno em 24 horas."
    assert guardrails.encaminhamento_sem_registro(certo, mensagens) is False
    assert guardrails.encaminhamento_sem_registro("Protocolo ATD-20261103-0007.", mensagens) is True
