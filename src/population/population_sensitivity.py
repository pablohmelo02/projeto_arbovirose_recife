"""Sensibilidade do experimento ML V2 à incerteza da reconstrução
populacional (seções 8-9 do pedido do experimento V2).

## Sensibilidade B: nunca uma margem inventada

A perturbação aplicada à população dos anos não observados
(`ESTIMATIVA_INTERCENSITARIA`/`PROJECAO_POS_CENSO`) é reamostrada
(bootstrap) da distribuição **real** de erro percentual por bairro já
medida em `src/population/reconstruction.py::validar_reconstrucao_sem_checkpoint_intermediario`
(reconstrução 2010→2022 sem usar o checkpoint de 2017, comparada contra o
valor real — MAE≈886, MAPE≈10,8%, pior caso 211%). Nunca um desvio-padrão
paramétrico assumido; a forma pesada da distribuição real (incluindo o
outlier de Mangabeira) é preservada por reamostragem direta dos 94 erros
observados, não por ajuste de uma família paramétrica a eles.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.gold.populacao import COLUNAS_GOLD_POPULACAO, calcular_features_populacao
from src.population.reconstruction import (
    carregar_checkpoint_censo2022,
    carregar_checkpoint_cievs,
    carregar_serie_municipal,
    validar_reconstrucao_sem_checkpoint_intermediario,
)


def obter_distribuicao_erro_percentual_real(
    caminho_cievs, caminho_censo2022, caminho_municipal, df_territorio: pd.DataFrame
) -> np.ndarray:
    """Erro percentual assinado (não absoluto — preserva a direção do
    viés) por bairro, medido pela validação cruzada real já existente."""
    df_cievs, _ = carregar_checkpoint_cievs(caminho_cievs, df_territorio)
    df_censo2022, _ = carregar_checkpoint_censo2022(caminho_censo2022, df_territorio)
    serie_municipal = carregar_serie_municipal(caminho_municipal)

    pop_2010 = df_cievs.loc[df_cievs["ano"] == 2010].set_index("codigo_bairro")["populacao"]
    pop_2017 = df_cievs.loc[df_cievs["ano"] == 2017].set_index("codigo_bairro")["populacao"]
    pop_2022 = df_censo2022.set_index("codigo_bairro")["populacao"]

    comparacao, _ = validar_reconstrucao_sem_checkpoint_intermediario(
        pop_2010, pop_2022, pop_2017, serie_municipal
    )
    erro_assinado = (
        100
        * (comparacao["populacao_2017_predita_sem_checkpoint"] - comparacao["populacao_2017_real_cievs"])
        / comparacao["populacao_2017_real_cievs"]
    )
    return erro_assinado.to_numpy()


def perturbar_populacao(
    df_silver_populacao: pd.DataFrame,
    distribuicao_erro_pct: np.ndarray,
    rng: np.random.Generator,
    tipos_afetados: tuple[str, ...] = ("ESTIMATIVA_INTERCENSITARIA", "PROJECAO_POS_CENSO"),
) -> pd.DataFrame:
    """Uma réplica perturbada da Silver de população: cada linha cujo
    `tipo_valor` está em `tipos_afetados` tem a população multiplicada por
    `(1 + erro/100)`, `erro` reamostrado de `distribuicao_erro_pct`. Linhas
    `CENSO_OBSERVADO` nunca são perturbadas (são dado observado, não
    reconstrução)."""
    df = df_silver_populacao.copy()
    mask = df["tipo_valor"].isin(tipos_afetados)
    n = int(mask.sum())
    if n == 0:
        return df
    erros = rng.choice(distribuicao_erro_pct, size=n, replace=True)
    nova_populacao = df.loc[mask, "populacao"].to_numpy() * (1 + erros / 100)
    df.loc[mask, "populacao"] = np.maximum(1, np.round(nova_populacao)).astype("int64")
    return df


def recalcular_gold_com_populacao_perturbada(
    df_gold: pd.DataFrame, df_populacao_perturbada: pd.DataFrame
) -> pd.DataFrame:
    """Recalcula `COLUNAS_GOLD_POPULACAO` (população/densidade/incidência)
    sobre `df_gold` usando a população perturbada — reusa
    `src/gold/populacao.py::calcular_features_populacao` sem duplicar a
    lógica de janelas móveis. Nunca escreve no Parquet real da Gold; é
    só para esta análise de sensibilidade, em memória."""
    df_base = df_gold.drop(columns=[c for c in COLUNAS_GOLD_POPULACAO if c in df_gold.columns])
    df_novo, _ = calcular_features_populacao(df_base, df_populacao_perturbada)
    return df_novo


def executar_analise_sensibilidade_b(
    df_gold: pd.DataFrame,
    df_silver_populacao: pd.DataFrame,
    distribuicao_erro_pct: np.ndarray,
    avaliar_replica,
    n_replicas: int = 20,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Gera `n_replicas` réplicas perturbadas e chama
    `avaliar_replica(df_gold_perturbada) -> dict` em cada uma — a função de
    avaliação (treino+métrica) é injetada pelo chamador (o experimento
    principal) para não duplicar a lógica de treino/avaliação aqui."""
    rng = np.random.default_rng(seed)
    resultados = []
    for i in range(n_replicas):
        pop_perturbada = perturbar_populacao(df_silver_populacao, distribuicao_erro_pct, rng)
        gold_perturbada = recalcular_gold_com_populacao_perturbada(df_gold, pop_perturbada)
        metrica = avaliar_replica(gold_perturbada)
        resultados.append({"replica": i, **metrica})
    return resultados
