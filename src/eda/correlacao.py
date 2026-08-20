"""Correlação exploratória clima × arboviroses — só sobre linhas com clima
real, sempre reportando o número de observações usadas.

**Correlação não é causalidade** — nenhuma função aqui decide relevância
estatística ou seleciona features para modelagem; isso é uma decisão
humana posterior (ver `reports/eda/README.md`, seção "Observação vs
hipótese").
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.eda.filtros import linhas_com_clima_real
from src.eda.schema_eda import COLUNAS_CLIMA_NUMERICAS, COLUNA_CASOS, JANELAS_LAG_DIAS

N_MINIMO_OBSERVACOES_CONFIAVEL = 30


def compute_lag_correlations(
    df_gold: pd.DataFrame, janelas: tuple[int, ...] = JANELAS_LAG_DIAS
) -> pd.DataFrame:
    """Correlação de Pearson entre `casos` e `chuva_{janela}d_mm`, uma
    linha por janela de lag — só sobre observações com a respectiva coluna
    de dias-válidos > 0 (não sobre linhas sem leitura real, que ficariam
    como `NaN` e seriam descartadas silenciosamente pelo pandas de qualquer
    forma, mas aqui a exclusão é explícita e contada)."""
    linhas = []
    for janela in janelas:
        coluna_chuva = f"chuva_{janela}d_mm"
        coluna_dias_validos = "dias_com_dado_valido_7d" if janela == 7 else (
            "dias_com_dado_valido_28d" if janela == 28 else None
        )
        if coluna_dias_validos is not None:
            valido = df_gold[df_gold[coluna_dias_validos].fillna(0) > 0]
        else:
            valido = df_gold[df_gold[coluna_chuva].notna()]

        n_obs = len(valido)
        correlacao = valido[COLUNA_CASOS].corr(valido[coluna_chuva]) if n_obs >= 2 else None
        linhas.append(
            {
                "janela_dias": janela,
                "n_observacoes": n_obs,
                "correlacao_pearson": round(correlacao, 4) if correlacao is not None else None,
                "confiavel": n_obs >= N_MINIMO_OBSERVACOES_CONFIAVEL,
            }
        )
    return pd.DataFrame(linhas)


def dados_dispersao_lag(df_gold: pd.DataFrame, janela_dias: int) -> pd.DataFrame:
    """Pontos (chuva na janela, casos) para o scatter plot de um lag
    específico — só linhas com leitura real na janela pedida."""
    if janela_dias not in JANELAS_LAG_DIAS:
        raise ValueError(f"janela_dias inválida: {janela_dias!r} (esperado um de {JANELAS_LAG_DIAS})")
    coluna_chuva = f"chuva_{janela_dias}d_mm"
    valido = df_gold[df_gold[coluna_chuva].notna() & df_gold[COLUNA_CASOS].notna()]
    return valido[
        ["codigo_bairro", "nome_bairro", "ano_epidemiologico", "semana_epidemiologica", "agravo", coluna_chuva, COLUNA_CASOS]
    ].rename(columns={coluna_chuva: "precipitacao_mm"})


def matriz_correlacao(df_gold: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Matriz de correlação (Pearson) entre `casos` e as colunas
    climáticas numéricas — nunca inclui códigos/IDs. Calculada só sobre
    linhas com clima real (`linhas_com_clima_real`); retorna também o
    número de observações usadas, para não ser interpretada sem contexto."""
    com_clima = linhas_com_clima_real(df_gold)
    colunas = [COLUNA_CASOS] + list(COLUNAS_CLIMA_NUMERICAS)
    colunas_presentes = [c for c in colunas if c in com_clima.columns]
    matriz = com_clima[colunas_presentes].corr()
    return matriz, len(com_clima)
