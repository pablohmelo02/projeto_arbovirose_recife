"""Classificação de recursos do CKAN em fato/dimensão, entidade e ano.

A classificação é feita exclusivamente pelo nome do recurso (campo `name`
retornado por `package_show`), de forma tolerante a maiúsculas/minúsculas,
acentos e pequenas variações de nomenclatura (ex.: "Zika" vs "Zica").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from src.utils.text import extract_year, normalize_text

FORMATOS_ACEITOS = {"csv", "xls", "xlsx"}


@dataclass(frozen=True)
class ResourceClassification:
    tipo: str  # "fato" ou "dimensao"
    entidade: str
    ano: Optional[int] = None


def classificar_recurso(resource: dict[str, Any]) -> Optional[ResourceClassification]:
    """Classifica um recurso do CKAN como fato ou dimensão.

    Retorna `None` quando o recurso não pertence a nenhuma das tabelas de
    interesse do projeto (ex.: arquivos de metadados em JSON, boletins, PDFs).
    """
    nome = resource.get("name") or ""
    formato = (resource.get("format") or "").strip().lower()
    norm = normalize_text(nome)

    if not norm:
        return None

    if formato and formato not in FORMATOS_ACEITOS:
        return None

    if "metadado" in norm:
        return None

    if re.search(r"\bdengue\b", norm):
        return ResourceClassification("fato", "dengue", extract_year(norm))

    if re.search(r"\bzi[ck]a\b", norm):
        return ResourceClassification("fato", "zika", extract_year(norm))

    if "chikungunya" in norm:
        return ResourceClassification("fato", "chikungunya", extract_year(norm))

    if "bairro" in norm:
        return ResourceClassification("dimensao", "bairro")

    if "distrito" in norm:
        return ResourceClassification("dimensao", "distrito")

    if "agravo" in norm:
        return ResourceClassification("dimensao", "agravo")

    if "municipio" in norm:
        return ResourceClassification("dimensao", "municipio")

    if re.search(r"\buf\b", norm):
        return ResourceClassification("dimensao", "uf")

    return None
