"""EDA da cobertura e dos valores climáticos reais na Gold.

Toda função aqui só considera dado real (`dias_com_dado_valido_semana > 0`
quando relevante) — nunca preenche ausência de leitura com `0`
(`missing ≠ 0 mm`, regra inegociável do projeto, ver CLAUDE.md §5).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.eda.filtros import linhas_com_clima_real


def resumo_cobertura_climatica(df_gold: pd.DataFrame) -> dict[str, Any]:
    """KPIs de cobertura climática real do recorte recebido."""
    com_clima = linhas_com_clima_real(df_gold)
    total_bairros = df_gold["codigo_bairro"].nunique()
    return {
        "total_linhas": len(df_gold),
        "linhas_com_clima_real": len(com_clima),
        "percentual_linhas_com_clima_real": (
            round(100 * len(com_clima) / len(df_gold), 4) if len(df_gold) else 0.0
        ),
        "bairros_com_clima_real": int(com_clima["codigo_bairro"].nunique()),
        "total_bairros": int(total_bairros),
        "percentual_bairros_com_clima_real": (
            round(100 * com_clima["codigo_bairro"].nunique() / total_bairros, 2) if total_bairros else 0.0
        ),
        "anos_com_clima_real": sorted(com_clima["ano_epidemiologico"].unique().tolist()),
        "estacoes_distintas": int(com_clima["codigo_estacao_clima"].nunique()),
        "fontes_climaticas": sorted(com_clima["fonte_clima"].dropna().unique().tolist()),
    }


def cobertura_por_ano(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Para cada ano epidemiológico do recorte: linhas totais, linhas com
    clima real, bairros com clima real — nunca força 94/94 nem esconde
    anos com 0% (ver README/CLAUDE.md: 2013-2023 devem aparecer como 0%,
    não como ausentes da tabela)."""
    colunas = [
        "ano_epidemiologico", "linhas", "linhas_com_clima_real",
        "percentual_linhas_com_clima_real", "bairros_com_clima_real",
        "percentual_bairros_com_clima_real",
    ]
    if df_gold.empty:
        return pd.DataFrame(columns=colunas)

    linhas = []
    for ano, grupo in df_gold.groupby("ano_epidemiologico", observed=True):
        com_clima = linhas_com_clima_real(grupo)
        total_bairros = grupo["codigo_bairro"].nunique()
        linhas.append(
            {
                "ano_epidemiologico": int(ano),
                "linhas": len(grupo),
                "linhas_com_clima_real": len(com_clima),
                "percentual_linhas_com_clima_real": (
                    round(100 * len(com_clima) / len(grupo), 4) if len(grupo) else 0.0
                ),
                "bairros_com_clima_real": int(com_clima["codigo_bairro"].nunique()),
                "percentual_bairros_com_clima_real": (
                    round(100 * com_clima["codigo_bairro"].nunique() / total_bairros, 2) if total_bairros else 0.0
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values("ano_epidemiologico").reset_index(drop=True)


def cobertura_por_bairro(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Para cada bairro do recorte: quantas semanas têm clima real e qual
    o percentual sobre o total de semanas do recorte — base do ranking de
    completude por bairro."""
    colunas = ["codigo_bairro", "nome_bairro", "semanas_com_clima_real", "percentual_semanas_com_clima_real"]
    if df_gold.empty:
        return pd.DataFrame(columns=colunas)

    total_semanas = df_gold[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0]
    linhas = []
    for (codigo, nome), grupo in df_gold.groupby(["codigo_bairro", "nome_bairro"], observed=True):
        com_clima = linhas_com_clima_real(grupo)
        linhas.append(
            {
                "codigo_bairro": codigo,
                "nome_bairro": nome,
                "semanas_com_clima_real": len(com_clima),
                "percentual_semanas_com_clima_real": (
                    round(100 * len(com_clima) / total_semanas, 2) if total_semanas else 0.0
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values("percentual_semanas_com_clima_real", ascending=False).reset_index(drop=True)


def cobertura_ano_semana(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Grade (ano × semana epidemiológica) com o percentual dos bairros do
    recorte que têm clima real naquela semana específica — base do heatmap
    obrigatório de disponibilidade (a cobertura climática não é homogênea
    no tempo, ver CLAUDE.md/instrução da etapa)."""
    total_bairros = df_gold["codigo_bairro"].nunique()
    if total_bairros == 0:
        return pd.DataFrame(columns=["ano_epidemiologico", "semana_epidemiologica", "percentual_bairros_com_clima"])

    com_clima = linhas_com_clima_real(df_gold)
    contagem = (
        com_clima.groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)["codigo_bairro"]
        .nunique()
        .reset_index(name="bairros_com_clima")
    )

    todas_semanas = df_gold[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates()
    grade = todas_semanas.merge(contagem, on=["ano_epidemiologico", "semana_epidemiologica"], how="left")
    grade["bairros_com_clima"] = grade["bairros_com_clima"].fillna(0).astype(int)
    grade["percentual_bairros_com_clima"] = round(100 * grade["bairros_com_clima"] / total_bairros, 2)
    return grade.sort_values(["ano_epidemiologico", "semana_epidemiologica"]).reset_index(drop=True)


def serie_precipitacao(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Série semanal de precipitação real agregada (média entre bairros com
    clima real na semana) — só sobre linhas com leitura real; semanas sem
    nenhum bairro com clima real ficam ausentes da série (não `0`)."""
    com_clima = linhas_com_clima_real(df_gold)
    if com_clima.empty:
        return pd.DataFrame(
            columns=[
                "ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio",
                "precipitacao_media_mm", "bairros_considerados",
            ]
        )
    agrupado = (
        com_clima.groupby(["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"], observed=True)
        .agg(
            precipitacao_media_mm=("precipitacao_total_semana_mm", "mean"),
            bairros_considerados=("codigo_bairro", "nunique"),
        )
        .reset_index()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
    )
    return agrupado
