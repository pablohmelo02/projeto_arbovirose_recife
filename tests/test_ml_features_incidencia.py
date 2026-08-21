import numpy as np
import pandas as pd

from src.ml.features import construir_indice_semana_global
from src.ml.features_incidencia import (
    FEATURES_HISTORICO_LOCAL_INCIDENCIA,
    FEATURES_INCIDENCIA_BASE,
    construir_features_incidencia,
)
from src.ml.target_incidencia import calcular_estado_alto_risco_incidencia


def _df_basico(casos: list[int], populacao: int = 10000) -> pd.DataFrame:
    linhas = []
    for i, c in enumerate(casos):
        ano = 2013 + i // 20
        semana = i % 20 + 1
        data_fim = pd.Timestamp("2013-01-05") + pd.Timedelta(weeks=i)
        data_inicio = data_fim - pd.Timedelta(days=6)
        linhas.append(
            {
                "codigo_bairro": "1",
                "ano_epidemiologico": ano,
                "semana_epidemiologica": semana,
                "semana_epi_data_inicio": data_inicio,
                "semana_epi_data_fim": data_fim,
                "casos": c,
                "populacao_bairro_ano": populacao,
                "incidencia_100k": 100000 * c / populacao,
                "incidencia_4s_100k": 100000 * c / populacao,
                "incidencia_8s_100k": 100000 * c / populacao,
            }
        )
    df = pd.DataFrame(linhas)
    df = construir_indice_semana_global(df)
    df = calcular_estado_alto_risco_incidencia(df, coluna_valor="incidencia_100k")
    return df


def test_lags_e_delta_incidencia():
    df = _df_basico([1, 2, 3, 4, 5] * 4)
    resultado = construir_features_incidencia(df)
    linha = resultado.iloc[5]  # indice 5: casos=2 (i=5 -> 5%5=0 -> casos[0]=1... vamos so checar consistencia)
    assert resultado["incidencia_lag1_100k"].iloc[1] == resultado["incidencia_t_100k"].iloc[0]
    assert resultado["incidencia_lag2_100k"].iloc[2] == resultado["incidencia_t_100k"].iloc[0]
    delta_esperado = resultado["incidencia_t_100k"].iloc[3] - resultado["incidencia_t_100k"].iloc[2]
    assert resultado["delta_incidencia"].iloc[3] == delta_esperado


def test_lags_iniciais_da_serie_ficam_nan():
    df = _df_basico([1] * 10)
    resultado = construir_features_incidencia(df)
    assert pd.isna(resultado["incidencia_lag4_100k"].iloc[0])
    assert pd.isna(resultado["incidencia_lag1_100k"].iloc[0])


def test_razao_incidencia_historico_local_nao_explode_com_limiar_zero():
    # historico com incidencia 0 -> limiar historico local = 0 quando definido
    df = _df_basico([0] * 25 + [5])
    resultado = construir_features_incidencia(df)
    ultima = resultado.iloc[-1]
    assert np.isfinite(ultima["razao_incidencia_historico_local"])


def test_desvio_incidencia_sazonal_nao_explode_com_std_zero():
    df = _df_basico([1] * 25 + [1])
    resultado = construir_features_incidencia(df)
    ultima = resultado.iloc[-1]
    assert np.isfinite(ultima["desvio_incidencia_sazonal"])


def test_log_populacao_e_monotonico_crescente():
    df1 = _df_basico([1] * 5, populacao=1000)
    df2 = _df_basico([1] * 5, populacao=100000)
    r1 = construir_features_incidencia(df1)
    r2 = construir_features_incidencia(df2)
    assert r2["log_populacao"].iloc[0] > r1["log_populacao"].iloc[0]


def test_features_incidencia_nao_inclui_media_movel_recalculada():
    """incidencia_4s_100k/8s_100k devem vir DIRETO da Gold (ja presentes em
    df), nunca recalculadas como media das incidencias semanais -- este
    modulo so deve referenciar, nunca sobrescrever essas colunas."""
    df = _df_basico([1, 100, 1, 1, 1])
    valor_original_4s = df["incidencia_4s_100k"].copy()
    resultado = construir_features_incidencia(df)
    pd.testing.assert_series_equal(resultado["incidencia_4s_100k"], valor_original_4s, check_names=False)


def test_todas_as_colunas_do_bloco_base_estao_presentes():
    df = _df_basico([1] * 30)
    resultado = construir_features_incidencia(df)
    for coluna in FEATURES_INCIDENCIA_BASE:
        assert coluna in resultado.columns, coluna
    for coluna in FEATURES_HISTORICO_LOCAL_INCIDENCIA:
        assert coluna in resultado.columns, coluna
