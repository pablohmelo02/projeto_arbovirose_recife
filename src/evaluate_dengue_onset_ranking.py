"""Entry point reprodutível da formulação B (onset + ranking territorial)
— continuação de `src/optimize_dengue_early_warning.py` (classificação da
etapa anterior: B — melhorou, mas ainda apresenta fragilidades relevantes,
decisão: NÃO integrar ao dashboard).

Uso:
    python -m src.evaluate_dengue_onset_ranking

Compara duas formulações do problema, usando o MESMO split temporal, as
MESMAS features (epidemiologia + sazonalidade + histórico local +
território [+ momentum]) e o MESMO modelo (HistGradientBoostingClassifier,
hiperparâmetros já escolhidos na etapa de otimização controlada):

- **Formulação A** (`src/ml/dataset.py::montar_dataset`, já existente):
  "o bairro estará em estado de risco elevado em t+1?" — inclui semanas de
  mera continuação de um episódio já ativo.
- **Formulação B** (`src/ml/onset.py`, nova): "um novo episódio de risco
  começará entre t+1 e t+N?" — só a PRIMEIRA semana de cada episódio conta
  como evento positivo.

O produto é tratado principalmente como **ranking territorial preventivo**
(seção 11 do pedido), não classificação binária isolada — por isso a
métrica central é Recall@K/Precision@K (K=5,10,15,20), não Precision/Recall
num único threshold.

Não faz deploy, não integra ao dashboard, não usa clima, não faz nova
busca extensa de hiperparâmetros/algoritmos.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.ml import alert_metrics, evaluation, models, ranking
from src.ml import split as split_mod
from src.ml.dataset import montar_dataset, montar_dataset_onset
from src.ml.features import construir_indice_semana_global
from src.ml.onset import HORIZONTES_ONSET
from src.ml.target import agregar_semanal_agravo, calcular_estado_alto_risco

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "ml"

HORIZONTE_ONSET_PRINCIPAL = 3
HORIZONTE_ONSET_COMPARACAO = 1
K_VALORES = (5, 10, 15, 20)
JANELA_LEAD_TIME = 4

# Hiperparâmetros escolhidos na etapa de otimização controlada (walk-forward,
# mediana de PR-AUC) -- reaproveitados sem nova busca, conforme instrução
# explícita desta etapa.
HIPERPARAMETROS_ARVORE = {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150}


def _treinar_e_prever(df_ctx: pd.DataFrame, X: pd.DataFrame, y: pd.Series, idx_treino, idx_teste):
    modelo = models.treinar_arvore(X.loc[idx_treino], y.loc[idx_treino], **HIPERPARAMETROS_ARVORE)
    proba = models.prever_probabilidade(modelo, X.loc[idx_teste])
    return modelo, proba


def _construir_df_ranking(ctx_teste: pd.DataFrame, proba: pd.Series, coluna_estado_real: pd.Series) -> pd.DataFrame:
    df_alertas = ctx_teste[["codigo_bairro", "indice_semana_alvo"]].copy()
    df_alertas["probabilidade"] = proba.to_numpy()
    df_alertas["estado_real"] = coluna_estado_real.to_numpy()
    return ranking.construir_ranking_semanal(df_alertas)


def _avaliar_ranking_completo(df_ranking: pd.DataFrame, df_episodios: pd.DataFrame, nome: str) -> dict:
    recall_k = ranking.recall_em_k(df_ranking, k_valores=K_VALORES)
    precision_k = ranking.precision_em_k(df_ranking, k_valores=K_VALORES)
    posicoes = ranking.posicao_antes_de_episodios(df_ranking, df_episodios, janela=JANELA_LEAD_TIME)
    resumo_posicoes = ranking.resumo_posicao_antes_de_episodios(posicoes, k_valores=K_VALORES)
    estabilidades = {k: ranking.estabilidade_ranking(df_ranking, k=k) for k in K_VALORES}
    return {
        "nome": nome,
        "recall_em_k": recall_k.to_dict("records"),
        "precision_em_k": precision_k.to_dict("records"),
        "resumo_posicao_antes_episodios": resumo_posicoes,
        "estabilidade_por_k": estabilidades,
    }, posicoes


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrado. Rode 'python -m src.export_dashboard_dataset' primeiro.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    logger.info("Gold carregada: %d linhas", len(df_gold))
    resultado: dict = {}

    # Estado completo (para episódios/onsets/lead-time, independente de horizonte)
    df_sem = agregar_semanal_agravo(df_gold, "DENGUE")
    df_estado = calcular_estado_alto_risco(df_sem)
    df_estado_idx = construir_indice_semana_global(df_estado)
    df_episodios_todos = alert_metrics.construir_episodios(df_estado_idx)
    df_episodios_teste = df_episodios_todos[df_episodios_todos["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM].reset_index(drop=True)

    # ==================================================================
    # FASE 1 — DATASETS: Formulação A (estado t+1) e B (onset h1, h3)
    # ==================================================================
    logger.info("FASE 1: montando datasets das formulações A e B")

    ctx_a, X_a, y_a, m_a = montar_dataset(df_gold, agravo="DENGUE", horizonte=1)
    ctx_b3, X_b3, y_b3, m_b3 = montar_dataset_onset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET_PRINCIPAL)
    ctx_b1, X_b1, y_b1, m_b1 = montar_dataset_onset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET_COMPARACAO)

    resultado["dataset_formulacao_a"] = m_a
    resultado["dataset_formulacao_b_h3"] = m_b3
    resultado["dataset_formulacao_b_h1"] = m_b1
    logger.info("Prevalência -- A: %.4f | B h1: %.4f | B h3: %.4f", m_a["proporcao_positiva"], m_b1["proporcao_positiva"], m_b3["proporcao_positiva"])

    # ==================================================================
    # FASE 2 — WALK-FORWARD (prevalência, PR-AUC, P/R/F1, eventos, lead time)
    # ==================================================================
    logger.info("FASE 2: walk-forward por ano (Formulação B, h1 e h3)")

    def _walk_forward_onset(ctx, X, y, horizonte):
        linhas = []
        for ano_teste, idx_tr, idx_te in split_mod.walk_forward_splits(ctx):
            _, proba = _treinar_e_prever(ctx, X, y, idx_tr, idx_te)
            met = evaluation.metricas_classificacao(y.loc[idx_te], proba, threshold=0.5)

            ctx_te = ctx.loc[idx_te]
            df_rank_fold = _construir_df_ranking(ctx_te, proba, y.loc[idx_te])
            episodios_ano = df_episodios_todos[df_episodios_todos["inicio_ano"] == ano_teste]
            posicoes_fold = ranking.posicao_antes_de_episodios(df_rank_fold, episodios_ano, janela=JANELA_LEAD_TIME)
            detectados_top10 = posicoes_fold["melhor_posicao_antes_do_inicio"].le(10).sum()
            leads = posicoes_fold.loc[posicoes_fold["melhor_posicao_antes_do_inicio"] <= 10, "semanas_antecedencia_melhor_posicao"]

            linhas.append(
                {
                    "ano_teste": ano_teste,
                    "horizonte": horizonte,
                    "n_teste": len(idx_te),
                    "prevalencia": met["proporcao_positiva"],
                    "pr_auc": met["pr_auc"],
                    "precision": met["precision"],
                    "recall": met["recall"],
                    "f1": met["f1"],
                    "eventos_reais": len(episodios_ano),
                    "eventos_top10_antes": int(detectados_top10),
                    "taxa_top10_antes": float(detectados_top10 / len(episodios_ano)) if len(episodios_ano) else None,
                    "lead_time_mediano_top10": float(leads.median()) if len(leads) else None,
                }
            )
        return pd.DataFrame(linhas)

    tabela_wf_b3 = _walk_forward_onset(ctx_b3, X_b3, y_b3, HORIZONTE_ONSET_PRINCIPAL)
    tabela_wf_b1 = _walk_forward_onset(ctx_b1, X_b1, y_b1, HORIZONTE_ONSET_COMPARACAO)
    tabela_wf_b3.to_csv(PASTA_RELATORIO / "onset_walk_forward_h3.csv", index=False)
    tabela_wf_b1.to_csv(PASTA_RELATORIO / "onset_walk_forward_h1.csv", index=False)
    resultado["walk_forward_onset_h3"] = tabela_wf_b3.to_dict("records")
    resultado["walk_forward_onset_h1"] = tabela_wf_b1.to_dict("records")
    resultado["walk_forward_onset_h3_resumo"] = {
        "pr_auc_media": float(tabela_wf_b3["pr_auc"].mean()),
        "pr_auc_mediana": float(tabela_wf_b3["pr_auc"].median()),
        "pr_auc_min": float(tabela_wf_b3["pr_auc"].min()),
        "pr_auc_max": float(tabela_wf_b3["pr_auc"].max()),
        "pr_auc_desvio": float(tabela_wf_b3["pr_auc"].std()),
    }

    # ==================================================================
    # FASE 3 — RANKING NO TESTE (2023-2025), FORMULAÇÃO B h3 (PRINCIPAL)
    # ==================================================================
    logger.info("FASE 3: ranking territorial no teste (Formulação B, h=%d)", HORIZONTE_ONSET_PRINCIPAL)

    idx_tr_b3, idx_val_b3, idx_te_b3 = split_mod.split_temporal(ctx_b3)
    _, proba_b3_teste = _treinar_e_prever(ctx_b3, X_b3, y_b3, idx_tr_b3, idx_te_b3)
    ctx_te_b3 = ctx_b3.loc[idx_te_b3]
    df_rank_b3 = _construir_df_ranking(ctx_te_b3, proba_b3_teste, y_b3.loc[idx_te_b3])

    resultado_b3, posicoes_b3 = _avaliar_ranking_completo(df_rank_b3, df_episodios_teste, "modelo_onset_h3")
    posicoes_b3.to_csv(PASTA_RELATORIO / "onset_posicao_antes_episodios_h3.csv", index=False)
    resultado["ranking_modelo_onset_h3"] = resultado_b3

    persistencia_b3 = ranking.persistencia_consecutiva_antes_de_onset(df_rank_b3, df_episodios_teste, k=10, janela=JANELA_LEAD_TIME)
    persistencia_b3.to_csv(PASTA_RELATORIO / "onset_persistencia_topk_h3.csv", index=False)
    resultado["persistencia_topk_10_resumo"] = {
        "media_semanas": float(persistencia_b3["semanas_consecutivas_topk_antes"].mean()),
        "pct_pelo_menos_2_semanas": float((persistencia_b3["semanas_consecutivas_topk_antes"] >= 2).mean() * 100),
    }

    # Lead time minimo (secao 27): % episodios com >=1,>=2,>=3 semanas de antecedencia
    leads_validos = posicoes_b3["semanas_antecedencia_melhor_posicao"].dropna()
    resultado["lead_time_minimo_pct"] = {
        f">={n}_semana(s)": float((leads_validos >= n).mean() * 100) if len(leads_validos) else None for n in (1, 2, 3)
    }

    # ==================================================================
    # FASE 4 — FORMULAÇÃO A: MESMO RANKING, PARA COMPARAÇÃO DIRETA
    # ==================================================================
    logger.info("FASE 4: ranking territorial no teste (Formulação A, estado t+1)")

    idx_tr_a, idx_val_a, idx_te_a = split_mod.split_temporal(ctx_a)
    _, proba_a_teste = _treinar_e_prever(ctx_a, X_a, y_a, idx_tr_a, idx_te_a)
    ctx_te_a = ctx_a.loc[idx_te_a]
    df_rank_a = _construir_df_ranking(ctx_te_a, proba_a_teste, y_a.loc[idx_te_a])

    resultado_a, posicoes_a = _avaliar_ranking_completo(df_rank_a, df_episodios_teste, "modelo_estado_t1")
    resultado["ranking_modelo_formulacao_a"] = resultado_a

    # ==================================================================
    # FASE 5 — BASELINES DE RANKING (sem modelo)
    # ==================================================================
    logger.info("FASE 5: baselines de ranking (casos atuais, crescimento, histórico local)")

    baselines_ranking = {
        "casos_atuais": ctx_te_b3["casos_t"],
        "crescimento_recente": ctx_te_b3["taxa_crescimento_suavizada"],
        "razao_historica_local": ctx_te_b3["razao_limiar_historico"],
    }
    resultado_baselines = {}
    for nome, coluna_score in baselines_ranking.items():
        df_rank_base = _construir_df_ranking(ctx_te_b3, coluna_score, y_b3.loc[idx_te_b3])
        recall_k_semanal = ranking.recall_em_k(df_rank_base, k_valores=K_VALORES)
        posicoes_base = ranking.posicao_antes_de_episodios(df_rank_base, df_episodios_teste, janela=JANELA_LEAD_TIME)
        resumo_base = ranking.resumo_posicao_antes_de_episodios(posicoes_base, k_valores=K_VALORES)
        resultado_baselines[nome] = {
            "recall_em_k_semanal": recall_k_semanal.to_dict("records"),
            "recall_em_k_por_episodio": resumo_base,
            "lead_time_mediano": resumo_base["antecedencia_media_semanas"],
        }
    resultado["baselines_ranking"] = resultado_baselines

    # Tabela comparativa final (seção 25) -- "Recall@K" aqui é a definição
    # pedida na seção 12: % de episódios cujo bairro apareceu no Top-K
    # ANTES do início (não o recall semanal per-linha, que é uma lente
    # complementar mais estrita — ver seção "Recall@K" do relatório).
    linhas_comparacao = []
    for nome, r in resultado_baselines.items():
        resumo = r["recall_em_k_por_episodio"]
        linhas_comparacao.append(
            {
                "metodo": nome,
                "recall_5_pct": resumo["pct_top_5_antes"],
                "recall_10_pct": resumo["pct_top_10_antes"],
                "recall_15_pct": resumo["pct_top_15_antes"],
                "recall_20_pct": resumo["pct_top_20_antes"],
                "lead_time_mediano": resumo["antecedencia_media_semanas"],
            }
        )
    resumo_modelo = resultado_b3["resumo_posicao_antes_episodios"]
    linhas_comparacao.append(
        {
            "metodo": "modelo_onset_h3",
            "recall_5_pct": resumo_modelo["pct_top_5_antes"],
            "recall_10_pct": resumo_modelo["pct_top_10_antes"],
            "recall_15_pct": resumo_modelo["pct_top_15_antes"],
            "recall_20_pct": resumo_modelo["pct_top_20_antes"],
            "lead_time_mediano": resumo_modelo["antecedencia_media_semanas"],
        }
    )
    tabela_comparacao_baseline = pd.DataFrame(linhas_comparacao)
    tabela_comparacao_baseline.to_csv(PASTA_RELATORIO / "onset_comparacao_baselines_ranking.csv", index=False)
    resultado["tabela_comparacao_baselines"] = tabela_comparacao_baseline.to_dict("records")

    # ==================================================================
    # FASE 6 — GRANDES EPISÓDIOS
    # ==================================================================
    logger.info("FASE 6: desempenho em grandes episódios")

    n_top = max(1, int(np.ceil(len(df_episodios_teste) * 0.10)))
    episodios_grandes = df_episodios_teste.sort_values("casos_totais_episodio", ascending=False).head(n_top)
    posicoes_grandes = ranking.posicao_antes_de_episodios(df_rank_b3, episodios_grandes, janela=JANELA_LEAD_TIME)
    resumo_grandes = ranking.resumo_posicao_antes_de_episodios(posicoes_grandes, k_valores=K_VALORES)
    resultado["grandes_episodios"] = {"n": len(episodios_grandes), **resumo_grandes}

    # ==================================================================
    # FASE 7 — POR ANO / POR BAIRRO / POR RPA
    # ==================================================================
    logger.info("FASE 7: desempenho por ano, bairro e RPA")

    posicoes_b3_com_ano = posicoes_b3.copy()
    linhas_ano = []
    for ano, sub in posicoes_b3_com_ano.groupby("inicio_ano"):
        disponivel = sub.dropna(subset=["melhor_posicao_antes_do_inicio"])
        linhas_ano.append(
            {
                "ano": int(ano),
                "n_episodios": len(sub),
                "recall_top10_pct": float((disponivel["melhor_posicao_antes_do_inicio"] <= 10).mean() * 100) if len(disponivel) else None,
                "recall_top20_pct": float((disponivel["melhor_posicao_antes_do_inicio"] <= 20).mean() * 100) if len(disponivel) else None,
                "lead_time_mediano": float(disponivel["semanas_antecedencia_melhor_posicao"].median()) if len(disponivel) else None,
            }
        )
    tabela_por_ano = pd.DataFrame(linhas_ano)
    tabela_por_ano.to_csv(PASTA_RELATORIO / "onset_desempenho_por_ano.csv", index=False)
    resultado["desempenho_por_ano"] = tabela_por_ano.to_dict("records")

    codigo_bairro_para_rpa = df_gold[["codigo_bairro", "codigo_rpa", "nome_bairro"]].drop_duplicates("codigo_bairro").set_index("codigo_bairro")
    posicoes_b3_com_bairro = posicoes_b3.merge(codigo_bairro_para_rpa, on="codigo_bairro", how="left")

    linhas_bairro = []
    for bairro, sub in posicoes_b3_com_bairro.groupby("codigo_bairro"):
        disponivel = sub.dropna(subset=["melhor_posicao_antes_do_inicio"])
        linhas_bairro.append(
            {
                "codigo_bairro": bairro,
                "nome_bairro": sub["nome_bairro"].iloc[0],
                "codigo_rpa": sub["codigo_rpa"].iloc[0],
                "n_episodios": len(sub),
                "n_detectados_top20": int((disponivel["melhor_posicao_antes_do_inicio"] <= 20).sum()),
                "posicao_mediana_antes": float(disponivel["melhor_posicao_antes_do_inicio"].median()) if len(disponivel) else None,
                "lead_time_mediano": float(disponivel["semanas_antecedencia_melhor_posicao"].median()) if len(disponivel) else None,
            }
        )
    tabela_por_bairro = pd.DataFrame(linhas_bairro)
    tabela_por_bairro["taxa_top20"] = tabela_por_bairro["n_detectados_top20"] / tabela_por_bairro["n_episodios"]
    tabela_por_bairro.to_csv(PASTA_RELATORIO / "onset_desempenho_por_bairro.csv", index=False)

    linhas_rpa = []
    for rpa, sub in posicoes_b3_com_bairro.groupby("codigo_rpa"):
        disponivel = sub.dropna(subset=["melhor_posicao_antes_do_inicio"])
        linhas_rpa.append(
            {
                "codigo_rpa": rpa,
                "n_episodios": len(sub),
                "recall_top10_pct": float((disponivel["melhor_posicao_antes_do_inicio"] <= 10).mean() * 100) if len(disponivel) else None,
                "recall_top20_pct": float((disponivel["melhor_posicao_antes_do_inicio"] <= 20).mean() * 100) if len(disponivel) else None,
            }
        )
    tabela_por_rpa = pd.DataFrame(linhas_rpa)
    tabela_por_rpa.to_csv(PASTA_RELATORIO / "onset_desempenho_por_rpa.csv", index=False)
    resultado["desempenho_por_rpa"] = tabela_por_rpa.to_dict("records")

    # IPSEP especificamente (codigo_bairro="213", ver etapas anteriores)
    linha_ipsep = tabela_por_bairro[tabela_por_bairro["codigo_bairro"] == "213"]
    resultado["ipsep_onset_ranking"] = linha_ipsep.to_dict("records")

    zero_deteccao = tabela_por_bairro[(tabela_por_bairro["taxa_top20"] == 0) & (tabela_por_bairro["n_episodios"] >= 1)]
    resultado["bairros_zero_deteccao_top20"] = {
        "n": len(zero_deteccao),
        "codigos": zero_deteccao["codigo_bairro"].tolist(),
    }

    # ==================================================================
    # FASE 8 — CENÁRIO DE ANTECIPAÇÃO GENUÍNA (bairro não ativo em t)
    # ==================================================================
    logger.info("FASE 8: cenário de antecipação genuína (bairro não ativo no início da janela)")

    estado_indexado = df_estado_idx.set_index(["codigo_bairro", "indice_semana_global"])["estado_alto_risco"]

    def _estava_ativo_no_inicio_da_janela(row) -> bool:
        semana_ref = row["inicio_indice"] - JANELA_LEAD_TIME
        v = estado_indexado.get((row["codigo_bairro"], semana_ref))
        return bool(v == 1) if v is not None else False

    df_episodios_teste_com_flag = df_episodios_teste.copy()
    df_episodios_teste_com_flag["ja_ativo_no_inicio_da_janela"] = df_episodios_teste_com_flag.apply(_estava_ativo_no_inicio_da_janela, axis=1)

    episodios_genuinos = df_episodios_teste_com_flag[~df_episodios_teste_com_flag["ja_ativo_no_inicio_da_janela"]]
    episodios_pos_episodio_recente = df_episodios_teste_com_flag[df_episodios_teste_com_flag["ja_ativo_no_inicio_da_janela"]]

    posicoes_genuinos = ranking.posicao_antes_de_episodios(df_rank_b3, episodios_genuinos, janela=JANELA_LEAD_TIME)
    posicoes_pos_recente = ranking.posicao_antes_de_episodios(df_rank_b3, episodios_pos_episodio_recente, janela=JANELA_LEAD_TIME)

    resultado["cenario_antecipacao_genuina"] = {
        "n_episodios_genuinos": len(episodios_genuinos),
        "n_episodios_pos_episodio_recente": len(episodios_pos_episodio_recente),
        "resumo_genuinos": ranking.resumo_posicao_antes_de_episodios(posicoes_genuinos, k_valores=K_VALORES),
        "resumo_pos_episodio_recente": ranking.resumo_posicao_antes_de_episodios(posicoes_pos_recente, k_valores=K_VALORES) if len(episodios_pos_episodio_recente) else None,
    }

    # ==================================================================
    # SALVAR RESULTADO COMPLETO
    # ==================================================================
    with open(PASTA_RELATORIO / "resultado_onset_ranking_completo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Resultado completo salvo em %s", PASTA_RELATORIO / "resultado_onset_ranking_completo.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
