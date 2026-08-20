"""Profiling da Gold `gold_arboviroses_clima_bairro` — só diagnóstico, nunca
corrige nada (mesmo princípio dos profilers de Bronze/Silver).

Separado das funções de transformação de propósito (`arboviroses_clima.py`
não importa este módulo): análise e transformação são responsabilidades
distintas.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

CHAVE_GOLD = ("codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica")


def perfilar_gold(df_gold: pd.DataFrame) -> dict[str, Any]:
    """Métricas reais de estrutura, cobertura, distribuição e integridade."""
    total = len(df_gold)

    missing_por_campo = {
        coluna: {
            "quantidade_null": int(df_gold[coluna].isna().sum()),
            "percentual_null": round(100 * df_gold[coluna].isna().sum() / total, 4) if total else 0.0,
        }
        for coluna in df_gold.columns
    }

    casos = df_gold["casos"]
    com_clima = df_gold["dias_com_dado_valido_semana"].fillna(0) > 0

    perfil: dict[str, Any] = {
        "total_linhas": total,
        "chave_gold": list(CHAVE_GOLD),
        "chave_gold_duplicadas": int(df_gold.duplicated(subset=list(CHAVE_GOLD)).sum()),
        "total_bairros": int(df_gold["codigo_bairro"].nunique()),
        "total_agravos": int(df_gold["agravo"].nunique()),
        "agravos": sorted(df_gold["agravo"].dropna().unique().tolist()),
        "ano_epidemiologico_min": int(df_gold["ano_epidemiologico"].min()),
        "ano_epidemiologico_max": int(df_gold["ano_epidemiologico"].max()),
        "total_periodos_distintos": int(
            df_gold[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0]
        ),
        "data_inicio_min": str(df_gold["semana_epi_data_inicio"].min()),
        "data_fim_max": str(df_gold["semana_epi_data_fim"].max()),
        "casos": {
            "total": int(casos.sum()),
            "media": round(float(casos.mean()), 4),
            "mediana": float(casos.median()),
            "maximo": int(casos.max()),
            "minimo": int(casos.min()),
            "linhas_com_caso": int((casos > 0).sum()),
            "linhas_sem_caso": int((casos == 0).sum()),
            "percentual_linhas_com_caso": round(100 * (casos > 0).sum() / total, 4) if total else 0.0,
            "negativos": int((casos < 0).sum()),
        },
        "casos_por_agravo": {k: int(v) for k, v in df_gold.groupby("agravo")["casos"].sum().items()},
        "clima": {
            "linhas_com_clima_real": int(com_clima.sum()),
            "percentual_linhas_com_clima_real": round(100 * com_clima.sum() / total, 4) if total else 0.0,
            "fontes_clima": sorted(df_gold["fonte_clima"].dropna().unique().tolist()),
            "estacoes_distintas": int(df_gold["codigo_estacao_clima"].nunique()),
            "precipitacao_negativa": int((df_gold["precipitacao_total_semana_mm"].fillna(0) < 0).sum()),
        },
        "missing_por_campo": missing_por_campo,
    }

    if com_clima.any():
        precip = df_gold.loc[com_clima, "precipitacao_total_semana_mm"]
        perfil["clima"]["precipitacao_semanal_mm"] = {
            "media": round(float(precip.mean()), 4),
            "mediana": float(precip.median()),
            "maximo": float(precip.max()),
            "minimo": float(precip.min()),
        }
        perfil["clima"]["periodo_com_clima_real"] = {
            "inicio": str(df_gold.loc[com_clima, "semana_epi_data_inicio"].min()),
            "fim": str(df_gold.loc[com_clima, "semana_epi_data_fim"].max()),
        }

    return perfil


def calcular_cobertura_temporal(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (ano_epi, semana_epi) com: casos totais, quantos bairros
    tiveram caso, e quantas linhas tiveram clima real — base das
    visualizações de cobertura/série temporal."""
    agrupado = (
        df_gold.groupby(["ano_epidemiologico", "semana_epidemiologica"])
        .agg(
            semana_epi_data_inicio=("semana_epi_data_inicio", "first"),
            casos=("casos", "sum"),
            bairros_com_caso=("casos", lambda s: int((s > 0).sum())),
            linhas_com_clima_real=(
                "dias_com_dado_valido_semana",
                lambda s: int((s.fillna(0) > 0).sum()),
            ),
            precipitacao_media_mm=("precipitacao_total_semana_mm", "mean"),
        )
        .reset_index()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
    )
    return agrupado


def calcular_metricas_por_bairro(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por bairro com totais epidemiológicos — base do mapa
    coroplético."""
    return (
        df_gold.groupby(["codigo_bairro", "nome_bairro"])
        .agg(
            casos_total=("casos", "sum"),
            area_km2=("area_km2", "first"),
            semanas_com_caso=("casos", lambda s: int((s > 0).sum())),
            fonte_clima=("fonte_clima", "first"),
            distancia_estacao_km=("distancia_estacao_km", "first"),
        )
        .reset_index()
        .sort_values("casos_total", ascending=False)
    )
