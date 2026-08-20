import pandas as pd

from src.ml.features import construir_features_epidemiologicas_e_sazonais
from src.ml.target import calcular_estado_alto_risco


def _semanal_um_bairro(n_semanas: int = 20, ano_inicio: int = 2020) -> pd.DataFrame:
    linhas = []
    ano, semana = ano_inicio, 1
    for i in range(n_semanas):
        data_fim = pd.Timestamp("2020-01-04") + pd.Timedelta(weeks=i)
        data_inicio = data_fim - pd.Timedelta(days=6)
        linhas.append(
            {
                "codigo_bairro": "1",
                "nome_bairro": "TESTE",
                "ano_epidemiologico": ano,
                "semana_epidemiologica": semana,
                "semana_epi_data_inicio": data_inicio,
                "semana_epi_data_fim": data_fim,
                "casos": i + 1,
            }
        )
        semana += 1
        if semana > 52:
            semana = 1
            ano += 1
    return pd.DataFrame(linhas)


def test_features_de_t_nao_mudam_quando_casos_futuros_mudam():
    df = _semanal_um_bairro()
    df_estado = calcular_estado_alto_risco(df)
    features_original = construir_features_epidemiologicas_e_sazonais(df_estado)

    df_alterado = df.copy()
    df_alterado.loc[df_alterado.index[-1], "casos"] = 99999  # última semana da série
    df_estado_alterado = calcular_estado_alto_risco(df_alterado)
    features_alteradas = construir_features_epidemiologicas_e_sazonais(df_estado_alterado)

    colunas_features = [
        "casos_t",
        "casos_t_menos_1",
        "casos_t_menos_2",
        "media_2s",
        "media_4s",
        "media_8s",
        "soma_4s",
        "max_4s",
        "tendencia_1s",
    ]
    # Todas as linhas exceto a última (a alterada) devem ser idênticas.
    original_sem_ultima = features_original.iloc[:-1][colunas_features].reset_index(drop=True)
    alteradas_sem_ultima = features_alteradas.iloc[:-1][colunas_features].reset_index(drop=True)
    pd.testing.assert_frame_equal(original_sem_ultima, alteradas_sem_ultima)


def test_rolling_nunca_inclui_semana_seguinte():
    df = _semanal_um_bairro(n_semanas=10)
    df_estado = calcular_estado_alto_risco(df)
    features = construir_features_epidemiologicas_e_sazonais(df_estado)
    # casos = i+1 (1..10); media_2s na linha i (0-indexado) deve ser media de casos[i-1:i+1]
    # Ex.: linha 5 (casos=6): media_2s = mean(5,6) = 5.5 -- nao pode "ver" casos=7 (linha 6)
    linha_5 = features.iloc[5]
    assert linha_5["casos_t"] == 6
    assert linha_5["media_2s"] == 5.5


def test_indice_semana_global_e_cronologico_nao_apenas_semana_epidemiologica():
    df = _semanal_um_bairro(n_semanas=60)  # atravessa virada de ano (semana 52 -> 1)
    df_estado = calcular_estado_alto_risco(df)
    features = construir_features_epidemiologicas_e_sazonais(df_estado)
    indices = features.sort_values("indice_semana_global")["indice_semana_global"].tolist()
    assert indices == list(range(len(features)))
