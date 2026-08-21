"""Todo construtor de gráfico do dashboard renderiza sem exceção.

Motivo de existir: um erro de assinatura do Plotly (por exemplo, passar
`title` e um layout que também define `title`) só aparece em tempo de
execução, dentro de uma página, e a fronteira de erro da UI o transforma
numa mensagem amigável — ou seja, **o painel continua "funcionando" com
gráficos faltando**. Este arquivo garante que a suíte pegue isso antes.

Nenhum teste aqui depende de Streamlit rodando, de rede ou dos artefatos
publicados: os DataFrames são sintéticos e mínimos.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import dashboard.components.graficos as G
import dashboard.components.graficos_produto as GP


# ---------------------------------------------------------------------------
# Fixtures sintéticas
# ---------------------------------------------------------------------------
@pytest.fixture
def serie_semanal() -> pd.DataFrame:
    inicios = pd.date_range("2024-01-07", periods=12, freq="7D")
    return pd.DataFrame(
        {
            "ano_epidemiologico": 2024,
            "semana_epidemiologica": range(2, 14),
            "semana_epi_data_inicio": inicios,
            "casos": [3, 5, 8, 13, 21, 18, 12, 9, 6, 4, 2, 1],
        }
    )


@pytest.fixture
def serie_por_agravo(serie_semanal: pd.DataFrame) -> pd.DataFrame:
    partes = []
    for agravo in ("DENGUE", "ZIKA", "CHIKUNGUNYA"):
        parte = serie_semanal.copy()
        parte["agravo"] = agravo
        partes.append(parte)
    return pd.concat(partes, ignore_index=True)


@pytest.fixture
def tabela_prioridade() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_bairro": ["1", "2", "3"],
            "nome_bairro": ["ALFA", "BETA", "GAMA"],
            "codigo_rpa": ["1", "2", "3"],
            "casos_semana": [4, 2, 0],
            "casos_janela_recente": [20, 11, 3],
            "casos_janela_anterior": [10, 12, 3],
            "variacao_pct": [100.0, -8.3, 0.0],
            "tendencia": ["em alta", "estável", "estável"],
            "media_historica": [2.0, 1.0, 0.5],
            "razao_historico": [2.22, 1.37, 0.86],
            "n_observacoes_historicas": [25, 25, 25],
        }
    )


@pytest.fixture
def geojson_minimo() -> dict:
    def quadrado(x: float, y: float) -> list:
        return [[[x, y], [x + 0.01, y], [x + 0.01, y + 0.01], [x, y + 0.01], [x, y]]]

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"codigo_bairro": codigo, "nome_bairro": nome},
                "geometry": {"type": "Polygon", "coordinates": quadrado(-34.9 + i * 0.02, -8.05)},
            }
            for i, (codigo, nome) in enumerate([("1", "ALFA"), ("2", "BETA"), ("3", "GAMA")])
        ],
    }


@pytest.fixture
def metricas_por_bairro() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_bairro": ["1", "2", "3"],
            "nome_bairro": ["ALFA", "BETA", "GAMA"],
            "casos": [30, 12, 4],
            "codigo_rpa": ["1", "2", "3"],
            "tendencia": ["em alta", "estável", "em queda"],
            "casos_janela_recente": [20, 11, 3],
        }
    )


@pytest.fixture
def recall_ic() -> pd.DataFrame:
    linhas = []
    for k in (5, 10, 15, 20):
        for metodo, base in (
            ("modelo", 0.25), ("casos_atuais", 0.11),
            ("crescimento_recente", 0.18), ("razao_historica_local", 0.20),
        ):
            observado = min(0.95, base + k / 100)
            linhas.append(
                {
                    "k": k, "metodo": metodo, "observado": observado, "n": 920,
                    "n_reamostragens": 2000,
                    "ic_baixo": observado - 0.03, "ic_alto": observado + 0.03,
                }
            )
    return pd.DataFrame(linhas)


@pytest.fixture
def delta_por_k() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "k": [5, 10, 15, 20],
            "melhor_baseline": ["razao_historica_local"] * 2 + ["crescimento_recente"] * 2,
            "observado": [0.06, 0.026, -0.007, -0.055],
            "n": [920] * 4,
            "n_reamostragens": [2000] * 4,
            "ic_baixo": [0.028, -0.008, -0.052, -0.101],
            "ic_alto": [0.091, 0.060, 0.039, -0.013],
        }
    )


# ---------------------------------------------------------------------------
# graficos.py
# ---------------------------------------------------------------------------
def test_serie_temporal_com_e_sem_agravo(serie_semanal, serie_por_agravo):
    assert G.grafico_serie_temporal(serie_por_agravo, "t").data
    assert G.grafico_serie_temporal(serie_semanal, "t", coluna_agravo=None).data


def test_titulo_do_grafico_e_preservado(serie_semanal):
    fig = G.grafico_serie_temporal(serie_semanal, "Titulo esperado", coluna_agravo=None)
    assert fig.layout.title.text == "Titulo esperado"


def test_sazonalidade_e_comparacao_de_agravos(serie_por_agravo):
    sazonalidade = pd.DataFrame(
        {
            "semana_epidemiologica": range(1, 6),
            "casos_totais": [10, 20, 30, 20, 10],
            "casos_media_por_ano": [2.0, 4.0, 6.0, 4.0, 2.0],
            "anos_observados": [5, 5, 5, 5, 4],
        }
    )
    assert G.grafico_sazonalidade(sazonalidade, "t").data
    comparado = serie_por_agravo.groupby(["ano_epidemiologico", "agravo"], as_index=False)["casos"].sum()
    assert G.grafico_comparacao_agravos(comparado).data


def test_ranking_e_mapa(metricas_por_bairro, geojson_minimo):
    ranking = metricas_por_bairro.assign(posicao=range(1, 4))
    assert G.grafico_ranking_bairros(ranking, "casos", "t").data
    assert G.grafico_mapa_coropletico(
        metricas_por_bairro, geojson_minimo, "casos", "t", hover_extra=["codigo_rpa"]
    ).data


def test_graficos_climaticos_de_estacao():
    grade = pd.DataFrame(
        {
            "ano_epidemiologico": [2024] * 4 + [2025] * 4,
            "semana_epidemiologica": [1, 2, 3, 4] * 2,
            "bairros_com_clima": [10, 20, 30, 40, 50, 60, 70, 80],
            "percentual_bairros_com_clima": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
        }
    )
    assert G.grafico_heatmap_cobertura(grade).data

    por_ano = pd.DataFrame(
        {"ano_epidemiologico": [2024, 2025], "percentual_bairros_com_clima_real": [26.7, 52.2]}
    )
    assert G.grafico_cobertura_por_ano(por_ano).data

    serie = pd.DataFrame(
        {
            "semana_epi_data_inicio": pd.date_range("2024-01-07", periods=4, freq="7D"),
            "precipitacao_media_mm": [10.0, 20.0, 5.0, 0.0],
            "bairros_considerados": [90, 90, 88, 80],
        }
    )
    assert G.grafico_precipitacao(serie).data


def test_graficos_de_correlacao():
    dispersao = pd.DataFrame(
        {
            "nome_bairro": ["ALFA"] * 40,
            "ano_epidemiologico": [2024] * 40,
            "semana_epidemiologica": list(range(1, 41)),
            "precipitacao_mm": np.linspace(0, 100, 40),
            "casos": np.linspace(0, 20, 40),
        }
    )
    assert G.grafico_dispersao_lag(dispersao, 28, "DENGUE").data

    lag = pd.DataFrame(
        {
            "janela_dias": [7, 14, 21, 28],
            "n_observacoes": [100, 100, 100, 100],
            "correlacao_pearson": [0.05, 0.07, 0.09, 0.11],
            "confiavel": [True, True, True, True],
        }
    )
    assert G.grafico_lag_correlacoes(lag, "DENGUE").data

    matriz = pd.DataFrame(
        np.array([[1.0, 0.2], [0.2, 1.0]]),
        columns=["casos", "chuva_7d_mm"], index=["casos", "chuva_7d_mm"],
    )
    assert G.grafico_matriz_correlacao(matriz, 500).data
    assert G.grafico_antes_depois(0.0, 6.11).data


# ---------------------------------------------------------------------------
# graficos_produto.py
# ---------------------------------------------------------------------------
def test_serie_com_media_movel_inclui_observado_e_suavizacao(serie_semanal):
    fig = GP.grafico_serie_com_media_movel(serie_semanal, "t")
    tipos = {trace.type for trace in fig.data}
    assert "bar" in tipos and "scatter" in tipos, "o observado e a média móvel devem aparecer juntos"


def test_comparacao_sazonal_destaca_um_ano():
    por_ano_semana = pd.DataFrame(
        {
            "ano_epidemiologico": [2023] * 5 + [2024] * 5,
            "semana_epidemiologica": list(range(1, 6)) * 2,
            "casos": [1, 2, 3, 2, 1, 5, 8, 12, 8, 5],
        }
    )
    fig = GP.grafico_comparacao_sazonal(por_ano_semana, 2024, "t")
    larguras = [trace.line.width for trace in fig.data]
    assert max(larguras) > min(larguras), "o ano em destaque deve ter traço mais grosso"


def test_casos_por_ano_e_prioridade(tabela_prioridade):
    por_ano = pd.DataFrame({"ano_epidemiologico": [2023, 2024], "casos": [100, 250]})
    assert GP.grafico_casos_por_ano(por_ano, "t").data
    assert GP.grafico_prioridade_observada(tabela_prioridade, 3, "t").data
    assert GP.grafico_dispersao_prioridade(tabela_prioridade, "t").data


def test_mapa_metricas_rotula_a_barra_de_cor(metricas_por_bairro, geojson_minimo):
    fig = GP.grafico_mapa_metricas(
        metricas_por_bairro, geojson_minimo, "casos", "Casos", "t", hover_extra=["codigo_rpa"]
    )
    assert fig.layout.coloraxis.colorbar.title.text == "Casos"


def test_recall_e_delta_por_k(recall_ic, delta_por_k):
    assert GP.grafico_recall_por_k(recall_ic, "t").data
    fig = GP.grafico_delta_por_k(delta_por_k, "t")
    rotulos = list(fig.data[0].text)
    assert any("conclusivo" in r for r in rotulos)
    assert any("inconclusivo" in r for r in rotulos), (
        "a distinção conclusivo/inconclusivo precisa estar no texto, não só na cor"
    )


def test_lead_time_e_cobertura_dupla():
    contagem = pd.Series([120, 90, 60, 30], index=[1.0, 2.0, 3.0, 4.0])
    assert GP.grafico_lead_time(contagem, "t").data

    cobertura = pd.DataFrame(
        {
            "ano_epidemiologico": [2023, 2024, 2025],
            "linhas": [100, 100, 100],
            "pct_com_grade": [100.0, 100.0, 100.0],
            "pct_com_estacao": [0.0, 26.7, 52.2],
        }
    )
    assert GP.grafico_cobertura_dupla(cobertura, "t").data


def test_backtest_de_um_bairro_marca_os_tres_momentos():
    historico = pd.DataFrame(
        {
            "ordem": range(8),
            "rotulo_semana": [f"SE {i:02d}/2024" for i in range(1, 9)],
            "casos": [0, 1, 2, 4, 6, 9, 12, 15],
            "momento": ["antes"] * 5 + ["decisao"] + ["desfecho"] * 2,
        }
    )
    fig = GP.grafico_backtest_bairro(historico, 3, "ALFA", "SE 06/2024")
    cores = set(fig.data[0].marker.color)
    assert len(cores) == 3, "antes, decisão e desfecho devem ser visualmente distintos"


def test_paleta_nao_usa_semaforo_de_risco():
    """Verde-amarelo-vermelho comunicaria categoria de risco, que a
    validação estatística não sustenta — a paleta não deve tê-la."""
    valores = {v.lower() for v in G.CORES_AGRAVOS.values()}
    verdes_proibidos = {"#27ae60", "#2ecc71", "#00b050", "green"}
    assert not (valores & verdes_proibidos)
