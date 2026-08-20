"""Filtros globais da barra lateral — combináveis, reutilizados por todas
as páginas. Só decide *o que* filtrar; a filtragem em si é sempre feita por
`src/eda/filtros.py` (nunca reimplementada aqui)."""
from __future__ import annotations

from typing import Optional, TypedDict

import pandas as pd
import streamlit as st

from src.eda.schema_eda import AGRAVOS

OPCAO_TODOS_AGRAVOS = "Total de arboviroses (soma dos 3)"


class Filtros(TypedDict):
    agravo: Optional[str]
    ano_inicio: int
    ano_fim: int
    escopo: str  # "recife" | "rpa" | "bairro"
    codigo_rpa: Optional[str]
    codigo_bairro: Optional[str]


def renderizar_filtros(df_gold: pd.DataFrame, key_prefix: str, permitir_escopo_geografico: bool = True) -> Filtros:
    """Renderiza os widgets de filtro na sidebar e devolve as seleções.
    `key_prefix` evita colisão de `key` do widget quando a mesma barra de
    filtros aparece em páginas diferentes."""
    st.sidebar.header("Filtros")

    agravo_escolhido = st.sidebar.selectbox(
        "Agravo",
        options=[OPCAO_TODOS_AGRAVOS, *AGRAVOS],
        index=0,
        key=f"{key_prefix}_agravo",
        help="'Total de arboviroses' soma Dengue + Zika + Chikungunya — nunca é tratado como uma quarta doença.",
    )
    agravo = None if agravo_escolhido == OPCAO_TODOS_AGRAVOS else agravo_escolhido

    ano_min = int(df_gold["ano_epidemiologico"].min())
    ano_max = int(df_gold["ano_epidemiologico"].max())
    ano_inicio, ano_fim = st.sidebar.slider(
        "Ano epidemiológico",
        min_value=ano_min,
        max_value=ano_max,
        value=(ano_min, ano_max),
        key=f"{key_prefix}_anos",
    )

    codigo_rpa: Optional[str] = None
    codigo_bairro: Optional[str] = None
    escopo = "recife"

    if permitir_escopo_geografico:
        escopo_label = st.sidebar.radio(
            "Escopo geográfico",
            options=["Recife (todos os bairros)", "Uma RPA", "Um bairro"],
            key=f"{key_prefix}_escopo",
        )
        if escopo_label == "Uma RPA":
            escopo = "rpa"
            rpas = sorted(df_gold["codigo_rpa"].dropna().unique().tolist())
            codigo_rpa = st.sidebar.selectbox("RPA", options=rpas, key=f"{key_prefix}_rpa")
        elif escopo_label == "Um bairro":
            escopo = "bairro"
            bairros = (
                df_gold[["codigo_bairro", "nome_bairro"]]
                .drop_duplicates()
                .sort_values("nome_bairro")
            )
            nome_escolhido = st.sidebar.selectbox(
                "Bairro", options=bairros["nome_bairro"].tolist(), key=f"{key_prefix}_bairro"
            )
            codigo_bairro = bairros.loc[bairros["nome_bairro"] == nome_escolhido, "codigo_bairro"].iloc[0]

    return Filtros(
        agravo=agravo, ano_inicio=ano_inicio, ano_fim=ano_fim,
        escopo=escopo, codigo_rpa=codigo_rpa, codigo_bairro=codigo_bairro,
    )
