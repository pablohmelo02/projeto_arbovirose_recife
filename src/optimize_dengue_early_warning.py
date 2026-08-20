"""Entry point reprodutível da etapa de OTIMIZAÇÃO do alerta antecipado de
dengue — continuação de `src/evaluate_dengue_alert_baseline.py`
(classificação da etapa anterior: B — existe sinal, precisa melhorar).

Uso:
    python -m src.optimize_dengue_early_warning

Ordem de execução (regra explícita da etapa — nunca tuning cego):

    diagnóstico (2023, drift, target)
        -> ablation de features
        -> alvo alternativo (comparação descritiva, não substitui o oficial)
        -> tuning controlado de hiperparâmetros (grade pequena, via walk-forward)
        -> validação walk-forward final (modelo/features escolhidos)
        -> threshold operacional (múltiplos limiares, métricas de linha E de episódio)
        -> ranking (Recall@K, posição antes do episódio)
        -> calibração (Brier score antes/depois)
        -> desempenho por bairro/ano/epidemias grandes
        -> feature importance por fold (estabilidade)

Não faz deploy, não integra ao dashboard, não usa deep learning/ensemble/
AutoML, não mexe em clima (mantido fora do modelo principal, ver etapa
anterior). Grava `reports/ml/dengue_early_warning_optimization.md` + CSVs
de apoio.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.ml import alert_metrics, baselines, diagnostics, evaluation, models, ranking
from src.ml import split as split_mod
from src.ml.dataset import montar_dataset
from src.ml.features import construir_indice_semana_global
from src.ml.target import (
    agregar_semanal_agravo,
    calcular_estado_alto_risco,
    calcular_estado_alto_risco_v2_experimental,
)

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "ml"

HORIZONTE_PRINCIPAL = 1
FEATURES_DRIFT = ["casos_t", "media_4s", "media_8s", "tendencia_1s", "estado_alto_risco_t", "media_historica_semana_exata"]

GRADE_HIPERPARAMETROS_CONTROLADA = [
    {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150},
    {"max_depth": 6, "learning_rate": 0.1, "max_iter": 200},  # == baseline anterior
    {"max_depth": 6, "learning_rate": 0.05, "max_iter": 300},
    {"max_depth": 8, "learning_rate": 0.1, "max_iter": 200},
]

THRESHOLDS_OPERACIONAIS = (0.3, 0.4, 0.5, 0.6, 0.7)


def _bloco_classificacao(nome: str, y_true, y_proba, threshold: float) -> dict:
    m = evaluation.metricas_classificacao(y_true, y_proba, threshold=threshold)
    m["nome"] = nome
    return m


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrado. Rode 'python -m src.export_dashboard_dataset' primeiro.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    logger.info("Gold carregada: %d linhas", len(df_gold))
    resultado: dict = {}

    # ==================================================================
    # FASE 1 — DIAGNÓSTICO
    # ==================================================================
    logger.info("FASE 1: diagnóstico (2023, drift, target)")

    df_sem = agregar_semanal_agravo(df_gold, "DENGUE")
    df_estado = calcular_estado_alto_risco(df_sem)
    df_estado_idx = construir_indice_semana_global(df_estado)

    resumo_ano = diagnostics.resumo_alvo_por_ano(df_estado)
    resumo_ano.to_csv(PASTA_RELATORIO / "diagnostico_alvo_por_ano.csv", index=False)

    episodios_todos = alert_metrics.construir_episodios(df_estado_idx)
    resumo_episodios_ano = diagnostics.resumo_episodios_por_ano(episodios_todos)
    resumo_episodios_ano.to_csv(PASTA_RELATORIO / "diagnostico_episodios_por_ano.csv", index=False)

    # Dataset BASE (mesmo da etapa anterior) para drift de features
    ctx, X, y, m_dataset = montar_dataset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_PRINCIPAL)
    grupos_drift = {
        "val_2020_2022": (ctx["ano_epidemiologico"] > split_mod.ANO_TREINO_FIM) & (ctx["ano_epidemiologico"] <= split_mod.ANO_VALIDACAO_FIM),
        "2023": ctx["ano_epidemiologico"] == 2023,
        "2024": ctx["ano_epidemiologico"] == 2024,
        "2025": ctx["ano_epidemiologico"] == 2025,
    }
    tabela_drift = diagnostics.drift_features(X, ctx["ano_epidemiologico"], FEATURES_DRIFT, split_mod.ANO_TREINO_FIM, grupos_drift)
    tabela_drift.to_csv(PASTA_RELATORIO / "diagnostico_drift_features.csv", index=False)

    resultado["diagnostico_alvo_por_ano"] = resumo_ano.to_dict("records")
    resultado["diagnostico_episodios_por_ano"] = resumo_episodios_ano.to_dict("records")

    # ==================================================================
    # FASE 2 — ABLATION DE FEATURES (grupos cumulativos, HGB default)
    # ==================================================================
    logger.info("FASE 2: ablation de features")

    configuracoes_ablation = [
        ("epi_basica", dict(incluir_sazonal=False, incluir_territorio=False, incluir_historico_local=False, incluir_momentum=False)),
        ("+sazonal", dict(incluir_sazonal=True, incluir_territorio=False, incluir_historico_local=False, incluir_momentum=False)),
        ("+territorio", dict(incluir_sazonal=True, incluir_territorio=True, incluir_historico_local=False, incluir_momentum=False)),
        ("+historico_local", dict(incluir_sazonal=True, incluir_territorio=True, incluir_historico_local=True, incluir_momentum=False)),
        ("+momentum (completo)", dict(incluir_sazonal=True, incluir_territorio=True, incluir_historico_local=True, incluir_momentum=True)),
    ]
    linhas_ablation = []
    for nome_config, kwargs in configuracoes_ablation:
        ctx_c, X_c, y_c, m_c = montar_dataset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_PRINCIPAL, **kwargs)
        idx_tr, idx_val, idx_te = split_mod.split_temporal(ctx_c)
        modelo_c = models.treinar_arvore(X_c.loc[idx_tr], y_c.loc[idx_tr])
        proba_c = models.prever_probabilidade(modelo_c, X_c.loc[idx_te])
        met_c = evaluation.metricas_classificacao(y_c.loc[idx_te], proba_c, threshold=0.5)
        linhas_ablation.append(
            {
                "configuracao": nome_config,
                "n_features": m_c["n_features"],
                "pr_auc": met_c["pr_auc"],
                "roc_auc": met_c["roc_auc"],
                "recall": met_c["recall"],
                "precision": met_c["precision"],
                "f1": met_c["f1"],
            }
        )
    tabela_ablation = pd.DataFrame(linhas_ablation)
    tabela_ablation.to_csv(PASTA_RELATORIO / "ablation_features.csv", index=False)
    resultado["ablation_features"] = tabela_ablation.to_dict("records")

    # ==================================================================
    # FASE 2b — TARGET ALTERNATIVO (comparação descritiva, não substitui o oficial)
    # ==================================================================
    logger.info("FASE 2b: comparação com target alternativo (experimental)")

    df_estado_v2 = calcular_estado_alto_risco_v2_experimental(df_estado)
    comparavel = df_estado_v2.dropna(subset=["estado_alto_risco", "estado_alto_risco_v2_experimental"])
    linhas_alvo_alt = []
    for ano, sub in comparavel.groupby("ano_epidemiologico"):
        oficial = sub["estado_alto_risco"]
        alt = sub["estado_alto_risco_v2_experimental"]
        concordancia = float((oficial == alt).mean())
        uniao = ((oficial == 1) | (alt == 1)).sum()
        intersecao = ((oficial == 1) & (alt == 1)).sum()
        jaccard = float(intersecao / uniao) if uniao > 0 else None
        linhas_alvo_alt.append(
            {
                "ano": int(ano),
                "n_positivos_oficial": int(oficial.sum()),
                "n_positivos_alt": int(alt.sum()),
                "concordancia": concordancia,
                "jaccard": jaccard,
            }
        )
    tabela_alvo_alt = pd.DataFrame(linhas_alvo_alt)
    tabela_alvo_alt.to_csv(PASTA_RELATORIO / "alvo_alternativo_comparacao.csv", index=False)
    resultado["alvo_alternativo_comparacao"] = tabela_alvo_alt.to_dict("records")

    # ==================================================================
    # FASE 3 — TUNING CONTROLADO (grade pequena, avaliada por walk-forward)
    # ==================================================================
    logger.info("FASE 3: tuning controlado de hiperparâmetros (walk-forward)")

    linhas_tuning = []
    for params in GRADE_HIPERPARAMETROS_CONTROLADA:
        pr_aucs = []
        for ano_teste, idx_tr, idx_te in split_mod.walk_forward_splits(ctx):
            modelo_g = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr], **params)
            proba_g = models.prever_probabilidade(modelo_g, X.loc[idx_te])
            met_g = evaluation.metricas_classificacao(y.loc[idx_te], proba_g, threshold=0.5)
            if met_g["pr_auc"] is not None:
                pr_aucs.append(met_g["pr_auc"])
        linhas_tuning.append(
            {
                **params,
                "pr_auc_media_walk_forward": float(np.mean(pr_aucs)),
                "pr_auc_mediana_walk_forward": float(np.median(pr_aucs)),
                "pr_auc_min_walk_forward": float(np.min(pr_aucs)),
            }
        )
    tabela_tuning = pd.DataFrame(linhas_tuning)
    tabela_tuning.to_csv(PASTA_RELATORIO / "tuning_hiperparametros.csv", index=False)
    resultado["tuning_hiperparametros"] = tabela_tuning.to_dict("records")

    melhor_config = tabela_tuning.loc[tabela_tuning["pr_auc_mediana_walk_forward"].idxmax()]
    melhores_params = {k: (int(melhor_config[k]) if k != "learning_rate" else float(melhor_config[k])) for k in ("max_depth", "learning_rate", "max_iter")}
    resultado["melhores_hiperparametros"] = melhores_params
    logger.info("Melhores hiperparâmetros (por mediana walk-forward): %s", melhores_params)

    # ==================================================================
    # FASE 4 — VALIDAÇÃO WALK-FORWARD FINAL (modelo/features escolhidos)
    # ==================================================================
    logger.info("FASE 4: walk-forward final")

    idx_treino, idx_val, idx_teste = split_mod.split_temporal(ctx)
    X_treino, y_treino = X.loc[idx_treino], y.loc[idx_treino]
    X_val, y_val = X.loc[idx_val], y.loc[idx_val]
    X_teste, y_teste = X.loc[idx_teste], y.loc[idx_teste]
    ctx_teste = ctx.loc[idx_teste]

    modelo_final = models.treinar_arvore(X_treino, y_treino, **melhores_params)

    linhas_wf_final = []
    for ano_teste, idx_tr, idx_te in split_mod.walk_forward_splits(ctx):
        modelo_wf = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr], **melhores_params)
        proba_wf = models.prever_probabilidade(modelo_wf, X.loc[idx_te])
        met_wf = evaluation.metricas_classificacao(y.loc[idx_te], proba_wf, threshold=0.5)
        linhas_wf_final.append(
            {
                "ano_teste": ano_teste,
                "n_treino": len(idx_tr),
                "n_teste": len(idx_te),
                "n_positivos": met_wf["n_positivos"],
                "pr_auc": met_wf["pr_auc"],
                "roc_auc": met_wf["roc_auc"],
                "recall": met_wf["recall"],
                "precision": met_wf["precision"],
                "f1": met_wf["f1"],
            }
        )
    tabela_wf_final = pd.DataFrame(linhas_wf_final)
    tabela_wf_final = diagnostics.lift_pr_auc(tabela_wf_final)
    tabela_wf_final.to_csv(PASTA_RELATORIO / "walk_forward_otimizado_por_ano.csv", index=False)

    resumo_variancia = {
        "pr_auc_media": float(tabela_wf_final["pr_auc"].mean()),
        "pr_auc_mediana": float(tabela_wf_final["pr_auc"].median()),
        "pr_auc_min": float(tabela_wf_final["pr_auc"].min()),
        "pr_auc_max": float(tabela_wf_final["pr_auc"].max()),
        "pr_auc_desvio": float(tabela_wf_final["pr_auc"].std()),
        "roc_auc_media": float(tabela_wf_final["roc_auc"].mean()),
        "roc_auc_min": float(tabela_wf_final["roc_auc"].min()),
        "lift_pr_auc_media": float(tabela_wf_final["lift_pr_auc"].mean()),
        "lift_pr_auc_mediana": float(tabela_wf_final["lift_pr_auc"].median()),
    }
    resultado["walk_forward_final"] = tabela_wf_final.to_dict("records")
    resultado["walk_forward_resumo_variancia"] = resumo_variancia

    # ==================================================================
    # FASE 5 — THRESHOLD OPERACIONAL (linha + episódio)
    # ==================================================================
    logger.info("FASE 5: threshold operacional")

    proba_val = models.prever_probabilidade(modelo_final, X_val)
    proba_teste = models.prever_probabilidade(modelo_final, X_teste)

    tabela_tradeoff = evaluation.trade_off_precision_recall(y_teste, proba_teste, thresholds=THRESHOLDS_OPERACIONAIS)

    df_episodios = alert_metrics.construir_episodios(df_estado_idx)
    df_episodios_teste = df_episodios[df_episodios["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM].reset_index(drop=True)

    linhas_threshold_operacional = []
    for t in THRESHOLDS_OPERACIONAIS:
        df_alertas_t = ctx_teste[["codigo_bairro", "indice_semana_alvo"]].copy()
        df_alertas_t["alerta"] = (proba_teste.to_numpy() >= t).astype(int)
        episodios_t, falsos_t = alert_metrics.avaliar_antecipacao(df_alertas_t, df_episodios_teste)
        resumo_t = alert_metrics.resumo_antecipacao(episodios_t, falsos_t)
        semanal_t = alert_metrics.metricas_operacionais_semanais(df_alertas_t, falsos_t)
        linha_class = tabela_tradeoff.loc[tabela_tradeoff["threshold"] == t].iloc[0]
        linhas_threshold_operacional.append(
            {
                "threshold": t,
                "precision": linha_class["precision"],
                "recall": linha_class["recall"],
                "f1": linha_class["f1"],
                "episodios_detectados_pct": resumo_t["taxa_deteccao"],
                "lead_time_mediano": resumo_t["lead_time_mediano_semanas"],
                "n_falsos_alertas": resumo_t["n_falsos_alertas"],
                "bairros_alertados_por_semana_media": semanal_t["bairros_alertados_por_semana_media"],
                "falsos_alertas_por_semana_media": semanal_t["falsos_alertas_por_semana_media"],
            }
        )
    tabela_threshold_operacional = pd.DataFrame(linhas_threshold_operacional)
    tabela_threshold_operacional.to_csv(PASTA_RELATORIO / "threshold_operacional.csv", index=False)
    resultado["threshold_operacional"] = tabela_threshold_operacional.to_dict("records")

    # Threshold escolhido por F1 na validação (mesma metodologia da etapa anterior)
    tabela_val = evaluation.trade_off_precision_recall(y_val, proba_val, thresholds=tuple(round(i / 100, 2) for i in range(5, 96, 5)))
    threshold_escolhido = float(tabela_val.loc[tabela_val["f1"].idxmax(), "threshold"])
    resultado["threshold_escolhido_na_validacao"] = threshold_escolhido
    logger.info("Threshold escolhido na validação (F1): %.2f", threshold_escolhido)

    df_alertas_final = ctx_teste[["codigo_bairro", "indice_semana_alvo"]].copy()
    df_alertas_final["alerta"] = (proba_teste.to_numpy() >= threshold_escolhido).astype(int)
    df_alertas_final["probabilidade"] = proba_teste.to_numpy()

    episodios_avaliados, falsos_alertas = alert_metrics.avaliar_antecipacao(df_alertas_final, df_episodios_teste)
    resumo_alerta_final = alert_metrics.resumo_antecipacao(episodios_avaliados, falsos_alertas)
    semanal_final = alert_metrics.metricas_operacionais_semanais(df_alertas_final, falsos_alertas)
    duracao_falsos = alert_metrics.duracao_falsos_alertas_consecutivos(falsos_alertas)
    resultado["alerta_resumo_final"] = resumo_alerta_final
    resultado["metricas_semanais_final"] = semanal_final
    resultado["duracao_falsos_alertas_final"] = duracao_falsos

    episodios_avaliados.to_csv(PASTA_RELATORIO / "episodios_avaliados_otimizado.csv", index=False)

    tabela_bairro = alert_metrics.metricas_por_bairro(episodios_avaliados, falsos_alertas)
    tabela_bairro.to_csv(PASTA_RELATORIO / "metricas_por_bairro_otimizado.csv", index=False)

    tabela_ano_ep = alert_metrics.metricas_por_ano(episodios_avaliados)
    tabela_ano_ep.to_csv(PASTA_RELATORIO / "metricas_por_ano_otimizado.csv", index=False)

    tabela_epidemias_grandes = alert_metrics.epidemias_grandes(episodios_avaliados)
    tabela_epidemias_grandes.to_csv(PASTA_RELATORIO / "epidemias_grandes_otimizado.csv", index=False)
    resultado["epidemias_grandes_resumo_final"] = {
        "n": len(tabela_epidemias_grandes),
        "taxa_deteccao": float(tabela_epidemias_grandes["detectado"].mean()) if len(tabela_epidemias_grandes) else None,
    }

    met_final_teste = evaluation.metricas_classificacao(y_teste, proba_teste, threshold=threshold_escolhido)
    resultado["metricas_classificacao_final_teste"] = met_final_teste

    # ==================================================================
    # FASE 6 — RANKING (Recall@K, posição antes do episódio)
    # ==================================================================
    logger.info("FASE 6: ranking territorial (Recall@K, posição antes de episódios)")

    df_ranking = ranking.construir_ranking_semanal(df_alertas_final[["codigo_bairro", "indice_semana_alvo", "probabilidade"]])
    estado_indexado = df_estado_idx.set_index(["codigo_bairro", "indice_semana_global"])["estado_alto_risco"]
    df_ranking["estado_real"] = df_ranking.apply(
        lambda r: estado_indexado.get((r["codigo_bairro"], r["indice_semana_alvo"])), axis=1
    )
    df_ranking_valido = df_ranking.dropna(subset=["estado_real"])

    tabela_recall_k = ranking.recall_em_k(df_ranking_valido, k_valores=(5, 10, 20))
    tabela_recall_k.to_csv(PASTA_RELATORIO / "recall_em_k.csv", index=False)
    resultado["recall_em_k"] = tabela_recall_k.to_dict("records")

    df_posicoes = ranking.posicao_antes_de_episodios(df_ranking, df_episodios_teste, janela=alert_metrics.JANELA_ALERTA_SEMANAS)
    df_posicoes.to_csv(PASTA_RELATORIO / "posicao_antes_episodios.csv", index=False)
    resumo_posicoes = ranking.resumo_posicao_antes_de_episodios(df_posicoes, k_valores=(5, 10, 20))
    resultado["resumo_posicao_antes_episodios"] = resumo_posicoes

    # ==================================================================
    # FASE 7 — CALIBRAÇÃO
    # ==================================================================
    logger.info("FASE 7: calibração (Brier score antes/depois)")

    brier_antes = evaluation.brier_score(y_teste, proba_teste)
    calib_antes = evaluation.diagnostico_calibracao(y_teste, proba_teste)
    calib_antes.to_csv(PASTA_RELATORIO / "calibracao_antes.csv", index=False)

    metodo_calibracao = "sigmoid" if len(idx_val) < 5000 else "isotonic"
    modelo_calibrado = models.calibrar_probabilidade(modelo_final, X_val, y_val, metodo=metodo_calibracao)
    proba_teste_calibrada = pd.Series(modelo_calibrado.predict_proba(X_teste)[:, 1], index=X_teste.index)
    brier_depois = evaluation.brier_score(y_teste, proba_teste_calibrada)
    calib_depois = evaluation.diagnostico_calibracao(y_teste, proba_teste_calibrada)
    calib_depois.to_csv(PASTA_RELATORIO / "calibracao_depois.csv", index=False)

    resultado["calibracao"] = {
        "metodo": metodo_calibracao,
        "n_validacao_usada": len(idx_val),
        "brier_antes": brier_antes,
        "brier_depois": brier_depois,
        "melhora_absoluta": brier_antes - brier_depois,
    }

    # ==================================================================
    # FASE 8 — FEATURE IMPORTANCE POR FOLD (estabilidade)
    # ==================================================================
    logger.info("FASE 8: feature importance por fold (estabilidade)")

    from sklearn.inspection import permutation_importance

    importancias_por_fold = []
    for ano_teste, idx_tr, idx_te in split_mod.walk_forward_splits(ctx):
        if len(idx_te) < 200:
            continue
        modelo_fold = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr], **melhores_params)
        imp = permutation_importance(
            modelo_fold, X.loc[idx_te], y.loc[idx_te], n_repeats=3, random_state=42, scoring="average_precision"
        )
        for feat, valor in zip(X.columns, imp.importances_mean):
            importancias_por_fold.append({"ano_teste": ano_teste, "feature": feat, "importancia": valor})
    tabela_importancia_fold = pd.DataFrame(importancias_por_fold)
    tabela_importancia_fold.to_csv(PASTA_RELATORIO / "feature_importance_por_fold.csv", index=False)

    estabilidade = (
        tabela_importancia_fold.groupby("feature")["importancia"]
        .agg(media="mean", desvio="std", minimo="min", maximo="max")
        .reset_index()
        .sort_values("media", ascending=False)
    )
    estabilidade.to_csv(PASTA_RELATORIO / "feature_importance_estabilidade.csv", index=False)
    resultado["feature_importance_estabilidade"] = estabilidade.head(15).to_dict("records")

    # ==================================================================
    # SALVAR RESULTADO COMPLETO
    # ==================================================================
    with open(PASTA_RELATORIO / "resultado_otimizacao_completo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Resultado completo salvo em %s", PASTA_RELATORIO / "resultado_otimizacao_completo.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
