"""Features de população e incidência epidemiológica no grão da Gold
(`bairro × semana epidemiológica × agravo`), derivadas de
`silver_populacao_bairro_ano`.

## Nunca soma taxas — sempre soma casos, divide uma vez

`incidencia_100k = casos / populacao_bairro_ano * 100000` na própria semana.
As janelas móveis (`incidencia_4s_100k`, `8s`, `12s`, `anual`) somam
`casos` na janela e dividem **uma única vez** pela população — nunca somam
incidências semanais já calculadas (isso infla o resultado e não tem
significado epidemiológico).

## Por que `incidencia_anual_100k` é uma janela móvel de 52 semanas, não "ano civil completo"

Um "ano civil completo" somaria semanas **futuras** em relação a uma linha
no meio do ano (ex.: a incidência anual da semana 5 incluiria casos da
semana 50, que ainda não aconteceram do ponto de vista daquela linha) —
violaria a mesma regra de ausência de vazamento temporal já aplicada e
testada para as features climáticas (`schema_gold_arboviroses_clima.py`,
seção "Leakage temporal"). Por isso `incidencia_anual_100k` é definida
como as outras janelas: uma janela móvel **terminando** na própria semana
(52 semanas, ~1 ano), nunca o ano corrente completo.

## Denominador populacional das janelas móveis

Toda janela (própria semana, 4/8/12/52 semanas) usa a população do
**ano epidemiológico da linha-alvo** como denominador, mesmo quando a
janela de 52 semanas cobre uma pequena cauda do ano anterior. A população
muda ~0,5-3% ao ano — o efeito de usar o ano-alvo em vez de uma média
ponderada pelas poucas semanas do ano anterior é desprezível frente à
incerteza já existente na própria reconstrução populacional (ver
`reports/population/population_incidence_integration.md`), e evita
recalcular uma população "por semana" que a fonte não publica.

## Ausência de população nunca vira zero

Se o bairro não tem `populacao_bairro_ano` para aquele ano (não deveria
acontecer para os 94 bairros oficiais em 2010-2025, mas o código nunca
assume isso), a incidência fica `None` — nunca `0` nem `inf`. Divisão por
população zero ou ausente é tratada da mesma forma.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

#: Janelas retrospectivas em semanas, além da própria semana. 52 ~ 1 ano.
JANELAS_SEMANAS_INCIDENCIA = (4, 8, 12)
JANELA_SEMANAS_ANUAL = 52

COLUNAS_GOLD_POPULACAO = (
    "populacao_bairro_ano",
    "tipo_populacao",
    "densidade_populacional_hab_km2",
    "incidencia_100k",
    *(f"incidencia_{n}s_100k" for n in JANELAS_SEMANAS_INCIDENCIA),
    "incidencia_anual_100k",
)


def incidencia_100k(casos: pd.Series, populacao: pd.Series) -> pd.Series:
    """`casos / populacao * 100000`, com população ausente/<=0 -> `None`."""
    populacao_segura = populacao.where(populacao > 0)
    return (100000 * casos / populacao_segura).astype("float64")


def calcular_features_populacao(
    df_grao: pd.DataFrame, df_populacao_bairro_ano: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Adiciona `COLUNAS_GOLD_POPULACAO` a `df_grao`, preservando a ordem
    original das linhas.

    `df_grao` precisa ter `codigo_bairro`, `agravo`, `ano_epidemiologico`,
    `semana_epidemiologica`, `casos`, `area_km2`. `df_populacao_bairro_ano`
    é `silver_populacao_bairro_ano` (uma linha por bairro x ano).
    """
    indice_original = df_grao.index
    df = df_grao.sort_values(
        ["codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica"]
    ).copy()

    pop_por_ano = df_populacao_bairro_ano.set_index(["codigo_bairro", "ano"])
    chave_pop = pd.MultiIndex.from_arrays([df["codigo_bairro"], df["ano_epidemiologico"]])
    df["populacao_bairro_ano"] = pop_por_ano["populacao"].reindex(chave_pop).to_numpy()
    df["tipo_populacao"] = pop_por_ano["tipo_valor"].reindex(chave_pop).to_numpy()

    df["densidade_populacional_hab_km2"] = (df["populacao_bairro_ano"] / df["area_km2"]).round(2)

    df["incidencia_100k"] = incidencia_100k(df["casos"], df["populacao_bairro_ano"])

    agrupado = df.groupby(["codigo_bairro", "agravo"], observed=True)["casos"]
    for n in JANELAS_SEMANAS_INCIDENCIA:
        casos_janela = agrupado.transform(lambda s, n=n: s.rolling(window=n, min_periods=1).sum())
        df[f"incidencia_{n}s_100k"] = incidencia_100k(casos_janela, df["populacao_bairro_ano"])

    casos_anual = agrupado.transform(
        lambda s: s.rolling(window=JANELA_SEMANAS_ANUAL, min_periods=1).sum()
    )
    df["incidencia_anual_100k"] = incidencia_100k(casos_anual, df["populacao_bairro_ano"])

    df = df.reindex(indice_original)

    n_sem_populacao = int(df["populacao_bairro_ano"].isna().sum())
    metricas = {
        "linhas_com_populacao": int(len(df) - n_sem_populacao),
        "linhas_sem_populacao": n_sem_populacao,
        "percentual_linhas_com_populacao": (
            round(100 * (len(df) - n_sem_populacao) / len(df), 4) if len(df) else 0.0
        ),
        "anos_com_populacao_na_silver": sorted(int(a) for a in df_populacao_bairro_ano["ano"].unique()),
        "tipos_populacao_presentes": sorted(df["tipo_populacao"].dropna().unique().tolist()),
        "bairros_sem_populacao": sorted(
            df.loc[df["populacao_bairro_ano"].isna(), "codigo_bairro"].unique().tolist()
        ),
    }
    return df, metricas
