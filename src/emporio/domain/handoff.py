"""Encaminhamento para atendente humano (seção 7.6): protocolo e registro em JSON Lines."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from emporio.clock import estado_loja

MOTIVOS = ("reclamacao", "pedido_atrasado", "solicitacao_do_cliente", "fora_das_regras", "outro")

_trava = threading.Lock()


def _proximo_numero(caminho: Path, data: str) -> int:
    if not caminho.exists():
        return 1
    with open(caminho, encoding="utf-8") as arquivo:
        return 1 + sum(1 for linha in arquivo if f'"protocolo": "ATD-{data}-' in linha)


def prazo_de_retorno(motivo: str) -> str:
    return "até 24 horas úteis" if motivo == "reclamacao" else "no próximo horário de atendimento"


def registrar_encaminhamento(
    caminho: Path,
    agora: datetime,
    session_id: str,
    motivo: str,
    resumo: str,
    numero_pedido: int | None = None,
    contato: str | None = None,
) -> dict[str, Any]:
    estado = estado_loja(agora)
    data = agora.strftime("%Y%m%d")
    with _trava:
        protocolo = f"ATD-{data}-{_proximo_numero(caminho, data):04d}"
        registro = {
            "protocolo": protocolo,
            "session_id": session_id,
            "data": agora.isoformat(),
            "motivo": motivo,
            "resumo": resumo,
            "numero_pedido": numero_pedido,
            "contato": contato,
        }
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {
        "protocolo": protocolo,
        "prazo_retorno": prazo_de_retorno(motivo),
        "equipe_disponivel_agora": estado.aberta,
        "proxima_abertura": estado.proxima_abertura.isoformat() if estado.proxima_abertura else None,
        "situacao_da_loja": estado.texto,
    }
