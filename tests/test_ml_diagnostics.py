import pandas as pd

from src.ml.diagnostics import drift_features, lift_pr_auc, resumo_alvo_por_ano, resumo_episodios_por_ano


def test_resumo_alvo_por_ano_calcula_prevalencia_e_indefinidos():
    df = pd.DataFrame(
        {
            "ano_epidemiologico": [2020, 2020, 2021, 2021],
            "codigo_bairro": ["1", "2", "1", "2"],
            "casos": [10, 0, 5, 0],
            "estado_alto_risco": [1.0, 0.0, float("nan"), 0.0],
            "limiar_historico_local": [5.0, 5.0, float("nan"), 3.0],
            "tipo_limiar": ["sazonal", "sazonal", "indefinido", "geral"],
        }
    )
    resumo = resumo_alvo_por_ano(df)
    linha_2020 = resumo[resumo["ano"] == 2020].iloc[0]
    assert linha_2020["pct_positivo"] == 50.0
    assert linha_2020["pct_indefinido"] == 0.0
    linha_2021 = resumo[resumo["ano"] == 2021].iloc[0]
    assert linha_2021["pct_indefinido"] == 50.0


def test_resumo_episodios_por_ano_agrega_intensidade():
    episodios = pd.DataFrame(
        {
            "inicio_ano": [2023, 2023, 2024],
            "codigo_bairro": ["1", "2", "1"],
            "duracao_semanas": [1, 2, 3],
            "casos_totais_episodio": [2.0, 4.0, 20.0],
            "casos_pico": [2.0, 3.0, 10.0],
        }
    )
    resumo = resumo_episodios_por_ano(episodios)
    linha_2023 = resumo[resumo["ano"] == 2023].iloc[0]
    assert linha_2023["n_episodios"] == 2
    assert linha_2023["n_bairros_distintos"] == 2
    assert linha_2023["casos_pico_media"] == 2.5


def test_drift_features_detecta_distribuicoes_diferentes():
    n = 200
    X = pd.DataFrame(
        {
            "feature_estavel": [1.0] * n,
            "feature_com_drift": [1.0] * (n // 2) + [100.0] * (n // 2),
        }
    )
    anos = pd.Series([2019] * (n // 2) + [2023] * (n // 2))
    resultado = drift_features(
        X, anos, features=["feature_estavel", "feature_com_drift"], ano_referencia_fim=2019, grupos_comparacao={"2023": anos == 2023}
    )
    estavel = resultado[resultado["feature"] == "feature_estavel"].iloc[0]
    com_drift = resultado[resultado["feature"] == "feature_com_drift"].iloc[0]
    assert estavel["ks_estatistica"] == 0.0
    assert com_drift["ks_estatistica"] == 1.0
    assert com_drift["ks_p_valor"] < estavel["ks_p_valor"] + 1e-9


def test_lift_pr_auc_normaliza_por_prevalencia():
    tabela = pd.DataFrame({"n_positivos": [50, 10], "n_teste": [500, 500], "pr_auc": [0.2, 0.2]})
    resultado = lift_pr_auc(tabela)
    # mesma PR-AUC, prevalencia menor (10/500=0.02) -> lift maior que a linha com prevalencia 0.1
    assert resultado.loc[1, "lift_pr_auc"] > resultado.loc[0, "lift_pr_auc"]
