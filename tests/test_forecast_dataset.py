from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.forecast.dataset import construir_serie_semanal


def _gold_sintetica(com_populacao: bool = True) -> pd.DataFrame:
    linhas = []
    for ano in (2023, 2024):
        for semana in range(1, 6):
            for bairro, pop in (("1", 100_000.0), ("2", 50_000.0)):
                for agravo, casos in (("DENGUE", 10 + semana), ("ZIKA", 2)):
                    linha = {
                        "codigo_bairro": bairro,
                        "agravo": agravo,
                        "ano_epidemiologico": ano,
                        "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": pd.Timestamp(f"{ano}-01-01") + pd.Timedelta(weeks=semana - 1),
                        "casos": casos,
                    }
                    if com_populacao:
                        linha["populacao_bairro_ano"] = pop
                    linhas.append(linha)
    return pd.DataFrame(linhas)


def test_construir_serie_semanal_soma_casos_de_todos_os_bairros():
    gold = _gold_sintetica()
    serie = construir_serie_semanal(gold, "DENGUE")
    linha = serie[(serie["ano_epidemiologico"] == 2023) & (serie["semana_epidemiologica"] == 1)].iloc[0]
    assert linha["casos"] == 11 + 11  # bairro 1 + bairro 2, mesma formula (10+semana)


def test_construir_serie_semanal_indice_contiguo_atravessa_virada_de_ano():
    gold = _gold_sintetica()
    serie = construir_serie_semanal(gold, "DENGUE")
    assert list(serie["indice_semana"]) == list(range(len(serie)))
    # a primeira semana de 2024 continua o indice da ultima semana de 2023
    assert serie["indice_semana"].is_monotonic_increasing


def test_construir_serie_semanal_incidencia_e_uma_unica_divisao():
    gold = _gold_sintetica()
    serie = construir_serie_semanal(gold, "DENGUE")
    linha = serie[(serie["ano_epidemiologico"] == 2023) & (serie["semana_epidemiologica"] == 1)].iloc[0]
    esperado = 22 / 150_000.0 * 100_000
    assert linha["incidencia_100k"] == pytest.approx(esperado)


def test_construir_serie_semanal_sem_populacao_incidencia_e_nan():
    gold = _gold_sintetica(com_populacao=False)
    serie = construir_serie_semanal(gold, "DENGUE")
    assert serie["incidencia_100k"].isna().all()


def test_construir_serie_semanal_agravo_invalido_levanta_erro():
    gold = _gold_sintetica()
    with pytest.raises(ValueError):
        construir_serie_semanal(gold, "MALARIA")


def test_construir_serie_semanal_dataframe_vazio_nao_quebra():
    serie = construir_serie_semanal(pd.DataFrame(columns=["agravo"]), "DENGUE")
    assert serie.empty
    assert list(serie.columns) == [
        "ano_epidemiologico", "semana_epidemiologica", "indice_semana",
        "semana_epi_data_inicio", "casos", "incidencia_100k",
    ]


def test_construir_serie_semanal_agravos_diferentes_nao_se_misturam():
    gold = _gold_sintetica()
    dengue = construir_serie_semanal(gold, "DENGUE")
    zika = construir_serie_semanal(gold, "ZIKA")
    assert not np.array_equal(dengue["casos"].to_numpy(), zika["casos"].to_numpy())
