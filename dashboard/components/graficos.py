"""Construtores de gráficos Plotly reutilizados pelas páginas do dashboard.

Uma única biblioteca de gráfico/mapa (Plotly) para toda a aplicação — ver
decisão registrada em `CLAUDE.md` (não Folium/PyDeck em paralelo). Nenhuma
função aqui decide "o que" filtrar/agregar (isso é `src/eda/`) — só "como
desenhar" o que já foi calculado.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

TEMA_COR_SEQUENCIAL = "Blues"
TEMA_COR_DIVERGENTE = "RdBu_r"

# Paleta institucional (ver dashboard/components/tema.py): azul para
# estrutura, vermelho contido reservado à dengue, âmbar só para atenção.
COR_INSTITUCIONAL = "#1f4e79"
COR_INSTITUCIONAL_CLARA = "#2e6da4"
COR_ATENCAO = "#b9770e"
COR_NEUTRA = "#8fa3b5"
CORES_AGRAVOS = {
    "DENGUE": "#a93226",
    "ZIKA": "#6c5b8f",
    "CHIKUNGUNYA": "#b9770e",
    "TOTAL_ARBOVIROSES": "#1f4e79",
}

LAYOUT_PADRAO = dict(
    template="plotly_white",
    margin=dict(l=10, r=10, t=54, b=10),
    font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13, color="#1b2631"),
    title_font=dict(size=15),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hoverlabel=dict(font_size=13),
)


def grafico_serie_temporal(serie: pd.DataFrame, titulo: str, coluna_agravo: Optional[str] = "agravo") -> go.Figure:
    """Casos por semana epidemiológica ao longo do tempo — uma linha por
    agravo, se a coluna existir; senão, uma série única (Recife total ou
    já filtrado por agravo)."""
    df = serie.copy()
    df["data"] = pd.to_datetime(df["semana_epi_data_inicio"])
    if coluna_agravo and coluna_agravo in df.columns:
        fig = px.line(
            df, x="data", y="casos", color=coluna_agravo,
            color_discrete_map=CORES_AGRAVOS, title=titulo,
        )
    else:
        fig = px.line(df, x="data", y="casos", title=titulo)
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title="Semana epidemiológica", yaxis_title="Casos")
    return fig


def grafico_sazonalidade(sazonalidade: pd.DataFrame, titulo: str) -> go.Figure:
    """Casos médios por semana epidemiológica (1-53), com o número de anos
    observados disponível no tooltip — nunca esconde que semanas 53 têm
    menos anos de suporte que as demais."""
    fig = px.bar(
        sazonalidade, x="semana_epidemiologica", y="casos_media_por_ano",
        hover_data={"anos_observados": True, "casos_totais": True},
        title=titulo, color_discrete_sequence=[COR_INSTITUCIONAL_CLARA],
    )
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title="Semana epidemiológica", yaxis_title="Casos (média entre os anos observados)")
    return fig


def grafico_comparacao_agravos(comparado: pd.DataFrame) -> go.Figure:
    """Casos por ano, um subplot/linha por agravo (facetado, para não
    forçar Dengue/Zika/Chikungunya na mesma escala e prejudicar a
    leitura)."""
    fig = px.bar(
        comparado, x="ano_epidemiologico", y="casos", color="agravo",
        facet_row="agravo", color_discrete_map=CORES_AGRAVOS,
    )
    fig.update_yaxes(matches=None)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(**LAYOUT_PADRAO, showlegend=False, height=550)
    return fig


def grafico_ranking_bairros(ranking: pd.DataFrame, metrica: str, titulo: str) -> go.Figure:
    """Ranking em barras horizontais (nomes de bairro legíveis)."""
    ordenado = ranking.sort_values(metrica, ascending=True)
    fig = px.bar(
        ordenado, x=metrica, y="nome_bairro", orientation="h", title=titulo,
        color_discrete_sequence=[COR_INSTITUCIONAL_CLARA],
    )
    fig.update_layout(**LAYOUT_PADRAO, yaxis_title="", xaxis_title=metrica.capitalize())
    return fig


def grafico_mapa_coropletico(
    df_metrica: pd.DataFrame,
    geojson: dict[str, Any],
    coluna_valor: str,
    titulo: str,
    escala_cor: str = TEMA_COR_SEQUENCIAL,
    hover_extra: Optional[list[str]] = None,
) -> go.Figure:
    """Mapa coroplético dos 94 bairros via GeoJSON — sem token de mapbox
    (`fitbounds='locations'` usa a projeção geográfica nativa do Plotly)."""
    hover_data = {c: True for c in (hover_extra or [])}
    fig = px.choropleth(
        df_metrica,
        geojson=geojson,
        locations="codigo_bairro",
        featureidkey="properties.codigo_bairro",
        color=coluna_valor,
        color_continuous_scale=escala_cor,
        hover_name="nome_bairro",
        hover_data=hover_data,
        title=titulo,
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(**LAYOUT_PADRAO, height=600)
    return fig


def grafico_heatmap_cobertura(grade: pd.DataFrame) -> go.Figure:
    """Heatmap ano × semana epidemiológica do percentual de bairros com
    clima real — obrigatório para não escondermos que a disponibilidade
    climática não é homogênea no tempo."""
    pivot = grade.pivot(
        index="ano_epidemiologico", columns="semana_epidemiologica", values="percentual_bairros_com_clima"
    )
    fig = px.imshow(
        pivot, color_continuous_scale=TEMA_COR_SEQUENCIAL, aspect="auto",
        labels=dict(x="Semana epidemiológica", y="Ano epidemiológico", color="% bairros com clima real"),
    )
    fig.update_layout(**LAYOUT_PADRAO, height=max(250, 60 * pivot.shape[0]))
    return fig


def grafico_cobertura_por_ano(tabela: pd.DataFrame) -> go.Figure:
    fig = px.bar(
        tabela, x="ano_epidemiologico", y="percentual_bairros_com_clima_real",
        title="Bairros com clima real, por ano epidemiológico",
        color_discrete_sequence=[COR_INSTITUCIONAL_CLARA],
    )
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title="Ano epidemiológico", yaxis_title="% dos 94 bairros")
    fig.update_yaxes(range=[0, 100])
    return fig


def grafico_precipitacao(serie: pd.DataFrame) -> go.Figure:
    df = serie.copy()
    df["data"] = pd.to_datetime(df["semana_epi_data_inicio"])
    fig = px.bar(
        df, x="data", y="precipitacao_media_mm",
        hover_data={"bairros_considerados": True}, color_discrete_sequence=[COR_INSTITUCIONAL],
        title="Precipitação semanal real (média entre bairros com clima real na semana)",
    )
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title="Semana", yaxis_title="Precipitação média (mm)")
    return fig


def grafico_dispersao_lag(dispersao: pd.DataFrame, janela_dias: int, agravo: str) -> go.Figure:
    fig = px.scatter(
        dispersao, x="precipitacao_mm", y="casos", trendline="ols",
        hover_data=["nome_bairro", "ano_epidemiologico", "semana_epidemiologica"],
        title=f"Precipitação acumulada em {janela_dias} dias × casos de {agravo} (n={len(dispersao)})",
        color_discrete_sequence=[CORES_AGRAVOS["DENGUE"]],
    )
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title=f"Chuva acumulada {janela_dias}d (mm)", yaxis_title="Casos")
    return fig


def grafico_lag_correlacoes(tabela: pd.DataFrame, agravo: str) -> go.Figure:
    fig = px.bar(
        tabela, x="janela_dias", y="correlacao_pearson", color="confiavel",
        hover_data=["n_observacoes"],
        color_discrete_map={True: COR_INSTITUCIONAL_CLARA, False: COR_ATENCAO},
        title=f"Correlação (Pearson) casos × chuva acumulada, por janela de lag — {agravo}",
    )
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title="Janela de lag (dias)", yaxis_title="Correlação de Pearson")
    fig.update_xaxes(type="category")
    return fig


def grafico_matriz_correlacao(matriz: pd.DataFrame, n_obs: int) -> go.Figure:
    fig = px.imshow(
        matriz, color_continuous_scale=TEMA_COR_DIVERGENTE, zmin=-1, zmax=1, text_auto=".2f",
        title=f"Matriz de correlação exploratória (n = {n_obs} observações com clima real)",
    )
    fig.update_layout(**LAYOUT_PADRAO, height=500)
    return fig


def grafico_antes_depois(percentual_antes: float, percentual_depois: float) -> go.Figure:
    df = pd.DataFrame(
        {
            "momento": ["Antes do backfill CEMADEN", "Depois do backfill CEMADEN"],
            "percentual": [percentual_antes, percentual_depois],
        }
    )
    fig = px.bar(
        df, x="momento", y="percentual", color="momento",
        color_discrete_sequence=[COR_NEUTRA, COR_INSTITUCIONAL],
        title="% da Gold com clima real — antes × depois do backfill",
        text="percentual",
    )
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
    fig.update_layout(**LAYOUT_PADRAO, showlegend=False, yaxis_title="% linhas Gold com clima real", xaxis_title="")
    return fig
