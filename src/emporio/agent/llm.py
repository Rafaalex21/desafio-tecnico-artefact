"""Cliente do LLM: qualquer servidor compatível com a API da OpenAI (seção 9.3)."""

from __future__ import annotations

from typing import Any, Protocol

import openai
from openai import OpenAI

from emporio.config import Settings, get_settings

MAX_TOKENS = 3000
TENTATIVAS_EXTRAS = 2


class ErroLLM(Exception):
    """O servidor do modelo não respondeu depois das tentativas."""


class ClienteLLM(Protocol):
    def completar(self, mensagens: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Uma volta do modelo. Devolve a mensagem do assistente: `role`, `content` e, se houver, `tool_calls`."""
        ...


class LLMOpenAI:
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or get_settings()
        self.cliente = OpenAI(
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            timeout=self.config.llm_timeout_s,
            max_retries=TENTATIVAS_EXTRAS,
        )

    def completar(self, mensagens: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        parametros: dict[str, Any] = {
            "model": self.config.llm_model,
            "messages": mensagens,
            "temperature": self.config.llm_temperature,
            "max_tokens": MAX_TOKENS,
        }
        if tools:
            parametros.update(tools=tools, tool_choice="auto")
        if self.config.extra_body:
            parametros["extra_body"] = self.config.extra_body
        try:
            resposta = self.cliente.chat.completions.create(**parametros)
        except openai.OpenAIError as erro:
            raise ErroLLM(f"{type(erro).__name__}: {erro}") from erro
        mensagem = resposta.choices[0].message
        saida: dict[str, Any] = {"role": "assistant", "content": mensagem.content or ""}
        if mensagem.tool_calls:
            saida["tool_calls"] = [
                {
                    "id": chamada.id,
                    "type": "function",
                    "function": {"name": chamada.function.name, "arguments": chamada.function.arguments},
                }
                for chamada in mensagem.tool_calls
            ]
        return saida
