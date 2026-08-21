"""Monta o dataset supervisionado da V2 (onset baseado em incidência) —
mesma orquestração de `src/ml/dataset.py::montar_dataset_onset`, trocando
o target por `target_onset_incidencia_h{N}` e permitindo 5 composições de
features (`variante`), usadas pelo experimento principal + ablation
(seção 24 do pedido).

## Variantes

| `variante` | features |
|---|---|
| `v1_features` | exatamente as 38 features de `dengue_onset_ranking_candidate_v1` (ablation A) |
| `v1_mais_populacao` | V1 + `log_populacao` + `densidade_populacional_hab_km2` (ablation B) |
| `v2_incidencia` | só incidência + sazonal/histórico de incidência + território — SEM casos absolutos (linha principal 2) |
| `v2_casos_incidencia` | V1 + bloco de incidência (linha principal 3 = ablation C) |
| `v2_casos_incidencia_populacao` | V1 + incidência + população/densidade (ablation D) |

Em TODAS as variantes o TARGET é o mesmo (`target_onset_incidencia_h{N}`,
onset sobre `estado_alto_risco_incidencia`) — só as features mudam, o que
isola de onde vem qualquer ganho (seção 24 do pedido: "descobrir de onde
vem eventual ganho").
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.ml.features import (
    FEATURES_TERRITORIAIS_CATEGORICAS,
    FEATURES_TERRITORIAIS_NUMERICAS,
    construir_features_epidemiologicas_e_sazonais,
    selecionar_matriz_features,
)
from src.ml.features_incidencia import (
    FEATURES_HISTORICO_LOCAL_INCIDENCIA,
    FEATURES_INCIDENCIA_BASE,
    FEATURES_POPULACAO,
    FEATURES_SAZONAIS_INCIDENCIA,
    construir_features_incidencia,
)
from src.ml.onset import HORIZONTES_ONSET
from src.ml.onset_incidencia import construir_target_onset_incidencia
from src.ml.target import calcular_estado_alto_risco
from src.ml.target_incidencia import (
    agregar_semanal_agravo_com_populacao,
    calcular_estado_alto_risco_incidencia,
)

VARIANTES_FEATURES = (
    "v1_features",
    "v1_mais_populacao",
    "v2_incidencia",
    "v2_casos_incidencia",
    "v2_casos_incidencia_populacao",
)


def _matriz_v2_incidencia_pura(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Território one-hot + incidência — nunca inclui `FEATURES_EPIDEMIOLOGICAS_BASE`
    (casos absolutos), ao contrário de `selecionar_matriz_features`, que os
    torna obrigatórios por design (ver docstring de `features.py`)."""
    colunas_numericas = (
        list(FEATURES_INCIDENCIA_BASE)
        + list(FEATURES_SAZONAIS_INCIDENCIA)
        + list(FEATURES_HISTORICO_LOCAL_INCIDENCIA)
        + list(FEATURES_TERRITORIAIS_NUMERICAS)
    )
    X_num = df[colunas_numericas].copy()
    X_cat = pd.get_dummies(
        df[list(FEATURES_TERRITORIAIS_CATEGORICAS)].astype("category"),
        prefix=list(FEATURES_TERRITORIAIS_CATEGORICAS),
        dummy_na=False,
    )
    X = pd.concat([X_num, X_cat], axis=1)
    return X, list(X.columns)


