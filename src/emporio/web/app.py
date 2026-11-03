"""API e tela de chat (seções 11.2 e 11.3): `uv run emporio-web`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from emporio.agent.loop import Agente
from emporio.clock import agora, estado_loja
from emporio.config import Settings, get_settings

log = logging.getLogger("emporio.web")

ESTATICOS = Path(__file__).parent / "static"
ID_SESSAO = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
MAX_MENSAGEM = 4000
FIM = object()


class Entrada(BaseModel):
    session_id: str = Field(..., pattern=ID_SESSAO.pattern)
    message: str = Field(..., min_length=1, max_length=MAX_MENSAGEM)


def evento(nome: str, dados: dict[str, Any] | None = None) -> str:
    return f"event: {nome}\ndata: {json.dumps(dados or {}, ensure_ascii=False)}\n\n"


def criar_app(agente: Agente | None = None, config: Settings | None = None) -> FastAPI:
    config = config or (agente.config if agente else get_settings())
    agente = agente or Agente(config=config)
    app = FastAPI(title="Empório da Música", docs_url=None, redoc_url=None)
    travas: dict[str, threading.Lock] = {}
    travas_guarda = threading.Lock()

    def trava(session_id: str) -> threading.Lock:
        """Um turno por vez em cada sessão: o histórico e a verificação de identidade são gravados ao fim do turno."""
        with travas_guarda:
            return travas.setdefault(session_id, threading.Lock())

    @app.get("/", include_in_schema=False)
    def tela() -> FileResponse:
        return FileResponse(ESTATICOS / "index.html", headers={"Cache-Control": "no-cache"})

    @app.post("/api/chat")
    async def chat(entrada: Entrada) -> StreamingResponse:
        fila: asyncio.Queue[Any] = asyncio.Queue()
        laco = asyncio.get_running_loop()

        def publicar(item: Any) -> None:
            laco.call_soon_threadsafe(fila.put_nowait, item)

        def executar() -> None:
            try:
                with trava(entrada.session_id):
                    resultado = agente.responder(
                        entrada.session_id,
                        entrada.message,
                        ao_status=lambda dados: publicar(("status", dados)),
                    )
                publicar(
                    (
                        "message",
                        {
                            "content": resultado.texto,
                            "ferramentas": [
                                {"nome": c.nome, "argumentos": json.loads(c.argumentos or "{}")}
                                for c in resultado.ferramentas
                                if _json_valido(c.argumentos)
                            ],
                            "latencia_ms": resultado.latencia_ms,
                            "erro": resultado.erro,
                        },
                    )
                )
            except Exception:
                log.exception("Falha no turno da sessão %s", entrada.session_id)
                publicar(("error", {"mensagem": "Algo deu errado do nosso lado. Tente de novo em instantes."}))
            finally:
                publicar(FIM)

        async def fluxo() -> AsyncIterator[str]:
            tarefa = asyncio.create_task(asyncio.to_thread(executar))
            try:
                while (item := await fila.get()) is not FIM:
                    yield evento(*item)
                yield evento("done")
            finally:
                await asyncio.shield(tarefa)

        return StreamingResponse(
            fluxo(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/sessions/{session_id}/messages")
    def mensagens(session_id: str) -> dict[str, Any]:
        if not ID_SESSAO.fullmatch(session_id):
            raise HTTPException(status_code=422, detail="Identificador de sessão inválido.")
        return {"messages": agente.memoria.mensagens_visiveis(session_id)}

    @app.get("/api/loja")
    def loja() -> dict[str, Any]:
        estado = estado_loja(agora(config))
        return {"aberta": estado.aberta, "texto": estado.texto}

    @app.get("/api/health")
    def saude() -> dict[str, str]:
        try:
            agente.llm.cliente.with_options(timeout=3, max_retries=0).models.list()  # type: ignore[attr-defined]
            situacao = "ok"
        except Exception:
            situacao = "erro"
        return {"llm": situacao, "modelo": config.llm_model}

    app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
    return app


def _json_valido(texto: str) -> bool:
    try:
        json.loads(texto or "{}")
    except json.JSONDecodeError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="emporio-web", description="Tela de chat da Empório da Música.")
    parser.add_argument("--host", default="127.0.0.1", help="endereço de escuta (padrão: apenas esta máquina)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(criar_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
