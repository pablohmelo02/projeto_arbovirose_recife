from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.forecast.baselines import media_historica_semana, naive_sazonal, tendencia_sazonal


def _serie(anos: range, semanas_por_ano: int = 10, casos_por_semana=None) -> pd.DataFrame:
    """Série sintética com `indice_semana` contíguo, para os baselines."""
    linhas = []
    indice = 0
    for ano in anos:
        for semana in range(1, semanas_por_ano + 1):
            casos = casos_por_semana(ano, semana) if casos_por_semana else semana
            linhas.append(
                {
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "indice_semana": indice,
                    "casos": casos,
                }
            )
            indice += 1
    return pd.DataFrame(linhas)


def _semanas_alvo(ano: int, semanas_por_ano: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        {"ano_epidemiologico": ano, "semana_epidemiologica": range(1, semanas_por_ano + 1)}
    )


def test_naive_sazonal_repete_o_ultimo_ano_disponivel():
    treino = _serie(range(2020, 2023))  # casos = semana, igual em todo ano
    alvo = _semanas_alvo(2023)
    previsao = naive_sazonal(treino, alvo)
    ultimo_ano = treino[treino["ano_epidemiologico"] == 2022].sort_values("semana_epidemiologica")
    assert list(previsao) == list(ultimo_ano["casos"])


def test_naive_sazonal_nao_usa_dado_alem_do_treino():
    """Semana que so existe no "futuro" (ausente do treino) cai no
    preenchimento sem vazamento -- nunca lê nada alem de `serie_treino`."""
    treino = _serie(range(2020, 2022), semanas_por_ano=5)
    alvo = pd.DataFrame({"ano_epidemiologico": [2022], "semana_epidemiologica": [99]})
    previsao = naive_sazonal(treino, alvo)
    assert not previsao.isna().any()
    assert previsao.iloc[0] == pytest.approx(treino["casos"].mean())


def test_media_historica_semana_usa_media_de_todos_os_anos_do_treino():
    def casos(ano, semana):
        return semana * (1 if ano % 2 == 0 else 3)

    treino = _serie(range(2020, 2024), casos_por_semana=casos)  # 2020,2022 par; 2021,2023 impar
    alvo = _semanas_alvo(2024)
    previsao = media_historica_semana(treino, alvo)
    # semana 1: valores (1,3,1,3) -> media 2
    assert previsao.iloc[0] == pytest.approx(2.0)


def test_tendencia_sazonal_extrapola_tendencia_linear_positiva():
    def casos(ano, semana):
        indice_ano = ano - 2020
        return 10 + 5 * indice_ano  # tendencia clara, sem variacao sazonal

    treino = _serie(range(2020, 2024), semanas_por_ano=20, casos_por_semana=casos)
    alvo = _semanas_alvo(2024, semanas_por_ano=20)
    previsao = tendencia_sazonal(treino, alvo)
    # a previsao para 2024 deve continuar a tendencia de alta, ficando acima
    # do ultimo ano de treino (2023: 10 + 5*3 = 25)
    assert previsao.mean() > 25


def test_baselines_nunca_produzem_negativo():
    def casos(ano, semana):
        return max(0, semana - 8)  # muitas semanas com 0 casos

    treino = _serie(range(2020, 2023), semanas_por_ano=10, casos_por_semana=casos)
    alvo = _semanas_alvo(2023)
    for fn in (naive_sazonal, media_historica_semana, tendencia_sazonal):
        previsao = fn(treino, alvo)
        assert (previsao >= 0).all(), f"{fn.__name__} produziu previsão negativa"
