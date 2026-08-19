"""Utilitários de normalização textual usados na classificação de recursos."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def normalize_text(text: str) -> str:
    """Remove acentos, colapsa espaços nas bordas e deixa o texto em lowercase."""
    if not text:
        return ""
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def extract_year(text: str) -> Optional[int]:
    """Extrai o primeiro ano de 4 dígitos (19xx ou 20xx) encontrado no texto."""
    matches = re.findall(r"(?:19|20)\d{2}", text)
    if not matches:
        return None
    return int(matches[0])
