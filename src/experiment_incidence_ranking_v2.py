"""Experimento V2: onset/ranking territorial baseado em incidência —
comparado honestamente contra o candidato congelado
`dengue_onset_ranking_candidate_v1`, com o mesmo rigor estatístico da
validação de evidência (bootstrap por episódio/cluster).

Uso:
    python -m src.experiment_incidence_ranking_v2

## O que NÃO faz (regra de parada desta etapa)

Não retreina nem altera `dengue_onset_ranking_candidate_v1` — os números
de V1 usados aqui são lidos de `reports/ml/resultado_evidence_validation_completo.json`
(já publicado, gerado por `src/validate_dengue_onset_ranking_evidence.py`),
exceto os episódios de teste baseados em casos (reconstruídos aqui, sem
treinar nenhum modelo, só para a comparação de sobreposição de episódios
com V2, seção 11). Não faz tuning de hiperparâmetro (mesmo
`HIPERPARAMETROS_ARVORE` de V1, mesma seed). Não usa clima. Não altera o
dashboard.

## As 5 variantes de features treinadas (mesmo target de incidência em todas)

`v1_features` (ablation A) · `v1_mais_populacao` (ablation B) ·
`v2_incidencia` (linha principal — só incidência, sem casos absolutos) ·
`v2_casos_incidencia` (linha principal — V1 + incidência = ablation C,
candidato principal desta etapa) · `v2_casos_incidencia_populacao`
(ablation D).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.ml import alert_metrics, evidence_validation, models, ranking
from src.ml import split as split_mod
from src.ml.baselines_incidencia import (
    baseline_crescimento_incidencia,
    baseline_incidencia_atual,
    baseline_razao_historica_incidencia,
)
from src.ml.dataset_incidencia import VARIANTES_FEATURES, montar_dataset_onset_incidencia
from src.ml.features import construir_indice_semana_global
from src.ml.onset_incidencia import construir_episodios_incidencia, construir_target_onset_incidencia
from src.ml.target import agregar_semanal_agravo, calcular_estado_alto_risco
from src.ml.target_incidencia import (
    agregar_semanal_agravo_com_populacao,
    calcular_estado_alto_risco_incidencia,
)
from src.population.population_sensitivity import (
    executar_analise_sensibilidade_b,
    obter_distribuicao_erro_percentual_real,
    perturbar_populacao,
)
from src.silver.pipeline_population import (
    CAMINHO_BRONZE_CENSO2022,
    CAMINHO_BRONZE_CIEVS,
    CAMINHO_BRONZE_MUNICIPAL,
    carregar_silver_populacao_local,
)

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "ml"
CAMINHO_EVIDENCIA_V1 = PASTA_RELATORIO / "resultado_evidence_validation_completo.json"

HORIZONTE_ONSET = 3
JANELA_LEAD_TIME = 4
K_VALORES = (5, 10, 15, 20)
HIPERPARAMETROS_ARVORE = {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150}  # idêntico ao V1
SEED = 42
N_REAMOSTRAGENS = 2000
N_REPLICAS_SENSIBILIDADE_B = 20

NOME_V2_PRINCIPAL = "v2_casos_incidencia"
CODIGO_IPSEP = "213"


def _construir_df_ranking(ctx: pd.DataFrame, score) -> pd.DataFrame:
    df_alertas = ctx[["codigo_bairro", "indice_semana_alvo"]].copy()
    df_alertas["probabilidade"] = score.to_numpy() if hasattr(score, "to_numpy") else np.asarray(score)
    return ranking.construir_ranking_semanal(df_alertas)


def _treinar_variante(df_gold: pd.DataFrame, variante: str) -> dict[str, Any]:
    """Monta o dataset da variante, treina no mesmo split temporal de V1,
    devolve tudo que as fases seguintes precisam."""
    ctx, X, y, metricas = montar_dataset_onset_incidencia(
        df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET, variante=variante
    )
    idx_tr, idx_val, idx_te = split_mod.split_temporal(ctx)
    modelo = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr], **HIPERPARAMETROS_ARVORE)
    proba_teste = models.prever_probabilidade(modelo, X.loc[idx_te])
    ctx_teste = ctx.loc[idx_te]
    df_rank = _construir_df_ranking(ctx_teste, proba_teste)
    return {
        "variante": variante,
        "ctx": ctx,
        "X": X,
        "y": y,
        "idx_treino": idx_tr,
        "idx_teste": idx_te,
        "ctx_teste": ctx_teste,
        "df_rank": df_rank,
        "metricas_dataset": metricas,
        "n_treino": len(idx_tr),
        "n_teste": len(idx_te),
    }


def main() -> int:  # noqa: C901 - orquestração de experimento, deliberadamente sequencial e legível por fase
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrado.", CAMINHO_GOLD)
        return 1
    if not CAMINHO_EVIDENCIA_V1.exists():
        logger.error("'%s' não encontrado — rode 'python -m src.validate_dengue_onset_ranking_evidence' primeiro.", CAMINHO_EVIDENCIA_V1)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    logger.info("Gold carregada: %d linhas", len(df_gold))
    resultado: dict[str, Any] = {"seed": SEED, "n_reamostragens": N_REAMOSTRAGENS}

    # ==================================================================
    # FASE 1 — V1 preservado: lê os números já publicados, reconstrói só
    # os episódios de teste (casos) para a comparação de sobreposição.
    # ==================================================================
    logger.info("FASE 1: carregando evidência V1 já publicada (sem retreinar)")
    with open(CAMINHO_EVIDENCIA_V1, encoding="utf-8") as f:
        evidencia_v1 = json.load(f)

    df_sem_casos = agregar_semanal_agravo(df_gold, "DENGUE")
    df_estado_casos = calcular_estado_alto_risco(df_sem_casos)
    df_estado_casos_idx = construir_indice_semana_global(df_estado_casos)
    episodios_casos_todos = alert_metrics.construir_episodios(df_estado_casos_idx)
    episodios_casos_teste = episodios_casos_todos[
        episodios_casos_todos["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM
    ].reset_index(drop=True)
    resultado["v1_evidencia_publicada"] = evidencia_v1
    resultado["v1_n_episodios_teste"] = len(episodios_casos_teste)
    logger.info("V1 (preservado): %d episódios reais no teste (2023-2025)", len(episodios_casos_teste))

    # ==================================================================
    # FASE 2 — Treina as 5 variantes de V2 (mesmo target de incidência,
    # mesmo modelo/seed/split; só as features mudam).
    # ==================================================================
    logger.info("FASE 2: treinando as 5 variantes de features (target = onset por incidência)")
    treinos: dict[str, dict[str, Any]] = {}
    for variante in VARIANTES_FEATURES:
        logger.info("  treinando variante=%s", variante)
        treinos[variante] = _treinar_variante(df_gold, variante)

    principal = treinos[NOME_V2_PRINCIPAL]
    ctx_principal, ctx_teste_principal = principal["ctx"], principal["ctx_teste"]

    # Episódios de incidência (a partir do ctx da variante principal — o
    # target/estado de incidência é idêntico entre variantes).
    episodios_incidencia_todos = construir_episodios_incidencia(ctx_principal)
    episodios_incidencia_teste = episodios_incidencia_todos[
        episodios_incidencia_todos["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM
    ].reset_index(drop=True)
    resultado["v2_n_episodios_teste"] = len(episodios_incidencia_teste)
    logger.info("V2 (incidência): %d episódios reais no teste (2023-2025)", len(episodios_incidencia_teste))

    resultado["dataset_por_variante"] = {v: t["metricas_dataset"] for v, t in treinos.items()}

    # ==================================================================
    # FASE 3 — Sobreposição de episódios V1 (casos) x V2 (incidência),
    # seção 11 do pedido.
    # ==================================================================
    logger.info("FASE 3: sobreposição de episódios V1 x V2")

    def _chave_episodio(df_ep: pd.DataFrame) -> set[tuple[str, int]]:
        return set(zip(df_ep["codigo_bairro"], df_ep["inicio_indice"]))

    chaves_v1 = _chave_episodio(episodios_casos_teste)
    chaves_v2 = _chave_episodio(episodios_incidencia_teste)
    intersecao = chaves_v1 & chaves_v2
    uniao = chaves_v1 | chaves_v2
    resultado["sobreposicao_episodios"] = {
        "n_episodios_v1": len(chaves_v1),
        "n_episodios_v2": len(chaves_v2),
        "n_em_comum": len(intersecao),
        "n_somente_v1": len(chaves_v1 - chaves_v2),
        "n_somente_v2": len(chaves_v2 - chaves_v1),
        "jaccard": (len(intersecao) / len(uniao)) if uniao else None,
    }

    por_bairro_v1 = episodios_casos_teste.groupby("codigo_bairro").size().rename("n_episodios_v1")
    por_bairro_v2 = episodios_incidencia_teste.groupby("codigo_bairro").size().rename("n_episodios_v2")
    tabela_por_bairro_sobreposicao = pd.concat([por_bairro_v1, por_bairro_v2], axis=1).fillna(0).astype(int)
    tabela_por_bairro_sobreposicao.to_csv(PASTA_RELATORIO / "incidence_v2_episodios_por_bairro.csv")

    codigo_bairro_para_rpa = (
        df_gold[["codigo_bairro", "codigo_rpa", "nome_bairro"]].drop_duplicates("codigo_bairro").set_index("codigo_bairro")
    )
    tabela_por_rpa_sobreposicao = tabela_por_bairro_sobreposicao.join(codigo_bairro_para_rpa).groupby("codigo_rpa")[
        ["n_episodios_v1", "n_episodios_v2"]
    ].sum()
    tabela_por_rpa_sobreposicao.to_csv(PASTA_RELATORIO / "incidence_v2_episodios_por_rpa.csv")

    # ==================================================================
    # FASE 4 — Baselines (3 casos + 3 incidência), todos avaliados contra
    # os episódios de INCIDÊNCIA (mesma verdade que V2 está tentando prever).
    # ==================================================================
    logger.info("FASE 4: baselines de casos e de incidência")
    rankings_baselines = {
        "casos_atuais": _construir_df_ranking(ctx_teste_principal, ctx_teste_principal["casos_t"]),
        "crescimento_recente": _construir_df_ranking(ctx_teste_principal, ctx_teste_principal["taxa_crescimento_suavizada"]),
        "razao_historica_local": _construir_df_ranking(ctx_teste_principal, ctx_teste_principal["razao_limiar_historico"]),
        "incidencia_atual": _construir_df_ranking(ctx_teste_principal, baseline_incidencia_atual(ctx_teste_principal)),
        "crescimento_incidencia": _construir_df_ranking(ctx_teste_principal, baseline_crescimento_incidencia(ctx_teste_principal)),
        "razao_historica_incidencia": _construir_df_ranking(ctx_teste_principal, baseline_razao_historica_incidencia(ctx_teste_principal)),
    }

    # ==================================================================
    # FASE 5 — Master (1 linha por episódio de incidência) + posição de
    # cada método (5 variantes de V2 + 6 baselines).
    # ==================================================================
    logger.info("FASE 5: master de episódios (incidência) + posição de cada método")

    estado_incidencia_indexado = ctx_principal.set_index(["codigo_bairro", "indice_semana_global"])[
        "estado_alto_risco_incidencia"
    ]

    def _ja_ativo(row) -> bool:
        v = estado_incidencia_indexado.get((row["codigo_bairro"], row["inicio_indice"] - JANELA_LEAD_TIME))
        return bool(v == 1) if v is not None else False

    master = episodios_incidencia_teste.copy()
    master["ja_ativo_no_inicio_da_janela"] = master.apply(_ja_ativo, axis=1)
    master = master.merge(codigo_bairro_para_rpa, on="codigo_bairro", how="left")

    todos_os_rankings = {v: t["df_rank"] for v, t in treinos.items()}
    todos_os_rankings.update(rankings_baselines)

    for nome_metodo, df_rank in todos_os_rankings.items():
        posicoes = ranking.posicao_antes_de_episodios(df_rank, episodios_incidencia_teste, janela=JANELA_LEAD_TIME)
        posicoes = posicoes.rename(
            columns={
                "melhor_posicao_antes_do_inicio": f"posicao_{nome_metodo}",
                "semanas_antecedencia_melhor_posicao": f"lead_{nome_metodo}",
            }
        )[["codigo_bairro", "inicio_indice", f"posicao_{nome_metodo}", f"lead_{nome_metodo}"]]
        master = master.merge(posicoes, on=["codigo_bairro", "inicio_indice"], how="left")
        for k in K_VALORES:
            master[f"detectado_{nome_metodo}_k{k}"] = (master[f"posicao_{nome_metodo}"] <= k).astype(int)

    master.to_csv(PASTA_RELATORIO / "incidence_v2_master_episodios.csv", index=False)
    logger.info("Master salvo: %d episódios x %d colunas", len(master), master.shape[1])

    # ==================================================================
    # FASE 6 — Recall@K + IC bootstrap para cada variante de V2 e cada
    # baseline; delta (candidato principal) vs melhor baseline (dos 6).
    # ==================================================================
    logger.info("FASE 6: bootstrap de evidência (episódio + cluster bairro/bairro-ano)")

    metodos_modelo = list(VARIANTES_FEATURES)
    metodos_baseline = list(rankings_baselines)
    todos_os_metodos = metodos_modelo + metodos_baseline

    linhas_recall = []
    for k in K_VALORES:
        for metodo in todos_os_metodos:
            arr = master[f"detectado_{metodo}_k{k}"].to_numpy(dtype=float)
            ic = evidence_validation.bootstrap_recall(arr, n_reamostragens=N_REAMOSTRAGENS, seed=SEED)
            linhas_recall.append({"k": k, "metodo": metodo, **ic})
    tabela_recall_ic = pd.DataFrame(linhas_recall)
    tabela_recall_ic.to_csv(PASTA_RELATORIO / "incidence_v2_recall_ic.csv", index=False)
    resultado["recall_ic"] = tabela_recall_ic.to_dict("records")

    linhas_delta = []
    for k in K_VALORES:
        obs_baselines = {b: master[f"detectado_{b}_k{k}"].mean() for b in metodos_baseline}
        melhor_baseline = max(obs_baselines, key=obs_baselines.get)
        arr_v2 = master[f"detectado_{NOME_V2_PRINCIPAL}_k{k}"].to_numpy(dtype=float)
        arr_baseline = master[f"detectado_{melhor_baseline}_k{k}"].to_numpy(dtype=float)
        delta = evidence_validation.bootstrap_delta(arr_v2, arr_baseline, n_reamostragens=N_REAMOSTRAGENS, seed=SEED)
        linha = {"k": k, "melhor_baseline": melhor_baseline, **delta}
        for sufixo, cluster_ids in (
            ("cluster_bairro", master["codigo_bairro"].to_numpy()),
            ("cluster_bairro_ano", (master["codigo_bairro"].astype(str) + "_" + master["inicio_ano"].astype(str)).to_numpy()),
        ):
            delta_cluster = evidence_validation.bootstrap_delta(
                arr_v2, arr_baseline, cluster_ids=cluster_ids, n_reamostragens=N_REAMOSTRAGENS, seed=SEED
            )
            linha[f"ic_baixo_{sufixo}"] = delta_cluster["ic_baixo"]
            linha[f"ic_alto_{sufixo}"] = delta_cluster["ic_alto"]

        arr_v1_equivalente_k = None
        if k in (5, 10, 15, 20):
            v1_recall_k = next(
                (r for r in evidencia_v1.get("recall_ic", []) if r["k"] == k and r["metodo"] == "modelo"), None
            )
            linha["v1_recall_observado"] = v1_recall_k["observado"] if v1_recall_k else None
        linhas_delta.append(linha)
    tabela_delta = pd.DataFrame(linhas_delta)
    tabela_delta.to_csv(PASTA_RELATORIO / "incidence_v2_delta_vs_baseline.csv", index=False)
    resultado["delta_v2_vs_melhor_baseline"] = tabela_delta.to_dict("records")

    # leave-one-year-out (K=5, candidato principal vs melhor baseline em K=5)
    melhor_baseline_k5 = tabela_delta.loc[tabela_delta["k"] == 5, "melhor_baseline"].iloc[0]
    loyo = evidence_validation.leave_one_group_out(
        master, "inicio_ano", f"detectado_{NOME_V2_PRINCIPAL}_k5", f"detectado_{melhor_baseline_k5}_k5"
    )
    loyo.to_csv(PASTA_RELATORIO / "incidence_v2_leave_one_year_out.csv", index=False)
    resultado["leave_one_year_out"] = loyo.to_dict("records")

    # ==================================================================
    # FASE 7 — Territorial (por ano / RPA / IPSEP / POÇO), estabilidade,
    # lead time, grandes episódios, genuíno x recaída — candidato principal.
    # ==================================================================
    logger.info("FASE 7: territorial, estabilidade, lead time, grandes episódios, genuíno x recaída")

    colunas_ano = [f"detectado_{NOME_V2_PRINCIPAL}_k5", f"detectado_{NOME_V2_PRINCIPAL}_k10"]
    tabela_por_ano = evidence_validation.agregar_recall_por_grupo(master, "inicio_ano", colunas_ano)
    tabela_por_ano.to_csv(PASTA_RELATORIO / "incidence_v2_por_ano.csv", index=False)
    resultado["por_ano"] = tabela_por_ano.to_dict("records")

    colunas_rpa = [f"detectado_{NOME_V2_PRINCIPAL}_k5", f"detectado_{NOME_V2_PRINCIPAL}_k10", f"detectado_{NOME_V2_PRINCIPAL}_k20"]
    tabela_por_rpa = evidence_validation.agregar_recall_por_grupo(master, "codigo_rpa", colunas_rpa)
    tabela_por_rpa.to_csv(PASTA_RELATORIO / "incidence_v2_por_rpa.csv", index=False)
    resultado["por_rpa"] = tabela_por_rpa.to_dict("records")

    linhas_bairro = []
    for (bairro, nome), sub in master.groupby(["codigo_bairro", "nome_bairro"]):
        linha = {"codigo_bairro": bairro, "nome_bairro": nome, "n_episodios": len(sub)}
        for k in (10, 20):
            linha[f"recall{k}_{NOME_V2_PRINCIPAL}"] = float(sub[f"detectado_{NOME_V2_PRINCIPAL}_k{k}"].mean())
        linhas_bairro.append(linha)
    tabela_bairro = pd.DataFrame(linhas_bairro).sort_values("n_episodios", ascending=False)
    tabela_bairro.to_csv(PASTA_RELATORIO / "incidence_v2_por_bairro.csv", index=False)

    resultado["ipsep"] = tabela_bairro[tabela_bairro["codigo_bairro"] == CODIGO_IPSEP].to_dict("records")
    codigo_poco = codigo_bairro_para_rpa.reset_index()
    codigo_poco = codigo_poco[codigo_poco["nome_bairro"].str.upper() == "POCO"]["codigo_bairro"]
    if len(codigo_poco):
        resultado["poco"] = tabela_bairro[tabela_bairro["codigo_bairro"].isin(codigo_poco)].to_dict("records")
    else:
        resultado["poco"] = []

    resultado["estabilidade_top10"] = {
        v: ranking.estabilidade_ranking(t["df_rank"], k=10) for v, t in treinos.items()
    }

    leads_k5 = master.loc[master[f"detectado_{NOME_V2_PRINCIPAL}_k5"] == 1, f"lead_{NOME_V2_PRINCIPAL}"].dropna().to_numpy(dtype=float)
    resultado["lead_time_k5"] = {
        "n": len(leads_k5),
        "media": float(np.mean(leads_k5)) if len(leads_k5) else None,
        "mediana_ic": evidence_validation.bootstrap_mediana(leads_k5, n_reamostragens=N_REAMOSTRAGENS, seed=SEED),
        "pct_>=1_semana": float((leads_k5 >= 1).mean() * 100) if len(leads_k5) else None,
        "pct_>=2_semanas": float((leads_k5 >= 2).mean() * 100) if len(leads_k5) else None,
        "pct_>=3_semanas": float((leads_k5 >= 3).mean() * 100) if len(leads_k5) else None,
    }

    n_top = max(1, int(np.ceil(len(master) * 0.10)))
    grandes = master.sort_values("casos_totais_episodio", ascending=False).head(n_top)
    resultado["grandes_episodios"] = {
        "n": len(grandes),
        "recall5": evidence_validation.bootstrap_recall(
            grandes[f"detectado_{NOME_V2_PRINCIPAL}_k5"].to_numpy(dtype=float), n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        ),
        "recall10": evidence_validation.bootstrap_recall(
            grandes[f"detectado_{NOME_V2_PRINCIPAL}_k10"].to_numpy(dtype=float), n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        ),
    }

    genuinos = master[~master["ja_ativo_no_inicio_da_janela"]]
    recaidas = master[master["ja_ativo_no_inicio_da_janela"]]
    resultado["genuino_vs_recaida"] = {
        "n_genuinos": len(genuinos),
        "n_recaidas": len(recaidas),
        "recall10_genuino": evidence_validation.bootstrap_recall(
            genuinos[f"detectado_{NOME_V2_PRINCIPAL}_k10"].to_numpy(dtype=float), n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        ),
        "recall10_recaida": evidence_validation.bootstrap_recall(
            recaidas[f"detectado_{NOME_V2_PRINCIPAL}_k10"].to_numpy(dtype=float), n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        ) if len(recaidas) else None,
    }

    # ==================================================================
    # FASE 8 — Bairros pequenos: incidência semanal x móvel de 4 semanas
    # (seção 10 do pedido).
    # ==================================================================
    logger.info("FASE 8: bairros pequenos — incidência semanal x incidência móvel 4 semanas")

    df_estado_4s = calcular_estado_alto_risco_incidencia(ctx_principal, coluna_valor="incidencia_4s_100k")
    populacao_mediana_bairro = ctx_principal.groupby("codigo_bairro")["populacao_bairro_ano"].median()
    limite_pequeno = populacao_mediana_bairro.quantile(0.25)
    bairros_pequenos = set(populacao_mediana_bairro[populacao_mediana_bairro <= limite_pequeno].index)

    def _n_eventos(serie_estado: pd.Series, bairros: set) -> int:
        mask = ctx_principal["codigo_bairro"].isin(bairros)
        return int((serie_estado[mask] == 1).sum())

    resultado["bairros_pequenos"] = {
        "limite_populacao_p25": float(limite_pequeno),
        "n_bairros_pequenos": len(bairros_pequenos),
        "eventos_incidencia_semanal_pequenos": _n_eventos(ctx_principal["estado_alto_risco_incidencia"], bairros_pequenos),
        "eventos_incidencia_4s_pequenos": _n_eventos(df_estado_4s["estado_alto_risco_incidencia"], bairros_pequenos),
        "eventos_incidencia_semanal_grandes": _n_eventos(
            ctx_principal["estado_alto_risco_incidencia"], set(ctx_principal["codigo_bairro"].unique()) - bairros_pequenos
        ),
        "eventos_incidencia_4s_grandes": _n_eventos(
            df_estado_4s["estado_alto_risco_incidencia"], set(ctx_principal["codigo_bairro"].unique()) - bairros_pequenos
        ),
    }

    # ==================================================================
    # FASE 9 — Ablation (seção 24): recall@5/10 das 4 variantes de feature
    # sobre o MESMO target de incidência.
    # ==================================================================
    logger.info("FASE 9: tabela de ablation")
    linhas_ablation = []
    for variante in VARIANTES_FEATURES:
        linha = {"variante": variante, "n_features": treinos[variante]["metricas_dataset"]["n_features"]}
        for k in (5, 10):
            arr = master[f"detectado_{variante}_k{k}"].to_numpy(dtype=float)
            linha[f"recall{k}"] = float(arr.mean())
        linhas_ablation.append(linha)
    tabela_ablation = pd.DataFrame(linhas_ablation)
    tabela_ablation.to_csv(PASTA_RELATORIO / "incidence_v2_ablation.csv", index=False)
    resultado["ablation"] = tabela_ablation.to_dict("records")

    # ==================================================================
    # FASE 10 — Sensibilidade populacional A (por tipo de população/ano)
    # e B (perturbação com erro real, seção 8-9 do pedido).
    # ==================================================================
    logger.info("FASE 10: sensibilidade populacional A (por ano) e B (perturbação)")

    tipo_por_ano = (
        ctx_principal.groupby("ano_epidemiologico")["tipo_populacao"].agg(lambda s: s.value_counts().idxmax())
    )
    tabela_sensibilidade_a = tabela_por_ano.merge(
        tipo_por_ano.rename("tipo_populacao_dominante"), left_on="inicio_ano", right_index=True, how="left"
    )
    tabela_sensibilidade_a.to_csv(PASTA_RELATORIO / "incidence_v2_sensibilidade_a_por_ano.csv", index=False)
    resultado["sensibilidade_a"] = tabela_sensibilidade_a.to_dict("records")

    df_silver_pop = carregar_silver_populacao_local()
    df_territorio_pop = df_gold[["codigo_bairro", "nome_bairro"]].drop_duplicates("codigo_bairro")
    distribuicao_erro = obter_distribuicao_erro_percentual_real(
        CAMINHO_BRONZE_CIEVS, CAMINHO_BRONZE_CENSO2022, CAMINHO_BRONZE_MUNICIPAL, df_territorio_pop
    )
    resultado["sensibilidade_b_distribuicao_erro"] = {
        "n_bairros": len(distribuicao_erro),
        "mae_pct": float(np.mean(np.abs(distribuicao_erro))),
        "bias_medio_pct": float(np.mean(distribuicao_erro)),
        "min_pct": float(np.min(distribuicao_erro)),
        "max_pct": float(np.max(distribuicao_erro)),
    }

    def _avaliar_replica(gold_perturbada: pd.DataFrame) -> dict[str, Any]:
        ctx_p, X_p, y_p, m_p = montar_dataset_onset_incidencia(
            gold_perturbada, agravo="DENGUE", horizonte=HORIZONTE_ONSET, variante=NOME_V2_PRINCIPAL
        )
        idx_tr_p, _, idx_te_p = split_mod.split_temporal(ctx_p)
        modelo_p = models.treinar_arvore(X_p.loc[idx_tr_p], y_p.loc[idx_tr_p], **HIPERPARAMETROS_ARVORE)
        proba_p = models.prever_probabilidade(modelo_p, X_p.loc[idx_te_p])
        ctx_te_p = ctx_p.loc[idx_te_p]
        df_rank_p = _construir_df_ranking(ctx_te_p, proba_p)
        episodios_p = construir_episodios_incidencia(ctx_p)
        episodios_p_teste = episodios_p[episodios_p["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM]
        posicoes_p = ranking.posicao_antes_de_episodios(df_rank_p, episodios_p_teste, janela=JANELA_LEAD_TIME)
        recall5 = float((posicoes_p["melhor_posicao_antes_do_inicio"] <= 5).mean()) if len(posicoes_p) else None
        return {"n_episodios": len(episodios_p_teste), "recall5": recall5, "prevalencia": m_p["proporcao_positiva"]}

    resultados_sensibilidade_b = executar_analise_sensibilidade_b(
        df_gold, df_silver_pop, distribuicao_erro, _avaliar_replica,
        n_replicas=N_REPLICAS_SENSIBILIDADE_B, seed=SEED,
    )
    tabela_sensibilidade_b = pd.DataFrame(resultados_sensibilidade_b)
    tabela_sensibilidade_b.to_csv(PASTA_RELATORIO / "incidence_v2_sensibilidade_b_replicas.csv", index=False)
    recall5_principal_observado = float(master[f"detectado_{NOME_V2_PRINCIPAL}_k5"].mean())
    resultado["sensibilidade_b"] = {
        "n_replicas": N_REPLICAS_SENSIBILIDADE_B,
        "recall5_sem_perturbacao": recall5_principal_observado,
        "recall5_replicas_media": float(tabela_sensibilidade_b["recall5"].mean()),
        "recall5_replicas_desvio": float(tabela_sensibilidade_b["recall5"].std()),
        "recall5_replicas_min": float(tabela_sensibilidade_b["recall5"].min()),
        "recall5_replicas_max": float(tabela_sensibilidade_b["recall5"].max()),
        "n_episodios_replicas_media": float(tabela_sensibilidade_b["n_episodios"].mean()),
        "n_episodios_replicas_desvio": float(tabela_sensibilidade_b["n_episodios"].std()),
    }

    # ==================================================================
    # SALVAR
    # ==================================================================
    with open(PASTA_RELATORIO / "resultado_incidence_v2_completo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Resultado completo salvo em %s", PASTA_RELATORIO / "resultado_incidence_v2_completo.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
