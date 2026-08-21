"""Baselines de ranking baseados em INCIDÊNCIA — paralelos aos 3 já usados
para o candidato V1 (`casos_atuais`, `crescimento_recente`,
`razao_historica_local`, ver `src/validate_dengue_onset_ranking_evidence.py:106-108`).
A V2 precisa superar tanto os baselines de casos quanto estes (seção 17 do
pedido) — nenhum deles usa modelo, todos são scores contínuos determinísticos
lidos direto de `df_contexto` (mesmo padrão de `baselines.py`)."""
from __future__ import annotations

import pandas as pd


def baseline_incidencia_atual(df_contexto: pd.DataFrame) -> pd.Series:
    """Rank por `incidencia_t_100k` — equivalente de incidência do
    baseline `casos_atuais`."""
    return df_contexto["incidencia_t_100k"].rename("baseline_incidencia_atual")


def baseline_crescimento_incidencia(df_contexto: pd.DataFrame) -> pd.Series:
    """Rank por `delta_incidencia` (incidência da semana menos a da semana
    anterior) — equivalente de incidência do baseline `crescimento_recente`."""
    return df_contexto["delta_incidencia"].rename("baseline_crescimento_incidencia")


def baseline_razao_historica_incidencia(df_contexto: pd.DataFrame) -> pd.Series:
    """Rank por `razao_incidencia_historico_local` — equivalente de
    incidência do baseline `razao_historica_local`."""
    return df_contexto["razao_incidencia_historico_local"].rename("baseline_razao_historica_incidencia")
