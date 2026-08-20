"""Feature engineering — simples, interpretável, sem leakage.

Todas as features de uma linha (`codigo_bairro`, `ano_epidemiologico`,
`semana_epidemiologica` = t) usam **somente** informação disponível em `t`
ou antes: lags/rolling de `casos` terminam em `t` (nunca `t+1`), features
sazonais expandem só sobre anos `< ano(t)` (mesma regra do target, ver
`target.py`), e as features climáticas são as que a própria Gold já garante
serem `data <= semana_epi_data_fim` da linha (ver
`src/gold/schema_gold_arboviroses_clima.py`, seção "Regra de leakage
temporal" — não recalculadas aqui, só consumidas).

Deliberadamente poucas features (pedido explícito: "não gere centenas de
features"). Território tratado como atributos categóricos/numéricos reais
(`codigo_rpa`/`codigo_microrregiao` como categoria via one-hot, nunca como
número contínuo; `centroide_lat/lon` são coordenadas, legitimamente
numéricas).

## Grupos de features (para ablation, ver `dataset.py`/entry point de
   otimização)

`FEATURES_EPIDEMIOLOGICAS_BASE` (contagens/rolling absolutas) ,
`FEATURES_SAZONAIS`, `FEATURES_TERRITORIAIS_*`, `FEATURES_HISTORICO_LOCAL`
(contexto relativo ao próprio histórico do bairro) e `FEATURES_MOMENTUM`
(crescimento/aceleração) são grupos independentes que `selecionar_matriz_features`
liga/desliga individualmente — a etapa de otimização compara o ganho
marginal de cada grupo (ablation cumulativo), não apenas "com tudo" vs
"sem nada".

## Features de histórico local e momentum (etapa de otimização)

Divisão por zero/ausência tratada explicitamente com suavização de Laplace
(`+ EPS_RAZAO`, `EPS_RAZAO=1.0`) — nunca `NaN`/`inf` silencioso quando o
denominador (limiar, média recente, casos da semana anterior) é zero:
`razao_limiar_historico = casos_t / (limiar_historico_local + 1)`,
`razao_media_recente = casos_t / (media_4s + 1)`,
`taxa_crescimento_suavizada = (casos_t - casos_t-1) / (casos_t-1 + 1)`.
`z_score_historico_local` usa o mesmo princípio com `std_historica_semana_exata
+ 1` no denominador (evita explosão quando o histórico da semana exata é
constante, `std=0`). `n_semanas_consecutivas_crescimento` conta quantas
comparações consecutivas `casos_t > casos_t-1 > ... ` valem, parando na
primeira quebra ou no primeiro lag ausente (início da série do bairro) —
nunca "pula" uma quebra para continuar contando.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LAGS_CASOS = (1, 2, 3, 4)
JANELAS_ROLLING_MEDIA = (2, 4, 8)
JANELA_ROLLING_SOMA = 4
JANELA_ROLLING_MAX = 4
EPS_RAZAO = 1.0

FEATURES_EPIDEMIOLOGICAS_BASE = (
    "casos_t",
    *(f"casos_t_menos_{k}" for k in LAGS_CASOS),
    *(f"media_{k}s" for k in JANELAS_ROLLING_MEDIA),
    f"soma_{JANELA_ROLLING_SOMA}s",
    f"max_{JANELA_ROLLING_MAX}s",
    "tendencia_1s",
    "estado_alto_risco_t",
)

FEATURES_SAZONAIS = (
    "semana_epidemiologica",
    "mes",
    "trimestre",
    "semana_sin",
    "semana_cos",
    "media_historica_semana_exata",
)

FEATURES_TERRITORIAIS_NUMERICAS = (
    "area_km2",
    "centroide_lat",
    "centroide_lon",
)
FEATURES_TERRITORIAIS_CATEGORICAS = (
    "codigo_rpa",
    "codigo_microrregiao",
)

FEATURES_HISTORICO_LOCAL = (
    "razao_limiar_historico",
    "z_score_historico_local",
    "razao_media_recente",
)

FEATURES_MOMENTUM = (
    "delta_1s",
    "delta_2s",
    "aceleracao_1s",
    "taxa_crescimento_suavizada",
    "n_semanas_consecutivas_crescimento",
)

FEATURES_CLIMATICAS = (
    "precipitacao_total_semana_mm",
    "precipitacao_media_diaria_mm",
    "precipitacao_maxima_diaria_mm",
    "dias_com_chuva",
    "completude_climatica_semana",
    "chuva_7d_mm",
    "chuva_14d_mm",
    "chuva_21d_mm",
    "chuva_28d_mm",
)


def construir_indice_semana_global(df: pd.DataFrame) -> pd.DataFrame:
    """Índice sequencial 0..N-1 sobre as combinações distintas
    (ano_epidemiologico, semana_epidemiologica), ordenado cronologicamente
    por `semana_epi_data_inicio` — necessário para deslocar (shift) o
    target por horizonte e para as janelas rolling respeitarem a ordem
    cronológica real (que não é a mesma coisa que ordenar por
    `semana_epidemiologica` sozinha, pois ela se repete a cada ano)."""
    calendario = (
        df[["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"]]
        .drop_duplicates()
        .sort_values("semana_epi_data_inicio")
        .reset_index(drop=True)
    )
    calendario["indice_semana_global"] = range(len(calendario))
    return df.merge(
        calendario[["ano_epidemiologico", "semana_epidemiologica", "indice_semana_global"]],
        on=["ano_epidemiologico", "semana_epidemiologica"],
        how="left",
        validate="many_to_one",
    )


def construir_features_epidemiologicas_e_sazonais(df_estado: pd.DataFrame) -> pd.DataFrame:
    """Recebe a saída de `target.calcular_estado_alto_risco` (uma linha por
    bairro x semana, já com `estado_alto_risco`/`media_historica_semana_exata`)
    e devolve o mesmo DataFrame com as features epidemiológicas/sazonais
    adicionadas. Não calcula o target (isso é responsabilidade de
    `dataset.py`, que desloca `estado_alto_risco` pelo horizonte)."""
    df = construir_indice_semana_global(df_estado)
    df = df.sort_values(["codigo_bairro", "indice_semana_global"]).reset_index(drop=True)

    df["casos_t"] = df["casos"]
    grp = df.groupby("codigo_bairro", sort=False)["casos"]
    for k in LAGS_CASOS:
        df[f"casos_t_menos_{k}"] = grp.shift(k)
    for k in JANELAS_ROLLING_MEDIA:
        df[f"media_{k}s"] = grp.transform(lambda s, k=k: s.rolling(window=k, min_periods=1).mean())
    df[f"soma_{JANELA_ROLLING_SOMA}s"] = grp.transform(
        lambda s: s.rolling(window=JANELA_ROLLING_SOMA, min_periods=1).sum()
    )
    df[f"max_{JANELA_ROLLING_MAX}s"] = grp.transform(
        lambda s: s.rolling(window=JANELA_ROLLING_MAX, min_periods=1).max()
    )
    df["tendencia_1s"] = df["casos_t"] - df["casos_t_menos_1"]

    df["estado_alto_risco_t"] = df["estado_alto_risco"]

    df["mes"] = pd.to_datetime(df["semana_epi_data_fim"]).dt.month
    df["trimestre"] = pd.to_datetime(df["semana_epi_data_fim"]).dt.quarter
    angulo = 2 * np.pi * df["semana_epidemiologica"] / 53.0
    df["semana_sin"] = np.sin(angulo)
    df["semana_cos"] = np.cos(angulo)

    # --- Histórico local (contexto relativo, nunca casos absolutos sozinhos) ---
    df["razao_limiar_historico"] = df["casos_t"] / (df["limiar_historico_local"] + EPS_RAZAO)
    df["z_score_historico_local"] = (df["casos_t"] - df["media_historica_semana_exata"]) / (
        df["std_historica_semana_exata"] + EPS_RAZAO
    )
    df["razao_media_recente"] = df["casos_t"] / (df["media_4s"] + EPS_RAZAO)

    # --- Momentum / aceleração ---
    df["delta_1s"] = df["tendencia_1s"]
    df["delta_2s"] = df["casos_t"] - df["casos_t_menos_2"]
    df["aceleracao_1s"] = df["casos_t"] - 2 * df["casos_t_menos_1"] + df["casos_t_menos_2"]
    df["taxa_crescimento_suavizada"] = (df["casos_t"] - df["casos_t_menos_1"]) / (df["casos_t_menos_1"] + EPS_RAZAO)

    colunas_lag_consecutivas = ["casos_t"] + [f"casos_t_menos_{k}" for k in LAGS_CASOS]
    contagem = pd.Series(0.0, index=df.index)
    ativo = pd.Series(True, index=df.index)
    for i in range(len(colunas_lag_consecutivas) - 1):
        atual, anterior = colunas_lag_consecutivas[i], colunas_lag_consecutivas[i + 1]
        cresceu = (df[atual] > df[anterior]) & df[anterior].notna() & ativo
        contagem = contagem + cresceu.astype(float)
        ativo = ativo & cresceu
    df["n_semanas_consecutivas_crescimento"] = contagem

    return df


def selecionar_matriz_features(
    df: pd.DataFrame,
    incluir_sazonal: bool = True,
    incluir_territorio: bool = True,
    incluir_historico_local: bool = True,
    incluir_momentum: bool = True,
    incluir_clima: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """Monta a matriz `X` (features numéricas/one-hot) a partir de
    `df` (já processado por `construir_features_epidemiologicas_e_sazonais`).
    Território categórico vira one-hot (nunca `codigo_rpa`/`codigo_microrregiao`
    como número contínuo). Cada grupo pode ser ligado/desligado
    independentemente — usado pelo ablation da etapa de otimização
    (`FEATURES_EPIDEMIOLOGICAS_BASE` é sempre incluído, é o grupo mínimo).
    Retorna `(X, nomes_colunas)`."""
    colunas_numericas = list(FEATURES_EPIDEMIOLOGICAS_BASE)
    if incluir_sazonal:
        colunas_numericas += list(FEATURES_SAZONAIS)
    if incluir_territorio:
        colunas_numericas += list(FEATURES_TERRITORIAIS_NUMERICAS)
    if incluir_historico_local:
        colunas_numericas += list(FEATURES_HISTORICO_LOCAL)
    if incluir_momentum:
        colunas_numericas += list(FEATURES_MOMENTUM)
    if incluir_clima:
        colunas_numericas += list(FEATURES_CLIMATICAS)

    X_num = df[colunas_numericas].copy()
    if incluir_territorio:
        X_cat = pd.get_dummies(
            df[list(FEATURES_TERRITORIAIS_CATEGORICAS)].astype("category"),
            prefix=list(FEATURES_TERRITORIAIS_CATEGORICAS),
            dummy_na=False,
        )
        X = pd.concat([X_num, X_cat], axis=1)
    else:
        X = X_num
    return X, list(X.columns)
