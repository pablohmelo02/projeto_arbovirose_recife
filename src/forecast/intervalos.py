"""Bandas de previsão 80%/95% (item 17 do pedido: nenhuma projeção é
publicada como linha única).

Baselines não têm distribuição de erro nativa — a banda vem dos quantis
empíricos dos erros observados no backtest do próprio modelo/agravo. O ETS
tem simulação de trajetórias nativa do `statsmodels`, usada quando o
modelo ajustado está disponível; do contrário cai no mesmo método empírico
dos baselines (documentado no retorno via `metodo`).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

NIVEIS_PADRAO = (0.80, 0.95)


def banda_empirica(
    previsao_central: np.ndarray, erros_backtest: np.ndarray, niveis: tuple[float, ...] = NIVEIS_PADRAO
) -> dict[str, Any]:
    """`erros_backtest` = amostra de erros (observado − previsto) de dobras
    passadas do mesmo modelo/agravo. Com menos de 2 erros, a banda colapsa
    na própria previsão central (não há amostra para estimar dispersão) —
    marcado em `metodo`."""
    resultado: dict[str, Any] = {"central": np.asarray(previsao_central, dtype=float), "metodo": "empirica"}
    erros = np.asarray(erros_backtest, dtype=float)
    if erros.size < 2:
        resultado["metodo"] = "empirica_sem_amostra_suficiente"
        for nivel in niveis:
            pct = int(round(nivel * 100))
            resultado[f"banda_{pct}_inferior"] = resultado["central"]
            resultado[f"banda_{pct}_superior"] = resultado["central"]
        return resultado

    for nivel in niveis:
        alpha = 1 - nivel
        inferior = np.quantile(erros, alpha / 2)
        superior = np.quantile(erros, 1 - alpha / 2)
        pct = int(round(nivel * 100))
        resultado[f"banda_{pct}_inferior"] = np.clip(resultado["central"] + inferior, a_min=0, a_max=None)
        resultado[f"banda_{pct}_superior"] = resultado["central"] + superior
    return resultado


def banda_ets(
    modelo_ajustado: Optional[Any],
    n_semanas_previsao: int,
    niveis: tuple[float, ...] = NIVEIS_PADRAO,
    n_simulacoes: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Simulação de trajetórias do próprio `statsmodels`
    (`HoltWintersResults.simulate`) — método suportado nativamente pela
    lib, não uma aproximação nossa."""
    previsao = np.clip(np.asarray(modelo_ajustado.forecast(n_semanas_previsao)), a_min=0, a_max=None)
    resultado: dict[str, Any] = {"central": previsao, "metodo": "simulacao_ets"}

    rng = np.random.RandomState(seed)
    simulacoes = modelo_ajustado.simulate(n_semanas_previsao, repetitions=n_simulacoes, error="add", random_state=rng)
    simulacoes = np.clip(np.asarray(simulacoes), a_min=0, a_max=None)

    for nivel in niveis:
        alpha = 1 - nivel
        pct = int(round(nivel * 100))
        resultado[f"banda_{pct}_inferior"] = np.quantile(simulacoes, alpha / 2, axis=1)
        resultado[f"banda_{pct}_superior"] = np.quantile(simulacoes, 1 - alpha / 2, axis=1)
    return resultado
