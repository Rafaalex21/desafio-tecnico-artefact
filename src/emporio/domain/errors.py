"""Erro de negócio das ferramentas: vira `{"erro": codigo, "mensagem": ...}` para o modelo, nunca exceção."""

from __future__ import annotations

from typing import Any


class ErroFerramenta(Exception):
    def __init__(self, codigo: str, mensagem: str, **extra: Any) -> None:
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.extra = extra

    def como_dict(self) -> dict[str, Any]:
        return {"erro": self.codigo, "mensagem": self.mensagem, **self.extra}
