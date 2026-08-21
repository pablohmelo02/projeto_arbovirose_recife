"""Único método adicional avaliado no backtest, além dos 3 baselines
obrigatórios (decisão do usuário — ver plano de implementação): Holt-Winters
(ETS) via `statsmodels`. Não SARIMA, não deep learning, não AutoML."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

SEMANAS_SAZONAIS_PADRAO = 52


class SerieCurtaDemaisError(ValueError):
    """A série de treino não tem histórico suficiente para estimar
    sazonalidade — nunca ajustamos ETS "no escuro"."""


def ajustar_ets(
    serie_treino: pd.DataFrame,
    n_semanas_previsao: int,
    semanas_sazonais: int = SEMANAS_SAZONAIS_PADRAO,
) -> tuple[np.ndarray, Any]:
    """Ajusta Holt-Winters aditivo (tendência + sazonalidade) sobre `casos`.

    Devolve `(previsao_central, modelo_ajustado)` — `modelo_ajustado` é
    reaproveitado por `intervalos.banda_ets` para simular a dispersão.
    """
    y = serie_treino["casos"].to_numpy(dtype=float)
    minimo_necessario = 2 * semanas_sazonais
    if len(y) < minimo_necessario:
        raise SerieCurtaDemaisError(
            f"série de treino com {len(y)} observações é curta demais para sazonalidade de "
            f"{semanas_sazonais} semanas (precisa de ao menos {minimo_necessario})"
        )
    modelo = ExponentialSmoothing(
        y,
        trend="add",
        seasonal="add",
        seasonal_periods=semanas_sazonais,
        initialization_method="estimated",
    ).fit()
    previsao = np.asarray(modelo.forecast(n_semanas_previsao))
    return np.clip(previsao, a_min=0, a_max=None), modelo


def ajustar_ets_previsao(serie_treino: pd.DataFrame, semanas_alvo: pd.DataFrame) -> np.ndarray:
    """Adaptador de `ajustar_ets` para a assinatura `ModeloForecast` usada
    pelo backtest (`src/forecast/backtest.py`) — descarta o modelo
    ajustado, só a previsão central."""
    previsao, _modelo = ajustar_ets(serie_treino, len(semanas_alvo))
    return previsao
