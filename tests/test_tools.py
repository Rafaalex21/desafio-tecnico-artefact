"""Testes da E3: as seis ferramentas ponta a ponta sobre o banco real, com o relógio fixo em 25/03/2026."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from emporio.agent.tools import MODELOS, Ferramentas
from emporio.domain.orders import MAX_FALHAS, MSG_NAO_CONFERE


def chamar(ferramentas: Ferramentas, nome: str, **argumentos: Any) -> dict[str, Any]:
    return json.loads(ferramentas.executar(nome, argumentos))


def ids(resultado: dict[str, Any]) -> list[int]:
    return [produto["id"] for produto in resultado["produtos"]]


def dados_do_titular(ferramentas: Ferramentas, pedido: int) -> sqlite3.Row:
    return ferramentas.conexao.execute(
        "SELECT c.* FROM orders o JOIN customers c USING (customer_id) WHERE o.order_id = ?", (pedido,)
    ).fetchone()


# Esquemas


def test_seis_ferramentas_com_esquema_valido(ferramentas: Ferramentas):
    esquemas = ferramentas.schemas()
    assert [e["function"]["name"] for e in esquemas] == list(MODELOS)
    for esquema in esquemas:
        funcao = esquema["function"]
        assert funcao["description"]
        assert funcao["parameters"]["type"] == "object"
        assert "title" not in json.dumps(funcao["parameters"])
        json.dumps(esquema)


def test_categoria_do_esquema_lista_as_nove_categorias(ferramentas: Ferramentas):
    busca = next(e for e in ferramentas.schemas() if e["function"]["name"] == "buscar_produtos")
    enum = busca["function"]["parameters"]["properties"]["categoria"]["enum"]
    assert len(enum) == 9
    assert "Violões" in enum and "Instrumentos de Sopro (Metais)" in enum


def test_topicos_de_politicas_sao_enum_no_esquema(ferramentas: Ferramentas):
    politicas = next(e for e in ferramentas.schemas() if e["function"]["name"] == "consultar_politicas")
    itens = politicas["function"]["parameters"]["properties"]["topicos"]["items"]
    assert "trocas_e_devolucoes" in itens["enum"]


# Entrada inválida


def test_ferramenta_desconhecida_e_argumentos_ruins_viram_erro_json(ferramentas: Ferramentas):
    assert chamar(ferramentas, "apagar_tudo")["erro"] == "ferramenta_desconhecida"
    assert json.loads(ferramentas.executar("buscar_produtos", "{isso nao e json"))["erro"] == "argumentos_invalidos"
    assert chamar(ferramentas, "simular_compra")["erro"] == "argumentos_invalidos"
    assert chamar(ferramentas, "buscar_produtos", ordenar_por="aleatorio")["erro"] == "argumentos_invalidos"


def test_argumentos_vazios_e_extras_sao_tolerados(ferramentas: Ferramentas):
    assert json.loads(ferramentas.executar("buscar_produtos", ""))["total_encontrado"] > 0
    assert "erro" not in chamar(ferramentas, "buscar_produtos", termo="violão", campo_inventado=1)


# buscar_produtos (7.1)


@pytest.mark.parametrize("termo", ["takamine gd20", "gd-20", "GD20", "Takamine GD 20"])
def test_busca_por_modelo_escrito_de_varios_jeitos_traz_o_95_primeiro(ferramentas: Ferramentas, termo: str):
    assert ids(chamar(ferramentas, "buscar_produtos", termo=termo))[0] == 95


def test_violoes_ate_mil_reais_excluem_esgotado_e_descontinuado(ferramentas: Ferramentas):
    resultado = chamar(ferramentas, "buscar_produtos", categoria="Violões", preco_max=1000, limite=30)
    assert resultado["total_encontrado"] == 12
    assert 96 not in ids(resultado) and 113 not in ids(resultado)


def test_indisponiveis_so_aparecem_quando_pedidos(ferramentas: Ferramentas):
    resultado = chamar(
        ferramentas, "buscar_produtos", categoria="Violões", preco_max=1000, incluir_indisponiveis=True, limite=30
    )
    assert {96, 113} <= set(ids(resultado))
    estados = {p["id"]: p["disponibilidade"] for p in resultado["produtos"]}
    assert estados[96] == "esgotado" and estados[113] == "descontinuado"


@pytest.mark.parametrize(
    "categoria", ["Instrumentos de Sopro (Metais)", "Instrumentos de Sopro (Madeiras)", "Cordas Orquestrais"]
)
def test_categorias_sem_produtos_sao_sinalizadas(ferramentas: Ferramentas, categoria: str):
    resultado = chamar(ferramentas, "buscar_produtos", categoria=categoria)
    assert resultado["categoria_sem_itens"] is True
    assert resultado["produtos"] == []


def test_categoria_com_itens_nao_e_marcada_como_vazia(ferramentas: Ferramentas):
    assert chamar(ferramentas, "buscar_produtos", categoria="Ukuleles")["categoria_sem_itens"] is False


def test_apenas_em_promocao_traz_os_quatro_ativos(ferramentas: Ferramentas):
    resultado = chamar(ferramentas, "buscar_produtos", apenas_em_promocao=True)
    assert set(ids(resultado)) == {90, 94, 121, 127}
    assert all(p["promocao"] for p in resultado["produtos"])


def test_filtro_de_preco_usa_o_preco_promocional(ferramentas: Ferramentas):
    # Kalani 127: tabela R$ 359,00, promocional R$ 323,10.
    assert 127 in ids(chamar(ferramentas, "buscar_produtos", termo="kalani", preco_max=330))
    assert 127 not in ids(chamar(ferramentas, "buscar_produtos", termo="kalani", preco_min=330))


def test_ordenacao_por_preco(ferramentas: Ferramentas):
    def precos(**kw: Any) -> list[float]:
        # A ordem usa o preço final (S10): o promocional, quando houver.
        produtos = chamar(ferramentas, "buscar_produtos", categoria="Ukuleles", **kw)["produtos"]
        efetivos = [p["promocao"]["preco_promocional"] if p["promocao"] else p["preco"] for p in produtos]
        return [float(texto.removeprefix("R$ ").replace(".", "").replace(",", ".")) for texto in efetivos]

    menor, maior = precos(ordenar_por="menor_preco"), precos(ordenar_por="maior_preco")
    assert menor == sorted(menor) and maior == sorted(maior, reverse=True)


def test_limite_e_total_encontrado(ferramentas: Ferramentas):
    resultado = chamar(ferramentas, "buscar_produtos", limite=3)
    assert resultado["exibidos"] == 3 and resultado["total_encontrado"] > 3
    assert chamar(ferramentas, "buscar_produtos", limite=500)["exibidos"] <= 30


def test_busca_sem_correspondencia_devolve_lista_vazia(ferramentas: Ferramentas):
    resultado = chamar(ferramentas, "buscar_produtos", termo="xyzzy qwerty")
    assert resultado["total_encontrado"] == 0


def test_descricao_de_outra_marca_nao_atrai_a_busca(ferramentas: Ferramentas):
    # T5: a descrição do 135 (Music Man) fala em Fender Jazz Bass e é ignorada na busca.
    assert 135 not in ids(chamar(ferramentas, "buscar_produtos", termo="fender jazz bass"))


def test_categoria_invalida_lista_as_validas(ferramentas: Ferramentas):
    erro = chamar(ferramentas, "buscar_produtos", categoria="Pianos de Cauda")
    assert erro["erro"] == "categoria_invalida" and len(erro["categorias_validas"]) == 9


# detalhes_produto (7.2)


def test_produto_descontinuado_traz_alternativas_da_mesma_categoria(ferramentas: Ferramentas):
    produto = chamar(ferramentas, "detalhes_produto", produto=113)
    assert produto["disponibilidade"] == "descontinuado"
    assert produto["preco_pix"] is None
    assert 1 <= len(produto["alternativas"]) <= 3
    assert any("7 Cordas" in alt["nome"] for alt in produto["alternativas"])


def test_produto_esgotado_tambem_traz_alternativas(ferramentas: Ferramentas):
    produto = chamar(ferramentas, "detalhes_produto", produto=96)
    assert produto["disponibilidade"] == "esgotado" and produto["alternativas"]
    assert 96 not in [alt["id"] for alt in produto["alternativas"]]


def test_produto_em_breve_nao_vira_oferta(ferramentas: Ferramentas):
    produto = chamar(ferramentas, "detalhes_produto", produto=130)
    assert produto["disponibilidade"] == "em_breve" and produto["preco_pix"] is None


def test_descricao_de_outra_marca_e_omitida(ferramentas: Ferramentas):
    produto = chamar(ferramentas, "detalhes_produto", produto=135)
    assert produto["descricao"] is None
    assert "Fender" not in json.dumps(produto, ensure_ascii=False)


def test_produto_em_promocao_nao_recebe_desconto_pix(ferramentas: Ferramentas):
    produto = chamar(ferramentas, "detalhes_produto", produto=94)
    assert produto["promocao"] == {"percentual": 8, "preco_promocional": "R$ 5.519,08"}
    assert produto["preco_pix"] is None


def test_produto_sem_promocao_tem_preco_pix(ferramentas: Ferramentas):
    produto = chamar(ferramentas, "detalhes_produto", produto=95)
    assert produto["preco"] == "R$ 2.199,00" and produto["preco_pix"] == "R$ 2.089,05"


def test_busca_por_nome_e_por_id_como_texto(ferramentas: Ferramentas):
    assert chamar(ferramentas, "detalhes_produto", produto="Taylor 110e")["id"] == 94
    assert chamar(ferramentas, "detalhes_produto", produto="94")["id"] == 94
    assert chamar(ferramentas, "detalhes_produto", produto=94)["id"] == 94


def test_nome_generico_pede_esclarecimento_com_candidatos(ferramentas: Ferramentas):
    erro = chamar(ferramentas, "detalhes_produto", produto="Yamaha")
    assert erro["erro"] == "produto_ambiguo" and len(erro["candidatos"]) >= 2


def test_produto_inexistente(ferramentas: Ferramentas):
    assert chamar(ferramentas, "detalhes_produto", produto=9999)["erro"] == "produto_nao_encontrado"
    assert chamar(ferramentas, "detalhes_produto", produto="theremin quântico")["erro"] == "produto_nao_encontrado"


def test_ultimas_unidades_so_com_um_ou_dois_em_estoque(ferramentas: Ferramentas):
    consulta = "SELECT product_id FROM catalogo WHERE disponibilidade = 'disponivel' AND estoque"
    pouco = ferramentas.conexao.execute(f"{consulta} <= 2").fetchall()
    muito = ferramentas.conexao.execute(f"{consulta} > 2").fetchall()
    assert pouco and muito
    assert chamar(ferramentas, "detalhes_produto", produto=pouco[0][0])["ultimas_unidades"] is True
    assert chamar(ferramentas, "detalhes_produto", produto=muito[0][0])["ultimas_unidades"] is False


# simular_compra (7.3)


def test_kalani_promocional_vai_ate_quatro_parcelas(ferramentas: Ferramentas):
    compra = chamar(ferramentas, "simular_compra", produtos=[{"id": 127}])
    assert compra["subtotal"] == "R$ 323,10"
    assert compra["parcelas_maximas"] == 4
    assert compra["opcoes_cartao"][-1] == {"parcelas": 4, "valor_parcela": "R$ 80,78"}
    assert compra["total_pix"] == "R$ 323,10"


def test_taylor_em_promocao_no_pix_nao_tem_desconto_adicional(ferramentas: Ferramentas):
    compra = chamar(ferramentas, "simular_compra", produtos=[{"id": 94}])
    assert compra["subtotal"] == compra["total_pix"] == "R$ 5.519,08"
    assert compra["economia_pix"] == "R$ 0,00"
    assert compra["parcelas_maximas"] == 12 and compra["combinacao_permitida"] is True


def test_takamine_sem_promocao_ganha_cinco_por_cento_no_pix(ferramentas: Ferramentas):
    compra = chamar(ferramentas, "simular_compra", produtos=[{"id": 95}])
    assert compra["total_pix"] == "R$ 2.089,05"
    assert compra["opcoes_cartao"][-1] == {"parcelas": 12, "valor_parcela": "R$ 183,25"}


def test_carrinho_misto_aplica_pix_item_a_item(ferramentas: Ferramentas):
    compra = chamar(ferramentas, "simular_compra", produtos=[{"id": 95}, {"id": 127, "quantidade": 2}])
    assert compra["subtotal"] == "R$ 2.845,20"  # 2.199,00 + 2 x 323,10
    assert compra["total_pix"] == "R$ 2.735,25"  # 2.089,05 + 2 x 323,10
    assert [i["quantidade"] for i in compra["itens"]] == [1, 2]


def test_itens_repetidos_sao_somados(ferramentas: Ferramentas):
    compra = chamar(ferramentas, "simular_compra", produtos=[{"id": 127}, {"id": 127, "quantidade": 2}])
    assert len(compra["itens"]) == 1 and compra["itens"][0]["quantidade"] == 3


def test_frete_em_campo_grande_depende_do_subtotal(ferramentas: Ferramentas):
    barato = chamar(ferramentas, "simular_compra", produtos=[{"id": 127}], cidade_entrega="Campo Grande")
    caro = chamar(ferramentas, "simular_compra", produtos=[{"id": 95}], cidade_entrega="campo grande - MS")
    assert barato["frete"]["valor"] == "R$ 35,00" and caro["frete"]["valor"] == "R$ 0,00"


def test_frete_de_outra_cidade_e_bateria_acustica(ferramentas: Ferramentas):
    fora = chamar(ferramentas, "simular_compra", produtos=[{"id": 95}], cidade_entrega="Dourados")
    assert fora["frete"]["valor"] is None and "SEDEX" in fora["frete"]["observacao"]
    bateria = chamar(ferramentas, "simular_compra", produtos=[{"id": 139}], cidade_entrega="Campo Grande")
    assert bateria["frete"]["tipo"] == "cotacao_individual"


@pytest.mark.parametrize(("produto", "estado"), [(96, "esgotado"), (113, "descontinuado"), (130, "em_breve")])
def test_produto_indisponivel_nao_entra_na_simulacao(ferramentas: Ferramentas, produto: int, estado: str):
    erro = chamar(ferramentas, "simular_compra", produtos=[{"id": 95}, {"id": produto}])
    assert erro["erro"] == "produto_indisponivel" and erro["disponibilidade"] == estado


def test_quantidade_acima_do_estoque_nao_revela_o_saldo(ferramentas: Ferramentas):
    erro = chamar(ferramentas, "simular_compra", produtos=[{"id": 95, "quantidade": 9999}])
    assert erro["erro"] == "estoque_insuficiente"
    assert set(erro) == {"erro", "mensagem", "produto_id"}


def test_quantidade_invalida_e_produto_inexistente(ferramentas: Ferramentas):
    zero = chamar(ferramentas, "simular_compra", produtos=[{"id": 95, "quantidade": 0}])
    inexistente = chamar(ferramentas, "simular_compra", produtos=[{"id": 9999}])
    assert zero["erro"] == "quantidade_invalida"
    assert inexistente["erro"] == "produto_nao_encontrado"
    assert chamar(ferramentas, "simular_compra", produtos=[])["erro"] == "carrinho_vazio"


# consultar_pedido (7.4 e 6.11)


def test_pedido_7_entregue_com_prazos_de_pos_venda(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    pedido = chamar(ferramentas, "consultar_pedido", numero_pedido=7, email=titular["email"])
    assert pedido["status"] == "delivered" and pedido["cliente_primeiro_nome"] == "Letícia"
    assert pedido["forma_pagamento_texto"] == "Cartão de crédito em 3x"
    eleg = pedido["elegibilidade"]
    assert eleg["arrependimento"]["elegivel"] is False and eleg["arrependimento"]["prazo_final"] == "24/02/2026"
    assert eleg["troca_por_defeito"]["elegivel"] is False and eleg["troca_por_defeito"]["prazo_final"] == "05/03/2026"
    assert eleg["garantia_legal"] == {"elegivel": True, "prazo_final": "18/05/2026", "dias_restantes": 54}


def test_pedido_aceita_telefone_no_lugar_do_email(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=7, telefone=titular["phone"])["numero"] == 7
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=7, telefone="997890123")["numero"] == 7


def test_email_sem_diferenciar_caixa_nem_espacos(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    desalinhado = f"  {titular['email'].upper()} "
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=7, email=desalinhado)["numero"] == 7


def test_resposta_nao_expoe_dados_pessoais(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    bruto = ferramentas.executar("consultar_pedido", {"numero_pedido": 7, "email": titular["email"]})
    for segredo in (titular["email"], titular["phone"], titular["phone_digits"], "Gonçalves", "Rocha"):
        assert segredo not in bruto


def test_pedido_enviado_com_previsao_vencida_esta_atrasado(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 8)
    pedido = chamar(ferramentas, "consultar_pedido", numero_pedido=8, email=titular["email"])
    assert pedido["status"] == "shipped" and pedido["entrega_atrasada"] is True
    assert pedido["rastreio"] and pedido["previsao_entrega"] == "28/02/2026" and pedido["elegibilidade"] is None


def test_pedido_cancelado_traz_o_motivo(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 17)
    pedido = chamar(ferramentas, "consultar_pedido", numero_pedido=17, email=titular["email"])
    assert pedido["status_texto"] == "Cancelado"
    assert pedido["motivo_cancelamento"] == "Pedido cancelado pelo cliente antes do processamento"


def test_pedido_sem_dados_pede_verificacao_sem_contar_falha(ferramentas: Ferramentas):
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=7)["erro"] == "verificacao_necessaria"
    assert chamar(ferramentas, "consultar_pedido")["erro"] == "verificacao_necessaria"
    assert ferramentas.verificacao.falhas == 0


def test_dados_errados_e_pedido_inexistente_dao_a_mesma_resposta(ferramentas: Ferramentas):
    existente = chamar(ferramentas, "consultar_pedido", numero_pedido=7, email="outra.pessoa@jmail.com")
    inexistente = chamar(ferramentas, "consultar_pedido", numero_pedido=9999, email="outra.pessoa@jmail.com")
    assert existente == inexistente
    assert existente["erro"] == "dados_nao_conferem" and existente["mensagem"] == MSG_NAO_CONFERE


def test_pedido_de_outro_cliente_nao_abre_com_dados_de_um_verificado(ferramentas: Ferramentas):
    titular7, titular8 = dados_do_titular(ferramentas, 7), dados_do_titular(ferramentas, 8)
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=7, email=titular7["email"])["numero"] == 7
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=8)["erro"] == "verificacao_necessaria"
    trocado = chamar(ferramentas, "consultar_pedido", numero_pedido=8, email=titular7["email"])
    assert trocado["erro"] == "dados_nao_conferem"
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=8, email=titular8["email"])["numero"] == 8


def test_verificacao_vale_para_a_sessao_inteira(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    chamar(ferramentas, "consultar_pedido", numero_pedido=7, email=titular["email"])
    outro_do_mesmo_cliente = ferramentas.conexao.execute(
        "SELECT order_id FROM orders WHERE customer_id = ? AND order_id != 7", (titular["customer_id"],)
    ).fetchone()
    assert chamar(ferramentas, "consultar_pedido", numero_pedido=7)["numero"] == 7
    if outro_do_mesmo_cliente:
        assert chamar(ferramentas, "consultar_pedido", numero_pedido=outro_do_mesmo_cliente[0])["numero"]
    assert [p["numero"] for p in chamar(ferramentas, "consultar_pedido")["pedidos"]]


def test_tres_falhas_bloqueiam_a_sessao_inclusive_para_dados_certos(ferramentas: Ferramentas):
    for _ in range(MAX_FALHAS):
        falha = chamar(ferramentas, "consultar_pedido", numero_pedido=7, email="errado@jmail.com")
        assert falha["erro"] == "dados_nao_conferem"
    titular = dados_do_titular(ferramentas, 7)
    bloqueado = chamar(ferramentas, "consultar_pedido", numero_pedido=7, email=titular["email"])
    assert bloqueado["erro"] == "tentativas_excedidas"


def test_sem_numero_exige_email_e_telefone_juntos(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    assert chamar(ferramentas, "consultar_pedido", email=titular["email"])["erro"] == "verificacao_necessaria"
    assert chamar(ferramentas, "consultar_pedido", telefone=titular["phone"])["erro"] == "verificacao_necessaria"
    lista = chamar(ferramentas, "consultar_pedido", email=titular["email"], telefone=titular["phone"])
    assert 7 in [p["numero"] for p in lista["pedidos"]]


def test_email_compartilhado_se_resolve_pelo_telefone(ferramentas: Ferramentas):
    # T8: bruno.martins@jmail.com pertence aos clientes 11 e 43.
    c11, c43 = (
        ferramentas.conexao.execute("SELECT * FROM customers WHERE customer_id = ?", (i,)).fetchone() for i in (11, 43)
    )
    assert c11["email"] == c43["email"]
    meus = {o[0] for o in ferramentas.conexao.execute("SELECT order_id FROM orders WHERE customer_id = 43")}
    lista = chamar(ferramentas, "consultar_pedido", email=c43["email"], telefone=c43["phone"])
    assert {p["numero"] for p in lista["pedidos"]} == meus
    pedido_do_11 = ferramentas.conexao.execute("SELECT order_id FROM orders WHERE customer_id = 11").fetchall()
    if pedido_do_11:
        vizinho = chamar(ferramentas, "consultar_pedido", numero_pedido=pedido_do_11[0][0])
        assert vizinho["erro"] == "verificacao_necessaria"


def test_nome_completo_nao_serve_de_verificacao(ferramentas: Ferramentas):
    titular = dados_do_titular(ferramentas, 7)
    erro = chamar(ferramentas, "consultar_pedido", numero_pedido=7, email=titular["name"])
    assert erro["erro"] == "dados_nao_conferem"


# consultar_politicas (7.5)


def test_politicas_devolvem_as_secoes_do_topico_em_ordem(ferramentas: Ferramentas):
    resultado = chamar(ferramentas, "consultar_politicas", topicos=["garantia"])
    assert [s["numero"] for s in resultado["secoes"]] == ["8", "8.1", "8.2", "8.3"]
    assert all(s["titulo"] for s in resultado["secoes"])
    assert sum(bool(s["texto"]) for s in resultado["secoes"]) >= 3


def test_politicas_sem_secao_repetida_entre_topicos(ferramentas: Ferramentas):
    topicos = ["formas_de_pagamento", "promocoes", "formas_de_pagamento"]
    resultado = chamar(ferramentas, "consultar_politicas", topicos=topicos)
    numeros = [s["numero"] for s in resultado["secoes"]]
    assert len(numeros) == len(set(numeros)) and "3.1" in numeros and "6.2" in numeros


def test_politicas_internas_nao_sao_expostas(ferramentas: Ferramentas):
    tudo = chamar(ferramentas, "consultar_politicas", topicos=["sobre_a_loja", "horario_funcionamento", "privacidade"])
    assert not {"7", "7.1", "7.2", "7.3", "10"} & {s["numero"] for s in tudo["secoes"]}


def test_politicas_com_topico_invalido(ferramentas: Ferramentas):
    assert chamar(ferramentas, "consultar_politicas", topicos=["segredos_internos"])["erro"] == "argumentos_invalidos"
    assert chamar(ferramentas, "consultar_politicas", topicos=[])["erro"] == "topicos_invalidos"
    quatro = ["garantia", "frete_e_entregas", "promocoes", "privacidade"]
    assert chamar(ferramentas, "consultar_politicas", topicos=quatro)["erro"] == "topicos_invalidos"


# encaminhar_atendente (7.6)


def test_encaminhamento_gera_protocolo_e_grava_a_linha(ferramentas: Ferramentas):
    resposta = chamar(
        ferramentas, "encaminhar_atendente", motivo="reclamacao", resumo="Pedido 8 atrasado", numero_pedido=8
    )
    assert resposta["protocolo"] == "ATD-20260325-0001"
    assert resposta["prazo_retorno"] == "até 24 horas úteis" and resposta["equipe_disponivel_agora"] is True
    registro = json.loads(ferramentas.handoff_path.read_text(encoding="utf-8").splitlines()[0])
    assert registro["session_id"] == "sessao-teste" and registro["numero_pedido"] == 8


def test_encaminhamento_exige_motivo_valido(ferramentas: Ferramentas):
    assert chamar(ferramentas, "encaminhar_atendente", motivo="tédio", resumo="x")["erro"] == "argumentos_invalidos"
    assert not ferramentas.handoff_path.exists()
