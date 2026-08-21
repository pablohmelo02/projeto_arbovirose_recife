import numpy as np
import pandas as pd

from src.ml.target import calcular_estado_alto_risco
from src.ml.target_incidencia import (
    agregar_semanal_agravo_com_populacao,
    calcular_estado_alto_risco_incidencia,
)


def _semanal(bairro: str, ano_semana_casos_pop: list[tuple[int, int, int, int]]) -> pd.DataFrame:
    linhas = [
        {
            "codigo_bairro": bairro,
            "ano_epidemiologico": ano,
            "semana_epidemiologica": semana,
            "casos": casos,
            "populacao_bairro_ano": pop,
            "incidencia_100k": 100000 * casos / pop,
        }
        for ano, semana, casos, pop in ano_semana_casos_pop
    ]
    return pd.DataFrame(linhas)


def test_wrapper_reproduz_algoritmo_original_quando_coluna_e_a_mesma_serie():
    """Chamar o wrapper com `coluna_valor='casos'` deve produzir exatamente
    os mesmos valores (renomeados) que `calcular_estado_alto_risco` direto
    -- prova de que a substituição de coluna não altera o algoritmo."""
    dados = [(ano, semana, ano % 5 + semana % 3, 10000) for ano in range(2013, 2020) for semana in range(1, 20)]
    df = _semanal("X", dados)

    original = calcular_estado_alto_risco(df)
    via_wrapper = calcular_estado_alto_risco_incidencia(df, coluna_valor="casos")

    np.testing.assert_array_equal(
        original["estado_alto_risco"].to_numpy(), via_wrapper["estado_alto_risco_incidencia"].to_numpy()
    )
    np.testing.assert_array_equal(
        original["limiar_historico_local"].to_numpy(), via_wrapper["limiar_historico_local_incidencia"].to_numpy()
    )
    assert list(original["tipo_limiar"]) == list(via_wrapper["tipo_limiar_incidencia"])


def test_wrapper_nao_sobrescreve_colunas_baseadas_em_casos():
    dados = [(ano, semana, ano % 5 + semana % 3, 10000) for ano in range(2013, 2020) for semana in range(1, 20)]
    df = _semanal("X", dados)

    com_estado_casos = calcular_estado_alto_risco(df)
    com_estado_incidencia = calcular_estado_alto_risco_incidencia(com_estado_casos, coluna_valor="incidencia_100k")

    # as colunas baseadas em casos (calculadas antes) devem estar intactas
    np.testing.assert_array_equal(
        com_estado_casos["estado_alto_risco"].to_numpy(), com_estado_incidencia["estado_alto_risco"].to_numpy()
    )
    assert "estado_alto_risco_incidencia" in com_estado_incidencia.columns
    assert "estado_alto_risco" in com_estado_incidencia.columns


def test_wrapper_usa_incidencia_nao_casos_quando_escalas_diferem():
    """Bairro pequeno (população baixa) com poucos casos absolutos mas
    incidência alta deve ser marcado como alto risco em incidência mesmo
    quando o correspondente casos-based não marcaria."""
    # historico estavel de 1 caso/semana com populacao MUITO maior nos anos recentes
    # (bairro criou uma anomalia de incidencia sem grande anomalia de casos absolutos)
    dados = []
    for ano in range(2013, 2020):
        for semana in range(8, 14):
            dados.append((ano, semana, 1, 100000))  # incidencia = 1.0/100k
    dados.append((2020, 10, 3, 100000))  # incidencia = 3.0/100k -- 3x o normal, mas so 3 casos absolutos
    df = _semanal("Y", dados)

    com_estado_casos = calcular_estado_alto_risco(df)
    resultado = calcular_estado_alto_risco_incidencia(com_estado_casos, coluna_valor="incidencia_100k")
    linha_pico = resultado[(resultado["ano_epidemiologico"] == 2020) & (resultado["semana_epidemiologica"] == 10)]
    assert linha_pico["estado_alto_risco_incidencia"].iloc[0] == 1.0


