"""Classificação de recursos do dataset CKAN de limites territoriais do Recife.

O dataset `mapas-de-limites-e-divisoes-territoriais` tem 4 recursos (bairros,
microrregiões, RPA, logradouros). Nesta etapa só o de bairros está no escopo
— os demais são ignorados (retornam `None`), do mesmo jeito que
`classifier.py` ignora metadados fora do escopo da Bronze de arboviroses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.utils.text import normalize_text

FORMATOS_ACEITOS = {"geojson", "json"}


@dataclass(frozen=True)
class TerritoryResourceClassification:
    entidade: str  # só "bairro" é suportado nesta etapa


def classificar_recurso_territorio(
    resource: dict[str, Any]
) -> Optional[TerritoryResourceClassification]:
    """Classifica um recurso do dataset territorial. `None` se fora do escopo."""
    nome = resource.get("name") or ""
    formato = (resource.get("format") or "").strip().lower()
    norm = normalize_text(nome)

    if not norm:
        return None

    if formato and formato not in FORMATOS_ACEITOS:
        return None

    if "bairro" in norm and "microrregiao" not in norm:
        return TerritoryResourceClassification("bairro")

    return None
