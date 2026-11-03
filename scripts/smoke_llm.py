"""Teste de fumaça do LLM local: valida uma tool call no endpoint compatível com a API da OpenAI.

Envia uma pergunta que exige chamar uma ferramenta fictícia, confere a chamada, devolve o resultado
da ferramenta e imprime a resposta final. Sem argumentos, usa LLM_BASE_URL, LLM_MODEL e LLM_EXTRA_BODY
do `.env`. Com --variacoes, testa em sequência valores candidatos de `LLM_EXTRA_BODY` e informa qual
funcionou.

Uso:
    uv run python scripts/smoke_llm.py
    uv run python scripts/smoke_llm.py --variacoes
    uv run python scripts/smoke_llm.py --base-url http://localhost:11434/v1 --model qwen3:14b
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from typing import Any

from openai import OpenAI

from emporio.config import get_settings

FERRAMENTA = {
    "type": "function",
    "function": {
        "name": "consultar_preco",
        "description": "Consulta o preço de um instrumento do catálogo. Use quando o cliente perguntar quanto custa.",
        "parameters": {
            "type": "object",
            "properties": {"produto": {"type": "string", "description": "Nome do instrumento"}},
            "required": ["produto"],
        },
    },
}
PERGUNTA = "Quanto custa o violão Takamine GD20?"
SISTEMA = "Você é o Riff, assistente da Empório da Música. Responda em português do Brasil, em uma frase."
VARIACOES: list[dict[str, Any] | None] = [
    None,
    {"reasoning_effort": "low"},
    {"reasoning_effort": "none"},
    {"chat_template_kwargs": {"enable_thinking": False}},
]
RE_RACIOCINIO = re.compile(r"<think>.*?</think>", re.DOTALL)


def runtime_por_url(base_url: str) -> str:
    if ":1234" in base_url:
        return "LM Studio"
    if ":11434" in base_url:
        return "Ollama"
    return "desconhecido"


def executar(cliente: OpenAI, modelo: str, temperatura: float, extra_body: dict[str, Any] | None) -> dict[str, Any]:
    mensagens: list[dict[str, Any]] = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": PERGUNTA},
    ]
    comum: dict[str, Any] = {"model": modelo, "temperature": temperatura, "max_tokens": 800, "tools": [FERRAMENTA]}
    if extra_body:
        comum["extra_body"] = extra_body

    inicio = time.perf_counter()
    r1 = cliente.chat.completions.create(messages=mensagens, **comum)
    m1 = r1.choices[0].message
    if not m1.tool_calls:
        raise RuntimeError(f"o modelo respondeu sem chamar a ferramenta: {m1.content!r}")
    chamada = m1.tool_calls[0]
    argumentos = json.loads(chamada.function.arguments)
    if chamada.function.name != "consultar_preco" or not isinstance(argumentos.get("produto"), str):
        raise RuntimeError(f"tool call inválida: {chamada.function.name} {chamada.function.arguments}")
    t_chamada = time.perf_counter() - inicio

    mensagens.append(m1.model_dump(exclude_none=True))
    mensagens.append(
        {
            "role": "tool",
            "tool_call_id": chamada.id,
            "content": json.dumps(
                {"produto": "Takamine GD20 Dreadnought Natural", "preco": "R$ 2.199,00"}, ensure_ascii=False
            ),
        }
    )
    r2 = cliente.chat.completions.create(messages=mensagens, **comum)
    resposta = RE_RACIOCINIO.sub("", r2.choices[0].message.content or "").strip()
    if "2.199,00" not in resposta:
        raise RuntimeError(f"a resposta final não traz o preço da ferramenta: {resposta!r}")
    return {
        "tool_call": {"nome": chamada.function.name, "argumentos": argumentos},
        "resposta": resposta,
        "latencia_tool_call_s": round(t_chamada, 2),
        "latencia_total_s": round(time.perf_counter() - inicio, 2),
    }


def main() -> int:
    cfg = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=cfg.llm_base_url)
    parser.add_argument("--model", default=cfg.llm_model)
    parser.add_argument("--extra-body", default=cfg.llm_extra_body, help="JSON; vazio = nenhum")
    parser.add_argument("--variacoes", action="store_true", help="testa valores candidatos de LLM_EXTRA_BODY")
    args = parser.parse_args()

    cliente = OpenAI(base_url=args.base_url, api_key=cfg.llm_api_key, timeout=cfg.llm_timeout_s, max_retries=0)
    runtime = runtime_por_url(args.base_url)
    print(f"Endpoint: {args.base_url} (runtime: {runtime})")
    try:
        disponiveis = [m.id for m in cliente.models.list().data]
    except Exception as erro:  # noqa: BLE001 - qualquer falha de conexão encerra o teste
        print(f"ERRO: não foi possível listar modelos em {args.base_url}: {erro}", file=sys.stderr)
        return 2
    print(f"Modelos disponíveis: {', '.join(disponiveis) or '(nenhum)'}")
    print(f"Modelo testado: {args.model}")
    if args.model not in disponiveis:
        print("ERRO: o modelo testado não está carregado/instalado no servidor.", file=sys.stderr)
        return 2

    if args.variacoes:
        candidatos = VARIACOES
    else:
        candidatos = [json.loads(args.extra_body) if args.extra_body.strip() else None]

    for extra in candidatos:
        rotulo = json.dumps(extra, ensure_ascii=False) if extra else "(vazio)"
        print(f"\nTentando LLM_EXTRA_BODY={rotulo}")
        try:
            resultado = executar(cliente, args.model, cfg.llm_temperature, extra)
        except Exception as erro:  # noqa: BLE001 - registra e tenta a próxima variação
            corpo = getattr(getattr(erro, "response", None), "text", "")
            print(f"  falhou: {erro} {corpo[:300]}")
            continue
        print(
            f"  tool call: {resultado['tool_call']['nome']}"
            f"({json.dumps(resultado['tool_call']['argumentos'], ensure_ascii=False)})"
        )
        print(f"  resposta final: {resultado['resposta']}")
        print(f"  latência: tool call {resultado['latencia_tool_call_s']} s, total {resultado['latencia_total_s']} s")
        print(f"\nOK. runtime={runtime} modelo={args.model} LLM_EXTRA_BODY={rotulo}")
        return 0

    print("\nFALHOU: nenhuma configuração produziu uma tool call válida.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
