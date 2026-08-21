"""Episódios e onset baseados em INCIDÊNCIA — reusa
`alert_metrics.construir_episodios` e `onset.construir_target_onset` sem
alteração (ambos hardcodam a coluna `estado_alto_risco`, por isso a
substituição é feita aqui por troca temporária de coluna, mesmo princípio
de `target_incidencia.py`).

`casos_totais_episodio`/`casos_pico` dos episódios de incidência continuam
sendo a contagem ABSOLUTA real de casos dentro do episódio (a coluna
`casos` nunca é sobrescrita) — é exatamente o que a seção 12 do pedido
precisa: "para cada caso (episódio de incidência), mostrar casos,
população, incidência".
"""
from __future__ import annotations

import pandas as pd

from src.ml.alert_metrics import construir_episodios
from src.ml.onset import HORIZONTES_ONSET, construir_target_onset


def construir_episodios_incidencia(df_com_estado_incidencia: pd.DataFrame) -> pd.DataFrame:
    """`df_com_estado_incidencia` precisa ter `estado_alto_risco_incidencia`
    (ver `target_incidencia.calcular_estado_alto_risco_incidencia`) e as
    colunas exigidas por `alert_metrics.construir_episodios`."""
    entrada = df_com_estado_incidencia.copy()
    entrada["estado_alto_risco"] = df_com_estado_incidencia["estado_alto_risco_incidencia"]
    return construir_episodios(entrada)


def construir_target_onset_incidencia(
    df_com_estado_incidencia: pd.DataFrame, horizontes: tuple[int, ...] = HORIZONTES_ONSET
) -> pd.DataFrame:
    """Como `construir_episodios_incidencia`, mas devolve
    `df_com_estado_incidencia` com `target_onset_incidencia_h{N}`
    adicionadas (renomeadas a partir de `onset.construir_target_onset`,
    que produz `target_onset_h{N}` sobre `estado_alto_risco`)."""
    entrada = df_com_estado_incidencia.copy()
    entrada["estado_alto_risco"] = df_com_estado_incidencia["estado_alto_risco_incidencia"]
    calculado = construir_target_onset(entrada, horizontes=horizontes)

    saida = df_com_estado_incidencia.copy()
    for h in horizontes:
        saida[f"target_onset_incidencia_h{h}"] = calculado[f"target_onset_h{h}"].to_numpy()
    return saida
