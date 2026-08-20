"""Carregamento (com cache) do dataset estático de publicação do dashboard.

O dashboard **nunca** lê o Data Lake/MinIO diretamente — só os arquivos em
`dashboard/data/`, gerados por `python -m src.export_dashboard_dataset`
(ver docstring desse módulo para o porquê). Isso é o que permite a
aplicação funcionar também no Streamlit Community Cloud, sem depender de
infraestrutura local.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARQUIVO_GOLD = DATA_DIR / "gold_arboviroses_clima_bairro.parquet"
ARQUIVO_BAIRRO_GEO = DATA_DIR / "bairro_geo.geojson"
ARQUIVO_PROFILING = DATA_DIR / "_profiling_export.json"


class DatasetNaoEncontradoError(RuntimeError):
    """Levantado quando `dashboard/data/` não tem o dataset exportado."""


@st.cache_data(show_spinner="Carregando dados da Gold...")
def load_gold_data() -> pd.DataFrame:
    """Carrega `gold_arboviroses_clima_bairro.parquet` — a única fonte de
    dado analítico do dashboard (nenhum join/agregação central é refeito
    aqui, só leitura + normalização de tipos de data)."""
    if not ARQUIVO_GOLD.exists():
        raise DatasetNaoEncontradoError(
            f"'{ARQUIVO_GOLD}' não encontrado. Rode "
            "'python -m src.export_dashboard_dataset' antes de iniciar o dashboard."
        )
    df = pd.read_parquet(ARQUIVO_GOLD)
    for coluna in ("semana_epi_data_inicio", "semana_epi_data_fim"):
        if coluna in df.columns:
            df[coluna] = pd.to_datetime(df[coluna])
    return df


@st.cache_data(show_spinner="Carregando geometria dos bairros...")
def load_bairro_geojson() -> dict[str, Any]:
    """Carrega o GeoJSON dos 94 bairros (geometria oficial, sem dado
    epidemiológico embutido — o valor mostrado no mapa vem sempre de um
    join em memória com a Gold, feito pela própria página)."""
    if not ARQUIVO_BAIRRO_GEO.exists():
        raise DatasetNaoEncontradoError(
            f"'{ARQUIVO_BAIRRO_GEO}' não encontrado. Rode "
            "'python -m src.export_dashboard_dataset' antes de iniciar o dashboard."
        )
    return json.loads(ARQUIVO_BAIRRO_GEO.read_text(encoding="utf-8"))


@st.cache_data
def load_export_profiling() -> dict[str, Any]:
    """Profiling gravado na última exportação (linhas, colunas, tamanho) —
    exibido na página de Qualidade dos Dados para rastreabilidade de onde
    o dataset publicado veio."""
    if not ARQUIVO_PROFILING.exists():
        return {}
    return json.loads(ARQUIVO_PROFILING.read_text(encoding="utf-8"))
