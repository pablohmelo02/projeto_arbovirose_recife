"""Item 20 do pedido: observado x projetado nunca depende só de cor.
`grafico_projecao_com_banda` (dashboard/components/graficos_produto.py)
precisa marcar o traço projetado com `dash` e nomear as duas séries em
texto explícito ("Observado"/"Projetado")."""
from __future__ import annotations

import pandas as pd
import pytest

from dashboard.components.graficos_produto import grafico_projecao_com_banda


@pytest.fixture
def series():
    observado = pd.DataFrame(
        {
            "semana_epi_data_inicio": pd.date_range("2024-01-01", periods=5, freq="7D"),
            "casos": [10, 12, 15, 11, 9],
        }
    )
    projetado = pd.DataFrame(
        {
            "semana_epi_data_inicio": pd.date_range("2026-01-01", periods=5, freq="7D"),
            "casos": [11, 13, 14, 10, 8],
            "banda_80_inferior": [5, 6, 7, 5, 4],
            "banda_80_superior": [17, 19, 20, 16, 13],
            "banda_95_inferior": [2, 3, 3, 2, 1],
            "banda_95_superior": [22, 24, 25, 21, 18],
        }
    )
    return observado, projetado


def test_traco_projetado_usa_linha_tracejada(series):
    observado, projetado = series
    fig = grafico_projecao_com_banda(observado, projetado, "teste")
    tracos_projetados = [t for t in fig.data if t.name == "Projetado 2026"]
    assert len(tracos_projetados) == 1
    assert tracos_projetados[0].line.dash == "dash"


def test_traco_observado_usa_linha_solida(series):
    observado, projetado = series
    fig = grafico_projecao_com_banda(observado, projetado, "teste")
    tracos_observados = [t for t in fig.data if t.name == "Observado (2013-2025)"]
    assert len(tracos_observados) == 1
    assert tracos_observados[0].line.dash in (None, "solid")


def test_nomes_das_series_sao_explicitos_em_texto():
    """A diferenciação não pode depender só de cor -- os nomes das séries
    (usados na legenda/hover) precisam dizer "observado"/"projetado"."""
    nomes_esperados = {"Observado (2013-2025)", "Projetado 2026", "Intervalo 80%", "Intervalo 95%"}
    observado = pd.DataFrame({"semana_epi_data_inicio": pd.date_range("2024-01-01", periods=2), "casos": [1, 2]})
    projetado = pd.DataFrame(
        {
            "semana_epi_data_inicio": pd.date_range("2026-01-01", periods=2),
            "casos": [1, 2],
            "banda_80_inferior": [0, 0],
            "banda_80_superior": [2, 3],
            "banda_95_inferior": [0, 0],
            "banda_95_superior": [3, 4],
        }
    )
    fig = grafico_projecao_com_banda(observado, projetado, "teste")
    nomes_presentes = {t.name for t in fig.data if t.name}
    assert nomes_esperados <= nomes_presentes


def test_banda_95_e_mais_larga_ou_igual_a_banda_80(series):
    observado, projetado = series
    assert (projetado["banda_95_superior"] - projetado["banda_95_inferior"] >=
            projetado["banda_80_superior"] - projetado["banda_80_inferior"]).all()
