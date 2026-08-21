import pandas as pd

from src.ml.baselines_incidencia import (
    baseline_crescimento_incidencia,
    baseline_incidencia_atual,
    baseline_razao_historica_incidencia,
)


def _ctx() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "incidencia_t_100k": [10.0, 20.0],
            "delta_incidencia": [1.0, -2.0],
            "razao_incidencia_historico_local": [0.5, 3.0],
        }
    )


def test_baseline_incidencia_atual_le_a_coluna_correta():
    resultado = baseline_incidencia_atual(_ctx())
    assert list(resultado) == [10.0, 20.0]
    assert resultado.name == "baseline_incidencia_atual"


def test_baseline_crescimento_incidencia_le_delta():
    resultado = baseline_crescimento_incidencia(_ctx())
    assert list(resultado) == [1.0, -2.0]


def test_baseline_razao_historica_incidencia_le_razao():
    resultado = baseline_razao_historica_incidencia(_ctx())
    assert list(resultado) == [0.5, 3.0]
