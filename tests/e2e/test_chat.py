"""Fluxos da tela de chat do ponto de vista do cliente (etapa E8)."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.e2e.paginas import Chat

from emporio.agent.loop import RESPOSTA_SEM_MODELO


@pytest.fixture()
def chat(page: Page) -> Chat:
    page.set_default_timeout(15_000)
    return Chat(page).abrir()


def test_abre_com_boas_vindas_sugestoes_e_loja_aberta(chat: Chat):
    expect(chat.page).to_have_title("Riff · Empório da Música")
    expect(chat.selo).to_have_text("Loja aberta")
    for texto in (
        "Quais violões até R$ 1.000?",
        "Quanto custa o Takamine GD20?",
        "Qual o endereço da loja?",
        "Me arrependi da compra, posso devolver?",
    ):
        expect(chat.sugestao(texto)).to_be_visible()


def test_sugestao_vira_pergunta_e_traz_a_lista_com_precos_do_catalogo(chat: Chat):
    chat.sugestao("Quais violões até R$ 1.000?").click()
    chat.esperar_resposta("Yamaha C40 Nylon Natural")
    expect(chat.conversa).to_contain_text("R$ 599,90")
    expect(chat.conversa.get_by_role("listitem")).to_have_count(12)
    expect(chat.sugestao("Qual o endereço da loja?")).to_have_count(0)


def test_enter_envia_e_o_parcelamento_vem_da_simulacao(chat: Chat):
    chat.perguntar("Em quantas vezes parcelo o Takamine GD20? Quero em 12x")
    chat.esperar_resposta("12x de R$ 183,25")
    expect(chat.campo).to_be_enabled()
    expect(chat.campo).to_have_value("")


def test_shift_enter_quebra_linha_sem_enviar(chat: Chat):
    chat.campo.fill("primeira linha")
    chat.campo.press("Shift+Enter")
    chat.campo.press_sequentially("segunda linha")
    expect(chat.campo).to_have_value("primeira linha\nsegunda linha")
    expect(chat.conversa.locator(".msg.usuario")).to_have_count(0)


def test_mensagem_vazia_nao_e_enviada(chat: Chat):
    chat.campo.press("Enter")
    chat.enviar_botao.click()
    expect(chat.conversa).to_contain_text("Eu sou o Riff")
    expect(chat.conversa.locator(".msg.usuario")).to_have_count(0)


def test_bastidores_mostram_a_ferramenta_chamada(chat: Chat):
    chat.bastidores.click()
    expect(chat.bastidores).to_have_attribute("aria-pressed", "true")
    chat.perguntar("Quanto custa o Takamine GD20?")
    chat.esperar_resposta("custa R$ 2.199,00")
    expect(chat.conversa).to_contain_text('detalhes_produto({"produto":"Takamine GD20"})')


def test_recarregar_restaura_a_conversa(chat: Chat):
    chat.perguntar("Qual o endereço da loja?")
    chat.esperar_resposta("Rua 14 de Maio, 3200")
    chat.page.reload()
    expect(chat.conversa).to_contain_text("Qual o endereço da loja?")
    expect(chat.conversa).to_contain_text("Rua 14 de Maio, 3200")
    expect(chat.conversa).not_to_contain_text("Eu sou o Riff")


def test_recarregar_no_meio_do_turno_entrega_a_resposta_quando_ficar_pronta(chat: Chat):
    chat.perguntar("responda devagar, estou com pressa? lento")
    expect(chat.pensando).to_be_visible()
    chat.page.reload()
    expect(chat.conversa).to_contain_text("responda devagar")
    chat.esperar_resposta("Desculpa a demora, já cheguei.")
    expect(chat.campo).to_be_enabled()


def test_nova_conversa_limpa_a_tela_e_a_sessao(chat: Chat):
    chat.perguntar("Qual o endereço da loja?")
    chat.esperar_resposta("Rua 14 de Maio, 3200")
    chat.nova.click()
    expect(chat.conversa).to_contain_text("Eu sou o Riff")
    expect(chat.conversa).not_to_contain_text("Rua 14 de Maio")
    chat.page.reload()
    expect(chat.conversa).to_contain_text("Eu sou o Riff")
    expect(chat.conversa).not_to_contain_text("Rua 14 de Maio")


def test_html_na_resposta_aparece_como_texto(chat: Chat):
    chat.perguntar("me mostre um html")
    chat.esperar_resposta("tudo certo")
    expect(chat.conversa).to_contain_text("<script>")
    assert chat.page.evaluate("window.__xss") is None


def test_html_digitado_pelo_cliente_aparece_como_texto(chat: Chat):
    chat.perguntar("<img src=x onerror='window.__xss=3'> oi")
    expect(chat.conversa.locator(".msg.usuario")).to_contain_text("<img src=x")
    chat.esperar_resposta("Posso ajudar")
    assert chat.page.evaluate("window.__xss") is None


def test_falha_do_servidor_de_modelos_vira_aviso_ao_cliente(chat: Chat):
    chat.perguntar("erro-modelo")
    chat.esperar_resposta(RESPOSTA_SEM_MODELO)
    expect(chat.campo).to_be_enabled()
    chat.perguntar("Qual o endereço da loja?")
    chat.esperar_resposta("Rua 14 de Maio, 3200")


def test_servidor_da_tela_fora_do_ar_nao_trava_a_entrada(chat: Chat):
    chat.page.route("**/api/chat", lambda rota: rota.abort())
    chat.perguntar("Qual o endereço da loja?")
    chat.esperar_resposta("Não consegui falar com o servidor")
    expect(chat.campo).to_be_enabled()


def test_celular_de_360_px_sem_rolagem_horizontal(chat: Chat):
    chat.page.set_viewport_size({"width": 360, "height": 740})
    chat.sugestao("Quais violões até R$ 1.000?").click()
    chat.esperar_resposta("Yamaha C40 Nylon Natural")
    sem_rolagem = chat.page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert sem_rolagem
    expect(chat.campo).to_be_visible()
    expect(chat.enviar_botao).to_be_in_viewport()


@pytest.mark.real
def test_modelo_real_responde_pelo_endereco_da_ficha(page: Page, url_modelo_real: str):
    page.set_default_timeout(120_000)
    page.goto(url_modelo_real)
    chat = Chat(page)
    chat.perguntar("Qual o endereço da loja?")
    chat.esperar_resposta("Rua 14 de Maio", timeout=120_000)
    expect(chat.conversa).to_contain_text("3200")
