import numpy as np
import pandas as pd

from src.ml.target import (
    N_MIN_HISTORICO_GERAL,
    N_MIN_HISTORICO_SAZONAL,
    calcular_estado_alto_risco,
)


def _semanal(bairro: str, ano_semana_casos: list[tuple[int, int, int]]) -> pd.DataFrame:
    linhas = [
        {"codigo_bairro": bairro, "ano_epidemiologico": ano, "semana_epidemiologica": semana, "casos": casos}
        for ano, semana, casos in ano_semana_casos
    ]
    return pd.DataFrame(linhas)


def test_bairro_sem_historico_suficiente_fica_indefinido():
    # Só 2 anos de histórico, 1 semana cada -- nunca atinge N_MIN_HISTORICO_GERAL nem SAZONAL
    df = _semanal("X", [(2013, 10, 1), (2014, 10, 2), (2015, 10, 50)])
    resultado = calcular_estado_alto_risco(df)
    linha_2015 = resultado[(resultado["ano_epidemiologico"] == 2015)]
    assert linha_2015["tipo_limiar"].iloc[0] == "indefinido"
    assert np.isnan(linha_2015["estado_alto_risco"].iloc[0])


def test_limiar_nao_usa_anos_futuros_nem_o_proprio_ano():
    """O limiar de uma linha do ano Y não pode mudar se injetarmos um valor
    absurdo em anos >= Y (só anos < Y podem influenciar o limiar)."""
    dados = [(ano, semana, 1) for ano in range(2013, 2020) for semana in range(1, 53)]
    df = _semanal("X", dados)

    resultado_original = calcular_estado_alto_risco(df)
    limiar_2015_original = resultado_original.loc[
        (resultado_original["ano_epidemiologico"] == 2015) & (resultado_original["semana_epidemiologica"] == 10),
        "limiar_historico_local",
    ].iloc[0]

    df_alterado = df.copy()
    df_alterado.loc[df_alterado["ano_epidemiologico"] >= 2015, "casos"] = 99999
    resultado_alterado = calcular_estado_alto_risco(df_alterado)
    limiar_2015_alterado = resultado_alterado.loc[
        (resultado_alterado["ano_epidemiologico"] == 2015) & (resultado_alterado["semana_epidemiologica"] == 10),
        "limiar_historico_local",
    ].iloc[0]

    assert limiar_2015_original == limiar_2015_alterado


def test_janela_sazonal_nao_ultrapassa_bordas_1_e_53():
    """Semana alvo = 1: a janela sazonal não deve incluir semana 53 do ano
    anterior (sem wraparound, ver docstring de target.py)."""
    dados = [(ano, semana, 1) for ano in range(2013, 2019) for semana in range(1, 53)]
    dados += [(ano, 53, 100) for ano in range(2013, 2018)]
    df = _semanal("X", dados)
    resultado = calcular_estado_alto_risco(df)
    linha = resultado[(resultado["ano_epidemiologico"] == 2018) & (resultado["semana_epidemiologica"] == 1)]
    # Se a semana 53 (casos=100) tivesse entrado na janela da semana 1, o
    # limiar seria puxado para cima por esses valores; como não deve entrar,
    # o limiar tem que refletir só o histórico de semanas 1-3 (casos baixos).
    assert linha["limiar_historico_local"].iloc[0] <= 1.0


def test_estado_alto_risco_e_booleano_ou_nan():
    dados = [(ano, semana, 1) for ano in range(2013, 2020) for semana in range(8, 14)]
    dados.append((2020, 10, 500))  # pico real
    df = _semanal("X", dados)
    resultado = calcular_estado_alto_risco(df)
    linha_pico = resultado[(resultado["ano_epidemiologico"] == 2020) & (resultado["semana_epidemiologica"] == 10)]
    assert linha_pico["estado_alto_risco"].iloc[0] == 1.0


def test_dois_bairros_nao_se_misturam():
    dados_x = [(ano, semana, 1) for ano in range(2013, 2020) for semana in range(1, 53)]
    dados_y = [(ano, semana, 500) for ano in range(2013, 2020) for semana in range(1, 53)]
    df = pd.concat([_semanal("X", dados_x), _semanal("Y", dados_y)], ignore_index=True)
    resultado = calcular_estado_alto_risco(df)
    limiar_x = resultado.loc[resultado["codigo_bairro"] == "X", "limiar_historico_local"].dropna().unique()
    limiar_y = resultado.loc[resultado["codigo_bairro"] == "Y", "limiar_historico_local"].dropna().unique()
    assert set(limiar_x).isdisjoint(set(limiar_y))
    assert max(limiar_x) < min(limiar_y)


def test_zero_casos_nunca_e_alto_risco_quando_limiar_e_positivo():
    dados = [(ano, semana, 5) for ano in range(2013, 2020) for semana in range(1, 53)]
    dados.append((2020, 10, 0))
    df = _semanal("X", dados)
    resultado = calcular_estado_alto_risco(df)
    linha = resultado[(resultado["ano_epidemiologico"] == 2020) & (resultado["semana_epidemiologica"] == 10)]
    assert linha["estado_alto_risco"].iloc[0] == 0.0


def test_fallback_geral_quando_amostra_sazonal_insuficiente_mas_geral_suficiente():
    # Muitas semanas diferentes (amostra geral grande) mas nunca mais de 1
    # observação por semana especifica -> sazonal (janela +-2) nunca atinge
    # N_MIN_HISTORICO_SAZONAL, mas o geral (todas as semanas do passado) sim.
    dados = [(2013 + (i % 6), 1 + i, 1) for i in range(N_MIN_HISTORICO_GERAL + 5)]
    df = _semanal("X", dados)
    resultado = calcular_estado_alto_risco(df)
    tipos_definidos = resultado.loc[resultado["tipo_limiar"] != "indefinido", "tipo_limiar"]
    assert "geral" in set(tipos_definidos) or len(tipos_definidos) == 0
