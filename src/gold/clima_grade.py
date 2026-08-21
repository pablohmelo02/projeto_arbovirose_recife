"""Features climáticas em grade no grão da Gold (`bairro × semana
epidemiológica`), derivadas de `silver_clima_grade_diario`.

Complementa — nunca substitui — as features de estação já existentes em
`arboviroses_clima.py::calcular_features_climaticas`. As duas famílias de
colunas coexistem na Gold com prefixos distintos e nunca são somadas,
mediadas ou usadas uma no lugar da outra:

| família  | colunas                     | origem                              |
|----------|-----------------------------|-------------------------------------|
| estação  | `precipitacao_total_semana_mm`, `chuva_*d_mm`, ... | sensor CEMADEN, 2024-2025 |
| grade    | `*_grade_*`                 | reanálise ERA5/ERA5-Land, 2013-2025 |

## Regra de leakage — idêntica à da camada de estação

Toda feature de uma linha usa somente dias com
`data <= semana_epi_data_fim` da própria linha. As janelas acumuladas de
2/3/4 semanas são janelas móveis **terminando** em `semana_epi_data_fim`
(incluem a própria semana; nunca um dia posterior). Testado por injeção
adversarial de chuva futura.

## Quantidade de variáveis: deliberadamente pequena

Onze colunas, não dezenas: precipitação semanal + 3 acumulados
(2/3/4 semanas), temperatura média/mínima/máxima, umidade relativa média,
e dois contadores de dias válidos + cobertura. A umidade relativa **não é
derivada** por este projeto — vem pronta do provedor (`relative_humidity_2m_mean`
do ERA5-Land); nenhuma fórmula psicrométrica é aplicada aqui.

## `missing != 0` preservado

Semana sem nenhum dia válido fica `None` nas colunas de valor (mm, °C, %) e
`0` nos contadores de dias válidos (uma contagem de zero dias é um fato
conhecido, não um "não sei") — exatamente a mesma distinção já adotada na
camada de estação.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.silver.schema_climate_grade import GRADE_PRECIPITACAO, GRADE_TEMPERATURA

logger = logging.getLogger(__name__)

#: Acumulados de precipitação em semanas (não em dias) — o pedido do produto
#: fala em "precipitação acumulada 2/3/4 semanas", e semana epidemiológica
#: tem exatamente 7 dias, então 2 semanas = janela móvel de 14 dias.
JANELAS_SEMANAS_ACUMULADO = (2, 3, 4)

COLUNAS_GOLD_CLIMA_GRADE = (
    "fonte_clima_grade",
    "celula_grade_precipitacao",
    "celula_grade_temperatura",
    "precipitacao_semana_grade_mm",
    *(f"precipitacao_{n}s_grade_mm" for n in JANELAS_SEMANAS_ACUMULADO),
    "temperatura_media_grade_c",
    "temperatura_minima_grade_c",
    "temperatura_maxima_grade_c",
    "umidade_relativa_media_grade_pct",
    "dias_validos_precipitacao_grade_semana",
    "dias_validos_temperatura_grade_semana",
    "cobertura_grade_semana",
)


def _serie_diaria_por_celula(
    df_celula: pd.DataFrame,
    coluna_valor: str,
    data_minima: pd.Timestamp,
    data_maxima: pd.Timestamp,
) -> pd.Series:
    """Série diária contínua de uma célula, com `NaN` nos dias sem valor
    (reindexação explícita — nunca `fillna(0)`)."""
    serie = df_celula.set_index(pd.to_datetime(df_celula["data"]))[coluna_valor].sort_index()
    serie = serie[~serie.index.duplicated(keep="last")]
    return serie.reindex(pd.date_range(data_minima, data_maxima, freq="D"))


def calcular_features_clima_grade(
    df_grao: pd.DataFrame,
    df_bairro_celula: pd.DataFrame,
    df_grade_diario: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Adiciona `COLUNAS_GOLD_CLIMA_GRADE` a `df_grao`.

    `df_grao` precisa ter `codigo_bairro`, `semana_epi_data_inicio`,
    `semana_epi_data_fim`. `df_bairro_celula` é `silver_bairro_celula_grade`
    (uma linha por bairro × grade). `df_grade_diario` é
    `silver_clima_grade_diario`.
    """
    df = df_grao.copy()

    celula_precip = (
        df_bairro_celula[df_bairro_celula["grade"] == GRADE_PRECIPITACAO]
        .set_index("codigo_bairro")["celula_id"]
    )
    celula_temp = (
        df_bairro_celula[df_bairro_celula["grade"] == GRADE_TEMPERATURA]
        .set_index("codigo_bairro")["celula_id"]
    )
    df["celula_grade_precipitacao"] = df["codigo_bairro"].map(celula_precip)
    df["celula_grade_temperatura"] = df["codigo_bairro"].map(celula_temp)

    colunas_valor = [
        "precipitacao_semana_grade_mm",
        *(f"precipitacao_{n}s_grade_mm" for n in JANELAS_SEMANAS_ACUMULADO),
        "temperatura_media_grade_c",
        "temperatura_minima_grade_c",
        "temperatura_maxima_grade_c",
        "umidade_relativa_media_grade_pct",
    ]
    for coluna in colunas_valor:
        df[coluna] = np.nan
    df["dias_validos_precipitacao_grade_semana"] = np.nan
    df["dias_validos_temperatura_grade_semana"] = np.nan

    if df_grade_diario.empty or df.empty:
        df["fonte_clima_grade"] = None
        df["cobertura_grade_semana"] = np.nan
        return df, {
            "linhas_com_precipitacao_grade": 0,
            "linhas_com_temperatura_grade": 0,
            "percentual_linhas_com_clima_grade": 0.0,
            "celulas_precipitacao_distintas": 0,
            "celulas_temperatura_distintas": 0,
        }

    max_dias_retro = 7 * max(JANELAS_SEMANAS_ACUMULADO)
    data_minima = pd.Timestamp(df["semana_epi_data_inicio"].min()) - pd.Timedelta(days=max_dias_retro)
    data_maxima = pd.Timestamp(df["semana_epi_data_fim"].max())

    # ---------------- precipitação (grade ERA5) ----------------
    grade_p = df_grade_diario[df_grade_diario["grade"] == GRADE_PRECIPITACAO]
    for celula_id, idx in df.groupby("celula_grade_precipitacao", dropna=True).groups.items():
        dados = grade_p[grade_p["celula_id"] == celula_id]
        if dados.empty:
            continue
        serie = _serie_diaria_por_celula(dados, "precipitacao_mm", data_minima, data_maxima)

        janelas = {"semana": serie.rolling(window=7, min_periods=1).sum()}
        for n in JANELAS_SEMANAS_ACUMULADO:
            janelas[f"{n}s"] = serie.rolling(window=7 * n, min_periods=1).sum()
        dias_validos = serie.notna().rolling(window=7, min_periods=1).sum()

        datas_fim = pd.to_datetime(df.loc[idx, "semana_epi_data_fim"])
        df.loc[idx, "precipitacao_semana_grade_mm"] = janelas["semana"].reindex(datas_fim.values).to_numpy()
        for n in JANELAS_SEMANAS_ACUMULADO:
            df.loc[idx, f"precipitacao_{n}s_grade_mm"] = janelas[f"{n}s"].reindex(datas_fim.values).to_numpy()
        df.loc[idx, "dias_validos_precipitacao_grade_semana"] = dias_validos.reindex(datas_fim.values).to_numpy()

    # ---------------- temperatura/umidade (grade ERA5-Land) ----------------
    grade_t = df_grade_diario[df_grade_diario["grade"] == GRADE_TEMPERATURA]
    for celula_id, idx in df.groupby("celula_grade_temperatura", dropna=True).groups.items():
        dados = grade_t[grade_t["celula_id"] == celula_id]
        if dados.empty:
            continue
        serie_media = _serie_diaria_por_celula(dados, "temperatura_media_c", data_minima, data_maxima)
        serie_min = _serie_diaria_por_celula(dados, "temperatura_minima_c", data_minima, data_maxima)
        serie_max = _serie_diaria_por_celula(dados, "temperatura_maxima_c", data_minima, data_maxima)
        serie_umid = _serie_diaria_por_celula(dados, "umidade_relativa_media_pct", data_minima, data_maxima)

        media_7 = serie_media.rolling(window=7, min_periods=1).mean()
        # `temperatura_minima_grade_c` da semana = a MENOR mínima diária da
        # semana (não a média das mínimas) -- e simétrico para a máxima.
        min_7 = serie_min.rolling(window=7, min_periods=1).min()
        max_7 = serie_max.rolling(window=7, min_periods=1).max()
        umid_7 = serie_umid.rolling(window=7, min_periods=1).mean()
        dias_validos_t = serie_media.notna().rolling(window=7, min_periods=1).sum()

        datas_fim = pd.to_datetime(df.loc[idx, "semana_epi_data_fim"])
        df.loc[idx, "temperatura_media_grade_c"] = media_7.reindex(datas_fim.values).to_numpy()
        df.loc[idx, "temperatura_minima_grade_c"] = min_7.reindex(datas_fim.values).to_numpy()
        df.loc[idx, "temperatura_maxima_grade_c"] = max_7.reindex(datas_fim.values).to_numpy()
        df.loc[idx, "umidade_relativa_media_grade_pct"] = umid_7.reindex(datas_fim.values).to_numpy()
        df.loc[idx, "dias_validos_temperatura_grade_semana"] = dias_validos_t.reindex(datas_fim.values).to_numpy()

    # Contadores: 0 é fato conhecido quando a célula existe; None quando o
    # bairro não tem célula associada nenhuma.
    tem_celula_p = df["celula_grade_precipitacao"].notna()
    tem_celula_t = df["celula_grade_temperatura"].notna()
    df.loc[tem_celula_p & df["dias_validos_precipitacao_grade_semana"].isna(), "dias_validos_precipitacao_grade_semana"] = 0
    df.loc[tem_celula_t & df["dias_validos_temperatura_grade_semana"].isna(), "dias_validos_temperatura_grade_semana"] = 0

    df["cobertura_grade_semana"] = (df["dias_validos_precipitacao_grade_semana"] / 7).round(3)
    df["fonte_clima_grade"] = np.where(tem_celula_p | tem_celula_t, "ERA5/ERA5-LAND", None)

    n_precip = int(df["dias_validos_precipitacao_grade_semana"].fillna(0).gt(0).sum())
    n_temp = int(df["dias_validos_temperatura_grade_semana"].fillna(0).gt(0).sum())
    metricas = {
        "linhas_com_precipitacao_grade": n_precip,
        "linhas_com_temperatura_grade": n_temp,
        "percentual_linhas_com_clima_grade": round(100 * n_precip / len(df), 4) if len(df) else 0.0,
        "celulas_precipitacao_distintas": int(df["celula_grade_precipitacao"].nunique()),
        "celulas_temperatura_distintas": int(df["celula_grade_temperatura"].nunique()),
    }
    return df, metricas
