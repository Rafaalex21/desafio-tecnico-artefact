"""CLI de conversa com o Riff (seção 11.1): `uv run emporio-chat`."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from emporio.agent.loop import Agente, ChamadaFerramenta, Resultado
from emporio.clock import agora, estado_loja
from emporio.config import Settings, get_settings

RESUMO_MAX = 300
SAIDAS = {"/sair", "/exit", "/quit"}


def resumir(texto: str) -> str:
    return texto if len(texto) <= RESUMO_MAX else texto[:RESUMO_MAX] + "…"


def mostrar_chamada(console: Console, chamada: ChamadaFerramenta) -> None:
    try:
        argumentos = json.dumps(json.loads(chamada.argumentos or "{}"), ensure_ascii=False)
    except json.JSONDecodeError:
        argumentos = chamada.argumentos
    console.print(Text(f"  ↳ {chamada.nome}({argumentos})", style="dim yellow"))
    console.print(Text(f"    {resumir(chamada.resultado)}", style="dim"))


def mostrar_resultado(console: Console, resultado: Resultado, debug: bool) -> None:
    if debug:
        for chamada in resultado.ferramentas:
            mostrar_chamada(console, chamada)
        console.print(
            Text(
                f"  [{resultado.latencia_ms} ms, {resultado.iteracoes} chamadas ao modelo, "
                f"{resultado.correcoes_g2} correções G2{', resposta segura' if resultado.resposta_segura else ''}]",
                style="dim",
            )
        )
    console.print(Panel(Markdown(resultado.texto), title="Riff", title_align="left", border_style="yellow"))


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emporio-chat", description="Converse com o Riff, da Empório da Música.")
    parser.add_argument("--session", help="retoma uma sessão anterior; sem a opção, começa uma nova")
    parser.add_argument("--debug", action="store_true", help="mostra cada chamada de ferramenta e as métricas do turno")
    parser.add_argument("--agora", help="data e hora de referência em ISO 8601, ex.: 2026-03-25T10:30:00-04:00")
    return parser


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    args = montar_parser().parse_args(argv)
    config: Settings = get_settings()
    if args.agora:
        config = config.model_copy(update={"agora_referencia": datetime.fromisoformat(args.agora)})

    console = Console()
    session_id = args.session or uuid.uuid4().hex[:8]
    agente = Agente(config=config)

    console.print(f"[bold yellow]Empório da Música[/] · {estado_loja(agora(config)).texto}")
    retomada = bool(args.session) and agente.memoria.existe(session_id)
    console.print(f"[dim]Sessão {session_id}{' (retomada)' if retomada else ''}. Digite /sair para encerrar.[/]\n")
    if retomada:
        for mensagem in agente.memoria.mensagens_visiveis(session_id)[-6:]:
            quem = "Você" if mensagem["role"] == "user" else "Riff"
            console.print(f"[dim]{quem}: {resumir(mensagem['content'])}[/]")
        console.print()

    while True:
        try:
            entrada = console.input("[bold cyan]Você:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if entrada.lower() in SAIDAS:
            break
        if not entrada:
            continue
        with console.status("[yellow]Riff está pensando…[/]") as status:
            resultado = agente.responder(
                session_id, entrada, ao_status=lambda evento: status.update(f"[yellow]{evento['rotulo']}…[/]")
            )
        mostrar_resultado(console, resultado, args.debug)

    console.print(f"[dim]Para retomar: emporio-chat --session {session_id}[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
