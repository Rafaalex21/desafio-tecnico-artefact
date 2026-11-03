"""Configuração do projeto, lida de variáveis de ambiente e do arquivo `.env` (seção 12)."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", env_file_encoding="utf-8", extra="ignore")

    llm_base_url: str = "http://localhost:1234/v1"
    llm_model: str = "qwen3-14b"
    llm_api_key: str = "local"
    llm_temperature: float = 0.3
    llm_timeout_s: float = 120
    llm_extra_body: str = ""
    agora_referencia: datetime | None = None
    history_max_tokens: int = 6000
    db_path: Path = Path("data/processed/emporio.db")
    conversas_db_path: Path = Path("data/processed/conversas.db")
    handoff_path: Path = Path("data/processed/handoff.jsonl")

    @field_validator("agora_referencia", mode="before")
    @classmethod
    def _vazio_como_none(cls, valor: Any) -> Any:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @property
    def extra_body(self) -> dict[str, Any] | None:
        """`LLM_EXTRA_BODY` interpretado como JSON; vazio vira None."""
        return json.loads(self.llm_extra_body) if self.llm_extra_body.strip() else None

    def caminho(self, relativo: Path) -> Path:
        """Resolve um caminho de dados em relação à raiz do repositório."""
        return relativo if relativo.is_absolute() else RAIZ / relativo


@lru_cache
def get_settings() -> Settings:
    return Settings()
