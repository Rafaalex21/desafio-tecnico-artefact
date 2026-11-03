"""Relógio do sistema e estado de funcionamento da loja (seção 6.10 da especificação).

`agora()` é a única fonte de data e hora do projeto: com `AGORA_REFERENCIA` definida, o relógio fica fixo nela.
Feriados não são modelados (suposição S8).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from emporio.config import Settings, get_settings

FUSO = ZoneInfo("America/Campo_Grande")

# Dia da semana (segunda = 0) para (abertura, fechamento). Domingo não consta: fechado.
HORARIOS: dict[int, tuple[time, time]] = {
    **{dia: (time(9, 0), time(18, 0)) for dia in range(5)},
    5: (time(9, 0), time(13, 0)),
}

DIAS_DA_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


@dataclass(frozen=True)
class EstadoLoja:
    aberta: bool
    fecha_as: time | None
    proxima_abertura: datetime | None
    texto: str

    def como_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["fecha_as"] = self.fecha_as.strftime("%H:%M") if self.fecha_as else None
        dados["proxima_abertura"] = self.proxima_abertura.isoformat() if self.proxima_abertura else None
        return dados


def _local(momento: datetime) -> datetime:
    return momento.replace(tzinfo=FUSO) if momento.tzinfo is None else momento.astimezone(FUSO)


def agora(config: Settings | None = None) -> datetime:
    """Data e hora corrente em Campo Grande, ou `AGORA_REFERENCIA` quando configurada."""
    referencia = (config or get_settings()).agora_referencia
    return _local(referencia) if referencia else datetime.now(FUSO)


def _proxima_abertura(local: datetime) -> datetime:
    for deslocamento in range(8):
        dia = (local + timedelta(days=deslocamento)).date()
        if dia.weekday() in HORARIOS:
            abertura = datetime.combine(dia, HORARIOS[dia.weekday()][0], tzinfo=FUSO)
            if abertura > local:
                return abertura
    raise RuntimeError("Nenhum horário de abertura nos próximos 8 dias")


def _quando(local: datetime, abertura: datetime) -> str:
    dias = (abertura.date() - local.date()).days
    dia = DIAS_DA_SEMANA[abertura.weekday()]
    if dias == 0:
        return "hoje"
    if dias == 1:
        return f"amanhã ({dia}, {abertura:%d/%m})"
    return f"{dia} ({abertura:%d/%m})"


def estado_loja(momento: datetime | None = None) -> EstadoLoja:
    """Aberta ou fechada no instante dado (padrão: `agora()`), com o horário de fechamento ou de reabertura."""
    local = _local(momento or agora())
    horario = HORARIOS.get(local.weekday())
    if horario and horario[0] <= local.time().replace(tzinfo=None) < horario[1]:
        fecha = horario[1]
        return EstadoLoja(True, fecha, None, f"Aberta agora; hoje fechamos às {fecha:%H:%M}.")
    abertura = _proxima_abertura(local)
    return EstadoLoja(
        False, None, abertura, f"Fechada agora; reabrimos {_quando(local, abertura)} às {abertura:%H:%M}."
    )
