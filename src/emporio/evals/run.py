"""Runner de avaliação (seção 13.3): `uv run emporio-evals --modelo <nome>`."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from emporio.agent.llm import ClienteLLM, LLMOpenAI
from emporio.agent.loop import Agente
from emporio.agent.memory import Memoria
from emporio.agent.tools import Ferramentas
from emporio.config import RAIZ, Settings, get_settings
from emporio.db import abrir_banco
from emporio.domain.policies import carregar_politicas
from emporio.evals.casos import Caso, Falha, ler_casos, verificar

CASOS_PADRAO = RAIZ / "evals" / "cases.yaml"
RELATORIOS_PADRAO = RAIZ / "evals" / "reports"
RESPOSTA_MAX = 700


@dataclass
class Turno:
    pergunta: str
    resposta: str
    ferramentas: list[str]
    latencia_ms: int
    correcoes_g2: int
    resposta_segura: bool


@dataclass
class ResultadoCaso:
    id: str
    categoria: str
    turnos: list[Turno]
    asercoes: int
    falhas: list[Falha] = field(default_factory=list)
    verifica_roteamento: bool = False

    @property
    def roteamento_ok(self) -> bool:
        return not any(f.tipo == "roteamento" for f in self.falhas)

    @property
    def resposta_segura(self) -> bool:
        return any(t.resposta_segura for t in self.turnos)

    @property
    def aprovado(self) -> bool:
        return not self.falhas and not self.resposta_segura


def percentil(valores: list[int], p: float) -> int:
    if not valores:
        return 0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p * (len(ordenados) - 1)))]


def executar_caso(
    caso: Caso, config: Settings, politicas: dict[str, Any], llm: ClienteLLM | None = None
) -> ResultadoCaso:
    """Roda os turnos do caso numa sessão nova, com memória e fila de atendimento descartáveis."""
    if caso.agora:
        config = config.model_copy(update={"agora_referencia": caso.agora})
    with tempfile.TemporaryDirectory() as pasta:
        base = Path(pasta)
        conexao = abrir_banco(config.caminho(config.db_path))
        agente = Agente(
            llm=llm or LLMOpenAI(config),
            memoria=Memoria(base / "conversas.db"),
            config=config,
            fabrica_ferramentas=lambda sid: Ferramentas(conexao, politicas, base / "handoff.jsonl", sid, config),
        )
        turnos = []
        try:
            for pergunta in caso.turnos:
                r = agente.responder(f"eval-{caso.id}", pergunta)
                turnos.append(
                    Turno(
                        pergunta,
                        r.texto,
                        [c.nome for c in r.ferramentas],
                        r.latencia_ms,
                        r.correcoes_g2,
                        r.resposta_segura,
                    )
                )
        finally:
            conexao.close()
    ultimo = turnos[-1]
    veredito = verificar(caso.espera, ultimo.resposta, ultimo.ferramentas)
    return ResultadoCaso(
        caso.id, caso.categoria, turnos, veredito.total, veredito.falhas, caso.espera.verifica_roteamento
    )


def resumir(resultados: list[ResultadoCaso]) -> dict[str, Any]:
    com_roteamento = [r for r in resultados if r.verifica_roteamento]
    total_asercoes = sum(r.asercoes for r in resultados)
    falhas = sum(len(r.falhas) for r in resultados)
    latencias = [t.latencia_ms for r in resultados for t in r.turnos]
    categorias: dict[str, dict[str, int]] = {}
    for r in resultados:
        c = categorias.setdefault(r.categoria, {"casos": 0, "aprovados": 0})
        c["casos"] += 1
        c["aprovados"] += r.aprovado
    return {
        "casos": len(resultados),
        "casos_aprovados": sum(r.aprovado for r in resultados),
        "casos_com_roteamento": len(com_roteamento),
        "roteamento_ok": sum(r.roteamento_ok for r in com_roteamento),
        "asercoes": total_asercoes,
        "asercoes_ok": total_asercoes - falhas,
        "correcoes_g2": sum(t.correcoes_g2 for r in resultados for t in r.turnos),
        "respostas_seguras": sum(t.resposta_segura for r in resultados for t in r.turnos),
        "turnos": len(latencias),
        "latencia_p50_ms": percentil(latencias, 0.5),
        "latencia_p95_ms": percentil(latencias, 0.95),
        "por_categoria": categorias,
    }


def pct(parte: int, todo: int) -> str:
    return f"{100 * parte / todo:.1f}%" if todo else "n/a"


def relatorio_md(rotulo: str, meta: dict[str, Any], resumo: dict[str, Any], resultados: list[ResultadoCaso]) -> str:
    s = resumo
    linhas = [
        f"# Avaliação: {rotulo}",
        "",
        f"Execução em {meta['executado_em']}, com a data de referência {meta['agora_referencia']}.",
        "",
        "## Configuração",
        "",
        "| Parâmetro | Valor |",
        "|---|---|",
        f"| Modelo | {meta['modelo']} |",
        f"| LLM_EXTRA_BODY | {meta['extra_body'] or '(vazio)'} |",
        f"| Temperatura | {meta['temperatura']} |",
        f"| Casos | {s['casos']} |",
        "",
        "## Resultados",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Acerto de roteamento | {s['roteamento_ok']}/{s['casos_com_roteamento']} "
        f"({pct(s['roteamento_ok'], s['casos_com_roteamento'])}) |",
        f"| Asserções aprovadas | {s['asercoes_ok']}/{s['asercoes']} ({pct(s['asercoes_ok'], s['asercoes'])}) |",
        f"| Casos aprovados | {s['casos_aprovados']}/{s['casos']} ({pct(s['casos_aprovados'], s['casos'])}) |",
        f"| Correções do guardrail G2 | {s['correcoes_g2']} |",
        f"| Respostas seguras (G1 ou G2) | {s['respostas_seguras']} |",
        f"| Latência por turno, p50 | {s['latencia_p50_ms'] / 1000:.1f} s |",
        f"| Latência por turno, p95 | {s['latencia_p95_ms'] / 1000:.1f} s |",
        "",
        "## Por categoria",
        "",
        "| Categoria | Aprovados |",
        "|---|---|",
        *[f"| {nome} | {c['aprovados']}/{c['casos']} |" for nome, c in s["por_categoria"].items()],
        "",
        "## Falhas",
        "",
    ]
    reprovados = [r for r in resultados if not r.aprovado]
    if not reprovados:
        linhas.append("Nenhum caso reprovado.")
    for r in reprovados:
        ultimo = r.turnos[-1]
        linhas += [f"### {r.id}", ""]
        linhas += [f"- Pergunta: {ultimo.pergunta}"]
        linhas += [f"- Ferramentas no último turno: {', '.join(ultimo.ferramentas) or 'nenhuma'}"]
        linhas += [f"- {f.descricao}" for f in r.falhas]
        if r.resposta_segura:
            linhas.append("- A resposta segura do guardrail foi acionada")
        resposta = ultimo.resposta.replace("\n", " ")
        linhas += [f"- Resposta obtida: {resposta[:RESPOSTA_MAX]}", ""]
    return "\n".join(linhas).rstrip() + "\n"


def nome_de_arquivo(rotulo: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", rotulo).strip("-")


def montar_parser(config: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emporio-evals", description="Avalia o agente com os casos de evals/cases.yaml."
    )
    parser.add_argument("--modelo", default=config.llm_model, help="identificador do modelo no servidor")
    parser.add_argument("--rotulo", help="nome do relatório; padrão: o modelo (use para variações de configuração)")
    parser.add_argument("--extra-body", default=config.llm_extra_body, help="JSON de LLM_EXTRA_BODY; vazio = nenhum")
    parser.add_argument("--temperatura", type=float, default=config.llm_temperature)
    parser.add_argument("--casos", default=str(CASOS_PADRAO), help="arquivo de casos")
    parser.add_argument("--so", help="ids separados por vírgula (ex.: cat-01,pol-06); não grava relatório")
    parser.add_argument("--saida", default=str(RELATORIOS_PADRAO), help="pasta dos relatórios")
    return parser


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    base = get_settings()
    args = montar_parser(base).parse_args(argv)
    config = base.model_copy(
        update={"llm_model": args.modelo, "llm_extra_body": args.extra_body, "llm_temperature": args.temperatura}
    )
    config.extra_body  # noqa: B018 - valida o JSON antes de gastar tempo com o modelo
    casos = ler_casos(Path(args.casos))
    if args.so:
        escolhidos = set(args.so.split(","))
        casos = [c for c in casos if c.id in escolhidos]
    politicas = carregar_politicas(config.caminho(config.politicas_path))

    resultados = []
    for caso in casos:
        resultado = executar_caso(caso, config, politicas)
        resultados.append(resultado)
        marca = "ok " if resultado.aprovado else "ERRO"
        detalhe = "" if resultado.aprovado else "  " + "; ".join(f.descricao for f in resultado.falhas)
        print(f"{marca} {caso.id}{detalhe}", flush=True)

    resumo = resumir(resultados)
    print(
        f"\nRoteamento {resumo['roteamento_ok']}/{resumo['casos_com_roteamento']}, "
        f"casos {resumo['casos_aprovados']}/{resumo['casos']}, asserções {resumo['asercoes_ok']}/{resumo['asercoes']}, "
        f"p50 {resumo['latencia_p50_ms'] / 1000:.1f} s, p95 {resumo['latencia_p95_ms'] / 1000:.1f} s"
    )
    if args.so:
        return 0

    rotulo = args.rotulo or args.modelo
    referencia = config.agora_referencia.isoformat() if config.agora_referencia else "relógio real"
    meta = {
        "executado_em": datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),
        "modelo": args.modelo,
        "extra_body": args.extra_body.strip(),
        "temperatura": args.temperatura,
        "agora_referencia": referencia,
    }
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = nome_de_arquivo(rotulo)
    (pasta / f"{nome}.md").write_text(relatorio_md(rotulo, meta, resumo, resultados), encoding="utf-8")
    (pasta / f"{nome}.json").write_text(
        json.dumps(
            {"rotulo": rotulo, **meta, "resumo": resumo, "casos": [asdict(r) for r in resultados]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Relatórios em {pasta / nome}.md e .json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
