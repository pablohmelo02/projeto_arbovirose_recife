"""EDA epidemiológica reutilizável (dashboard + `reports/eda/`).

Cobre 2013-2025 (dimensão epidemiológica + territorial) — nenhuma dessas
funções depende de clima, então nunca ficam limitadas pela janela
2024-2025 (ver `src/eda/clima.py` e `src/eda/correlacao.py` para o que É
limitado a essa janela).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def resumo_epidemiologico(df_gold: pd.DataFrame) -> dict[str, Any]:
    """KPIs de visão geral: total de casos, bairros, período, semanas,
    agravos — sempre calculados do DataFrame recebido (já filtrado ou não
    por quem chama), nunca de um número fixo."""
    return {
        "total_linhas": len(df_gold),
        "total_casos": int(df_gold["casos"].sum()),
        "total_bairros": int(df_gold["codigo_bairro"].nunique()),
        "ano_epidemiologico_min": int(df_gold["ano_epidemiologico"].min()) if len(df_gold) else None,
        "ano_epidemiologico_max": int(df_gold["ano_epidemiologico"].max()) if len(df_gold) else None,
        "total_semanas_distintas": int(
            df_gold[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0]
        ),
        "agravos_presentes": sorted(df_gold["agravo"].unique().tolist()),
        "bairros_com_pelo_menos_1_caso": int(df_gold.loc[df_gold["casos"] > 0, "codigo_bairro"].nunique()),
        "bairros_com_clima_real": int(
            df_gold.loc[df_gold["dias_com_dado_valido_semana"].fillna(0) > 0, "codigo_bairro"].nunique()
        ),
        "percentual_linhas_com_clima_real": (
            round(100 * (df_gold["dias_com_dado_valido_semana"].fillna(0) > 0).mean(), 4) if len(df_gold) else 0.0
        ),
    }


def serie_temporal_semanal(df_gold: pd.DataFrame, por_agravo: bool = True) -> pd.DataFrame:
    """Casos agregados por semana epidemiológica (soma de todos os bairros
    do recorte recebido). `por_agravo=True` mantém uma linha por
    (ano, semana, agravo) — nunca soma agravos diferentes silenciosamente;
    `por_agravo=False` soma os 3 agravos numa série única (Recife total)."""
    colunas_grupo = ["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"]
    if por_agravo:
        colunas_grupo.append("agravo")
    serie = (
        df_gold.groupby(colunas_grupo, observed=True)["casos"]
        .sum()
        .reset_index()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
    )
    return serie


def sazonalidade_semanal(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Distribuição de casos por semana epidemiológica (1-53), agregando
    todos os anos disponíveis no recorte — usada para observar recorrência
    sazonal, nunca para inferir causalidade (só descreve o padrão nos dados
    reais). Retorna total, média por ano e número de anos observados por
    semana (uma semana 53 só existe em alguns anos, e isso deve ficar
    visível)."""
    por_ano_semana = (
        df_gold.groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)["casos"]
        .sum()
        .reset_index()
    )
    agrupado = (
        por_ano_semana.groupby("semana_epidemiologica", observed=True)
        .agg(
            casos_totais=("casos", "sum"),
            casos_media_por_ano=("casos", "mean"),
            anos_observados=("ano_epidemiologico", "nunique"),
        )
        .reset_index()
        .sort_values("semana_epidemiologica")
    )
    return agrupado


def comparar_agravos(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Casos totais por agravo e por ano epidemiológico — para comparação
    visual em escalas separadas (Dengue tende a dominar em volume; forçar
    Zika/Chikungunya na mesma escala linear prejudica a leitura, decisão
    de UI, não desta função)."""
    return (
        df_gold.groupby(["ano_epidemiologico", "agravo"], observed=True)["casos"]
        .sum()
        .reset_index()
        .sort_values(["ano_epidemiologico", "agravo"])
    )


def rank_bairros(
    df_gold: pd.DataFrame,
    metrica: str = "casos",
    top_n: Optional[int] = 10,
    ascendente: bool = False,
) -> pd.DataFrame:
    """Ranking de bairros por uma métrica (soma de `casos` no recorte
    recebido — quem chama já deve ter filtrado agravo/ano/etc. via
    `src/eda/filtros.py`). `metrica` só aceita colunas realmente somáveis
    da Gold; `incidencia_por_100k` não é oferecida (não existe, ver
    `schema_eda.py`)."""
    if metrica not in ("casos",):
        raise ValueError(f"métrica de ranking não suportada: {metrica!r}")

    agrupado = (
        df_gold.groupby(["codigo_bairro", "nome_bairro"], observed=True)[metrica]
        .sum()
        .reset_index()
        .sort_values(metrica, ascending=ascendente)
    )
    agrupado["posicao"] = range(1, len(agrupado) + 1)
    if top_n is not None:
        agrupado = agrupado.head(top_n)
    return agrupado.reset_index(drop=True)
