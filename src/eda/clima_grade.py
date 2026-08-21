"""EDA do bloco climático em **grade** (reanálise) presente na Gold >= 1.1.

Separado de `src/eda/clima.py` (que trata do clima de **estação**) porque as
duas famílias respondem perguntas diferentes e não devem ser misturadas num
mesmo indicador:

| | estação (CEMADEN) | grade (ERA5 / ERA5-Land) |
|---|---|---|
| natureza | leitura de pluviômetro | estimativa de célula de reanálise |
| cobertura temporal | 2024-2025, parcial | todo o período, integral |
| resolução espacial | 16 estações, mediana 1,4 km do bairro | 2-3 células para 94 bairros |
| uso legítimo | medir chuva num ponto | descrever *quando* chove na cidade |

Nenhuma função aqui soma, media ou substitui uma família pela outra.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

COLUNAS_GRADE_PRECIPITACAO = (
    "precipitacao_semana_grade_mm",
    "precipitacao_2s_grade_mm",
    "precipitacao_3s_grade_mm",
    "precipitacao_4s_grade_mm",
)
COLUNAS_GRADE_TEMPERATURA = (
    "temperatura_media_grade_c",
    "temperatura_minima_grade_c",
    "temperatura_maxima_grade_c",
)
COLUNA_GRADE_UMIDADE = "umidade_relativa_media_grade_pct"

COLUNA_DIAS_VALIDOS_GRADE = "dias_validos_precipitacao_grade_semana"

#: Janelas em SEMANAS oferecidas na análise de defasagem com a grade.
#: 1 semana é a própria semana; 2/3/4 são acumulados retrospectivos.
JANELAS_LAG_SEMANAS = (1, 2, 3, 4)

MAPA_JANELA_COLUNA = {
    1: "precipitacao_semana_grade_mm",
    2: "precipitacao_2s_grade_mm",
    3: "precipitacao_3s_grade_mm",
    4: "precipitacao_4s_grade_mm",
}

N_MINIMO_OBSERVACOES_CONFIAVEL = 30


def gold_tem_clima_grade(df_gold: pd.DataFrame) -> bool:
    """`True` se a Gold carregada tem o bloco em grade (versão >= 1.1)."""
    return COLUNA_DIAS_VALIDOS_GRADE in df_gold.columns


def linhas_com_grade(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Linhas com pelo menos um dia válido na grade. Nunca `fillna(0)` nos
    valores — a filtragem usa o contador de dias válidos."""
    if not gold_tem_clima_grade(df_gold):
        return df_gold.iloc[0:0]
    return df_gold[df_gold[COLUNA_DIAS_VALIDOS_GRADE].fillna(0) > 0]


def resumo_cobertura_grade(df_gold: pd.DataFrame) -> dict[str, Any]:
    if not gold_tem_clima_grade(df_gold) or df_gold.empty:
        return {"disponivel": False}
    com_grade = linhas_com_grade(df_gold)
    return {
        "disponivel": True,
        "linhas_totais": int(len(df_gold)),
        "linhas_com_grade": int(len(com_grade)),
        "percentual_linhas": round(100 * len(com_grade) / len(df_gold), 4),
        "anos_cobertos": sorted(int(a) for a in com_grade["ano_epidemiologico"].unique()),
        "celulas_precipitacao": int(com_grade["celula_grade_precipitacao"].nunique())
        if "celula_grade_precipitacao" in com_grade.columns else None,
        "celulas_temperatura": int(com_grade["celula_grade_temperatura"].nunique())
        if "celula_grade_temperatura" in com_grade.columns else None,
        "valores_distintos_por_semana_mediana": float(
            com_grade.groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)[
                "precipitacao_semana_grade_mm"
            ].nunique().median()
        ) if len(com_grade) else None,
    }


