import numpy as np
import pandas as pd

from src.ml.evaluation import brier_score
from src.ml.models import calibrar_probabilidade, treinar_arvore


def _dataset_sintetico(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        {
            "f1": rng.normal(size=n),
            "f2": rng.normal(size=n),
        }
    )
    logit = 1.5 * X["f1"] - 0.5 * X["f2"]
    prob_real = 1 / (1 + np.exp(-logit))
    y = pd.Series((rng.uniform(size=n) < prob_real).astype(int))
    return X, y


def test_brier_score_e_zero_para_previsao_perfeita():
    y_true = pd.Series([1, 0, 1, 0])
    y_proba = pd.Series([1.0, 0.0, 1.0, 0.0])
    assert brier_score(y_true, y_proba) == 0.0


def test_brier_score_penaliza_confianca_errada():
    y_true = pd.Series([1, 0])
    proba_confiante_errada = pd.Series([0.0, 1.0])
    proba_incerta = pd.Series([0.5, 0.5])
    assert brier_score(y_true, proba_confiante_errada) > brier_score(y_true, proba_incerta)


def test_calibrar_probabilidade_usa_apenas_validacao_e_produz_probabilidades_validas():
    X_treino, y_treino = _dataset_sintetico(seed=1)
    X_val, y_val = _dataset_sintetico(seed=2)
    modelo = treinar_arvore(X_treino, y_treino)
    calibrado = calibrar_probabilidade(modelo, X_val, y_val, metodo="sigmoid")
    proba = calibrado.predict_proba(X_val)[:, 1]
    assert (proba >= 0).all() and (proba <= 1).all()
    assert len(proba) == len(X_val)


def test_calibracao_e_deterministica():
    X_treino, y_treino = _dataset_sintetico(seed=1)
    X_val, y_val = _dataset_sintetico(seed=2)
    modelo = treinar_arvore(X_treino, y_treino)
    calibrado_a = calibrar_probabilidade(modelo, X_val, y_val, metodo="sigmoid")
    calibrado_b = calibrar_probabilidade(modelo, X_val, y_val, metodo="sigmoid")
    proba_a = calibrado_a.predict_proba(X_val)[:, 1]
    proba_b = calibrado_b.predict_proba(X_val)[:, 1]
    np.testing.assert_allclose(proba_a, proba_b)
