"""Montagem do system prompt a cada turno (seção 8.2): o texto fixo vem de `prompts/system.md`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from emporio.clock import DIAS_DA_SEMANA, EstadoLoja
from emporio.domain.loja import FICHA, HORARIO_TEXTO

ARQUIVO = Path(__file__).parent / "prompts" / "system.md"

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


def data_por_extenso(momento: datetime) -> str:
    dia = DIAS_DA_SEMANA[momento.weekday()]
    return f"{dia}, {momento.day} de {MESES[momento.month - 1]} de {momento.year}, {momento:%H:%M}"


def ficha_em_texto() -> str:
    return "\n".join(
        [
            f"- Nome: {FICHA['nome']} ({FICHA['slogan']})",
            f"- Endereço: {FICHA['endereco']}",
            f"- Telefone e WhatsApp: {FICHA['telefone_whatsapp']}",
            f"- E-mail: {FICHA['email']}",
            f"- Horário: {HORARIO_TEXTO}",
        ]
    )


def montar_system(agora: datetime, estado: EstadoLoja) -> str:
    texto = ARQUIVO.read_text(encoding="utf-8")
    marcadores = {
        "{{agora}}": data_por_extenso(agora),
        "{{estado_loja}}": estado.texto,
        "{{ficha}}": ficha_em_texto(),
    }
    for marcador, valor in marcadores.items():
        texto = texto.replace(marcador, valor)
    return texto
