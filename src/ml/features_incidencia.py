"""Features baseadas em INCIDÊNCIA — poucas, defensáveis (seção 4 do
pedido), nunca duplicando o que a Gold já calcula
(`src/gold/populacao.py::incidencia_100k`, `incidencia_4s_100k`,
`incidencia_8s_100k`).

## Por que não recalcular janelas móveis de incidência

`incidencia_4s_100k`/`incidencia_8s_100k` já existem na Gold, calculadas
corretamente como "soma de casos na janela / população × 100.000" — nunca
"média das incidências semanais já calculadas" (que infla o resultado,
ver `src/gold/populacao.py`). Recalcular aqui como média de
`incidencia_100k` sobre uma janela seria uma fórmula DIFERENTE e pior —
por isso este módulo só referencia as colunas já existentes, não as
recria.

## Suavização de Laplace: mesma constante de `features.py`, não uma nova

`EPS_RAZAO` (de `features.py`) evita divisão por zero quando o limiar ou o
desvio-padrão histórico é exatamente `0` — o papel dela é ser um guarda
contra zero, não uma escala de suavização proporcional à unidade da
variável. Como incidência e casos têm essa mesma necessidade (limiar pode
ser `0` em bairros/semanas sem histórico de casos), reusar a constante já
vetada evita inventar um novo parâmetro sem justificativa (regra explícita
do pedido: "não inventar margem arbitrária").
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.ml.features import EPS_RAZAO

LAGS_INCIDENCIA = (1, 2, 3, 4)

#: Features de incidência (seção 4 do pedido) — bloco mínimo, sem
#: duplicar `incidencia_4s_100k`/`incidencia_8s_100k` (já na Gold).
FEATURES_INCIDENCIA_BASE = (
    "incidencia_t_100k",
    *(f"incidencia_lag{k}_100k" for k in LAGS_INCIDENCIA),
    "incidencia_4s_100k",
    "incidencia_8s_100k",
    "delta_incidencia",
    "estado_alto_risco_incidencia_t",
)

FEATURES_HISTORICO_LOCAL_INCIDENCIA = (
    "razao_incidencia_historico_local",
    "desvio_incidencia_sazonal",
)

#: População como feature (seção 5) — nunca `codigo_bairro` como variável
#: contínua, nunca população do ano como alvo implícito (só como preditor).
FEATURES_POPULACAO = (
    "log_populacao",
    "densidade_populacional_hab_km2",
)

#: Features sazonais equivalentes a `features.FEATURES_SAZONAIS`, mas com
#: `media_historica_semana_exata` trocada pela versão de incidência —
#: `semana_epidemiologica`/`mes`/`trimestre`/`semana_sin`/`semana_cos` são
#: calendário puro (independentes de casos/incidência) e já existem no
#: DataFrame se `features.construir_features_epidemiologicas_e_sazonais`
#: rodou antes neste pipeline (ver `dataset_incidencia.py`) — não
#: recalculadas aqui.
FEATURES_SAZONAIS_INCIDENCIA = (
    "semana_epidemiologica",
    "mes",
    "trimestre",
    "semana_sin",
    "semana_cos",
    "media_historica_semana_exata_incidencia",
)


def construir_features_incidencia(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona `FEATURES_INCIDENCIA_BASE` + `FEATURES_HISTORICO_LOCAL_INCIDENCIA`
    + `FEATURES_POPULACAO` a `df`.

    Pré-requisitos (já deve ter passado por):
    `target_incidencia.agregar_semanal_agravo_com_populacao` (traz
    `incidencia_100k`/`incidencia_4s_100k`/`incidencia_8s_100k`/
    `populacao_bairro_ano`/`densidade_populacional_hab_km2`) e
    `target_incidencia.calcular_estado_alto_risco_incidencia` (traz
    `limiar_historico_local_incidencia`/`media_historica_semana_exata_incidencia`/
    `std_historica_semana_exata_incidencia`/`estado_alto_risco_incidencia`) e
    `features.construir_indice_semana_global` (traz `indice_semana_global`,
    necessário para os lags respeitarem a ordem cronológica real)."""
    df = df.sort_values(["codigo_bairro", "indice_semana_global"]).reset_index(drop=True)

    df["incidencia_t_100k"] = df["incidencia_100k"]
    grp = df.groupby("codigo_bairro", sort=False)["incidencia_100k"]
    for k in LAGS_INCIDENCIA:
        df[f"incidencia_lag{k}_100k"] = grp.shift(k)

    df["delta_incidencia"] = df["incidencia_t_100k"] - df["incidencia_lag1_100k"]
    df["estado_alto_risco_incidencia_t"] = df["estado_alto_risco_incidencia"]

    df["razao_incidencia_historico_local"] = df["incidencia_t_100k"] / (
        df["limiar_historico_local_incidencia"] + EPS_RAZAO
    )
    df["desvio_incidencia_sazonal"] = (
        df["incidencia_t_100k"] - df["media_historica_semana_exata_incidencia"]
    ) / (df["std_historica_semana_exata_incidencia"] + EPS_RAZAO)

    df["log_populacao"] = np.log1p(df["populacao_bairro_ano"])

    return df
