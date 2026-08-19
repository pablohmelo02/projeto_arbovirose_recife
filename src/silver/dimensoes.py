"""Transformação Silver das dimensões (bairro, distrito, agravo, município, UF).

Mapeamento POSICIONAL, não por nome de coluna (ver `schema.py` para o porquê).
Cada dimensão recebe: tipagem para string, normalização textual, remoção de
duplicidade pela chave natural, e validação de que a chave natural não é
nula. Preserva a chave original da fonte — não cria surrogate keys (essas
pertencem ao modelo dimensional da Gold, não à Silver).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.silver.quality import limpar_codigo, limpar_texto
from src.silver.schema import (
    COLUNAS_DIMENSAO_AGRAVO,
    COLUNAS_DIMENSAO_BAIRRO,
    COLUNAS_DIMENSAO_DISTRITO,
    COLUNAS_DIMENSAO_MUNICIPIO,
    COLUNAS_DIMENSAO_UF,
)

# entidade -> (colunas canônicas por posição, índice da chave natural)
_CONFIGURACAO: dict[str, tuple[tuple[str, ...], int]] = {
    "bairro": (COLUNAS_DIMENSAO_BAIRRO, 0),
    "distrito": (COLUNAS_DIMENSAO_DISTRITO, 0),
    "agravo": (COLUNAS_DIMENSAO_AGRAVO, 0),
    "municipio": (COLUNAS_DIMENSAO_MUNICIPIO, 1),
    "uf": (COLUNAS_DIMENSAO_UF, 0),
}

ENTIDADES_DIMENSAO = tuple(_CONFIGURACAO.keys())


def transformar_dimensao(df_bruto: pd.DataFrame, entidade: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Transforma uma dimensão bruta em `(df_conformado, metricas)`."""
    if entidade not in _CONFIGURACAO:
        raise ValueError(f"Dimensão desconhecida: '{entidade}'")

    colunas_canonicas, indice_chave = _CONFIGURACAO[entidade]

    if len(df_bruto.columns) < len(colunas_canonicas):
        raise ValueError(
            f"Dimensão '{entidade}' esperava ao menos {len(colunas_canonicas)} colunas, "
            f"encontrou {len(df_bruto.columns)}"
        )

    df = df_bruto.iloc[:, : len(colunas_canonicas)].copy()
    df.columns = list(colunas_canonicas)
    linhas_lidas = len(df)

    for coluna in df.columns:
        if coluna.startswith("nome_") or coluna.endswith("_sigla") or coluna.startswith("sigla_"):
            df[coluna] = df[coluna].map(limpar_texto)
        else:
            df[coluna] = df[coluna].map(limpar_codigo)

    chave = colunas_canonicas[indice_chave]
    sem_chave = df[chave].isna()
    rejeitados_sem_chave = int(sem_chave.sum())
    df = df.loc[~sem_chave]

    duplicados = df.duplicated(subset=[chave])
    rejeitados_duplicados = int(duplicados.sum())
    df = df.loc[~duplicados].reset_index(drop=True)

    metricas = {
        "entidade": entidade,
        "linhas_lidas": linhas_lidas,
        "linhas_validas": len(df),
        "rejeitados_sem_chave_natural": rejeitados_sem_chave,
        "rejeitados_duplicados": rejeitados_duplicados,
    }

    return df, metricas
