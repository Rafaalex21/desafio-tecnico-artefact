"""Normalização de texto para comparação e busca."""

from __future__ import annotations

import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()
