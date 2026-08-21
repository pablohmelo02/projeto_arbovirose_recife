"""Filtros combináveis sobre `gold_arboviroses_clima_bairro`.

Esta camada nunca reimplementa lógica da Gold (joins Silver, Estratégia A,
cálculo epidemiológico, agregação climática) — ela só recorta/filtra o
DataFrame que a Gold já produziu. `pipeline gera dado, EDA/dashboard
consome dado` (ver CLAUDE.md).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.eda.schema_eda import AGRAVOS
from src.gold.populacao import incidencia_100k


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
    a soma das três doenças, nunca como um quarto "agravo" silencioso.

    Quando `populacao_bairro_ano` está presente (Gold >= 1.2), a coluna
    `incidencia_100k_combinada` também é calculada — **nunca** como soma das
    três incidências já publicadas (isso infla o resultado sem significado
    epidemiológico, ver docstring de `src/gold/populacao.py`), sempre como
    `casos_totais / populacao * 100000` numa única divisão. A população não
    varia por agravo dentro do mesmo bairro/ano, então usar o primeiro valor
    não-nulo do grupo é seguro."""
    # soma casos por todo o resto da chave (bairro/semana/etc.), colapsando agravo
    colunas_chave = [
        "codigo_bairro", "nome_bairro", "ano_epidemiologico", "semana_epidemiologica",
        "semana_epi_data_inicio", "semana_epi_data_fim",
    ]
    colunas_chave = [c for c in colunas_chave if c in df_gold.columns]

    agregacoes: dict[str, Any] = {"casos": "sum"}
    if "populacao_bairro_ano" in df_gold.columns:
        agregacoes["populacao_bairro_ano"] = "first"
    if "tipo_populacao" in df_gold.columns:
        agregacoes["tipo_populacao"] = "first"

    resultado = (
        df_gold.groupby(colunas_chave, observed=True)
        .agg(agregacoes)
        .reset_index()
        .assign(agravo="TOTAL_ARBOVIROSES")
    )
    if "populacao_bairro_ano" in resultado.columns:
        resultado["incidencia_100k_combinada"] = incidencia_100k(
            resultado["casos"], resultado["populacao_bairro_ano"]
        )
    return resultado


def linhas_com_clima_real(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Recorte das linhas com pelo menos 1 dia de leitura climática real na
    semana (`dias_com_dado_valido_semana > 0`) — nunca `fillna(0)`, nunca
    assume que um ano "dentro" da janela de backfill tem clima em toda
    linha (ver `ANO_INICIO_COBERTURA_CLIMATICA_REAL` na docstring de
    `schema_eda.py`: é só um marcador de contexto, não um filtro)."""
    return df_gold[df_gold["dias_com_dado_valido_semana"].fillna(0) > 0]
