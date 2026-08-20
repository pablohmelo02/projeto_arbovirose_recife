"""Entry point reprodutível da etapa de alerta antecipado de dengue.

Uso:
    python -m src.evaluate_dengue_alert_baseline

Lê o mesmo dataset estático que o dashboard/EDA usam
(`dashboard/data/gold_arboviroses_clima_bairro.parquet`), reproduz o
dataset supervisionado, os splits, os baselines, os dois modelos
(regressão logística + árvore), as métricas de classificação e as métricas
operacionais de alerta (episódios/lead time/falsos alertas), e grava
`reports/ml/dengue_early_warning_baseline.md` + CSVs de apoio.

Regra de parada (ver CLAUDE.md/pedido da etapa): nenhum tuning extensivo,
nenhum ensemble, nenhum deep learning, nenhum deploy, nenhuma alteração no
dashboard.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

from src.ml import alert_metrics, baselines, evaluation, models, split as split_mod
from src.ml.dataset import montar_dataset
from src.ml.target import agregar_semanal_agravo, calcular_estado_alto_risco

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "ml"

HORIZONTE_PRINCIPAL = 1
HORIZONTE_SECUNDARIO = 2
THRESHOLDS_TRADEOFF = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _selecionar_threshold_por_f1(y_val, proba_val) -> float:
    """Escolhe o limiar de decisão que maximiza F1 na VALIDAÇÃO (nunca no
    teste) — evita "escolher o limiar que faz o teste parecer bom"."""
    tabela = evaluation.trade_off_precision_recall(y_val, proba_val, thresholds=tuple(round(x, 2) for x in [i / 100 for i in range(5, 96, 5)]))
    linha = tabela.loc[tabela["f1"].idxmax()]
    return float(linha["threshold"])


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

    resultado: dict = {"horizonte_principal": HORIZONTE_PRINCIPAL}

    # ------------------------------------------------------------------
    # 1) Dataset BASE (dengue, 2013-2025, sem clima), horizonte principal
    # ------------------------------------------------------------------
    df_ctx, X, y, metricas_dataset = montar_dataset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_PRINCIPAL, incluir_clima=False)
    logger.info("Dataset BASE (h=%d): %s", HORIZONTE_PRINCIPAL, metricas_dataset)
    resultado["dataset_base"] = metricas_dataset

    idx_treino, idx_val, idx_teste = split_mod.split_temporal(df_ctx)
    logger.info("Split: treino=%d val=%d teste=%d", len(idx_treino), len(idx_val), len(idx_teste))
    resultado["split"] = {
        "n_treino": len(idx_treino),
        "n_validacao": len(idx_val),
        "n_teste": len(idx_teste),
        "ano_treino_fim": split_mod.ANO_TREINO_FIM,
        "ano_validacao_fim": split_mod.ANO_VALIDACAO_FIM,
    }

    X_treino, y_treino = X.loc[idx_treino], y.loc[idx_treino]
    X_val, y_val = X.loc[idx_val], y.loc[idx_val]
    X_teste, y_teste = X.loc[idx_teste], y.loc[idx_teste]

    # ------------------------------------------------------------------
    # 2) Baselines (classificação) no teste
    # ------------------------------------------------------------------
    ctx_teste = df_ctx.loc[idx_teste]
    proba_persistencia = baselines.baseline_persistencia(ctx_teste)
    proba_crescimento = baselines.baseline_crescimento_recente(ctx_teste)
    proba_sazonal = baselines.baseline_sazonal_simples(ctx_teste)

    resultado["baselines_classificacao"] = [
        _bloco_classificacao("persistencia", y_teste, proba_persistencia, threshold=0.5),
        _bloco_classificacao("crescimento_recente", y_teste, proba_crescimento, threshold=0.5),
        _bloco_classificacao("sazonal_simples", y_teste, proba_sazonal, threshold=0.5),
    ]

    # Baseline de contagem (previsão quantitativa, Saída A)
    casos_previstos_persist = baselines.baseline_contagem_persistencia(ctx_teste)
    casos_previstos_media4s = baselines.baseline_contagem_media_movel_4s(ctx_teste)
    resultado["baselines_quantitativos"] = {
        "persistencia": evaluation.erro_previsao_quantitativa(ctx_teste["casos_alvo"], casos_previstos_persist),
        "media_movel_4s": evaluation.erro_previsao_quantitativa(ctx_teste["casos_alvo"], casos_previstos_media4s),
    }

    # ------------------------------------------------------------------
    # 3) Modelos: Logistic Regression + HistGradientBoosting
    # ------------------------------------------------------------------
    modelo_lr = models.treinar_logistic_regression(X_treino, y_treino)
    proba_lr_val = models.prever_probabilidade(modelo_lr, X_val)
    proba_lr_teste = models.prever_probabilidade(modelo_lr, X_teste)
    threshold_lr = _selecionar_threshold_por_f1(y_val, proba_lr_val)

    modelo_arvore = models.treinar_arvore(X_treino, y_treino)
    proba_arvore_val = models.prever_probabilidade(modelo_arvore, X_val)
    proba_arvore_teste = models.prever_probabilidade(modelo_arvore, X_teste)
    threshold_arvore = _selecionar_threshold_por_f1(y_val, proba_arvore_val)

    resultado["modelos_classificacao"] = [
        _bloco_classificacao("logistic_regression", y_teste, proba_lr_teste, threshold=threshold_lr),
        _bloco_classificacao("arvore_histgb", y_teste, proba_arvore_teste, threshold=threshold_arvore),
    ]
    resultado["thresholds_escolhidos_na_validacao"] = {
        "logistic_regression": threshold_lr,
        "arvore_histgb": threshold_arvore,
    }

    tabela_tradeoff_arvore = evaluation.trade_off_precision_recall(y_teste, proba_arvore_teste, thresholds=THRESHOLDS_TRADEOFF)
    tabela_tradeoff_arvore.to_csv(PASTA_RELATORIO / "tradeoff_precision_recall_arvore.csv", index=False)

    calibracao_arvore = evaluation.diagnostico_calibracao(y_teste, proba_arvore_teste)
    calibracao_arvore.to_csv(PASTA_RELATORIO / "calibracao_arvore.csv", index=False)

    # Feature importance (permutation, modelo de árvore)
    try:
        from sklearn.inspection import permutation_importance

        imp = permutation_importance(modelo_arvore, X_teste, y_teste, n_repeats=5, random_state=42, scoring="average_precision")
        importancias = pd.DataFrame({"feature": X_teste.columns, "importancia_media": imp.importances_mean, "importancia_std": imp.importances_std}).sort_values("importancia_media", ascending=False)
        importancias.to_csv(PASTA_RELATORIO / "feature_importance_arvore.csv", index=False)
        resultado["top_features"] = importancias.head(10).to_dict("records")
    except Exception:  # pragma: no cover - diagnóstico, não crítico
        logger.exception("Falha ao calcular permutation importance")
        resultado["top_features"] = []

    # ------------------------------------------------------------------
    # 4) Walk-forward (HistGradientBoosting) — generalização por ano
    # ------------------------------------------------------------------
    linhas_wf = []
    for ano_teste, idx_tr, idx_te in split_mod.walk_forward_splits(df_ctx):
        modelo_wf = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr])
        proba_wf = models.prever_probabilidade(modelo_wf, X.loc[idx_te])
        m = evaluation.metricas_classificacao(y.loc[idx_te], proba_wf, threshold=0.5)
        linhas_wf.append({"ano_teste": ano_teste, "n_treino": len(idx_tr), "n_teste": len(idx_te), **{k: m[k] for k in ("precision", "recall", "f1", "pr_auc", "roc_auc", "n_positivos")}})
    tabela_walk_forward = pd.DataFrame(linhas_wf)
    tabela_walk_forward.to_csv(PASTA_RELATORIO / "walk_forward_por_ano.csv", index=False)
    resultado["walk_forward"] = tabela_walk_forward.to_dict("records")

    # ------------------------------------------------------------------
    # 5) Métricas operacionais de alerta (episódios/lead time/falsos alertas)
    #    Usa o modelo de árvore (melhor PR-AUC esperado) no conjunto de teste.
    # ------------------------------------------------------------------
    df_semanal_completo = agregar_semanal_agravo(df_gold, "DENGUE")
    df_estado_completo = calcular_estado_alto_risco(df_semanal_completo)
    # precisa do indice_semana_global -- reaproveita a mesma função de features
    from src.ml.features import construir_indice_semana_global

    df_estado_completo = construir_indice_semana_global(df_estado_completo)

    df_episodios = alert_metrics.construir_episodios(df_estado_completo)
    df_episodios_teste = df_episodios[df_episodios["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM].reset_index(drop=True)

    df_alertas = ctx_teste[["codigo_bairro", "indice_semana_alvo"]].copy()
    df_alertas["alerta"] = (proba_arvore_teste.to_numpy() >= threshold_arvore).astype(int)

    episodios_avaliados, falsos_alertas = alert_metrics.avaliar_antecipacao(df_alertas, df_episodios_teste)
    resumo_alerta = alert_metrics.resumo_antecipacao(episodios_avaliados, falsos_alertas)
    resultado["alerta_resumo"] = resumo_alerta

    episodios_avaliados.to_csv(PASTA_RELATORIO / "episodios_avaliados_teste.csv", index=False)

    tabela_bairro = alert_metrics.metricas_por_bairro(episodios_avaliados, falsos_alertas)
    tabela_bairro.to_csv(PASTA_RELATORIO / "metricas_por_bairro.csv", index=False)

    tabela_ano = alert_metrics.metricas_por_ano(episodios_avaliados)
    tabela_ano.to_csv(PASTA_RELATORIO / "metricas_por_ano.csv", index=False)

    tabela_epidemias_grandes = alert_metrics.epidemias_grandes(episodios_avaliados)
    tabela_epidemias_grandes.to_csv(PASTA_RELATORIO / "epidemias_grandes.csv", index=False)
    resultado["epidemias_grandes_resumo"] = {
        "n": len(tabela_epidemias_grandes),
        "taxa_deteccao": float(tabela_epidemias_grandes["detectado"].mean()) if len(tabela_epidemias_grandes) else None,
    }

    # ------------------------------------------------------------------
    # 6) Horizonte secundário (t+2) — comparação rápida, sem pipeline completo
    # ------------------------------------------------------------------
    df_ctx_h2, X_h2, y_h2, metricas_dataset_h2 = montar_dataset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_SECUNDARIO, incluir_clima=False)
    idx_tr_h2, idx_val_h2, idx_te_h2 = split_mod.split_temporal(df_ctx_h2)
    modelo_arvore_h2 = models.treinar_arvore(X_h2.loc[idx_tr_h2], y_h2.loc[idx_tr_h2])
    proba_h2_teste = models.prever_probabilidade(modelo_arvore_h2, X_h2.loc[idx_te_h2])
    m_h2 = evaluation.metricas_classificacao(y_h2.loc[idx_te_h2], proba_h2_teste, threshold=0.5)
    resultado["horizonte_secundario_t2"] = {"dataset": metricas_dataset_h2, "metricas": m_h2}

    # ------------------------------------------------------------------
    # 7) BASE x BASE+CLIMA (2024-2025, mesmas linhas, mesmo split, mesmo modelo)
    # ------------------------------------------------------------------
    ctx_base_c, X_base_c, y_base_c, m_base_c = montar_dataset(
        df_gold, agravo="DENGUE", horizonte=HORIZONTE_PRINCIPAL, incluir_clima=False, exigir_clima_real=True, permitir_nan_features=True
    )
    ctx_clima, X_clima, y_clima, m_clima = montar_dataset(
        df_gold, agravo="DENGUE", horizonte=HORIZONTE_PRINCIPAL, incluir_clima=True, exigir_clima_real=True, permitir_nan_features=True
    )
    assert len(ctx_base_c) == len(ctx_clima), "BASE e BASE+CLIMA devem ter exatamente as mesmas linhas"

    idx_tr_c = ctx_base_c.index[ctx_base_c["ano_epidemiologico"] == 2024]
    idx_te_c = ctx_base_c.index[ctx_base_c["ano_epidemiologico"] == 2025]

    resultado["comparacao_clima"] = {
        "n_linhas": len(ctx_base_c),
        "n_treino_2024": len(idx_tr_c),
        "n_teste_2025": len(idx_te_c),
    }
    if len(idx_tr_c) > 0 and len(idx_te_c) > 0 and y_base_c.loc[idx_tr_c].nunique() > 1:
        modelo_base_c = models.treinar_arvore(X_base_c.loc[idx_tr_c], y_base_c.loc[idx_tr_c])
        proba_base_c = models.prever_probabilidade(modelo_base_c, X_base_c.loc[idx_te_c])
        m_base_c_result = evaluation.metricas_classificacao(y_base_c.loc[idx_te_c], proba_base_c, threshold=0.5)

        modelo_clima = models.treinar_arvore(X_clima.loc[idx_tr_c], y_clima.loc[idx_tr_c])
        proba_clima = models.prever_probabilidade(modelo_clima, X_clima.loc[idx_te_c])
        m_clima_result = evaluation.metricas_classificacao(y_clima.loc[idx_te_c], proba_clima, threshold=0.5)

        resultado["comparacao_clima"]["base"] = m_base_c_result
        resultado["comparacao_clima"]["base_mais_clima"] = m_clima_result
        resultado["comparacao_clima"]["ganho_pr_auc"] = (
            (m_clima_result["pr_auc"] - m_base_c_result["pr_auc"])
            if m_clima_result["pr_auc"] is not None and m_base_c_result["pr_auc"] is not None
            else None
        )
    else:
        resultado["comparacao_clima"]["aviso"] = "amostra insuficiente ou target sem as duas classes em treino/teste 2024/2025"

    with open(PASTA_RELATORIO / "resultado_completo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Resultado completo salvo em %s", PASTA_RELATORIO / "resultado_completo.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
