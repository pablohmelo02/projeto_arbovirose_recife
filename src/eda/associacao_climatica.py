"""Associação clima × arboviroses com defasagem (lag) real — Recife total.

Diferente de `src/eda/correlacao.py` e `src/eda/clima_grade.py`
(`correlacoes_lag_grade`), que correlacionam casos da semana `t` com chuva
**acumulada retrospectivamente até `t`** (uma janela cumulativa, calculada
uma única vez dentro da própria Gold), este módulo calcula a defasagem
**deslocada** de verdade: `alvo[t]` × `clima[t-k]`, para `k` de 0 a 12
semanas, deslocando a série climática para o passado com `.shift(k)`. As
duas metodologias coexistem de propósito — nenhuma substitui a outra nos
relatórios/painel já publicados.

## Por que só Recife total (nunca bairro/RPA)

A reanálise em grade (ERA5/ERA5-Land, única fonte com cobertura real
2013-2025) resolve só **2 células de precipitação e 3 de temperatura** para
os 94 bairros do Recife, com distância mediana de 8,06 km entre o
centroide do bairro e o centro da célula (ver CLAUDE.md §19.1 e
`reports/climate_source_analysis/gridded_climate_investigation.md`). Uma
correlação "por bairro" ou "por RPA" nessas condições compararia, na
prática, o mesmo valor de clima (ou um entre 2-3 valores) contra recortes
territoriais menores dos casos — produzindo uma falsa precisão espacial que
a fonte não sustenta. Por isso nenhuma função aqui aceita parâmetro de
bairro/RPA: a série climática é sempre a série-cidade de
`src.eda.clima_grade.serie_climatica_grade`.

## Casos vs. incidência

Duas quantidades diferentes, nunca assumidas equivalentes (ver item 7 do
pedido de produto): `casos` é a contagem absoluta semanal da cidade;
`incidencia_100k` é a mesma contagem dividida pela população total da
cidade naquele ano-epidemiológico × 100.000 — uma única divisão sobre os
agregados, nunca a soma de incidências por bairro já calculadas (mesma
regra de `src/gold/populacao.py` e `src/eda/filtros.py::total_arboviroses`).
Como a população cresce lentamente (~0,5-3% ao ano) e os casos variam muito
mais, as duas séries tendem a apontar para lags parecidos, mas isso é
verificado empiricamente a cada execução, nunca assumido.

## Dessazonalização é descritiva, não uma feature com fronteira de vazamento

`dessazonalizar` calcula o resíduo contra a média de **todas** as
observações da mesma semana epidemiológica (passadas e futuras em relação a
qualquer ponto da série) — diferente da regra "só anos estritamente
anteriores" usada em `src/eda/prioridade_observada.py` para evitar vazamento
temporal numa feature usada por outra função que também tem semântica de
"olhar para o futuro". Aqui não há esse risco: é uma análise exploratória
de associação histórica sobre a série completa já fechada, não uma feature
de um modelo com fronteira treino/teste. Simplicidade documentada de
propósito.

## Seleção do lag "mais forte" nunca é por p-valor

`resumo_textual` escolhe o lag de maior `|correlação de Spearman|` **entre
os lags com amostra confiável** (`n_observacoes >= 30`) — nunca o de menor
p-valor. Menor p-valor tende a favorecer lags com mais observações mesmo
quando a correlação em si é mais fraca; a tarefa pediu explicitamente para
não usar esse critério.

Nada aqui afirma causalidade em nenhuma circunstância.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from src.eda.clima_grade import serie_climatica_grade
from src.eda.filtros import aplicar_filtros
from src.eda.schema_eda import AGRAVOS
from src.gold.populacao import incidencia_100k

#: Mesmo limiar usado em `src/eda/correlacao.py` e `src/eda/clima_grade.py`
#: -- tamanho mínimo de amostra para uma leitura "confiável" (não é teste de
#: significância estatística).
N_MINIMO_OBSERVACOES_CONFIAVEL = 30

#: Defasagens padrão da análise: da própria semana até 12 semanas antes.
LAGS_PADRAO = tuple(range(0, 13))

#: Variáveis climáticas suportadas -> coluna correspondente na série-cidade
#: de `serie_climatica_grade`.
VARIAVEIS_CLIMATICAS = {
    "precipitacao": "precipitacao_mm",
    "temperatura_media": "temperatura_media_c",
    "temperatura_minima": "temperatura_minima_c",
    "temperatura_maxima": "temperatura_maxima_c",
    "umidade": "umidade_relativa_media_pct",
}

COLUNAS_SERIE_SEMANAL_AGRAVO = (
    "ano_epidemiologico",
    "semana_epidemiologica",
    "semana_epi_data_inicio",
    "indice_semana",
    "casos",
    "populacao_total_cidade",
    "incidencia_100k",
)

COLUNAS_TABELA_LAGS = (
    "lag_semanas",
    "correlacao_spearman",
    "p_value",
    "n_observacoes",
    "confiavel",
)

COLUNAS_TABELA_BRUTA_VS_AJUSTADA = (
    "lag_semanas",
    "correlacao_bruta",
    "correlacao_ajustada",
    "n_observacoes",
    "n_observacoes_ajustada",
)


def construir_serie_semanal_agravo(df_gold: pd.DataFrame, agravo: str) -> pd.DataFrame:
    """Série semanal Recife-total (casos e incidência) de um único agravo.

    `casos` = soma dos 94 bairros na semana. `incidencia_100k` = casos
    totais / população total da cidade naquele ano × 100.000 (`None` se a
    Gold carregada não tiver `populacao_bairro_ano`). `indice_semana` é um
    inteiro contíguo (0, 1, 2, ...) na ordem cronológica -- necessário para
    que `.shift(k)` desloque exatamente `k` semanas mesmo atravessando a
    virada de ano epidemiológico.
    """
    if agravo not in AGRAVOS:
        raise ValueError(f"agravo inválido: {agravo!r} (esperado um de {AGRAVOS})")

    df = aplicar_filtros(df_gold, agravo=agravo)
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_SERIE_SEMANAL_AGRAVO)

    casos = (
        df.groupby(
            ["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"], observed=True
        )["casos"]
        .sum()
        .reset_index()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
        .reset_index(drop=True)
    )
    casos["indice_semana"] = range(len(casos))

    if "populacao_bairro_ano" in df.columns:
        pop_bairro_ano = df[
            ["codigo_bairro", "ano_epidemiologico", "populacao_bairro_ano"]
        ].drop_duplicates(subset=["codigo_bairro", "ano_epidemiologico"])
        pop_total_ano = (
            pop_bairro_ano.groupby("ano_epidemiologico")["populacao_bairro_ano"]
            .sum()
            .rename("populacao_total_cidade")
            .reset_index()
        )
        casos = casos.merge(pop_total_ano, on="ano_epidemiologico", how="left")
        casos["incidencia_100k"] = incidencia_100k(casos["casos"], casos["populacao_total_cidade"])
    else:
        casos["populacao_total_cidade"] = np.nan
        casos["incidencia_100k"] = np.nan

    return casos[list(COLUNAS_SERIE_SEMANAL_AGRAVO)]


def _spearman_seguro(x: pd.Series, y: pd.Series) -> tuple[Optional[float], Optional[float]]:
    if len(x) < 2 or x.nunique() < 2 or y.nunique() < 2:
        return None, None
    try:
        resultado = scipy_stats.spearmanr(x, y)
    except Exception:  # pragma: no cover - guarda defensiva, não esperado com os checks acima
        return None, None
    correlacao = float(resultado.statistic) if not np.isnan(resultado.statistic) else None
    p_value = float(resultado.pvalue) if correlacao is not None and not np.isnan(resultado.pvalue) else None
    return correlacao, p_value


def calcular_lags_deslocados(
    serie_alvo: pd.Series, serie_clima: pd.Series, lags: "range | tuple[int, ...]" = LAGS_PADRAO
) -> pd.DataFrame:
    """Correlação de Spearman entre `serie_alvo[t]` e `serie_clima[t-k]`,
    para cada `k` em `lags` -- defasagem deslocada de verdade (`.shift(k)`),
    não janela cumulativa. `serie_alvo` e `serie_clima` devem estar
    indexadas pela mesma ordem cronológica (ex.: `indice_semana`).

    Nunca seleciona/filtra o "melhor" lag -- devolve a tabela completa,
    inclusive lags sem amostra suficiente. Nunca levanta exceção com
    entrada vazia ou curta demais: os lags aparecem na tabela com
    `n_observacoes=0` e `confiavel=False`.
    """
    linhas = []
    for k in lags:
        clima_deslocada = serie_clima.shift(k)
        combinado = pd.DataFrame({"alvo": serie_alvo.to_numpy(), "clima": clima_deslocada.to_numpy()}).dropna()
        n = len(combinado)
        correlacao, p_value = (
            _spearman_seguro(combinado["alvo"], combinado["clima"]) if n >= 2 else (None, None)
        )
        linhas.append(
            {
                "lag_semanas": int(k),
                "correlacao_spearman": round(correlacao, 4) if correlacao is not None else None,
                "p_value": round(p_value, 4) if p_value is not None else None,
                "n_observacoes": int(n),
                "confiavel": bool(n >= N_MINIMO_OBSERVACOES_CONFIAVEL),
            }
        )
    return pd.DataFrame(linhas, columns=list(COLUNAS_TABELA_LAGS))


def dessazonalizar(serie: pd.Series, semanas_epidemiologicas: pd.Series) -> pd.Series:
    """Resíduo = valor menos a média histórica de todas as observações da
    mesma semana epidemiológica (1-53) na série inteira. Ver docstring do
    módulo para o porquê de não restringir a anos anteriores aqui."""
    df = pd.DataFrame(
        {"valor": serie.to_numpy(), "semana": semanas_epidemiologicas.to_numpy()}, index=serie.index
    )
    media_por_semana = df.groupby("semana")["valor"].transform("mean")
    return (df["valor"] - media_por_semana).rename(serie.name)


def comparar_bruta_vs_ajustada(
    serie_alvo: pd.Series,
    serie_clima: pd.Series,
    semanas_epidemiologicas: pd.Series,
    lags: "range | tuple[int, ...]" = LAGS_PADRAO,
) -> pd.DataFrame:
    """Tabela de lags calculada duas vezes: sobre as séries brutas e sobre
    as séries dessazonalizadas (`dessazonalizar`) -- para distinguir
    associação que só existe por sazonalidade compartilhada de associação
    que sobrevive ao remover esse componente."""
    bruta = calcular_lags_deslocados(serie_alvo, serie_clima, lags)
    alvo_resid = dessazonalizar(serie_alvo, semanas_epidemiologicas)
    clima_resid = dessazonalizar(serie_clima, semanas_epidemiologicas)
    ajustada = calcular_lags_deslocados(alvo_resid, clima_resid, lags)

    resultado = bruta[["lag_semanas", "correlacao_spearman", "n_observacoes"]].rename(
        columns={"correlacao_spearman": "correlacao_bruta"}
    )
    resultado["correlacao_ajustada"] = ajustada["correlacao_spearman"].to_numpy()
    resultado["n_observacoes_ajustada"] = ajustada["n_observacoes"].to_numpy()
    return resultado[list(COLUNAS_TABELA_BRUTA_VS_AJUSTADA)]


def resumo_textual(tabela_lags: pd.DataFrame) -> str:
    """Frase automática apontando o lag de maior |correlação| **entre os
    confiáveis** -- nunca o de menor p-valor. Nunca afirma causalidade."""
    confiaveis = tabela_lags[tabela_lags["confiavel"] & tabela_lags["correlacao_spearman"].notna()]
    if confiaveis.empty:
        return (
            "Nenhuma defasagem teve amostra suficiente (n ≥ "
            f"{N_MINIMO_OBSERVACOES_CONFIAVEL}) para uma leitura confiável nesta combinação de "
            "agravo e variável climática."
        )
    indice = confiaveis["correlacao_spearman"].abs().idxmax()
    linha = confiaveis.loc[indice]
    lag = int(linha["lag_semanas"])
    correlacao = float(linha["correlacao_spearman"])
    n = int(linha["n_observacoes"])
    unidade = "semana" if lag == 1 else "semanas"
    return (
        f"A maior associação observada ocorreu com {lag} {unidade} de defasagem "
        f"(Spearman={correlacao:.2f}, n={n}), mas isso representa associação histórica, "
        "não causalidade."
    )


def serie_variavel_climatica(df_gold: pd.DataFrame, variavel: str) -> pd.DataFrame:
    """Série-cidade semanal de uma variável climática suportada, a partir
    de `serie_climatica_grade` (nunca recalculada aqui)."""
    if variavel not in VARIAVEIS_CLIMATICAS:
        raise ValueError(
            f"variável climática inválida: {variavel!r} (esperado uma de {tuple(VARIAVEIS_CLIMATICAS)})"
        )
    coluna = VARIAVEIS_CLIMATICAS[variavel]
    serie = serie_climatica_grade(df_gold)
    colunas = ["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio", coluna]
    colunas_presentes = [c for c in colunas if c in serie.columns]
    return serie[colunas_presentes].rename(columns={coluna: "valor"})
