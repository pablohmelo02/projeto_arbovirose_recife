"""Série semanal Recife-total por agravo, base do forecast 2026.

Grão: `ano_epidemiologico × semana_epidemiologica`, um agravo por chamada
(nunca "Todas as arboviroses" somadas — cada doença tem sazonalidade e
processo distintos, ver item 15 do pedido de produto: somar as três não
produziria uma série cujo baseline sazonal/ETS tivesse sentido).

Só Recife total (nunca bairro/RPA) — mesma razão de
`src/eda/associacao_climatica.py`: a granularidade fina não é o objetivo
aqui, e a série de casos por bairro é curta e ruidosa demais para
sazonalidade/ETS estáveis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.eda.schema_eda import AGRAVOS
from src.gold.populacao import incidencia_100k

#: Último ano com caso observado verificado na fonte oficial (CKAN,
#: `dados.recife.pe.gov.br`) — verificado ao vivo nesta sessão (2026-08-21):
#: os recursos mais recentes do dataset são rotulados 2025, nenhum recurso
#: 2026 existe (ver `reports/forecast/arbovirus_2026_projection.md`).
#: Atualizar esta constante SÓ depois de reverificar a fonte oficial — o
#: objetivo é que uma Gold que um dia passe a ter 2026 real force uma
#: revisão deliberada deste módulo, em vez de ser silenciosamente tratada
#: como "mais um ano de treino".
ULTIMO_ANO_HISTORICO_VALIDADO = 2025


class DadoFuturoInesperadoError(ValueError):
    """A Gold recebida tem `ano_epidemiologico` além do último ano
    verificado como observado — ver `ULTIMO_ANO_HISTORICO_VALIDADO`."""


def garantir_sem_observado_futuro(
    df_gold: pd.DataFrame, ano_limite: int = ULTIMO_ANO_HISTORICO_VALIDADO
) -> None:
    """Levanta `DadoFuturoInesperadoError` se a Gold tiver alguma linha com
    `ano_epidemiologico > ano_limite` — guarda contra tratar uma futura
    atualização da fonte (ex.: 2026 real aparecendo) como observado sem
    revisão deliberada do código do forecast."""
    if "ano_epidemiologico" not in df_gold.columns or df_gold.empty:
        return
    anos_alem = sorted(int(a) for a in df_gold["ano_epidemiologico"].dropna().unique() if a > ano_limite)
    if anos_alem:
        raise DadoFuturoInesperadoError(
            f"Gold contém ano(s) epidemiológico(s) {anos_alem} além do último ano verificado "
            f"como observado ({ano_limite}). Revise ULTIMO_ANO_HISTORICO_VALIDADO e a fonte "
            "oficial antes de tratar esses dados como observados no forecast."
        )


COLUNAS_SERIE = (
    "ano_epidemiologico",
    "semana_epidemiologica",
    "indice_semana",
    "semana_epi_data_inicio",
    "casos",
    "incidencia_100k",
)


def construir_serie_semanal(df_gold: pd.DataFrame, agravo: str) -> pd.DataFrame:
    """Casos e incidência semanais Recife-total para `agravo`.

    `incidencia_100k` é `casos_totais_da_semana / populacao_total_da_cidade
    naquele ano * 100000` — uma única divisão sobre os agregados, nunca a
    soma de incidências por bairro já calculadas. Fica `NaN` se
    `populacao_bairro_ano` não estiver na Gold recebida (ex.: fixture de
    teste sem população) — nunca `0`/`inf`.

    `indice_semana` é um índice inteiro contíguo (0, 1, 2, ...) ordenado por
    (ano, semana), necessário para `.shift()`/ajuste de tendência em séries
    que atravessam a virada do ano epidemiológico (52 ou 53 semanas).
    """
    if agravo not in AGRAVOS:
        raise ValueError(f"agravo inválido: {agravo!r} (esperado um de {AGRAVOS})")
    garantir_sem_observado_futuro(df_gold)

    df = df_gold[df_gold["agravo"] == agravo]
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_SERIE)

    casos = (
        df.groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)
        .agg(
            casos=("casos", "sum"),
            semana_epi_data_inicio=("semana_epi_data_inicio", "first"),
        )
        .reset_index()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
        .reset_index(drop=True)
    )
    casos["indice_semana"] = range(len(casos))

    if "populacao_bairro_ano" in df.columns:
        populacao_por_ano = (
            df[["codigo_bairro", "ano_epidemiologico", "populacao_bairro_ano"]]
            .drop_duplicates(["codigo_bairro", "ano_epidemiologico"])
            .groupby("ano_epidemiologico", observed=True)["populacao_bairro_ano"]
            .sum()
        )
        populacao_total = casos["ano_epidemiologico"].map(populacao_por_ano)
        casos["incidencia_100k"] = incidencia_100k(casos["casos"], populacao_total)
    else:
        casos["incidencia_100k"] = np.nan

    return casos[list(COLUNAS_SERIE)]
