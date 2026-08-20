"""Diagnóstico — antes de qualquer ajuste de feature/modelo/threshold.

Responde à pergunta central desta etapa: **2023 foi um ano
epidemiologicamente diferente ou o modelo simplesmente falhou?** Nenhuma
das funções aqui treina modelo — são estatísticas descritivas sobre
target/episódios (`target.py`/`alert_metrics.py`) e sobre a distribuição
das features (`features.py`), sempre por ano, para comparar o "antes"
(treino/validação) com cada ano de teste individualmente em vez de tratar
2023-2025 como um bloco homogêneo.

## PR-AUC não é comparável entre anos com prevalência muito diferente

PR-AUC de um classificador aleatório é, em expectativa, igual à prevalência
da classe positiva. Como a prevalência do target varia fortemente entre
anos (ver `resumo_alvo_por_ano` — de ~2% em 2022/2023 a ~17% em 2021), um
PR-AUC de 0,074 em um ano de baixa prevalência não é diretamente comparável
a um PR-AUC de 0,652 em um ano de alta prevalência. `lift_pr_auc` calcula
`PR-AUC / prevalência` — um "ganho sobre o acaso" comparável entre anos.
ROC-AUC (`roc_auc`, já reportado no walk-forward) é a métrica
prevalência-invariante complementar.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats


def resumo_alvo_por_ano(df_estado: pd.DataFrame) -> pd.DataFrame:
    """Por `ano_epidemiologico`: linhas, % positivo, % indefinido, limiar
    médio, nº de bairros com pelo menos 1 caso, % de linhas que caíram no
    fallback `tipo_limiar="geral"` (sinal de bairros com pouco histórico
    sazonal específico naquele ano)."""
    linhas = []
    for ano, sub in df_estado.groupby("ano_epidemiologico"):
        n = len(sub)
        n_indef = int(sub["estado_alto_risco"].isna().sum())
        linhas.append(
            {
                "ano": int(ano),
                "n_linhas": n,
                "casos_totais": float(sub["casos"].sum()),
                "casos_medio": float(sub["casos"].mean()),
                "pct_positivo": float((sub["estado_alto_risco"] == 1).mean() * 100),
                "pct_indefinido": float(100 * n_indef / n) if n else None,
                "limiar_medio": float(sub["limiar_historico_local"].mean()),
                "n_bairros_com_caso": int(sub.loc[sub["casos"] > 0, "codigo_bairro"].nunique()),
                "pct_tipo_geral": float((sub["tipo_limiar"] == "geral").mean() * 100),
            }
        )
    return pd.DataFrame(linhas).sort_values("ano").reset_index(drop=True)


def resumo_episodios_por_ano(df_episodios: pd.DataFrame) -> pd.DataFrame:
    """Por `inicio_ano`: quantidade, duração média, intensidade (casos
    totais/pico do episódio) e número de bairros distintos afetados —
    mostra se um ano teve poucos episódios PORQUE foram curtos/fracos
    (baixa atividade real) ou porque o alvo/modelo falhou."""
    linhas = []
    for ano, sub in df_episodios.groupby("inicio_ano"):
        linhas.append(
            {
                "ano": int(ano),
                "n_episodios": len(sub),
                "duracao_media_semanas": float(sub["duracao_semanas"].mean()),
                "casos_totais_episodio_media": float(sub["casos_totais_episodio"].mean()),
                "casos_pico_media": float(sub["casos_pico"].mean()),
                "casos_pico_mediana": float(sub["casos_pico"].median()),
                "n_bairros_distintos": int(sub["codigo_bairro"].nunique()),
            }
        )
    return pd.DataFrame(linhas).sort_values("ano").reset_index(drop=True)


def drift_features(
    X: pd.DataFrame,
    anos: pd.Series,
    features: Sequence[str],
    ano_referencia_fim: int,
    grupos_comparacao: dict[str, pd.Series],
) -> pd.DataFrame:
    """Teste KS (2 amostras) de cada feature em `features`, comparando a
    referência (`ano <= ano_referencia_fim`, tipicamente o treino) contra
    cada máscara booleana em `grupos_comparacao` (ex.: `{"2023": anos==2023}`).
    Reporta também média/mediana/p90 de cada grupo — o KS isolado não diz a
    direção da mudança."""
    mask_ref = anos <= ano_referencia_fim
    linhas = []
    for feat in features:
        ref = X.loc[mask_ref, feat].dropna()
        for nome, mask in grupos_comparacao.items():
            vals = X.loc[mask, feat].dropna()
            if len(vals) == 0 or len(ref) == 0:
                continue
            ks = stats.ks_2samp(ref, vals)
            linhas.append(
                {
                    "feature": feat,
                    "grupo": nome,
                    "n": len(vals),
                    "media": float(vals.mean()),
                    "mediana": float(vals.median()),
                    "p90": float(vals.quantile(0.9)),
                    "media_referencia": float(ref.mean()),
                    "ks_estatistica": float(ks.statistic),
                    "ks_p_valor": float(ks.pvalue),
                }
            )
    return pd.DataFrame(linhas)


def lift_pr_auc(tabela_walk_forward: pd.DataFrame) -> pd.DataFrame:
    """Adiciona `prevalencia` e `lift_pr_auc` (`pr_auc / prevalencia`) a uma
    tabela de walk-forward (precisa de `n_positivos`, `n_teste`, `pr_auc`).
    Permite comparar anos com prevalência muito diferente sem o viés
    mecânico de que PR-AUC baixo pode só refletir prevalência baixa."""
    tabela = tabela_walk_forward.copy()
    tabela["prevalencia"] = tabela["n_positivos"] / tabela["n_teste"]
    tabela["lift_pr_auc"] = tabela["pr_auc"] / tabela["prevalencia"].replace(0, np.nan)
    return tabela
