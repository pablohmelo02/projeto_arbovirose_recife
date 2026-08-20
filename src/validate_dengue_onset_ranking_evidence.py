"""Entry point da validação estatística da evidência — última etapa antes
de decidir se o ranking territorial pode ser apresentado como prova de
conceito experimental. NENHUM retrain, NENHUMA feature nova, NENHUM
tuning: esta etapa só reamostra (bootstrap) os resultados já obtidos por
`src/evaluate_dengue_onset_ranking.py`.

Uso:
    python -m src.validate_dengue_onset_ranking_evidence

## Candidato congelado avaliado: `dengue_onset_ranking_candidate_v1`

- Agravo: DENGUE. Unidade: bairro x semana epidemiológica (94 bairros).
- Target: onset (início de novo episódio) em `t+1..t+3`
  (`src/ml/onset.py::construir_target_onset`, `horizonte=3`).
- Features: epidemiológica básica + sazonal + território + histórico
  local + momentum (sem clima) — `src/ml/features.py`, sem alteração.
- Modelo: `HistGradientBoostingClassifier`, `max_depth=4,
  learning_rate=0.1, max_iter=150` (escolhidos na etapa de otimização,
  reaproveitados sem nova busca), `random_state=42`.
- Split: treino 2013-2019, validação 2020-2022 (não usada nesta etapa,
  ranking não precisa de threshold), teste 2023-2025 (14.476 linhas no
  dataset supervisionado de onset).
- Episódios: `alert_metrics.construir_episodios` (semanas consecutivas em
  `estado_alto_risco=1`, mesmo bairro). Janela de lead time: 4 semanas.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.ml import alert_metrics, evidence_validation, models, ranking
from src.ml import split as split_mod
from src.ml.dataset import montar_dataset_onset
from src.ml.features import construir_indice_semana_global
from src.ml.target import agregar_semanal_agravo, calcular_estado_alto_risco

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "ml"

ID_CANDIDATO = "dengue_onset_ranking_candidate_v1"
HORIZONTE_ONSET = 3
JANELA_LEAD_TIME = 4
K_VALORES = (5, 10, 15, 20)
HIPERPARAMETROS_ARVORE = {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150}
SEED = 42
N_REAMOSTRAGENS = 2000


def _construir_df_ranking(ctx: pd.DataFrame, score: pd.Series) -> pd.DataFrame:
    df_alertas = ctx[["codigo_bairro", "indice_semana_alvo"]].copy()
    df_alertas["probabilidade"] = score.to_numpy() if hasattr(score, "to_numpy") else np.asarray(score)
    return ranking.construir_ranking_semanal(df_alertas)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrado. Rode 'python -m src.export_dashboard_dataset' primeiro.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    logger.info("Gold carregada: %d linhas", len(df_gold))
    resultado: dict = {"id_candidato": ID_CANDIDATO, "seed": SEED, "n_reamostragens": N_REAMOSTRAGENS}

    # ------------------------------------------------------------------
    # Reconstrução determinística do candidato congelado (sem tuning)
    # ------------------------------------------------------------------
    df_sem = agregar_semanal_agravo(df_gold, "DENGUE")
    df_estado = calcular_estado_alto_risco(df_sem)
    df_estado_idx = construir_indice_semana_global(df_estado)
    df_episodios_todos = alert_metrics.construir_episodios(df_estado_idx)
    df_episodios_teste = df_episodios_todos[df_episodios_todos["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM].reset_index(drop=True)

    ctx, X, y, m = montar_dataset_onset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET)
    idx_tr, idx_val, idx_te = split_mod.split_temporal(ctx)
    modelo = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr], **HIPERPARAMETROS_ARVORE)
    proba_teste = models.prever_probabilidade(modelo, X.loc[idx_te])
    ctx_teste = ctx.loc[idx_te]

    resultado["configuracao"] = {
        "target": "onset (inicio de novo episodio)",
        "horizonte_semanas": HORIZONTE_ONSET,
        "n_features": m["n_features"],
        "hiperparametros_arvore": HIPERPARAMETROS_ARVORE,
        "split_treino_ate": split_mod.ANO_TREINO_FIM,
        "split_validacao_ate": split_mod.ANO_VALIDACAO_FIM,
        "n_treino": len(idx_tr),
        "n_teste": len(idx_te),
        "n_episodios_teste": len(df_episodios_teste),
        "janela_lead_time_semanas": JANELA_LEAD_TIME,
    }
    logger.info("Candidato reconstruído: %d episódios reais no teste (2023-2025)", len(df_episodios_teste))

    df_rank_modelo = _construir_df_ranking(ctx_teste, proba_teste)
    df_rank_baselines = {
        "casos_atuais": _construir_df_ranking(ctx_teste, ctx_teste["casos_t"]),
        "crescimento_recente": _construir_df_ranking(ctx_teste, ctx_teste["taxa_crescimento_suavizada"]),
        "razao_historica_local": _construir_df_ranking(ctx_teste, ctx_teste["razao_limiar_historico"]),
    }
    todos_os_rankings = {"modelo": df_rank_modelo, **df_rank_baselines}

    # ------------------------------------------------------------------
    # Master: 1 linha por episódio real x 1 conjunto de colunas por método
    # ------------------------------------------------------------------
    codigo_bairro_para_rpa = df_gold[["codigo_bairro", "codigo_rpa", "nome_bairro"]].drop_duplicates("codigo_bairro")

    estado_indexado = df_estado_idx.set_index(["codigo_bairro", "indice_semana_global"])["estado_alto_risco"]

    def _ja_ativo(row) -> bool:
        v = estado_indexado.get((row["codigo_bairro"], row["inicio_indice"] - JANELA_LEAD_TIME))
        return bool(v == 1) if v is not None else False

    master = df_episodios_teste.copy()
    master["ja_ativo_no_inicio_da_janela"] = master.apply(_ja_ativo, axis=1)
    master = master.merge(codigo_bairro_para_rpa, on="codigo_bairro", how="left")

    for nome_metodo, df_rank in todos_os_rankings.items():
        posicoes = ranking.posicao_antes_de_episodios(df_rank, df_episodios_teste, janela=JANELA_LEAD_TIME)
        posicoes = posicoes.rename(
            columns={
                "melhor_posicao_antes_do_inicio": f"posicao_{nome_metodo}",
                "semanas_antecedencia_melhor_posicao": f"lead_{nome_metodo}",
            }
        )[["codigo_bairro", "inicio_indice", f"posicao_{nome_metodo}", f"lead_{nome_metodo}"]]
        master = master.merge(posicoes, on=["codigo_bairro", "inicio_indice"], how="left")
        for k in K_VALORES:
            master[f"detectado_{nome_metodo}_k{k}"] = (master[f"posicao_{nome_metodo}"] <= k).astype(int)

    master.to_csv(PASTA_RELATORIO / "evidence_master_episodios.csv", index=False)
    logger.info("Master de episódios salvo (%d episódios, %d colunas)", len(master), master.shape[1])

    # ------------------------------------------------------------------
    # Recall@K por método + IC bootstrap (episódio) + delta vs melhor baseline
    # ------------------------------------------------------------------
    metodos = ["modelo", "casos_atuais", "crescimento_recente", "razao_historica_local"]
    linhas_recall = []
    for k in K_VALORES:
        for metodo in metodos:
            arr = master[f"detectado_{metodo}_k{k}"].to_numpy(dtype=float)
            ic = evidence_validation.bootstrap_recall(arr, n_reamostragens=N_REAMOSTRAGENS, seed=SEED)
            linhas_recall.append({"k": k, "metodo": metodo, **ic})
    tabela_recall_ic = pd.DataFrame(linhas_recall)
    tabela_recall_ic.to_csv(PASTA_RELATORIO / "evidence_recall_ic.csv", index=False)

    linhas_delta = []
    melhor_baseline_por_k = {}
    for k in K_VALORES:
        obs_baselines = {
            b: master[f"detectado_{b}_k{k}"].mean() for b in ("casos_atuais", "crescimento_recente", "razao_historica_local")
        }
        melhor_baseline = max(obs_baselines, key=obs_baselines.get)
        melhor_baseline_por_k[k] = melhor_baseline
        arr_modelo = master[f"detectado_modelo_k{k}"].to_numpy(dtype=float)
        arr_baseline = master[f"detectado_{melhor_baseline}_k{k}"].to_numpy(dtype=float)
        delta = evidence_validation.bootstrap_delta(arr_modelo, arr_baseline, n_reamostragens=N_REAMOSTRAGENS, seed=SEED)
        linhas_delta.append({"k": k, "melhor_baseline": melhor_baseline, **delta})

        # sensibilidade: bootstrap por cluster (bairro e bairro x ano)
        for sufixo, cluster_ids in (
            ("cluster_bairro", master["codigo_bairro"].to_numpy()),
            (
                "cluster_bairro_ano",
                (master["codigo_bairro"].astype(str) + "_" + master["inicio_ano"].astype(str)).to_numpy(),
            ),
        ):
            delta_cluster = evidence_validation.bootstrap_delta(
                arr_modelo, arr_baseline, cluster_ids=cluster_ids, n_reamostragens=N_REAMOSTRAGENS, seed=SEED
            )
            linhas_delta[-1][f"ic_baixo_{sufixo}"] = delta_cluster["ic_baixo"]
            linhas_delta[-1][f"ic_alto_{sufixo}"] = delta_cluster["ic_alto"]

    tabela_delta = pd.DataFrame(linhas_delta)
    tabela_delta.to_csv(PASTA_RELATORIO / "evidence_delta_vs_baseline.csv", index=False)
    resultado["recall_ic"] = tabela_recall_ic.to_dict("records")
    resultado["delta_vs_melhor_baseline"] = tabela_delta.to_dict("records")

    # ------------------------------------------------------------------
    # Análise por ano (não esconder em média global) + leave-one-year-out
    # ------------------------------------------------------------------
    colunas_k5_k10 = ["detectado_modelo_k5", "detectado_modelo_k10"] + [
        f"detectado_{melhor_baseline_por_k[k]}_k{k}" for k in (5, 10)
    ]
    tabela_por_ano = evidence_validation.agregar_recall_por_grupo(master, "inicio_ano", colunas_k5_k10)
    tabela_por_ano = tabela_por_ano.rename(
        columns={
            "detectado_modelo_k5": "recall5_modelo",
            "detectado_modelo_k10": "recall10_modelo",
            f"detectado_{melhor_baseline_por_k[5]}_k5": "recall5_melhor_baseline",
            f"detectado_{melhor_baseline_por_k[10]}_k10": "recall10_melhor_baseline",
        }
    )
    tabela_por_ano["delta5"] = tabela_por_ano["recall5_modelo"] - tabela_por_ano["recall5_melhor_baseline"]
    tabela_por_ano["delta10"] = tabela_por_ano["recall10_modelo"] - tabela_por_ano["recall10_melhor_baseline"]
    tabela_por_ano["lead_time_mediano"] = [
        float(master.loc[master["inicio_ano"] == ano, "lead_modelo"].dropna().median())
        if len(master.loc[master["inicio_ano"] == ano, "lead_modelo"].dropna())
        else None
        for ano in tabela_por_ano["inicio_ano"]
    ]
    tabela_por_ano.to_csv(PASTA_RELATORIO / "evidence_por_ano.csv", index=False)
    resultado["por_ano"] = tabela_por_ano.to_dict("records")

    # leave-one-year-out: recall@5/10 do MODELO excluindo cada ano
    loyo_k5 = evidence_validation.leave_one_group_out(
        master, "inicio_ano", "detectado_modelo_k5", f"detectado_{melhor_baseline_por_k[5]}_k5"
    ).rename(columns={"recall_modelo": "recall5_modelo", "recall_melhor_baseline": "recall5_melhor_baseline"})
    loyo_k10 = evidence_validation.leave_one_group_out(
        master, "inicio_ano", "detectado_modelo_k10", f"detectado_{melhor_baseline_por_k[10]}_k10"
    ).rename(columns={"recall_modelo": "recall10_modelo", "recall_melhor_baseline": "recall10_melhor_baseline"})
    tabela_loyo = loyo_k5.merge(loyo_k10[["inicio_ano_excluido", "recall10_modelo", "recall10_melhor_baseline"]], on="inicio_ano_excluido")
    tabela_loyo = tabela_loyo.rename(columns={"inicio_ano_excluido": "ano_excluido"})
    tabela_loyo.to_csv(PASTA_RELATORIO / "evidence_leave_one_year_out.csv", index=False)
    resultado["leave_one_year_out"] = tabela_loyo.to_dict("records")

    # ------------------------------------------------------------------
    # Territorial: RPA + bairros críticos
    # ------------------------------------------------------------------
    colunas_rpa = ["detectado_modelo_k5", "detectado_modelo_k10", "detectado_modelo_k20"]
    tabela_rpa = evidence_validation.agregar_recall_por_grupo(master, "codigo_rpa", colunas_rpa)
    tabela_rpa = tabela_rpa.rename(
        columns={"detectado_modelo_k5": "recall5_modelo", "detectado_modelo_k10": "recall10_modelo", "detectado_modelo_k20": "recall20_modelo"}
    )
    tabela_rpa.to_csv(PASTA_RELATORIO / "evidence_por_rpa.csv", index=False)
    resultado["por_rpa"] = tabela_rpa.to_dict("records")

    linhas_bairro = []
    for (bairro, nome), sub in master.groupby(["codigo_bairro", "nome_bairro"]):
        linha = {"codigo_bairro": bairro, "nome_bairro": nome, "n_episodios": len(sub)}
        for k in (10, 20):
            linha[f"recall{k}_modelo"] = float(sub[f"detectado_modelo_k{k}"].mean())
        linhas_bairro.append(linha)
    tabela_bairro = pd.DataFrame(linhas_bairro).sort_values("n_episodios", ascending=False)
    tabela_bairro.to_csv(PASTA_RELATORIO / "evidence_por_bairro.csv", index=False)

    ipsep = tabela_bairro[tabela_bairro["codigo_bairro"] == "213"]
    resultado["ipsep"] = ipsep.to_dict("records")
    baixa_amostra_extrema = tabela_bairro[(tabela_bairro["n_episodios"] <= 2) & (tabela_bairro["recall20_modelo"].isin([0.0, 1.0]))]
    muitos_episodios_baixa_deteccao = tabela_bairro[(tabela_bairro["n_episodios"] >= 5) & (tabela_bairro["recall20_modelo"] < 0.3)]
    resultado["bairros_criticos"] = {
        "muitos_episodios_baixa_deteccao": muitos_episodios_baixa_deteccao.to_dict("records"),
        "poucos_episodios_percentual_extremo": baixa_amostra_extrema.to_dict("records"),
    }

    # ------------------------------------------------------------------
    # Grandes episódios vs todos
    # ------------------------------------------------------------------
    n_top = max(1, int(np.ceil(len(master) * 0.10)))
    grandes = master.sort_values("casos_totais_episodio", ascending=False).head(n_top)
    linhas_grandes = {"n": len(grandes)}
    for k in (5, 10):
        arr_grandes = grandes[f"detectado_modelo_k{k}"].to_numpy(dtype=float)
        arr_todos = master[f"detectado_modelo_k{k}"].to_numpy(dtype=float)
        linhas_grandes[f"recall{k}_grandes"] = evidence_validation.bootstrap_recall(arr_grandes, n_reamostragens=N_REAMOSTRAGENS, seed=SEED)
        linhas_grandes[f"recall{k}_todos"] = evidence_validation.bootstrap_recall(arr_todos, n_reamostragens=N_REAMOSTRAGENS, seed=SEED)
    leads_grandes = grandes["lead_modelo"].dropna()
    linhas_grandes["lead_time_mediano"] = float(leads_grandes.median()) if len(leads_grandes) else None
    resultado["grandes_episodios"] = linhas_grandes

    # ------------------------------------------------------------------
    # Antecipação genuína x recaída
    # ------------------------------------------------------------------
    genuinos = master[~master["ja_ativo_no_inicio_da_janela"]]
    recaidas = master[master["ja_ativo_no_inicio_da_janela"]]
    linhas_genuino = {"n_genuinos": len(genuinos), "n_recaidas": len(recaidas)}
    for k in (5, 10, 20):
        linhas_genuino[f"recall{k}_genuino"] = evidence_validation.bootstrap_recall(
            genuinos[f"detectado_modelo_k{k}"].to_numpy(dtype=float), n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        )
        linhas_genuino[f"recall{k}_recaida"] = evidence_validation.bootstrap_recall(
            recaidas[f"detectado_modelo_k{k}"].to_numpy(dtype=float), n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        )
    resultado["genuino_vs_recaida"] = linhas_genuino

    # ------------------------------------------------------------------
    # Lead time (K=10 como referência) + IC bootstrap da mediana
    # ------------------------------------------------------------------
    leads_k10 = master.loc[master["detectado_modelo_k10"] == 1, "lead_modelo"].dropna().to_numpy(dtype=float)
    resultado["lead_time_k10"] = {
        "n": len(leads_k10),
        "media": float(np.mean(leads_k10)) if len(leads_k10) else None,
        "p25": float(np.percentile(leads_k10, 25)) if len(leads_k10) else None,
        "mediana_ic": evidence_validation.bootstrap_mediana(leads_k10, n_reamostragens=N_REAMOSTRAGENS, seed=SEED),
        "p75": float(np.percentile(leads_k10, 75)) if len(leads_k10) else None,
        "minimo": float(np.min(leads_k10)) if len(leads_k10) else None,
        "maximo": float(np.max(leads_k10)) if len(leads_k10) else None,
        "pct_>=1_semana": float((leads_k10 >= 1).mean() * 100) if len(leads_k10) else None,
        "pct_>=2_semanas": float((leads_k10 >= 2).mean() * 100) if len(leads_k10) else None,
        "pct_>=3_semanas": float((leads_k10 >= 3).mean() * 100) if len(leads_k10) else None,
    }

    # ------------------------------------------------------------------
    # Estabilidade Top-10 (reaproveita o ranking já calculado do modelo)
    # ------------------------------------------------------------------
    resultado["estabilidade_top10"] = ranking.estabilidade_ranking(df_rank_modelo, k=10)
    serie_jaccard = evidence_validation.serie_jaccard_consecutivo(df_rank_modelo, k=10)
    serie_jaccard.to_csv(PASTA_RELATORIO / "evidence_estabilidade_top10_semanal.csv", index=False)

    # ------------------------------------------------------------------
    # Carga operacional
    # ------------------------------------------------------------------
    linhas_carga = []
    for k in K_VALORES:
        detectados = int(master[f"detectado_modelo_k{k}"].sum())
        linhas_carga.append(
            {
                "k": k,
                "bairros_priorizados_por_semana": k,
                "episodios_antecipados": detectados,
                "episodios_perdidos": len(master) - detectados,
                "taxa_antecipacao": detectados / len(master),
            }
        )
    tabela_carga = pd.DataFrame(linhas_carga)

    # priorizações (bairro x semana) que NÃO precederam nenhum episódio novo:
    # usa o target real de onset da própria linha, nunca a previsão.
    df_rank_com_onset = df_rank_modelo.copy()
    df_rank_com_onset["onset_futuro"] = y.loc[idx_te].to_numpy()
    tabela_priorizacao = evidence_validation.calcular_carga_priorizacao(df_rank_com_onset, k_valores=K_VALORES)
    tabela_carga = tabela_carga.merge(tabela_priorizacao, on="k", how="left")
    tabela_carga.to_csv(PASTA_RELATORIO / "evidence_carga_operacional.csv", index=False)
    resultado["carga_operacional"] = tabela_carga.to_dict("records")

    # ------------------------------------------------------------------
    # Salvar resultado completo
    # ------------------------------------------------------------------
    with open(PASTA_RELATORIO / "resultado_evidence_validation_completo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Resultado completo salvo em %s", PASTA_RELATORIO / "resultado_evidence_validation_completo.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
