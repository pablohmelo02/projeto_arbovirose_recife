"""Monta o dataset supervisionado: Gold -> DENGUE -> estado/target -> features
-> matriz `(X, y)` pronta para split/baseline/modelo.

## Definição formal do caso de uso

- **Unidade operacional**: bairro x semana epidemiológica (mesma unidade da
  Gold).
- **Instante de previsão `t`**: uma linha (`codigo_bairro`,
  `ano_epidemiologico`, `semana_epidemiologica`) — representa "tudo que
  sabemos até o fim dessa semana".
- **Horizonte**: `horizonte` semanas epidemiológicas (parâmetro; ver
  `reports/ml/dengue_early_warning_baseline.md` para a escolha do horizonte
  principal usado nesta etapa).
- **Target**: `estado_alto_risco` do bairro em `t + horizonte` (ver
  `target.py`) — **não** é "quantidade de casos em t+h", é "o bairro estará
  em estado de risco elevado (acima do limiar histórico-sazonal local) em
  t+h?". A previsão quantitativa (Saída A, `casos_t+h`) é tratada à parte
  (ver `baselines.py`, seção de contagem) — não é o produto principal desta
  etapa.
- **Informação permitida**: tudo calculável a partir de `t` ou antes
  (lags/rolling de casos, estado atual, sazonalidade expandindo só sobre
  anos passados, território estático, clima da Gold — já garantidamente
  `data <= semana_epi_data_fim` de `t`).
- **Informação proibida**: qualquer `casos`/`estado_alto_risco` de semana
  `> t` na construção das FEATURES de `t` (o target em si, por definição, é
  o único lugar onde `t+horizonte` aparece — isso é o desenho pretendido,
  não leakage, ver `target.py`).

## Linhas excluídas (contadas, nunca silenciosas)

1. Target indefinido em `t+horizonte` (`tipo_limiar="indefinido"` na semana
   alvo — bairro/período sem histórico suficiente para definir surto).
2. Últimas `horizonte` semanas de cada bairro (não existe `t+horizonte`
   dentro da série).
3. Linhas com alguma feature ausente na matriz `X` selecionada — no caso
   BASE (sem clima) isso só acontece no início de cada série de bairro
   (lags/rolling ainda não têm profundidade suficiente) ou sem histórico
   sazonal (`media_historica_semana_exata`); no caso BASE+CLIMA, ausência de
   leitura climática real também exclui a linha (`missing != 0`, nunca
   imputado para o modelo de regressão logística — ver `models.py` para por
   que o modelo de árvore não precisa dessa exclusão).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.eda.filtros import linhas_com_clima_real
from src.ml.features import construir_features_epidemiologicas_e_sazonais, selecionar_matriz_features
from src.ml.onset import HORIZONTES_ONSET, construir_target_onset
from src.ml.target import agregar_semanal_agravo, calcular_estado_alto_risco


def montar_dataset(
    df_gold: pd.DataFrame,
    agravo: str = "DENGUE",
    horizonte: int = 1,
    incluir_clima: bool = False,
    exigir_clima_real: bool = False,
    permitir_nan_features: bool = False,
    incluir_sazonal: bool = True,
    incluir_territorio: bool = True,
    incluir_historico_local: bool = True,
    incluir_momentum: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, dict[str, Any]]:
    """Devolve `(df_contexto, X, y, metricas)`.

    `df_contexto` preserva identificação (`codigo_bairro`, `ano_epidemiologico`,
    `semana_epidemiologica`, `indice_semana_global`) e colunas de estado —
    necessário para split temporal, agrupamento em episódios e relatórios por
    bairro/ano (ver `alert_metrics.py`). `X`/`y` têm o mesmo índice posicional
    (0..n-1) que `df_contexto` — sempre usar `.reset_index(drop=True)` já
    aplicado aqui, nunca reindexar de outra forma.
    """
    df_semanal = agregar_semanal_agravo(df_gold, agravo)
    df_estado = calcular_estado_alto_risco(df_semanal)
    df_feat = construir_features_epidemiologicas_e_sazonais(df_estado)
    df_feat = df_feat.sort_values(["codigo_bairro", "indice_semana_global"]).reset_index(drop=True)

    linhas_antes = len(df_feat)

    df_feat["target_t_mais_h"] = df_feat.groupby("codigo_bairro", sort=False)["estado_alto_risco"].shift(-horizonte)
    df_feat["casos_alvo"] = df_feat.groupby("codigo_bairro", sort=False)["casos"].shift(-horizonte)
    df_feat["indice_semana_alvo"] = df_feat["indice_semana_global"] + horizonte

    linhas_target_indefinido = int(df_feat["target_t_mais_h"].isna().sum())

    if exigir_clima_real:
        df_feat = linhas_com_clima_real(df_feat).reset_index(drop=True)
    linhas_apos_filtro_clima = len(df_feat)

    X, colunas = selecionar_matriz_features(
        df_feat,
        incluir_sazonal=incluir_sazonal,
        incluir_territorio=incluir_territorio,
        incluir_historico_local=incluir_historico_local,
        incluir_momentum=incluir_momentum,
        incluir_clima=incluir_clima,
    )
    y = df_feat["target_t_mais_h"]

    if permitir_nan_features:
        # Usado só para o experimento BASE+CLIMA com o modelo de árvore
        # (`HistGradientBoostingClassifier` aceita NaN nativamente, ver
        # `models.py`) -- garante que a linha comparada BASE x BASE+CLIMA
        # seja exatamente a mesma (mesmo filtro `exigir_clima_real`, sem
        # exclusão adicional por NaN pontual de alguma janela climática).
        mask_valida = y.notna()
    else:
        mask_valida = y.notna() & X.notna().all(axis=1)
    linhas_feature_nan = int((~mask_valida & y.notna()).sum())

    df_contexto = df_feat.loc[mask_valida].reset_index(drop=True)
    X_final = X.loc[mask_valida].reset_index(drop=True)
    y_final = y.loc[mask_valida].astype(int).reset_index(drop=True)

    metricas = {
        "agravo": agravo,
        "horizonte_semanas": horizonte,
        "incluir_clima": incluir_clima,
        "incluir_sazonal": incluir_sazonal,
        "incluir_territorio": incluir_territorio,
        "incluir_historico_local": incluir_historico_local,
        "incluir_momentum": incluir_momentum,
        "exigir_clima_real": exigir_clima_real,
        "linhas_antes": linhas_antes,
        "linhas_target_indefinido": linhas_target_indefinido,
        "linhas_apos_filtro_clima_real": linhas_apos_filtro_clima if exigir_clima_real else linhas_antes,
        "linhas_excluidas_feature_nan": linhas_feature_nan,
        "linhas_finais": len(y_final),
        "proporcao_positiva": float(y_final.mean()) if len(y_final) else None,
        "n_positivos": int(y_final.sum()) if len(y_final) else 0,
        "n_negativos": int((y_final == 0).sum()) if len(y_final) else 0,
        "n_features": len(colunas),
        "colunas_features": colunas,
    }
    return df_contexto, X_final, y_final, metricas


def montar_dataset_onset(
    df_gold: pd.DataFrame,
    agravo: str = "DENGUE",
    horizonte: int = 3,
    incluir_sazonal: bool = True,
    incluir_territorio: bool = True,
    incluir_historico_local: bool = True,
    incluir_momentum: bool = True,
    incluir_clima: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, dict[str, Any]]:
    """Formulação B desta etapa (`src/ml/onset.py`): "um novo episódio de
    risco começará entre `t+1` e `t+horizonte`?" — diferente de
    `montar_dataset` (formulação A: "o bairro estará em estado de risco
    elevado em `t+horizonte`?", que também é `1` para semanas de mera
    continuação de um episódio já ativo).

    Mesmas FEATURES de `montar_dataset` (`features.py`, sem mudança) — só
    o TARGET muda. `indice_semana_alvo` aqui é igual a `indice_semana_global`
    (o próprio `t`, não deslocado): como o target já resume "existe onset
    em algum lugar da janela `t+1..t+horizonte`?", o ranking/alerta
    operacionalmente relevante é "isto foi sinalizado no instante `t`", não
    uma única semana-alvo deslocada (ver `reports/ml/dengue_onset_ranking_analysis.md`
    para a justificativa completa)."""
    if horizonte not in HORIZONTES_ONSET:
        raise ValueError(f"horizonte {horizonte!r} não está em HORIZONTES_ONSET={HORIZONTES_ONSET}")

    df_semanal = agregar_semanal_agravo(df_gold, agravo)
    df_estado = calcular_estado_alto_risco(df_semanal)
    df_feat = construir_features_epidemiologicas_e_sazonais(df_estado)
    df_feat = df_feat.sort_values(["codigo_bairro", "indice_semana_global"]).reset_index(drop=True)
    df_feat = construir_target_onset(df_feat, horizontes=HORIZONTES_ONSET)

    linhas_antes = len(df_feat)
    df_feat["indice_semana_alvo"] = df_feat["indice_semana_global"]

    coluna_target = f"target_onset_h{horizonte}"
    linhas_target_indefinido = int(df_feat[coluna_target].isna().sum())

    X, colunas = selecionar_matriz_features(
        df_feat,
        incluir_sazonal=incluir_sazonal,
        incluir_territorio=incluir_territorio,
        incluir_historico_local=incluir_historico_local,
        incluir_momentum=incluir_momentum,
        incluir_clima=incluir_clima,
    )
    y = df_feat[coluna_target]

    mask_valida = y.notna() & X.notna().all(axis=1)
    linhas_feature_nan = int((~mask_valida & y.notna()).sum())

    df_contexto = df_feat.loc[mask_valida].reset_index(drop=True)
    X_final = X.loc[mask_valida].reset_index(drop=True)
    y_final = y.loc[mask_valida].astype(int).reset_index(drop=True)

    metricas = {
        "agravo": agravo,
        "formulacao": "onset",
        "horizonte_semanas": horizonte,
        "incluir_clima": incluir_clima,
        "incluir_sazonal": incluir_sazonal,
        "incluir_territorio": incluir_territorio,
        "incluir_historico_local": incluir_historico_local,
        "incluir_momentum": incluir_momentum,
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
