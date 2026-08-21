import numpy as np
import pandas as pd
import pytest

from src.ml.dataset_incidencia import VARIANTES_FEATURES, montar_dataset_onset_incidencia
from src.ml.features import FEATURES_EPIDEMIOLOGICAS_BASE
from src.ml.features_incidencia import FEATURES_INCIDENCIA_BASE, FEATURES_POPULACAO


def _gold_sintetica(n_semanas: int = 120, bairros: tuple[str, ...] = ("1", "2")) -> pd.DataFrame:
    linhas = []
    populacoes = {"1": 2000, "2": 200000}
    for bairro in bairros:
        ano, semana = 2013, 1
        casos_base = 1 if bairro == "1" else 50
        pop = populacoes[bairro]
        for i in range(n_semanas):
            data_fim = pd.Timestamp("2013-01-05") + pd.Timedelta(weeks=i)
            data_inicio = data_fim - pd.Timedelta(days=6)
            casos = casos_base + (5 if (i % 20 == 0) else 0)
            linhas.append(
                {
                    "codigo_bairro": bairro,
                    "nome_bairro": f"BAIRRO {bairro}",
                    "agravo": "DENGUE",
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "semana_epi_data_inicio": data_inicio,
                    "semana_epi_data_fim": data_fim,
                    "casos": casos,
                    "area_km2": 1.0,
                    "codigo_rpa": "1",
                    "codigo_microrregiao": "1.1",
                    "centroide_lat": -8.0,
                    "centroide_lon": -34.9,
                    "populacao_bairro_ano": pop,
                    "tipo_populacao": "CENSO_OBSERVADO",
                    "densidade_populacional_hab_km2": float(pop),
                    "incidencia_100k": 100000 * casos / pop,
                    "incidencia_4s_100k": 100000 * casos / pop,
                    "incidencia_8s_100k": 100000 * casos / pop,
                    "incidencia_12s_100k": 100000 * casos / pop,
                    "incidencia_anual_100k": 100000 * casos / pop,
                }
            )
            semana += 1
            if semana > 52:
                semana = 1
                ano += 1
    return pd.DataFrame(linhas)


@pytest.mark.parametrize("variante", VARIANTES_FEATURES)
def test_todas_as_variantes_produzem_dataset_valido(variante):
    df_gold = _gold_sintetica()
    ctx, X, y, metricas = montar_dataset_onset_incidencia(df_gold, variante=variante)
    assert len(ctx) == len(X) == len(y)
    assert metricas["variante"] == variante
    assert set(y.unique()).issubset({0, 1})


def test_v2_incidencia_pura_nao_inclui_casos_absolutos():
    df_gold = _gold_sintetica()
    _, X, _, _ = montar_dataset_onset_incidencia(df_gold, variante="v2_incidencia")
    for coluna in FEATURES_EPIDEMIOLOGICAS_BASE:
        assert coluna not in X.columns, f"{coluna} nao deveria estar na variante v2_incidencia"


def test_v1_features_nao_inclui_incidencia():
    df_gold = _gold_sintetica()
    _, X, _, _ = montar_dataset_onset_incidencia(df_gold, variante="v1_features")
    for coluna in FEATURES_INCIDENCIA_BASE:
        assert coluna not in X.columns, f"{coluna} nao deveria estar na variante v1_features"


def test_v2_casos_incidencia_inclui_ambos_os_blocos():
    df_gold = _gold_sintetica()
    _, X, _, _ = montar_dataset_onset_incidencia(df_gold, variante="v2_casos_incidencia")
    assert "casos_t" in X.columns
    assert "incidencia_t_100k" in X.columns
    for coluna in FEATURES_POPULACAO:
        assert coluna not in X.columns  # essa variante NAO inclui populacao/densidade


def test_v2_casos_incidencia_populacao_inclui_tudo():
    df_gold = _gold_sintetica()
    _, X, _, _ = montar_dataset_onset_incidencia(df_gold, variante="v2_casos_incidencia_populacao")
    assert "casos_t" in X.columns
    assert "incidencia_t_100k" in X.columns
    for coluna in FEATURES_POPULACAO:
        assert coluna in X.columns


def test_variante_invalida_levanta_erro():
    df_gold = _gold_sintetica()
    with pytest.raises(ValueError, match="variante"):
        montar_dataset_onset_incidencia(df_gold, variante="inexistente")


def test_horizonte_invalido_levanta_erro():
    df_gold = _gold_sintetica()
    with pytest.raises(ValueError, match="horizonte"):
        montar_dataset_onset_incidencia(df_gold, horizonte=99)


def test_target_e_identico_entre_variantes_nas_linhas_em_comum():
    """O target (onset baseado em incidencia) nao depende da variante de
    features -- so a composicao de X muda."""
    df_gold = _gold_sintetica()
    ctx_a, _, y_a, _ = montar_dataset_onset_incidencia(df_gold, variante="v1_features")
    ctx_b, _, y_b, _ = montar_dataset_onset_incidencia(df_gold, variante="v2_incidencia")

    chave_a = ctx_a.set_index(["codigo_bairro", "indice_semana_alvo"])
    chave_b = ctx_b.set_index(["codigo_bairro", "indice_semana_alvo"])
    comuns = chave_a.index.intersection(chave_b.index)
    assert len(comuns) > 0
    ya_comum = pd.Series(y_a.to_numpy(), index=chave_a.index).loc[comuns]
    yb_comum = pd.Series(y_b.to_numpy(), index=chave_b.index).loc[comuns]
    np.testing.assert_array_equal(ya_comum.to_numpy(), yb_comum.to_numpy())


def test_montar_dataset_onset_incidencia_e_deterministico():
    df_gold = _gold_sintetica()
    ctx1, X1, y1, _ = montar_dataset_onset_incidencia(df_gold, variante="v2_casos_incidencia")
    ctx2, X2, y2, _ = montar_dataset_onset_incidencia(df_gold, variante="v2_casos_incidencia")
    pd.testing.assert_frame_equal(X1, X2)
    pd.testing.assert_series_equal(y1, y2)