def test_limiar_incidencia_nao_usa_anos_futuros():
    dados = [(ano, semana, ano % 4 + 1, 10000) for ano in range(2013, 2020) for semana in range(1, 53)]
    df = _semanal("X", dados)

    resultado_original = calcular_estado_alto_risco_incidencia(df, coluna_valor="incidencia_100k")
    limiar_original = resultado_original.loc[
        (resultado_original["ano_epidemiologico"] == 2016) & (resultado_original["semana_epidemiologica"] == 10),
        "limiar_historico_local_incidencia",
    ].iloc[0]

    df_alterado = df.copy()
    df_alterado.loc[df_alterado["ano_epidemiologico"] >= 2016, "incidencia_100k"] = 99999.0
    resultado_alterado = calcular_estado_alto_risco_incidencia(df_alterado, coluna_valor="incidencia_100k")
    limiar_alterado = resultado_alterado.loc[
        (resultado_alterado["ano_epidemiologico"] == 2016) & (resultado_alterado["semana_epidemiologica"] == 10),
        "limiar_historico_local_incidencia",
    ].iloc[0]

    assert limiar_original == limiar_alterado


def _gold_minima_com_populacao(bairros: tuple[str, ...] = ("1", "2")) -> pd.DataFrame:
    linhas = []
    for bairro in bairros:
        for ano in range(2013, 2015):
            for semana in range(1, 4):
                linhas.append(
                    {
                        "codigo_bairro": bairro,
                        "nome_bairro": f"BAIRRO {bairro}",
                        "agravo": "DENGUE",
                        "ano_epidemiologico": ano,
                        "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": pd.Timestamp(f"{ano}-01-01") + pd.Timedelta(weeks=semana - 1),
                        "semana_epi_data_fim": pd.Timestamp(f"{ano}-01-07") + pd.Timedelta(weeks=semana - 1),
                        "casos": 1,
                        "area_km2": 1.0,
                        "codigo_rpa": "1",
                        "codigo_microrregiao": "1",
                        "centroide_lat": -8.0,
                        "centroide_lon": -34.9,
                        "populacao_bairro_ano": 10000,
                        "tipo_populacao": "CENSO_OBSERVADO",
                        "densidade_populacional_hab_km2": 10000.0,
                        "incidencia_100k": 10.0,
                        "incidencia_4s_100k": 10.0,
                        "incidencia_8s_100k": 10.0,
                        "incidencia_12s_100k": 10.0,
                        "incidencia_anual_100k": 10.0,
                    }
                )
    return pd.DataFrame(linhas)


def test_agregar_semanal_agravo_com_populacao_preserva_casos_e_traz_populacao():
    df_gold = _gold_minima_com_populacao()
    resultado = agregar_semanal_agravo_com_populacao(df_gold, "DENGUE")
    assert "casos" in resultado.columns
    assert "populacao_bairro_ano" in resultado.columns
    assert "incidencia_100k" in resultado.columns
    assert (resultado["casos"] == 1).all()
    assert (resultado["populacao_bairro_ano"] == 10000).all()


def test_agregar_semanal_agravo_com_populacao_levanta_erro_sem_colunas_populacao():
    df_gold = _gold_minima_com_populacao().drop(columns=["populacao_bairro_ano"])
    try:
        agregar_semanal_agravo_com_populacao(df_gold, "DENGUE")
        assert False, "deveria levantar ValueError"
    except ValueError as exc:
        assert "populacao_bairro_ano" in str(exc)


def test_bairro_com_populacao_ausente_em_um_ano_gera_incidencia_nan_nunca_erro():
    """Um bairro sem `populacao_bairro_ano` num ano específico (não deveria
    ocorrer para os 94 bairros oficiais 2010-2025, mas o código nunca deve
    quebrar nem inventar incidência 0/infinita nesse caso)."""
    df_gold = _gold_minima_com_populacao(bairros=("1",))
    df_gold.loc[df_gold["ano_epidemiologico"] == 2014, "populacao_bairro_ano"] = None
    df_gold.loc[df_gold["ano_epidemiologico"] == 2014, "incidencia_100k"] = None

    df_sem = agregar_semanal_agravo_com_populacao(df_gold, "DENGUE")
    resultado = calcular_estado_alto_risco_incidencia(df_sem, coluna_valor="incidencia_100k")

    linhas_2014 = resultado[resultado["ano_epidemiologico"] == 2014]
    assert linhas_2014["incidencia_100k"].isna().all()
    # NaN na serie de entrada nao pode gerar excecao nem virar 0/1 arbitrario
    assert linhas_2014["tipo_limiar_incidencia"].isin(["indefinido", "sazonal", "geral"]).all()
