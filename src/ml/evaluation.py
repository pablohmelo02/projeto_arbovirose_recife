"""Métricas de classificação (linha a linha) — complementares às métricas
operacionais de alerta (`alert_metrics.py`, que trabalham em nível de
episódio/bairro/ano). PR-AUC é reportado como métrica principal (seção 26)
porque o target é raro (ver `proporcao_positiva` em `dataset.py`) — ROC-AUC
é complementar, não a métrica de decisão.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

THRESHOLD_PADRAO = 0.5


def metricas_classificacao(y_true: pd.Series, y_proba: pd.Series, threshold: float = THRESHOLD_PADRAO) -> dict[str, Any]:
    """Precision/Recall/F1 (no threshold dado) + PR-AUC/ROC-AUC (limiar-
    independentes, calculados sobre a probabilidade contínua) + matriz de
    confusão. `y_proba` pode ser 0.0/1.0 (baseline determinístico) — nesse
    caso PR-AUC/ROC-AUC degeneram para um único ponto, o que é esperado e
    documentado, não um erro."""
    y_pred = (y_proba >= threshold).astype(int)
    n_pos = int(y_true.sum())
    n_neg = int((y_true == 0).sum())

    resultado: dict[str, Any] = {
        "threshold": threshold,
        "n": len(y_true),
        "n_positivos": n_pos,
        "n_negativos": n_neg,
        "proporcao_positiva": float(y_true.mean()) if len(y_true) else None,
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }

    try:
        resultado["pr_auc"] = float(average_precision_score(y_true, y_proba))
    except ValueError:
        resultado["pr_auc"] = None
    try:
        resultado["roc_auc"] = float(roc_auc_score(y_true, y_proba)) if y_true.nunique() > 1 else None
    except ValueError:
        resultado["roc_auc"] = None

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    resultado["matriz_confusao"] = {
        "verdadeiro_negativo": int(tn),
        "falso_positivo": int(fp),
        "falso_negativo": int(fn),
        "verdadeiro_positivo": int(tp),
    }
    return resultado


def trade_off_precision_recall(y_true: pd.Series, y_proba: pd.Series, thresholds: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)) -> pd.DataFrame:
    """Precision/Recall/F1/contagem de falsos negativos em vários limiares —
    para reportar o trade-off explicitamente (seção 27), nunca escolher um
    limiar só para maximizar Recall ignorando falsos alertas."""
    linhas = []
    for t in thresholds:
        m = metricas_classificacao(y_true, y_proba, threshold=t)
        linhas.append(
            {
                "threshold": t,
                "precision": m["precision"],
                "recall": m["recall"],
                "f1": m["f1"],
                "falsos_positivos": m["matriz_confusao"]["falso_positivo"],
                "falsos_negativos": m["matriz_confusao"]["falso_negativo"],
            }
        )
    return pd.DataFrame(linhas)


def diagnostico_calibracao(y_true: pd.Series, y_proba: pd.Series, n_bins: int = 10) -> pd.DataFrame:
    """Diagnóstico básico de calibração (não calibração avançada, conforme
    regra de parada): agrupa em `n_bins` faixas de probabilidade e compara
    a probabilidade média prevista com a frequência observada real do
    target em cada faixa. Faixas sem nenhuma observação são omitidas
    (nunca preenchidas com 0 artificial)."""
    df = pd.DataFrame({"y_true": y_true.to_numpy(), "y_proba": y_proba.to_numpy()})
    if df["y_proba"].nunique() <= 1:
        # baseline determinístico (0/1 puro) -- 1 ou 2 grupos naturais, não n_bins
        agrupado = (
            df.groupby("y_proba")
            .agg(n=("y_true", "size"), proba_media=("y_proba", "mean"), frequencia_observada=("y_true", "mean"))
            .reset_index(drop=True)
        )
        return agrupado
    df["faixa"] = pd.cut(df["y_proba"], bins=n_bins, include_lowest=True)
    agrupado = (
        df.groupby("faixa", observed=True)
        .agg(n=("y_true", "size"), proba_media=("y_proba", "mean"), frequencia_observada=("y_true", "mean"))
        .reset_index()
    )
    return agrupado


def brier_score(y_true: pd.Series, y_proba: pd.Series) -> float:
    """Brier Score (erro quadrático médio da probabilidade prevista contra
    o desfecho binário real, 0 = perfeito, 0,25 = "sempre prever 0,5") —
    métrica-resumo de calibração, complementar ao diagnóstico por faixas
    de `diagnostico_calibracao`."""
    return float(brier_score_loss(y_true, y_proba))


def erro_previsao_quantitativa(casos_reais: pd.Series, casos_previstos: pd.Series) -> dict[str, float]:
    """MAE/RMSE da previsão quantitativa (Saída A) — reportado à parte,
    não é o critério principal de sucesso da etapa (ver seção 4 do
    pedido)."""
    erro = casos_reais.to_numpy() - casos_previstos.to_numpy()
    return {
        "mae": float(np.mean(np.abs(erro))),
        "rmse": float(np.sqrt(np.mean(erro**2))),
        "n": int(len(erro)),
    }
