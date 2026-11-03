"""LLM de roteiro para os testes end-to-end: decide por palavras-chave da pergunta e redige a resposta final
a partir do resultado das ferramentas reais. Mantém o teste determinístico sem trocar nada do sistema testado."""

from __future__ import annotations

import json
import time
from typing import Any

from emporio.agent.llm import ErroLLM

ESPERA_LENTA_S = 3


def _fala(texto: str) -> dict[str, Any]:
    return {"role": "assistant", "content": texto}


def _chama(nome: str, argumentos: dict[str, Any]) -> dict[str, Any]:
    chamada = {"id": "c1", "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}
    return {"role": "assistant", "content": "", "tool_calls": [chamada]}


class LLMDeRoteiro:
    def completar(self, mensagens: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        ultimo = mensagens[-1]
        if ultimo["role"] == "tool":
            ferramenta = mensagens[-2]["tool_calls"][-1]["function"]["name"]
            return _fala(self._final(ferramenta, json.loads(ultimo["content"])))

        pergunta = str(ultimo["content"]).lower()
        if "erro-modelo" in pergunta:
            raise ErroLLM("falha simulada do servidor de modelos")
        if "lento" in pergunta:
            time.sleep(ESPERA_LENTA_S)
            return _fala("Desculpa a demora, já cheguei.")
        if "html" in pergunta:
            return _fala("<script>window.__xss = 1</script> **tudo certo** <img src=x onerror=\"window.__xss = 2\">")
        if "12x" in pergunta:
            return _chama("simular_compra", {"produtos": [{"id": 95, "quantidade": 1}]})
        if "takamine" in pergunta:
            return _chama("detalhes_produto", {"produto": "Takamine GD20"})
        if "viol" in pergunta:
            return _chama("buscar_produtos", {"categoria": "Violões", "preco_max": 1000})
        if "endereço" in pergunta or "endereco" in pergunta:
            return _fala("A loja fica na Rua 14 de Maio, 3200, Centro, Campo Grande (MS).")
        return _fala("Posso ajudar com instrumentos, preços e pedidos. O que você procura?")

    @staticmethod
    def _final(ferramenta: str, dados: dict[str, Any]) -> str:
        if ferramenta == "buscar_produtos":
            linhas = [f"- **{p['nome']}**: {p['preco']}" for p in dados["produtos"]]
            return f"Encontrei {dados['total_encontrado']} violões até R$ 1.000,00:\n" + "\n".join(linhas)
        if ferramenta == "detalhes_produto":
            return f"O {dados['nome']} custa {dados['preco']}."
        if ferramenta == "simular_compra":
            item = dados["itens"][0]
            ultima = dados["opcoes_cartao"][-1]
            parcela = f"{ultima['parcelas']}x de {ultima['valor_parcela']}"
            return f"O {item['nome']} sai por {dados['subtotal']}. No cartão, até {parcela}."
        return "Pronto."
