"""Gráficos das páginas reorganizadas do produto (situação, histórico,
priorização observada e módulo experimental).

Separado de `graficos.py` (que segue servindo as páginas de EDA e clima)
apenas para manter cada arquivo legível — a paleta, o layout padrão e a
regra "aqui só se desenha, nunca se calcula" são os mesmos.

Nenhuma função aqui usa escala verde-amarelo-vermelho de risco: a validação
estatística não sustenta categorizar risco, e cor de semáforo comunicaria
exatamente essa categorização.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.components.graficos import (
    COR_ATENCAO,
    COR_INSTITUCIONAL,
    COR_INSTITUCIONAL_CLARA,
    COR_NEUTRA,
    CORES_AGRAVOS,
    LAYOUT_PADRAO,
    TEMA_COR_SEQUENCIAL,
)


def grafico_serie_com_media_movel(
    serie: pd.DataFrame, titulo: str, cor: str = CORES_AGRAVOS["DENGUE"], janela: int = 4
) -> go.Figure:
    """Série semanal observada + média móvel de `janela` semanas.

    A média móvel existe para tornar a tendência legível sem esconder o dado
    bruto: as barras são o observado, a linha é a suavização — as duas
    aparecem juntas, nunca a suavização sozinha."""
    df = serie.copy()
    df["data"] = pd.to_datetime(df["semana_epi_data_inicio"])
    df = df.sort_values("data")
    df["media_movel"] = df["casos"].rolling(window=janela, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=df["data"], y=df["casos"], name="Casos por semana", marker_color=cor, opacity=0.55)
    )
    fig.add_trace(
        go.Scatter(
            x=df["data"], y=df["media_movel"], name=f"Média móvel ({janela} semanas)",
            line=dict(color=COR_INSTITUCIONAL, width=2.4),
        )
    )
    fig.update_layout(
        **LAYOUT_PADRAO, title_text=titulo, xaxis_title="Semana epidemiológica", yaxis_title="Casos notificados"
    )
    return fig


def grafico_comparacao_sazonal(
    por_ano_semana: pd.DataFrame, ano_destaque: int, titulo: str
) -> go.Figure:
    """Curvas de casos por semana epidemiológica, um traço por ano, com o
    ano em destaque sobreposto. É a leitura sazonal que um gestor pede:
    "estamos acima ou abaixo dos anos anteriores nesta época?"."""
    fig = go.Figure()
    for ano, sub in por_ano_semana.groupby("ano_epidemiologico", observed=True):
        destaque = int(ano) == int(ano_destaque)
        fig.add_trace(
            go.Scatter(
                x=sub["semana_epidemiologica"], y=sub["casos"], name=str(int(ano)),
                line=dict(
                    color=CORES_AGRAVOS["DENGUE"] if destaque else COR_NEUTRA,
                    width=3 if destaque else 1.1,
                ),
                opacity=1.0 if destaque else 0.5,
                hovertemplate=f"{int(ano)} · SE %{{x}} · %{{y}} casos<extra></extra>",
            )
        )
    fig.update_layout(
        **LAYOUT_PADRAO, title_text=titulo,
        xaxis_title="Semana epidemiológica (1–53)", yaxis_title="Casos notificados",
    )
    return fig


def grafico_casos_por_ano(por_ano: pd.DataFrame, titulo: str) -> go.Figure:
    """Total anual, com o valor impresso em cada barra (leitura sem tooltip)."""
    fig = px.bar(
        por_ano, x="ano_epidemiologico", y="casos", text="casos",
        color_discrete_sequence=[COR_INSTITUCIONAL_CLARA], title=titulo,
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", cliponaxis=False)
    fig.update_layout(**LAYOUT_PADRAO, xaxis_title="Ano epidemiológico", yaxis_title="Casos notificados")
    fig.update_xaxes(type="category")
    return fig


def grafico_prioridade_observada(tabela: pd.DataFrame, top_n: int, titulo: str) -> go.Figure:
    """Barras horizontais dos bairros com mais casos recentes, anotadas com
    a razão contra o próprio histórico. Duas informações, um gráfico — sem
    depender de cor para diferenciá-las."""
    sub = tabela.head(top_n).sort_values("casos_janela_recente")
    rotulos = [
        f"{nome.title()} — {razao:.1f}× o histórico"
        for nome, razao in zip(sub["nome_bairro"], sub["razao_historico"].fillna(0))
    ]
    fig = go.Figure(
        go.Bar(
            x=sub["casos_janela_recente"], y=sub["nome_bairro"].str.title(), orientation="h",
            marker_color=COR_INSTITUCIONAL_CLARA, text=rotulos, textposition="auto",
            hovertemplate="%{y}<br>%{x} casos nas últimas semanas<extra></extra>",
        )
    )
    fig.update_layout(
        **LAYOUT_PADRAO, title_text=titulo, xaxis_title="Casos nas últimas semanas", yaxis_title="",
        height=max(320, 30 * len(sub) + 110),
    )
    return fig


def grafico_dispersao_prioridade(tabela: pd.DataFrame, titulo: str) -> go.Figure:
    """Volume recente (x) × razão contra o histórico local (y).

    Separa duas perguntas que se confundem: "onde há mais casos" e "onde há
    mais casos do que o normal para esta época". A linha em y=1 é o próprio
    histórico do bairro."""
    df = tabela.dropna(subset=["razao_historico"]).copy()
    fig = px.scatter(
        df, x="casos_janela_recente", y="razao_historico",
        hover_name=df["nome_bairro"].str.title(),
        hover_data={"codigo_rpa": True, "tendencia": True, "casos_semana": True},
        color_discrete_sequence=[COR_INSTITUCIONAL], title=titulo,
    )
    fig.add_hline(
        y=1.0, line_dash="dash", line_color=COR_ATENCAO,
        annotation_text="igual à média histórica do bairro", annotation_position="top left",
    )
    fig.update_layout(
        **LAYOUT_PADRAO,
        xaxis_title="Casos nas últimas semanas", yaxis_title="Razão contra o histórico do bairro",
    )
    return fig


def grafico_mapa_metricas(
    df_metrica: pd.DataFrame,
    geojson: dict[str, Any],
    coluna_valor: str,
    rotulo_valor: str,
    titulo: str,
    hover_extra: Optional[list[str]] = None,
) -> go.Figure:
    """Mapa coroplético com rótulo de métrica explícito na barra de cor."""
    fig = px.choropleth(
        df_metrica,
        geojson=geojson,
        locations="codigo_bairro",
        featureidkey="properties.codigo_bairro",
        color=coluna_valor,
        color_continuous_scale=TEMA_COR_SEQUENCIAL,
        hover_name="nome_bairro",
        hover_data={c: True for c in (hover_extra or [])},
        labels={coluna_valor: rotulo_valor},
        title=titulo,
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(**LAYOUT_PADRAO, height=560, coloraxis_colorbar=dict(title_text=rotulo_valor))
    return fig


def grafico_recall_por_k(recall_ic: pd.DataFrame, titulo: str) -> go.Figure:
    """Recall@K do modelo × baselines, com IC 95 %."""
    fig = go.Figure()
    estilos = {
        "modelo": dict(color=CORES_AGRAVOS["DENGUE"], width=3),
        "casos_atuais": dict(color=COR_NEUTRA, width=1.6, dash="dot"),
        "crescimento_recente": dict(color=COR_INSTITUCIONAL, width=1.6, dash="dash"),
        "razao_historica_local": dict(color=COR_ATENCAO, width=1.6, dash="dashdot"),
    }
    rotulos = {
        "modelo": "Modelo experimental",
        "casos_atuais": "Regra simples: casos atuais",
        "crescimento_recente": "Regra simples: crescimento recente",
        "razao_historica_local": "Regra simples: razão histórica local",
    }
    for metodo in recall_ic["metodo"].unique():
        sub = recall_ic[recall_ic["metodo"] == metodo].sort_values("k")
        fig.add_trace(
            go.Scatter(
                x=sub["k"], y=sub["observado"] * 100, mode="lines+markers",
                name=rotulos.get(metodo, metodo), line=estilos.get(metodo, {}),
                error_y=dict(
                    type="data", symmetric=False,
                    array=(sub["ic_alto"] - sub["observado"]) * 100,
                    arrayminus=(sub["observado"] - sub["ic_baixo"]) * 100,
                ),
            )
        )
    fig.update_layout(
        **LAYOUT_PADRAO, title_text=titulo,
        xaxis_title="K — bairros priorizados por semana",
        yaxis_title="% de episódios antecipados",
    )
    fig.update_xaxes(tickvals=sorted(recall_ic["k"].unique()))
    return fig


def grafico_delta_por_k(delta: pd.DataFrame, titulo: str) -> go.Figure:
    """Ganho do modelo sobre a melhor regra simples, por K.

    Barras com IC; a distinção "conclusivo × inconclusivo" é marcada por
    **padrão de preenchimento e rótulo textual**, não só por cor."""
    conclusivo = [
        (lo > 0 or hi < 0) for lo, hi in zip(delta["ic_baixo"], delta["ic_alto"])
    ]
    fig = go.Figure(
        go.Bar(
            x=delta["k"].astype(str), y=delta["observado"] * 100,
            marker=dict(
                color=[COR_INSTITUCIONAL if c else "#ffffff" for c in conclusivo],
                line=dict(color=COR_INSTITUCIONAL, width=1.8),
                pattern=dict(shape=["" if c else "/" for c in conclusivo]),
            ),
            text=[
                f"{v * 100:+.1f} pp<br>{'conclusivo' if c else 'inconclusivo'}"
                for v, c in zip(delta["observado"], conclusivo)
            ],
            textposition="outside",
            hovertemplate="K=%{x}<br>%{y:.2f} pontos percentuais<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color="#8fa3b5")
    fig.update_layout(
        **LAYOUT_PADRAO, title_text=titulo,
        xaxis_title="K — bairros priorizados por semana",
        yaxis_title="Ganho sobre a melhor regra simples (pontos percentuais)",
    )
    return fig


def grafico_lead_time(contagem: pd.Series, titulo: str) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=[f"{int(v)} semana(s)" for v in contagem.index], y=contagem.to_numpy(),
            marker_color=COR_INSTITUCIONAL_CLARA, text=contagem.to_numpy(), textposition="outside",
        )
    )
    fig.update_layout(
        **LAYOUT_PADRAO, title_text=titulo,
        xaxis_title="Antecedência em relação ao início observado", yaxis_title="Episódios",
    )
    return fig


def grafico_backtest_bairro(
    historico: pd.DataFrame, ranking_na_semana: int, nome_bairro: str, semana_rotulo: str
) -> go.Figure:
    """Para um bairro no backtest: casos observados por semana, com a semana
    de decisão marcada e a janela de desfecho (t+1..t+3) sombreada."""
    df = historico.sort_values("ordem")
    fig = make_subplots(specs=[[{"secondary_y": False}]])
    fig.add_trace(
        go.Bar(
            x=df["rotulo_semana"], y=df["casos"], name="Casos observados",
            marker_color=[
                CORES_AGRAVOS["DENGUE"] if m == "decisao" else
                (COR_ATENCAO if m == "desfecho" else COR_NEUTRA)
                for m in df["momento"]
            ],
        )
    )
    fig.update_layout(
        **LAYOUT_PADRAO,
        title_text=(
            f"{nome_bairro.title()} — posição {ranking_na_semana}º no ranking de {semana_rotulo}"
        ),
        xaxis_title="Semana epidemiológica", yaxis_title="Casos notificados",
    )
    fig.add_annotation(
        text="Cinza: antes da decisão · Vermelho: semana da decisão · Âmbar: janela de desfecho (t+1 a t+3)",
        xref="paper", yref="paper", x=0, y=1.13, showarrow=False,
        font=dict(size=11, color="#5b6b7b"),
    )
    return fig


def grafico_cobertura_dupla(tabela: pd.DataFrame, titulo: str) -> go.Figure:
    """Cobertura climática por ano: estação × grade, lado a lado.

    Torna visível de imediato que a reanálise cobre todo o período e a rede
    de estações não — e que são coisas diferentes."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=tabela["ano_epidemiologico"].astype(str), y=tabela["pct_com_grade"],
            name="Reanálise em grade", marker_color=COR_INSTITUCIONAL,
        )
    )
    fig.add_trace(
        go.Bar(
            x=tabela["ano_epidemiologico"].astype(str), y=tabela["pct_com_estacao"],
            name="Estações físicas (CEMADEN)", marker_color=COR_ATENCAO,
        )
    )
    fig.update_layout(
        **LAYOUT_PADRAO, barmode="group", title_text=titulo,
        xaxis_title="Ano epidemiológico", yaxis_title="% de bairro × semana com dado",
    )
    fig.update_yaxes(range=[0, 105])
    return fig
