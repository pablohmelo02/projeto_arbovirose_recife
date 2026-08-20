"""Filtros combináveis sobre `gold_arboviroses_clima_bairro`.

Esta camada nunca reimplementa lógica da Gold (joins Silver, Estratégia A,
cálculo epidemiológico, agregação climática) — ela só recorta/filtra o
DataFrame que a Gold já produziu. `pipeline gera dado, EDA/dashboard
consome dado` (ver CLAUDE.md).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.eda.schema_eda import AGRAVOS


def aplicar_filtros(
    df_gold: pd.DataFrame,
    agravo: Optional[str] = None,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
    codigo_rpa: Optional[str] = None,
    codigo_bairro: Optional[str] = None,
) -> pd.DataFrame:
    """Aplica filtros combináveis sobre a Gold. Qualquer combinação de
    filtros é válida — filtros não passados (`None`) não recortam nada.
    `agravo=None` mantém os 3 agravos nas linhas (nunca soma Dengue+Zika+
    Chikungunya como se fosse uma única doença — ver `total_arboviroses`
    para o agregado explícito)."""
    df = df_gold
    if agravo is not None:
        if agravo not in AGRAVOS:
            raise ValueError(f"agravo inválido: {agravo!r} (esperado um de {AGRAVOS})")
        df = df[df["agravo"] == agravo]
    if ano_inicio is not None:
        df = df[df["ano_epidemiologico"] >= ano_inicio]
    if ano_fim is not None:
        df = df[df["ano_epidemiologico"] <= ano_fim]
    if codigo_rpa is not None:
        df = df[df["codigo_rpa"] == codigo_rpa]
    if codigo_bairro is not None:
        df = df[df["codigo_bairro"] == codigo_bairro]
    return df


def total_arboviroses(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Agregado explícito "Total de arboviroses" (soma dos 3 agravos) —
    só deve ser chamado quando a UI identifica claramente que o número é
    a soma das três doenças, nunca como um quarto "agravo" silencioso."""
    grupo_cols = [c for c in df_gold.columns if c not in ("agravo", "casos") and not c.startswith("_")]
    # soma casos por todo o resto da chave (bairro/semana/etc.), colapsando agravo
    colunas_chave = [
        "codigo_bairro", "nome_bairro", "ano_epidemiologico", "semana_epidemiologica",
        "semana_epi_data_inicio", "semana_epi_data_fim",
    ]
    colunas_chave = [c for c in colunas_chave if c in df_gold.columns]
    return (
        df_gold.groupby(colunas_chave, observed=True)["casos"]
        .sum()
        .reset_index()
        .assign(agravo="TOTAL_ARBOVIROSES")
    )


def linhas_com_clima_real(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Recorte das linhas com pelo menos 1 dia de leitura climática real na
    semana (`dias_com_dado_valido_semana > 0`) — nunca `fillna(0)`, nunca
    assume que um ano "dentro" da janela de backfill tem clima em toda
    linha (ver `ANO_INICIO_COBERTURA_CLIMATICA_REAL` na docstring de
    `schema_eda.py`: é só um marcador de contexto, não um filtro)."""
    return df_gold[df_gold["dias_com_dado_valido_semana"].fillna(0) > 0]
