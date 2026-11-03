"""Objeto de página da tela de chat: seletores por papel e rótulo, como o cliente enxerga a tela."""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect


class Chat:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.conversa = page.get_by_role("log", name="Conversa com o Riff")
        self.campo = page.get_by_label("Mensagem para o Riff")
        self.enviar_botao = page.get_by_role("button", name="Enviar mensagem")
        self.nova = page.get_by_role("button", name="Nova conversa")
        self.bastidores = page.get_by_role("button", name="Bastidores")
        self.selo = page.get_by_text(re.compile(r"^Loja (aberta|fechada)$"))
        self.pensando = page.get_by_text("Pensando", exact=False)

    def abrir(self) -> Chat:
        self.page.goto("/")
        expect(self.conversa).to_contain_text("Eu sou o Riff")
        return self

    def sugestao(self, texto: str) -> Locator:
        return self.page.get_by_role("button", name=texto)

    def perguntar(self, texto: str) -> None:
        self.campo.fill(texto)
        self.campo.press("Enter")

    def esperar_resposta(self, trecho: str, timeout: int = 20_000) -> None:
        expect(self.conversa).to_contain_text(trecho, timeout=timeout)
