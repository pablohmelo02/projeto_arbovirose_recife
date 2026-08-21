"""Testes de `src/eda/associacao_climatica.py` -- defasagem deslocada real,
dessazonalização descritiva e o resumo textual que nunca afirma causalidade
nem escolhe lag por p-valor."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.eda import associacao_climatica as ac


# ---------------------------------------------------------------------------
# calcular_lags_deslocados
# ---------------------------------------------------------------------------


def test_lag_deslocado_encontra_o_lag_verdadeiro():
    rng = np.random.default_rng(42)
    n = 100
    t = np.arange(n)
    # onda periodica (periodo 13) -- dentro da janela de lags 0..12, so o
    # deslocamento correto reconstroi a fase original (ver docstring do
    # modulo de teste para a demonstracao de que o maximo e unico).
    clima = pd.Series(10 * np.sin(2 * np.pi * t / 13) + rng.normal(scale=0.05, size=n))
    k0 = 5
    alvo = pd.Series(clima.shift(k0).to_numpy() + rng.normal(scale=0.05, size=n))

    tabela = ac.calcular_lags_deslocados(alvo, clima, lags=range(0, 13))
    melhor = tabela.loc[tabela["correlacao_spearman"].abs().idxmax(), "lag_semanas"]
    assert int(melhor) == k0
    assert tabela.loc[tabela["lag_semanas"] == k0, "correlacao_spearman"].iloc[0] > 0.95


def test_lag_deslocado_reporta_p_value_e_n_observacoes():
    rng = np.random.default_rng(1)
    n = 60
    clima = pd.Series(rng.normal(size=n))
    alvo = pd.Series(rng.normal(size=n))
    tabela = ac.calcular_lags_deslocados(alvo, clima, lags=range(0, 3))
    for _, linha in tabela.iterrows():
        assert linha["p_value"] is None or 0.0 <= linha["p_value"] <= 1.0
        # lag 0 usa todas as observacoes; lags maiores perdem linhas no dropna
        assert linha["n_observacoes"] <= n


def test_lag_deslocado_amostra_pequena_marca_nao_confiavel():
    clima = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    alvo = pd.Series([2.0, 3.0, 1.0, 5.0, 4.0])
    tabela = ac.calcular_lags_deslocados(alvo, clima, lags=range(0, 2))
    assert (~tabela["confiavel"]).all()
    assert (tabela["n_observacoes"] < ac.N_MINIMO_OBSERVACOES_CONFIAVEL).all()


def test_lag_deslocado_com_series_vazias_nao_levanta_erro():
    tabela = ac.calcular_lags_deslocados(pd.Series([], dtype=float), pd.Series([], dtype=float))
    assert list(tabela.columns) == list(ac.COLUNAS_TABELA_LAGS)
    assert (tabela["n_observacoes"] == 0).all()
    assert (~tabela["confiavel"]).all()
    assert tabela["correlacao_spearman"].isna().all()


def test_lag_deslocado_serie_constante_nao_levanta_erro():
    # variancia zero -- spearman indefinido, deve virar None, nao NaN/erro.
    clima = pd.Series([5.0] * 40)
    alvo = pd.Series([1.0] * 40)
    tabela = ac.calcular_lags_deslocados(alvo, clima, lags=range(0, 2))
    assert tabela["correlacao_spearman"].isna().all()


# ---------------------------------------------------------------------------
# dessazonalizar
# ---------------------------------------------------------------------------


def test_dessazonalizar_remove_padrao_sazonal_conhecido():
    rng = np.random.default_rng(7)
    semanas = pd.Series(list(range(1, 53)) * 5)  # 5 anos completos
    sazonal = 10 * np.sin(2 * np.pi * semanas.to_numpy() / 52)
    ruido = rng.normal(scale=0.2, size=len(semanas))
    serie = pd.Series(sazonal + ruido)

    residuo = ac.dessazonalizar(serie, semanas)

    # a variancia do residuo deve ser muito menor que a da serie bruta --
    # o componente sazonal (que domina a variancia aqui) foi removido.
    assert residuo.var() < serie.var() * 0.1
    # o residuo nao deve mais estar correlacionado com o proprio padrao sazonal.
    correlacao_residuo_sazonalidade = np.corrcoef(residuo.to_numpy(), sazonal)[0, 1]
    assert abs(correlacao_residuo_sazonalidade) < 0.1


def test_dessazonalizar_preserva_nan():
    semanas = pd.Series([1, 1, 2, 2])
    serie = pd.Series([1.0, np.nan, 3.0, 5.0])
    residuo = ac.dessazonalizar(serie, semanas)
    assert residuo.isna().iloc[1]


# ---------------------------------------------------------------------------
# comparar_bruta_vs_ajustada
# ---------------------------------------------------------------------------


def test_comparar_bruta_vs_ajustada_reduz_correlacao_puramente_sazonal():
    # duas series que so se parecem por compartilhar a mesma sazonalidade --
    # a correlacao bruta deve cair bastante depois de dessazonalizar.
    rng = np.random.default_rng(3)
    semanas = pd.Series(list(range(1, 53)) * 4)
    fase_clima = 10 * np.sin(2 * np.pi * semanas.to_numpy() / 52) + rng.normal(scale=0.3, size=len(semanas))
    fase_alvo = 10 * np.sin(2 * np.pi * semanas.to_numpy() / 52) + rng.normal(scale=0.3, size=len(semanas))
    clima = pd.Series(fase_clima)
    alvo = pd.Series(fase_alvo)

    tabela = ac.comparar_bruta_vs_ajustada(alvo, clima, semanas, lags=range(0, 3))
    lag0 = tabela[tabela["lag_semanas"] == 0].iloc[0]
    assert abs(lag0["correlacao_bruta"]) > abs(lag0["correlacao_ajustada"])


# ---------------------------------------------------------------------------
# resumo_textual
# ---------------------------------------------------------------------------


def test_resumo_textual_nunca_afirma_causalidade():
    tabela = pd.DataFrame(
        {
            "lag_semanas": [0, 1, 2],
            "correlacao_spearman": [0.1, 0.8, -0.3],
            "p_value": [0.4, 0.001, 0.2],
            "n_observacoes": [40, 40, 40],
            "confiavel": [True, True, True],
        }
    )
    texto = ac.resumo_textual(tabela)
    assert "não causalidade" in texto
    for termo_proibido in ("causa ", "causada", "provoca", "é a causa"):
        assert termo_proibido not in texto.lower()


def test_resumo_textual_escolhe_por_correlacao_nao_por_p_valor():
    # lag 1 tem o menor p-valor, mas lag 2 tem a maior |correlacao| --
    # o resumo deve citar o lag 2.
    tabela = pd.DataFrame(
        {
            "lag_semanas": [0, 1, 2],
            "correlacao_spearman": [0.1, 0.3, 0.9],
            "p_value": [0.9, 0.0001, 0.2],
            "n_observacoes": [50, 50, 50],
            "confiavel": [True, True, True],
        }
    )
    texto = ac.resumo_textual(tabela)
    assert "2 semanas" in texto


def test_resumo_textual_sem_lag_confiavel():
    tabela = pd.DataFrame(
        {
            "lag_semanas": [0, 1],
            "correlacao_spearman": [0.9, 0.8],
            "p_value": [0.01, 0.02],
            "n_observacoes": [5, 5],
            "confiavel": [False, False],
        }
    )
    texto = ac.resumo_textual(tabela)
    assert "amostra suficiente" in texto.lower()


# ---------------------------------------------------------------------------
# construir_serie_semanal_agravo
# ---------------------------------------------------------------------------


def _linha_gold(**overrides) -> dict:
    base = {
        "codigo_bairro": "1",
        "nome_bairro": "BAIRRO A",
        "agravo": "DENGUE",
        "ano_epidemiologico": 2024,
        "semana_epidemiologica": 1,
        "semana_epi_data_inicio": pd.Timestamp("2024-01-07"),
        "casos": 0,
    }
    base.update(overrides)
    return base


def _gold_duas_semanas_dois_bairros(com_populacao: bool) -> pd.DataFrame:
    linhas = []
    for bairro, pop in (("1", 100_000.0), ("2", 300_000.0)):
        for semana, casos in ((1, 10), (2, 20)):
            extra = {"populacao_bairro_ano": pop} if com_populacao else {}
            linhas.append(
                _linha_gold(
                    codigo_bairro=bairro,
                    semana_epidemiologica=semana,
                    semana_epi_data_inicio=pd.Timestamp("2024-01-07") + pd.Timedelta(weeks=semana - 1),
                    casos=casos,
                    **extra,
                )
            )
    return pd.DataFrame(linhas)


def test_construir_serie_semanal_agravo_soma_casos_dos_bairros():
    gold = _gold_duas_semanas_dois_bairros(com_populacao=False)
    serie = ac.construir_serie_semanal_agravo(gold, "DENGUE")
    assert list(serie["casos"]) == [20, 40]
    assert list(serie["indice_semana"]) == [0, 1]
    assert serie["incidencia_100k"].isna().all()


def test_construir_serie_semanal_agravo_incidencia_e_uma_unica_divisao():
    gold = _gold_duas_semanas_dois_bairros(com_populacao=True)
    serie = ac.construir_serie_semanal_agravo(gold, "DENGUE")
    populacao_total = 100_000.0 + 300_000.0
    esperado_semana1 = 20 / populacao_total * 100000
    assert serie.loc[serie["semana_epidemiologica"] == 1, "incidencia_100k"].iloc[0] == pytest.approx(
        esperado_semana1
    )


def test_construir_serie_semanal_agravo_agravo_invalido_levanta_erro():
    gold = _gold_duas_semanas_dois_bairros(com_populacao=False)
    with pytest.raises(ValueError):
        ac.construir_serie_semanal_agravo(gold, "MALARIA")


def test_construir_serie_semanal_agravo_dataframe_vazio():
    serie = ac.construir_serie_semanal_agravo(pd.DataFrame(columns=["agravo", "casos"]), "DENGUE")
    assert serie.empty
    assert list(serie.columns) == list(ac.COLUNAS_SERIE_SEMANAL_AGRAVO)
