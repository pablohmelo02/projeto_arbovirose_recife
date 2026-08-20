"""Primeiro modelo interpretável (Logistic Regression) e primeiro modelo de
árvores (HistGradientBoostingClassifier) — sem tuning extensivo, sem
ensemble (regra de parada da etapa).

`HistGradientBoostingClassifier` foi escolhido entre as opções da seção 24
(Random Forest / HistGradientBoosting / XGBoost / LightGBM) por já vir no
`scikit-learn` (única dependência nova desta etapa, ver `requirements.txt`)
e por lidar nativamente com `NaN` — importante para o experimento
BASE+CLIMA, onde features de chuva têm ausência real (`missing != 0`, nunca
`fillna(0)`, ver `src/gold/`) sem exigir uma escolha de imputação que
poderia, ela mesma, introduzir viés na comparação BASE x BASE+CLIMA (seção
45 do pedido). `LogisticRegression` não tolera `NaN`; por isso o
experimento climático (seção 15/45) usa exclusivamente o modelo de árvore —
ver `reports/ml/dengue_early_warning_baseline.md`.

Desbalanceamento (seção 25): ambos os modelos usam `sample_weight`
balanceado por classe (`class_weight="balanced"` via
`sklearn.utils.class_weight.compute_sample_weight`) — não oversampling,
nunca aplicado antes do split (treinado só sobre `X_train`/`y_train`).
"""
from __future__ import annotations

from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

RANDOM_STATE = 42


def treinar_logistic_regression(X_train, y_train) -> Pipeline:
    """Regressão logística com padronização (necessária para LR convergir
    de forma estável com features em escalas muito diferentes — ex.:
    `area_km2` vs `semana_sin`). `class_weight="balanced"` compensa o
    desbalanceamento sem reamostrar linhas."""
    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


HIPERPARAMETROS_PADRAO_ARVORE = {"max_iter": 200, "max_depth": 6, "learning_rate": 0.1}
"""Hiperparâmetros usados na etapa de baseline (`dengue_early_warning_baseline.md`)
— mantidos como padrão de `treinar_arvore` para não quebrar reprodutibilidade
de quem chama sem argumentos. A etapa de otimização testa um espaço pequeno
em torno deste ponto (ver `GRADE_HIPERPARAMETROS_CONTROLADA` no entry point
`src/optimize_dengue_early_warning.py`), nunca um GridSearch irrestrito."""


def treinar_arvore(X_train, y_train, **hiperparametros) -> HistGradientBoostingClassifier:
    """`HistGradientBoostingClassifier` — aceita `NaN` diretamente em
    `X_train`, então não precisa de imputação (ver docstring do módulo).
    `hiperparametros` sobrepõe `HIPERPARAMETROS_PADRAO_ARVORE` (usado sem
    argumentos extras, reproduz exatamente o modelo da etapa de
    baseline)."""
    params = {**HIPERPARAMETROS_PADRAO_ARVORE, **hiperparametros}
    pesos = compute_sample_weight(class_weight="balanced", y=y_train)
    modelo = HistGradientBoostingClassifier(random_state=RANDOM_STATE, **params)
    modelo.fit(X_train, y_train, sample_weight=pesos)
    return modelo


def prever_probabilidade(modelo, X) -> "pd.Series":  # type: ignore[name-defined]
    import pandas as pd

    proba = modelo.predict_proba(X)[:, 1]
    return pd.Series(proba, index=X.index, name="probabilidade")


def calibrar_probabilidade(modelo, X_val, y_val, metodo: str = "isotonic") -> CalibratedClassifierCV:
    """Calibra a probabilidade de um modelo JÁ TREINADO usando somente a
    VALIDAÇÃO (nunca o teste, regra explícita do pedido — seção 24/"Não
    calibre no teste"). `FrozenEstimator` marca `modelo` como já ajustado —
    `CalibratedClassifierCV` usa `X_val`/`y_val` só para o ajuste da curva
    de calibração, não re-treina os pesos do classificador de base.

    `metodo="isotonic"` é não-paramétrico (mais flexível, mas precisa de
    volume razoável de validação para não sobreajustar a própria
    calibração); `"sigmoid"` (Platt scaling) é paramétrico e mais estável
    com pouco dado. A escolha entre os dois é reportada no relatório junto
    com o tamanho da validação disponível."""
    calibrado = CalibratedClassifierCV(FrozenEstimator(modelo), method=metodo)
    calibrado.fit(X_val, y_val)
    return calibrado
