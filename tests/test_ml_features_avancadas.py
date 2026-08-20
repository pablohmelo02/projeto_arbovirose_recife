import numpy as np
import pandas as pd

from src.ml.features import construir_features_epidemiologicas_e_sazonais
from src.ml.target import calcular_estado_alto_risco


def _semanal_casos(casos: list[int], ano_inicio: int = 2020) -> pd.DataFrame:
    linhas = []
    ano, semana = ano_inicio, 1
    for i, c in enumerate(casos):
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
                "casos": c,
            }
        )
        semana += 1
        if semana > 52:
            semana = 1
            ano += 1
    return pd.DataFrame(linhas)


def _features(casos):
    df = _semanal_casos(casos)
    df_estado = calcular_estado_alto_risco(df)
    return construir_features_epidemiologicas_e_sazonais(df_estado)


def test_momentum_delta_e_aceleracao():
    features = _features([1, 2, 4, 3, 3, 10])
    # linha 5 (indice 5, casos=10): casos_t_menos_1=3, casos_t_menos_2=3
    linha = features.iloc[5]
    assert linha["delta_1s"] == 10 - 3
    assert linha["delta_2s"] == 10 - 3
    assert linha["aceleracao_1s"] == (10 - 3) - (3 - 3)


def test_n_semanas_consecutivas_crescimento_para_no_primeiro_nao_crescimento():
    features = _features([1, 2, 3, 4, 2, 5])
    # indice 3 (casos=4): 4>3>2>1 -- cresceu nas 3 comparacoes anteriores
    assert features.iloc[3]["n_semanas_consecutivas_crescimento"] == 3
    # indice 4 (casos=2): 2>4? nao -- 0 semanas consecutivas
    assert features.iloc[4]["n_semanas_consecutivas_crescimento"] == 0
    # indice 5 (casos=5): 5>2? sim; 2>4? nao -- para em 1
    assert features.iloc[5]["n_semanas_consecutivas_crescimento"] == 1


def test_taxa_crescimento_suavizada_nao_gera_inf_com_denominador_zero():
    features = _features([0, 0, 5, 0, 3])
    # nenhuma linha pode ter +-inf por divisao por zero (NaN no inicio da
    # serie, por falta de lag, e esperado e diferente de inf)
    assert not np.isinf(features["taxa_crescimento_suavizada"]).any()
    # indice 2 (casos=5, casos_t_menos_1=0): taxa = (5-0)/(0+1) = 5.0
    assert features.iloc[2]["taxa_crescimento_suavizada"] == 5.0


def test_razao_limiar_historico_e_z_score_nao_geram_inf():
    # historico suficiente para gerar limiar definido (>=20 semanas passadas)
    casos = [1] * 60 + [50]
    features = _features(casos)
    ultima = features.iloc[-1]
    assert not np.isinf(ultima["razao_limiar_historico"])
    assert not np.isinf(ultima["z_score_historico_local"])
    assert not np.isinf(ultima["razao_media_recente"])
    # pico bem acima do historico -> razoes e z-score devem ser claramente positivos
    assert ultima["razao_limiar_historico"] > 1
    assert ultima["z_score_historico_local"] > 0


def test_features_historico_local_nao_usam_futuro():
    casos_originais = [1] * 60 + [1]
    casos_alterados = casos_originais.copy()
    casos_alterados[-1] = 99999
    original = _features(casos_originais)
    alterado = _features(casos_alterados)
    colunas = ["razao_limiar_historico", "z_score_historico_local", "razao_media_recente", "n_semanas_consecutivas_crescimento"]
    pd.testing.assert_frame_equal(
        original.iloc[:-1][colunas].reset_index(drop=True),
        alterado.iloc[:-1][colunas].reset_index(drop=True),
    )
