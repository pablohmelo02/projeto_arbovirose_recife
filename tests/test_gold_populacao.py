import numpy as np
import pandas as pd

from src.gold.populacao import COLUNAS_GOLD_POPULACAO, calcular_features_populacao


def _df_grao_2_bairros_4_semanas() -> pd.DataFrame:
    linhas = []
    for codigo, area, casos_por_semana in [
        ("1", 10.0, [1, 2, 3, 4]),
        ("2", 5.0, [0, 0, 0, 0]),
    ]:
        for i, casos in enumerate(casos_por_semana, start=1):
            linhas.append(
                {
                    "codigo_bairro": codigo,
                    "nome_bairro": f"BAIRRO {codigo}",
                    "agravo": "DENGUE",
                    "ano_epidemiologico": 2024,
                    "semana_epidemiologica": i,
                    "casos": casos,
                    "area_km2": area,
                }
            )
    return pd.DataFrame(linhas)


def _df_populacao_2_bairros() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_bairro": ["1", "2"],
            "ano": [2024, 2024],
            "populacao": [100000, 0],
            "tipo_valor": ["CENSO_OBSERVADO", "CENSO_OBSERVADO"],
        }
    )


def test_calcular_features_populacao_adiciona_todas_as_colunas():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    for coluna in COLUNAS_GOLD_POPULACAO:
        assert coluna in df.columns


def test_incidencia_100k_da_propria_semana_e_casos_sobre_populacao():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    linha = df[(df["codigo_bairro"] == "1") & (df["semana_epidemiologica"] == 1)].iloc[0]
    assert linha["incidencia_100k"] == 1 / 100000 * 100000  # == 1.0


def test_incidencia_janela_soma_casos_antes_de_dividir_nao_soma_taxas():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    linha_semana4 = df[(df["codigo_bairro"] == "1") & (df["semana_epidemiologica"] == 4)].iloc[0]
    # janela de 4 semanas: soma dos casos (1+2+3+4=10) / 100000 * 100000 = 10
    assert linha_semana4["incidencia_4s_100k"] == 10.0
    # nao pode ser a soma das incidencias semanais (1+2+3+4 = 10 tambem aqui,
    # mas testado de outra forma abaixo para nao ficar ambiguo)
    incidencias_semanais = df[df["codigo_bairro"] == "1"]["incidencia_100k"].to_numpy()
    assert incidencias_semanais.sum() == linha_semana4["incidencia_4s_100k"]


def test_incidencia_janela_e_estritamente_trailing_ate_a_semana_atual():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    linha_semana2 = df[(df["codigo_bairro"] == "1") & (df["semana_epidemiologica"] == 2)].iloc[0]
    # janela de 4 semanas na semana 2 (min_periods=1): so ha semana 1+2 disponiveis = 1+2=3
    assert linha_semana2["incidencia_4s_100k"] == 3.0


def test_populacao_zero_gera_incidencia_none_nunca_zero_ou_infinito():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    linhas_bairro_2 = df[df["codigo_bairro"] == "2"]
    assert linhas_bairro_2["incidencia_100k"].isna().all()
    assert not np.isinf(linhas_bairro_2["incidencia_100k"].to_numpy(dtype=float)).any()


def test_zero_casos_gera_incidencia_zero_nao_none():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    # bairro 2 tem populacao=0 -> None; troca por um bairro com populacao > 0 e casos=0
    df_populacao = pd.DataFrame(
        {"codigo_bairro": ["1"], "ano": [2024], "populacao": [100000], "tipo_valor": ["CENSO_OBSERVADO"]}
    )
    df_grao = pd.DataFrame(
        [
            {
                "codigo_bairro": "1", "nome_bairro": "X", "agravo": "DENGUE",
                "ano_epidemiologico": 2024, "semana_epidemiologica": 1, "casos": 0, "area_km2": 1.0,
            }
        ]
    )
    df, _ = calcular_features_populacao(df_grao, df_populacao)
    assert df["incidencia_100k"].iloc[0] == 0.0


def test_bairro_sem_populacao_na_silver_fica_none_e_e_reportado_na_metrica():
    df_populacao = pd.DataFrame(
        {"codigo_bairro": ["1"], "ano": [2024], "populacao": [100000], "tipo_valor": ["CENSO_OBSERVADO"]}
    )
    df, metricas = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), df_populacao)
    linhas_bairro_2 = df[df["codigo_bairro"] == "2"]
    assert linhas_bairro_2["populacao_bairro_ano"].isna().all()
    assert "2" in metricas["bairros_sem_populacao"]


def test_densidade_populacional_e_populacao_sobre_area():
    df, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    linha = df[df["codigo_bairro"] == "1"].iloc[0]
    assert linha["densidade_populacional_hab_km2"] == 100000 / 10.0


def test_calcular_features_populacao_preserva_ordem_original_das_linhas():
    df_grao = _df_grao_2_bairros_4_semanas().sample(frac=1, random_state=42)  # embaralha
    ordem_original = df_grao.index.tolist()
    df, _ = calcular_features_populacao(df_grao, _df_populacao_2_bairros())
    assert df.index.tolist() == ordem_original


def test_calcular_features_populacao_e_deterministico():
    df1, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    df2, _ = calcular_features_populacao(_df_grao_2_bairros_4_semanas(), _df_populacao_2_bairros())
    pd.testing.assert_frame_equal(df1, df2)


def test_calcular_features_populacao_nao_altera_casos_nem_cardinalidade():
    df_grao = _df_grao_2_bairros_4_semanas()
    df, _ = calcular_features_populacao(df_grao, _df_populacao_2_bairros())
    assert len(df) == len(df_grao)
    assert df["casos"].sum() == df_grao["casos"].sum()
