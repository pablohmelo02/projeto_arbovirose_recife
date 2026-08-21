"""Baselines obrigatórios do forecast (item 13 do pedido de produto).

Nenhum é "inteligente" — servem de piso de comparação para o ETS no
backtest (`src/forecast/backtest.py`). Todos recebem `serie_treino` (saída
de `dataset.construir_serie_semanal`, restrita a `ano_epidemiologico <=`
corte) e `semanas_alvo` (DataFrame com `ano_epidemiologico`,
`semana_epidemiologica` das semanas a prever) e devolvem uma série de
previsões alinhada a `semanas_alvo.index` — nunca usam dado além do corte
de `serie_treino` (sem vazamento temporal).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sem_vazamento(previsao: pd.Series, media_geral: float) -> pd.Series:
    """Preenche `NaN` (ex.: semana 53 que não existiu no ano usado como
    referência) com a média geral do treino — nunca com 0, que forjaria
    ausência de casos."""
    return previsao.fillna(media_geral).clip(lower=0)


def naive_sazonal(serie_treino: pd.DataFrame, semanas_alvo: pd.DataFrame) -> pd.Series:
    """Valor da mesma semana epidemiológica no último ano disponível em
    `serie_treino`."""
    ultimo_ano = int(serie_treino["ano_epidemiologico"].max())
    referencia = serie_treino[serie_treino["ano_epidemiologico"] == ultimo_ano].set_index(
        "semana_epidemiologica"
    )["casos"]
    previsao = semanas_alvo["semana_epidemiologica"].map(referencia).astype("float64")
    return _sem_vazamento(previsao.reset_index(drop=True), float(serie_treino["casos"].mean()))


def media_historica_semana(serie_treino: pd.DataFrame, semanas_alvo: pd.DataFrame) -> pd.Series:
    """Média de todos os anos de `serie_treino` na mesma semana
    epidemiológica."""
    media_por_semana = serie_treino.groupby("semana_epidemiologica")["casos"].mean()
    previsao = semanas_alvo["semana_epidemiologica"].map(media_por_semana).astype("float64")
    return _sem_vazamento(previsao.reset_index(drop=True), float(serie_treino["casos"].mean()))


def tendencia_sazonal(serie_treino: pd.DataFrame, semanas_alvo: pd.DataFrame) -> pd.Series:
    """Tendência linear sobre `indice_semana` + média sazonal dos resíduos
    por semana epidemiológica (decomposição simples: tendência + sazonal).

    Os índices de `semanas_alvo` são assumidos contíguos ao fim de
    `serie_treino` (a projeção começa imediatamente após o último índice do
    treino) — verdade tanto no backtest (treina até o ano N, prevê o ano
    N+1 completo) quanto na projeção final para 2026 (treina 2013-2025,
    prevê 2026).
    """
    x = serie_treino["indice_semana"].to_numpy(dtype=float)
    y = serie_treino["casos"].to_numpy(dtype=float)
    inclinacao, intercepto = np.polyfit(x, y, 1)
    tendencia_treino = inclinacao * x + intercepto
    residuo = y - tendencia_treino
    media_residuo_semana = (
        pd.Series(residuo, index=serie_treino["semana_epidemiologica"].to_numpy())
        .groupby(level=0)
        .mean()
    )

    ultimo_indice = float(serie_treino["indice_semana"].max())
    indices_alvo = ultimo_indice + 1 + np.arange(len(semanas_alvo))
    tendencia_alvo = inclinacao * indices_alvo + intercepto
    residuo_alvo = (
        semanas_alvo["semana_epidemiologica"].map(media_residuo_semana).astype("float64").to_numpy()
    )
    residuo_alvo = np.where(np.isnan(residuo_alvo), 0.0, residuo_alvo)

    previsao = pd.Series(tendencia_alvo + residuo_alvo).reset_index(drop=True)
    return _sem_vazamento(previsao, float(serie_treino["casos"].mean()))
