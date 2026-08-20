"""Baselines simples — devem ser superados para justificar qualquer modelo
de ML (seção 3/48 do pedido). Nenhum baseline aqui usa informação de
`t+horizonte` — todos operam só com colunas já presentes em `df_contexto`
(`dataset.montar_dataset`), que por sua vez só usa `t` ou antes.

Cada função de classificação devolve uma `pd.Series` de "probabilidade"
(na prática 0.0/1.0 — os baselines são determinísticos, não têm grau de
confiança) alinhada ao índice de `df_contexto`. Isso permite reaproveitar
exatamente as mesmas funções de `evaluation.py` usadas para os modelos de
ML (PR-AUC degenera para o baseline determinístico, mas Precision/Recall/F1
continuam válidos).
"""
from __future__ import annotations

import pandas as pd

N_SEMANAS_CRESCIMENTO_CONSECUTIVO = 3
"""Número de semanas consecutivas de crescimento exigidas pelo baseline de
crescimento recente (seção 20). Escolha explícita, não escondida: 2 semanas
(1 comparação) captura ruído semana-a-semana comum em contagens baixas;
exigir 3 semanas consecutivas (2 comparações `casos_t > casos_t-1 > casos_t-2`)
é o menor valor que já distingue "flutuação de uma semana" de "tendência
sustentada", sem introduzir nenhum ajuste (tuning) sobre o resultado."""


def baseline_persistencia(df_contexto: pd.DataFrame) -> pd.Series:
    """"Se o bairro está em risco elevado agora (`estado_alto_risco_t`),
    prevê que continuará em `t+horizonte`" — a hipótese nula mais simples
    possível para uma série com autocorrelação temporal."""
    return df_contexto["estado_alto_risco_t"].astype(float).rename("baseline_persistencia")


def baseline_crescimento_recente(
    df_contexto: pd.DataFrame,
    n_semanas: int = N_SEMANAS_CRESCIMENTO_CONSECUTIVO,
) -> pd.Series:
    """Alerta se `casos` cresceu estritamente em cada uma das últimas
    `n_semanas` semanas consecutivas (ex.: `n_semanas=3` exige
    `casos_t > casos_t-1` E `casos_t-1 > casos_t-2`)."""
    if n_semanas < 2:
        raise ValueError("n_semanas deve ser >= 2 (precisa de ao menos 1 comparação)")
    if n_semanas - 1 > 4:
        raise ValueError("n_semanas-1 excede os lags disponíveis (máximo 4, ver features.LAGS_CASOS)")

    condicao = pd.Series(True, index=df_contexto.index)
    for k in range(0, n_semanas - 1):
        col_atual = "casos_t" if k == 0 else f"casos_t_menos_{k}"
        col_anterior = f"casos_t_menos_{k + 1}"
        condicao &= df_contexto[col_atual] > df_contexto[col_anterior]
    return condicao.astype(float).rename("baseline_crescimento_recente")


def baseline_sazonal_simples(df_contexto: pd.DataFrame) -> pd.Series:
    """Compara a semana atual à MÉDIA histórica (não ao percentil 90 usado
    no target, ver `target.py`) da mesma semana epidemiológica exata (sem
    janela de +-2 semanas) no mesmo bairro, usando só anos anteriores —
    regra mais simples e mais sensível que a do target, deliberadamente
    distinta dele (nunca reaproveita o limiar do target 1:1, senão o
    baseline "sazonal" e o baseline "persistência" seriam operacionalmente
    idênticos)."""
    condicao = df_contexto["casos_t"] > df_contexto["media_historica_semana_exata"]
    return condicao.astype(float).rename("baseline_sazonal_simples")


def baseline_contagem_persistencia(df_contexto: pd.DataFrame) -> pd.Series:
    """Previsão quantitativa (Saída A): `casos_previstos_(t+h) = casos_t`."""
    return df_contexto["casos_t"].astype(float).rename("casos_previstos_persistencia")


def baseline_contagem_media_movel_4s(df_contexto: pd.DataFrame) -> pd.Series:
    """Previsão quantitativa (Saída A): `casos_previstos_(t+h)` = média móvel
    das últimas 4 semanas (já calculada em `features.py` como `media_4s`)."""
    return df_contexto["media_4s"].astype(float).rename("casos_previstos_media_movel_4s")
