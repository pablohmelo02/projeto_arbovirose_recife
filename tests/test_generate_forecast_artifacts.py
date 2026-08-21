"""Montagem do artefato de forecast consumido pelo dashboard (item 19-20
do pedido): observado e projetado precisam poder ser concatenados numa
única tabela com tipos de coluna homogêneos (Parquet/pyarrow não aceita
misturar `datetime.date` com `Timestamp` na mesma coluna — bug real
encontrado ao rodar a geração contra a Gold real, coberto aqui)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.forecast.dataset import construir_serie_semanal
from src.forecast.projecao_2026 import projetar_agravo
from src.generate_forecast_artifacts import (
    COLUNAS_ARTEFATO,
    _linhas_observadas,
    _linhas_projetadas,
    _metadados_agravo,
)


def _gold_sintetica() -> pd.DataFrame:
    rng = np.random.RandomState(3)
    linhas = []
    for i_ano in range(7):
        ano = 2019 + i_ano
        for semana in range(1, 53):
            sazonal = 10 * np.sin(2 * np.pi * semana / 52) + 15
            casos = max(0, int(round(sazonal + rng.normal(0, 1.0))))
            linhas.append(
                {
                    "codigo_bairro": "1",
                    "agravo": "DENGUE",
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "semana_epi_data_inicio": pd.Timestamp(f"{ano}-01-01") + pd.Timedelta(weeks=semana - 1),
                    "casos": casos,
                    "populacao_bairro_ano": 100_000.0,
                }
            )
    return pd.DataFrame(linhas)


def test_linhas_observadas_e_projetadas_tem_as_mesmas_colunas():
    gold = _gold_sintetica()
    serie = construir_serie_semanal(gold, "DENGUE")
    resultado = projetar_agravo(gold, "DENGUE")

    observadas = _linhas_observadas(serie, "DENGUE")
    projetadas = _linhas_projetadas(resultado["projecao_2026"], "DENGUE")

    assert list(observadas.columns) == list(COLUNAS_ARTEFATO)
    assert list(projetadas.columns) == list(COLUNAS_ARTEFATO)
    assert observadas["is_observado"].all()
    assert not projetadas["is_observado"].any()


def test_concatenar_observado_e_projetado_produz_coluna_de_data_homogenea():
    """Regressão do bug real: `semana_epi_data_inicio` observado vinha como
    `Timestamp` da Gold e projetado como `datetime.date` do calendário
    epidemiológico -- concatenados, a coluna ficava `object` com os dois
    tipos misturados e o Parquet (`pyarrow`) recusava a escrita."""
    gold = _gold_sintetica()
    serie = construir_serie_semanal(gold, "DENGUE")
    resultado = projetar_agravo(gold, "DENGUE")

    artefato = pd.concat(
        [_linhas_observadas(serie, "DENGUE"), _linhas_projetadas(resultado["projecao_2026"], "DENGUE")],
        ignore_index=True,
    )
    tipos = artefato["semana_epi_data_inicio"].map(type).unique()
    assert len(tipos) == 1, f"tipos mistos na coluna de data: {tipos}"
    assert pd.api.types.is_datetime64_any_dtype(pd.to_datetime(artefato["semana_epi_data_inicio"]))


def test_metadados_agravo_indisponivel():
    metadados = _metadados_agravo({"disponivel": False, "motivo": "sem histórico"})
    assert metadados == {"disponivel": False, "motivo": "sem histórico"}


def test_metadados_agravo_disponivel_marca_incidencia_2026_indisponivel():
    gold = _gold_sintetica()
    resultado = projetar_agravo(gold, "DENGUE")
    metadados = _metadados_agravo(resultado)
    assert metadados["disponivel"] is True
    assert metadados["incidencia_2026_disponivel"] is False


def test_metadados_agravo_tem_modelo_escolhido_e_pico():
    gold = _gold_sintetica()
    resultado = projetar_agravo(gold, "DENGUE")
    metadados = _metadados_agravo(resultado)
    assert isinstance(metadados["modelo_escolhido"], str)
    assert "semana_epidemiologica" in metadados["pico_projetado"]


def test_metadados_agravo_traz_cobertura_de_intervalo():
    gold = _gold_sintetica()
    resultado = projetar_agravo(gold, "DENGUE")
    metadados = _metadados_agravo(resultado)
    assert "cobertura_intervalo_media" in metadados
    assert "cobertura_intervalo_por_dobra" in metadados
    assert "cobertura_80_media" in metadados["cobertura_intervalo_media"]


def test_metadados_agravo_traz_backtest_por_dobra_do_modelo_escolhido_sem_erros_pontuais():
    gold = _gold_sintetica()
    resultado = projetar_agravo(gold, "DENGUE")
    metadados = _metadados_agravo(resultado)
    dobras = metadados["backtest_por_dobra_do_modelo_escolhido"]
    assert len(dobras) >= 1
    for dobra in dobras:
        assert "erros_pontuais" not in dobra
        assert "mae" in dobra
        assert "ano_alvo" in dobra
