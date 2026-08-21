import numpy as np
import pandas as pd

from src.population.population_sensitivity import (
    executar_analise_sensibilidade_b,
    perturbar_populacao,
    recalcular_gold_com_populacao_perturbada,
)


def _silver_populacao() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_bairro": ["1", "1", "2", "2"],
            "ano": [2022, 2024, 2022, 2024],
            "populacao": [10000, 10500, 5000, 5200],
            "tipo_valor": ["CENSO_OBSERVADO", "PROJECAO_POS_CENSO", "CENSO_OBSERVADO", "PROJECAO_POS_CENSO"],
        }
    )


def test_perturbar_populacao_nao_toca_censo_observado():
    df = _silver_populacao()
    erros = np.array([50.0, -50.0, 10.0])  # erros grandes para deixar o efeito obvio
    rng = np.random.default_rng(0)
    resultado = perturbar_populacao(df, erros, rng)

    censo = resultado[resultado["tipo_valor"] == "CENSO_OBSERVADO"]
    original_censo = df[df["tipo_valor"] == "CENSO_OBSERVADO"]
    pd.testing.assert_series_equal(censo["populacao"], original_censo["populacao"])


def test_perturbar_populacao_altera_projecao_pos_censo():
    df = _silver_populacao()
    erros = np.array([100.0])  # +100% -- efeito garantido de ser detectavel
    rng = np.random.default_rng(0)
    resultado = perturbar_populacao(df, erros, rng)

    projecao = resultado[resultado["tipo_valor"] == "PROJECAO_POS_CENSO"]
    original = df[df["tipo_valor"] == "PROJECAO_POS_CENSO"]
    assert (projecao["populacao"].to_numpy() > original["populacao"].to_numpy()).all()


def test_perturbar_populacao_nunca_gera_populacao_nao_positiva():
    df = _silver_populacao()
    erros = np.array([-99.9, -150.0, -200.0])  # erros extremos negativos
    rng = np.random.default_rng(1)
    resultado = perturbar_populacao(df, erros, rng)
    assert (resultado["populacao"] >= 1).all()


def test_perturbar_populacao_e_deterministico_com_mesma_seed():
    df = _silver_populacao()
    erros = np.array([10.0, -10.0, 20.0, -20.0])
    r1 = perturbar_populacao(df, erros, np.random.default_rng(7))
    r2 = perturbar_populacao(df, erros, np.random.default_rng(7))
    pd.testing.assert_frame_equal(r1, r2)


def _gold_grao() -> pd.DataFrame:
    linhas = []
    for bairro, area in [("1", 5.0), ("2", 3.0)]:
        for ano in (2022, 2024):
            for agravo in ("DENGUE",):
                for semana in (1, 2):
                    linhas.append(
                        {
                            "codigo_bairro": bairro,
                            "agravo": agravo,
                            "ano_epidemiologico": ano,
                            "semana_epidemiologica": semana,
                            "casos": 2,
                            "area_km2": area,
                        }
                    )
    return pd.DataFrame(linhas)


def test_recalcular_gold_com_populacao_perturbada_reflete_nova_populacao():
    df_gold = _gold_grao()
    pop = _silver_populacao()
    resultado = recalcular_gold_com_populacao_perturbada(df_gold, pop)
    linha = resultado[(resultado["codigo_bairro"] == "1") & (resultado["ano_epidemiologico"] == 2022)].iloc[0]
    assert linha["populacao_bairro_ano"] == 10000
    assert linha["incidencia_100k"] == 100000 * 2 / 10000


def test_executar_analise_sensibilidade_b_chama_avaliar_replica_n_vezes():
    df_gold = _gold_grao()
    pop = _silver_populacao()
    erros = np.array([10.0, -10.0])

    chamadas = []

    def _avaliar(gold_perturbada):
        chamadas.append(len(gold_perturbada))
        return {"recall_5": 0.5}

    resultados = executar_analise_sensibilidade_b(df_gold, pop, erros, _avaliar, n_replicas=5, seed=42)
    assert len(resultados) == 5
    assert len(chamadas) == 5
    assert all(r["recall_5"] == 0.5 for r in resultados)
