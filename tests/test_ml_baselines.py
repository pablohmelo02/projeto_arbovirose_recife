import pandas as pd
import pytest

from src.ml.baselines import (
    baseline_contagem_media_movel_4s,
    baseline_contagem_persistencia,
    baseline_crescimento_recente,
    baseline_persistencia,
    baseline_sazonal_simples,
)


def _ctx():
    return pd.DataFrame(
        {
            "estado_alto_risco_t": [1.0, 0.0, 0.0],
            "casos_t": [10, 5, 8],
            "casos_t_menos_1": [8, 6, 3],
            "casos_t_menos_2": [5, 7, 1],
            "casos_t_menos_3": [3, 8, 0],
            "media_historica_semana_exata": [9.0, 6.0, 20.0],
            "media_4s": [6.5, 6.0, 3.0],
        }
    )


def test_baseline_persistencia_replica_estado_atual():
    resultado = baseline_persistencia(_ctx())
    assert resultado.tolist() == [1.0, 0.0, 0.0]


def test_baseline_crescimento_recente_exige_n_semanas_consecutivas():
    resultado = baseline_crescimento_recente(_ctx(), n_semanas=3)
    # linha 0: 10>8>5 -> True ; linha1: 5>6? False ; linha2: 8>3>1 -> True
    assert resultado.tolist() == [1.0, 0.0, 1.0]


def test_baseline_crescimento_recente_rejeita_n_semanas_invalido():
    with pytest.raises(ValueError):
        baseline_crescimento_recente(_ctx(), n_semanas=1)


def test_baseline_sazonal_simples_compara_media_historica():
    resultado = baseline_sazonal_simples(_ctx())
    # linha0: 10>9 True; linha1: 5>6 False; linha2: 8>20 False
    assert resultado.tolist() == [1.0, 0.0, 0.0]


def test_baselines_contagem_retornam_colunas_esperadas():
    ctx = _ctx()
    p1 = baseline_contagem_persistencia(ctx)
    p2 = baseline_contagem_media_movel_4s(ctx)
    assert p1.tolist() == [10.0, 5.0, 8.0]
    assert p2.tolist() == [6.5, 6.0, 3.0]