def cobertura_dupla_por_ano(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Percentual de bairro × semana com dado, por ano, para as duas
    famílias — a comparação que torna a diferença de cobertura óbvia."""
    colunas = ["ano_epidemiologico", "linhas", "pct_com_grade", "pct_com_estacao"]
    if df_gold.empty:
        return pd.DataFrame(columns=colunas)

    tem_grade = (
        df_gold[COLUNA_DIAS_VALIDOS_GRADE].fillna(0) > 0
        if gold_tem_clima_grade(df_gold)
        else pd.Series(False, index=df_gold.index)
    )
    tem_estacao = (
        df_gold["dias_com_dado_valido_semana"].fillna(0) > 0
        if "dias_com_dado_valido_semana" in df_gold.columns
        else pd.Series(False, index=df_gold.index)
    )
    agrupado = (
        df_gold.assign(_g=tem_grade, _e=tem_estacao)
        .groupby("ano_epidemiologico", observed=True)
        .agg(linhas=("casos", "size"), com_grade=("_g", "sum"), com_estacao=("_e", "sum"))
        .reset_index()
    )
    agrupado["pct_com_grade"] = (100 * agrupado["com_grade"] / agrupado["linhas"]).round(2)
    agrupado["pct_com_estacao"] = (100 * agrupado["com_estacao"] / agrupado["linhas"]).round(2)
    return agrupado[colunas].sort_values("ano_epidemiologico").reset_index(drop=True)


def serie_climatica_grade(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Série semanal da cidade: precipitação, temperatura e umidade médias
    entre os bairros com valor em grade naquela semana."""
    colunas = [
        "ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio",
        "precipitacao_mm", "temperatura_media_c", "temperatura_maxima_c",
        "umidade_relativa_media_pct", "bairros_considerados",
    ]
    com_grade = linhas_com_grade(df_gold)
    if com_grade.empty:
        return pd.DataFrame(columns=colunas)

    # Uma linha por bairro x semana (o clima é igual entre os 3 agravos).
    unico = com_grade.drop_duplicates(
        subset=["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]
    )
    agrupado = (
        unico.groupby(
            ["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"], observed=True
        )
        .agg(
            precipitacao_mm=("precipitacao_semana_grade_mm", "mean"),
            temperatura_media_c=("temperatura_media_grade_c", "mean"),
            temperatura_maxima_c=("temperatura_maxima_grade_c", "mean"),
            umidade_relativa_media_pct=(COLUNA_GRADE_UMIDADE, "mean"),
            bairros_considerados=("codigo_bairro", "nunique"),
        )
        .reset_index()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
    )
    return agrupado[colunas]


def sazonalidade_climatica_grade(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Perfil climático médio por semana epidemiológica (1-53) — a
    sazonalidade da chuva/temperatura que o painel não conseguia mostrar
    antes de existir uma série longa."""
    serie = serie_climatica_grade(df_gold)
    if serie.empty:
        return pd.DataFrame(
            columns=[
                "semana_epidemiologica", "precipitacao_media_mm", "temperatura_media_c",
                "umidade_relativa_media_pct", "anos_observados",
            ]
        )
    return (
        serie.groupby("semana_epidemiologica", observed=True)
        .agg(
            precipitacao_media_mm=("precipitacao_mm", "mean"),
            temperatura_media_c=("temperatura_media_c", "mean"),
            umidade_relativa_media_pct=("umidade_relativa_media_pct", "mean"),
            anos_observados=("ano_epidemiologico", "nunique"),
        )
        .reset_index()
        .sort_values("semana_epidemiologica")
    )


def correlacoes_lag_grade(
    df_gold: pd.DataFrame, janelas: tuple[int, ...] = JANELAS_LAG_SEMANAS
) -> pd.DataFrame:
    """Correlação exploratória (Pearson e Spearman) entre casos e chuva
    acumulada em grade, por janela retrospectiva em semanas.

    **Associação observada, não causalidade.** Devolve sempre o número de
    observações; nenhuma linha é omitida por ser "pouco interessante".
    """
    com_grade = linhas_com_grade(df_gold)
    linhas = []
    for janela in janelas:
        coluna = MAPA_JANELA_COLUNA[janela]
        if coluna not in com_grade.columns:
            continue
        valido = com_grade[com_grade[coluna].notna() & com_grade["casos"].notna()]
        n = len(valido)
        pearson = float(valido["casos"].corr(valido[coluna])) if n >= 2 else None
        spearman = (
            float(valido["casos"].corr(valido[coluna], method="spearman")) if n >= 2 else None
        )
        linhas.append(
            {
                "janela_semanas": janela,
                "janela_dias": janela * 7,
                "n_observacoes": n,
                "correlacao_pearson": round(pearson, 4) if pearson is not None else None,
                "correlacao_spearman": round(spearman, 4) if spearman is not None else None,
                "amostra_suficiente": n >= N_MINIMO_OBSERVACOES_CONFIAVEL,
            }
        )
    return pd.DataFrame(linhas)


def dispersao_lag_grade(df_gold: pd.DataFrame, janela_semanas: int) -> pd.DataFrame:
    if janela_semanas not in MAPA_JANELA_COLUNA:
        raise ValueError(
            f"janela_semanas inválida: {janela_semanas!r} (esperado uma de {JANELAS_LAG_SEMANAS})"
        )
    coluna = MAPA_JANELA_COLUNA[janela_semanas]
    com_grade = linhas_com_grade(df_gold)
    if coluna not in com_grade.columns:
        return pd.DataFrame()
    valido = com_grade[com_grade[coluna].notna() & com_grade["casos"].notna()]
    return valido[
        ["codigo_bairro", "nome_bairro", "ano_epidemiologico", "semana_epidemiologica", "agravo",
         coluna, "casos"]
    ].rename(columns={coluna: "precipitacao_mm"})


def comparar_estacao_com_grade(df_gold: pd.DataFrame) -> Optional[dict[str, Any]]:
    """Concordância entre as duas famílias nas linhas em que ambas existem —
    a única comparação honesta entre elas, e o lugar onde a subestimação da
    reanálise fica visível."""
    if not gold_tem_clima_grade(df_gold) or "precipitacao_total_semana_mm" not in df_gold.columns:
        return None
    ambos = df_gold[
        (df_gold["dias_com_dado_valido_semana"].fillna(0) > 0)
        & (df_gold[COLUNA_DIAS_VALIDOS_GRADE].fillna(0) > 0)
    ].drop_duplicates(subset=["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"])
    if len(ambos) < 3:
        return None
    estacao = ambos["precipitacao_total_semana_mm"]
    grade = ambos["precipitacao_semana_grade_mm"]
    return {
        "n_bairro_semana": int(len(ambos)),
        "pearson": round(float(grade.corr(estacao)), 4),
        "spearman": round(float(grade.corr(estacao, method="spearman")), 4),
        "media_estacao_mm": round(float(estacao.mean()), 2),
        "media_grade_mm": round(float(grade.mean()), 2),
        "razao_grade_sobre_estacao": round(float(grade.sum() / estacao.sum()), 4)
        if estacao.sum() > 0 else None,
        "anos": sorted(int(a) for a in ambos["ano_epidemiologico"].unique()),
    }