def _montar_matriz(df_feat: pd.DataFrame, variante: str) -> tuple[pd.DataFrame, list[str]]:
    if variante == "v1_features":
        return selecionar_matriz_features(df_feat)
    if variante == "v1_mais_populacao":
        X, colunas = selecionar_matriz_features(df_feat)
        X_pop = df_feat[list(FEATURES_POPULACAO)]
        X = pd.concat([X, X_pop], axis=1)
        return X, colunas + list(FEATURES_POPULACAO)
    if variante == "v2_incidencia":
        return _matriz_v2_incidencia_pura(df_feat)
    if variante == "v2_casos_incidencia":
        X, colunas = selecionar_matriz_features(df_feat)
        colunas_incid = list(FEATURES_INCIDENCIA_BASE) + list(FEATURES_HISTORICO_LOCAL_INCIDENCIA)
        X = pd.concat([X, df_feat[colunas_incid]], axis=1)
        return X, colunas + colunas_incid
    if variante == "v2_casos_incidencia_populacao":
        X, colunas = _montar_matriz(df_feat, "v2_casos_incidencia")
        X_pop = df_feat[list(FEATURES_POPULACAO)]
        X = pd.concat([X, X_pop], axis=1)
        return X, colunas + list(FEATURES_POPULACAO)
    raise ValueError(f"variante desconhecida: {variante!r} — esperado um de {VARIANTES_FEATURES}")


def montar_dataset_onset_incidencia(
    df_gold: pd.DataFrame,
    agravo: str = "DENGUE",
    horizonte: int = 3,
    variante: str = "v2_casos_incidencia",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, dict[str, Any]]:
    """Devolve `(df_contexto, X, y, metricas)`, mesmo contrato de
    `dataset.montar_dataset_onset`. `df_contexto` traz tanto as colunas de
    estado baseadas em casos (`estado_alto_risco`, ...) quanto as baseadas
    em incidência (`estado_alto_risco_incidencia`, ...) — útil para
    `alert_metrics.construir_episodios`/análises territoriais depois."""
    if horizonte not in HORIZONTES_ONSET:
        raise ValueError(f"horizonte {horizonte!r} não está em HORIZONTES_ONSET={HORIZONTES_ONSET}")
    if variante not in VARIANTES_FEATURES:
        raise ValueError(f"variante {variante!r} não está em VARIANTES_FEATURES={VARIANTES_FEATURES}")

    df_sem = agregar_semanal_agravo_com_populacao(df_gold, agravo)
    df_estado = calcular_estado_alto_risco(df_sem)
    df_feat = construir_features_epidemiologicas_e_sazonais(df_estado)
    df_feat = df_feat.sort_values(["codigo_bairro", "indice_semana_global"]).reset_index(drop=True)

    df_feat = calcular_estado_alto_risco_incidencia(df_feat, coluna_valor="incidencia_100k")
    df_feat = construir_features_incidencia(df_feat)
    df_feat = construir_target_onset_incidencia(df_feat, horizontes=HORIZONTES_ONSET)

    linhas_antes = len(df_feat)
    df_feat["indice_semana_alvo"] = df_feat["indice_semana_global"]

    coluna_target = f"target_onset_incidencia_h{horizonte}"
    linhas_target_indefinido = int(df_feat[coluna_target].isna().sum())

    X, colunas = _montar_matriz(df_feat, variante)
    y = df_feat[coluna_target]

    mask_valida = y.notna() & X.notna().all(axis=1)
    linhas_feature_nan = int((~mask_valida & y.notna()).sum())

    df_contexto = df_feat.loc[mask_valida].reset_index(drop=True)
    X_final = X.loc[mask_valida].reset_index(drop=True)
    y_final = y.loc[mask_valida].astype(int).reset_index(drop=True)

    metricas = {
        "agravo": agravo,
        "formulacao": "onset_incidencia",
        "variante": variante,
        "horizonte_semanas": horizonte,
        "linhas_antes": linhas_antes,
        "linhas_target_indefinido": linhas_target_indefinido,
        "linhas_excluidas_feature_nan": linhas_feature_nan,
        "linhas_finais": len(y_final),
        "proporcao_positiva": float(y_final.mean()) if len(y_final) else None,
        "n_positivos": int(y_final.sum()) if len(y_final) else 0,
        "n_negativos": int((y_final == 0).sum()) if len(y_final) else 0,
        "n_features": len(colunas),
        "colunas_features": colunas,
    }
    return df_contexto, X_final, y_final, metricas
