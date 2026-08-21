"""Experimento controlado ÚNICO: o clima em grade acrescenta valor
incremental ao ranking territorial de onset de dengue?

Uso:
    python -m src.experiment_dengue_ranking_clima

## O que este experimento é — e o que ele deliberadamente não é

É a comparação **A × B** autorizada para esta etapa:

| | Modelo A (referência) | Modelo B (com clima em grade) |
|---|---|---|
| Target | onset em t+1..t+3 | idêntico |
| Linhas | as mesmas | as mesmas |
| Split | 2013-2019 / 2020-2022 / 2023-2025 | idêntico |
| Modelo | `HistGradientBoostingClassifier` | idêntico |
| Hiperparâmetros | `max_depth=4, lr=0.1, max_iter=150`, seed 42 | idênticos |
| Features | 38 (sem clima) | 38 + 8 de clima em grade |

**Não** é: novo tuning, nova seleção de features, novo algoritmo, novo
target, novo horizonte, nova busca de hiperparâmetro. A única diferença
entre A e B é o bloco de 8 colunas climáticas em grade.

Se B não melhorar de forma consistente, o clima **não** é incorporado ao
modelo do produto — e o resultado negativo é publicado, não descartado.

## Expectativa a priori (registrada antes de rodar)

A investigação da fonte
(`reports/climate_source_analysis/gridded_climate_investigation.md`) mediu
que a grade produz no máximo **2 valores distintos de precipitação entre os
94 bairros na mesma semana**. O produto avaliado aqui é um **ranking entre
bairros dentro da mesma semana**. Uma variável quase constante entre as
unidades comparadas não tem como discriminá-las — logo o ganho esperado é
nulo ou marginal, e viria apenas de interação entre clima e histórico local
dentro das árvores. O experimento existe para medir isso com números, não
para confirmar a intuição.

## Métricas avaliadas (as pedidas para esta etapa)

Recall@5 (a faixa em que o candidato congelado tem ganho defensável),
delta contra o melhor baseline sem modelo, estabilidade ano a ano,
onset genuíno × recaída, e grandes episódios.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.logging_config import configurar_logging
from src.ml import alert_metrics, evidence_validation, models, ranking
from src.ml import split as split_mod
from src.ml.dataset import montar_dataset_onset
from src.ml.features import FEATURES_CLIMATICAS_GRADE, construir_indice_semana_global
from src.ml.target import agregar_semanal_agravo, calcular_estado_alto_risco
from src.utils.io_atomico import escrever_csv_atomico, escrever_json_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "ml"

HORIZONTE_ONSET = 3
JANELA_LEAD_TIME = 4
K_VALORES = (5, 10, 15, 20)
HIPERPARAMETROS_ARVORE = {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150}
SEED = 42
N_REAMOSTRAGENS = 2000

BASELINES = {
    "casos_atuais": "casos_t",
    "crescimento_recente": "taxa_crescimento_suavizada",
    "razao_historica_local": "razao_limiar_historico",
}

def _ranking_de(ctx: pd.DataFrame, score) -> pd.DataFrame:
    df = ctx[["codigo_bairro", "indice_semana_alvo"]].copy()
    df["probabilidade"] = np.asarray(score)
    return ranking.construir_ranking_semanal(df)

def _deteccoes_por_episodio(
    df_rank: pd.DataFrame, df_episodios: pd.DataFrame, prefixo: str
) -> pd.DataFrame:
    posicoes = ranking.posicao_antes_de_episodios(df_rank, df_episodios, janela=JANELA_LEAD_TIME).rename(
        columns={
            "melhor_posicao_antes_do_inicio": f"posicao_{prefixo}",
            "semanas_antecedencia_melhor_posicao": f"lead_{prefixo}",
        }
    )[["codigo_bairro", "inicio_indice", f"posicao_{prefixo}", f"lead_{prefixo}"]]
    for k in K_VALORES:
        posicoes[f"detectado_{prefixo}_k{k}"] = (posicoes[f"posicao_{prefixo}"] <= k).astype(int)
    return posicoes

def main() -> int:
    configurar_logging()
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrada.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    faltando = [c for c in FEATURES_CLIMATICAS_GRADE if c not in df_gold.columns]
    if faltando:
        logger.error(
            "Gold sem o bloco climático em grade (%s). Rode 'python -m src.enrich_gold_clima_grade'.",
            faltando,
        )
        return 1

    resultado: dict[str, Any] = {
        "experimento": "clima_em_grade_no_ranking_de_onset_dengue",
        "seed": SEED,
        "n_reamostragens": N_REAMOSTRAGENS,
        "hiperparametros": HIPERPARAMETROS_ARVORE,
        "horizonte_onset": HORIZONTE_ONSET,
        "features_clima_grade": list(FEATURES_CLIMATICAS_GRADE),
    }

    # ------------------------------------------------------------------
    # Episódios reais (independentes do modelo — dependem só do target)
    # ------------------------------------------------------------------
    df_estado_idx = construir_indice_semana_global(
        calcular_estado_alto_risco(agregar_semanal_agravo(df_gold, "DENGUE"))
    )
    episodios_todos = alert_metrics.construir_episodios(df_estado_idx)
    episodios_teste = episodios_todos[
        episodios_todos["inicio_ano"] > split_mod.ANO_VALIDACAO_FIM
    ].reset_index(drop=True)
    logger.info("Episódios reais no teste (2023-2025): %d", len(episodios_teste))

    estado_indexado = df_estado_idx.set_index(["codigo_bairro", "indice_semana_global"])["estado_alto_risco"]
    rpa_por_bairro = df_gold[["codigo_bairro", "codigo_rpa", "nome_bairro"]].drop_duplicates("codigo_bairro")

    master = episodios_teste.copy()
    master["ja_ativo_no_inicio_da_janela"] = master.apply(
        lambda r: bool(
            estado_indexado.get((r["codigo_bairro"], r["inicio_indice"] - JANELA_LEAD_TIME)) == 1
        ),
        axis=1,
    )
    master = master.merge(rpa_por_bairro, on="codigo_bairro", how="left")

    # ------------------------------------------------------------------
    # Modelos A e B — mesmas linhas, mesmo split, mesmos hiperparâmetros
    # ------------------------------------------------------------------
    variantes = {"A_sem_clima": False, "B_com_clima_grade": True}
    metricas_dataset: dict[str, Any] = {}
    ctx_teste_por_variante: dict[str, pd.DataFrame] = {}

    for nome, com_clima in variantes.items():
        ctx, X, y, m = montar_dataset_onset(
            df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET, incluir_clima_grade=com_clima
        )
        idx_tr, _, idx_te = split_mod.split_temporal(ctx)
        modelo = models.treinar_arvore(X.loc[idx_tr], y.loc[idx_tr], **HIPERPARAMETROS_ARVORE)
        proba = models.prever_probabilidade(modelo, X.loc[idx_te])
        ctx_teste = ctx.loc[idx_te]
        ctx_teste_por_variante[nome] = ctx_teste

        metricas_dataset[nome] = {
            "n_features": m["n_features"],
            "linhas_finais": m["linhas_finais"],
            "n_treino": len(idx_tr),
            "n_teste": len(idx_te),
            "proporcao_positiva": m["proporcao_positiva"],
        }
        logger.info(
            "%s: %d features · %d linhas (treino %d / teste %d)",
            nome, m["n_features"], m["linhas_finais"], len(idx_tr), len(idx_te),
        )

        df_rank = _ranking_de(ctx_teste, proba)
        master = master.merge(
            _deteccoes_por_episodio(df_rank, episodios_teste, nome),
            on=["codigo_bairro", "inicio_indice"], how="left",
        )
        if nome == "A_sem_clima":
            resultado["estabilidade_top10_A"] = ranking.estabilidade_ranking(df_rank, k=10)
        else:
            resultado["estabilidade_top10_B"] = ranking.estabilidade_ranking(df_rank, k=10)

    # Pré-condição do experimento: A e B têm de avaliar as MESMAS linhas.
    mesmas_linhas = (
        len(ctx_teste_por_variante["A_sem_clima"]) == len(ctx_teste_por_variante["B_com_clima_grade"])
    )
    resultado["mesmas_linhas_em_A_e_B"] = bool(mesmas_linhas)
    if not mesmas_linhas:
        logger.error(
            "A e B não avaliam as mesmas linhas (%d vs %d) — comparação inválida, abortando.",
            len(ctx_teste_por_variante["A_sem_clima"]),
            len(ctx_teste_por_variante["B_com_clima_grade"]),
        )
        return 1

    # ------------------------------------------------------------------
    # Baselines sem modelo (idênticos nas duas variantes)
    # ------------------------------------------------------------------
    ctx_teste = ctx_teste_por_variante["A_sem_clima"]
    for nome_baseline, coluna in BASELINES.items():
        df_rank = _ranking_de(ctx_teste, ctx_teste[coluna])
        master = master.merge(
            _deteccoes_por_episodio(df_rank, episodios_teste, nome_baseline),
            on=["codigo_bairro", "inicio_indice"], how="left",
        )

    escrever_csv_atomico(PASTA_RELATORIO / "clima_experimento_master_episodios.csv", master)

    # ------------------------------------------------------------------
    # Recall@K + delta pareado B - A (mesmos episódios reamostrados)
    # ------------------------------------------------------------------
    metodos = ["A_sem_clima", "B_com_clima_grade", *BASELINES]
    linhas_recall = []
    for k in K_VALORES:
        for metodo in metodos:
            arr = master[f"detectado_{metodo}_k{k}"].to_numpy(dtype=float)
            linhas_recall.append(
                {"k": k, "metodo": metodo, **evidence_validation.bootstrap_recall(
                    arr, n_reamostragens=N_REAMOSTRAGENS, seed=SEED
                )}
            )
    tabela_recall = pd.DataFrame(linhas_recall)
    escrever_csv_atomico(PASTA_RELATORIO / "clima_experimento_recall_ic.csv", tabela_recall)
    resultado["recall_ic"] = tabela_recall.to_dict("records")

    # Clusters para a análise de sensibilidade: episódios do mesmo bairro (ou
    # do mesmo bairro no mesmo ano) não são independentes. Mesmo protocolo da
    # validação do candidato congelado (`evidence_validation`).
    cluster_bairro = master["codigo_bairro"].to_numpy()
    cluster_bairro_ano = (
        master["codigo_bairro"].astype(str) + "_" + master["inicio_ano"].astype(str)
    ).to_numpy()

    def _delta_com_sensibilidade(arr_x: np.ndarray, arr_y: np.ndarray, sufixo: str) -> dict[str, Any]:
        """Delta pareado + os dois esquemas de cluster, com o mesmo sufixo de
        nome de coluna — para nenhuma conclusão desta etapa depender só do
        bootstrap por episódio."""
        principal = evidence_validation.bootstrap_delta(
            arr_x, arr_y, n_reamostragens=N_REAMOSTRAGENS, seed=SEED
        )
        saida = {
            f"delta_{sufixo}": principal["observado"],
            f"ic_baixo_{sufixo}": principal["ic_baixo"],
            f"ic_alto_{sufixo}": principal["ic_alto"],
        }
        for nome_cluster, ids in (("cluster_bairro", cluster_bairro), ("cluster_bairro_ano", cluster_bairro_ano)):
            por_cluster = evidence_validation.bootstrap_delta(
                arr_x, arr_y, cluster_ids=ids, n_reamostragens=N_REAMOSTRAGENS, seed=SEED
            )
            saida[f"ic_baixo_{sufixo}_{nome_cluster}"] = por_cluster["ic_baixo"]
            saida[f"ic_alto_{sufixo}_{nome_cluster}"] = por_cluster["ic_alto"]
        return saida

    linhas_delta = []
    for k in K_VALORES:
        arr_b = master[f"detectado_B_com_clima_grade_k{k}"].to_numpy(dtype=float)
        arr_a = master[f"detectado_A_sem_clima_k{k}"].to_numpy(dtype=float)
        obs_baselines = {b: master[f"detectado_{b}_k{k}"].mean() for b in BASELINES}
        melhor = max(obs_baselines, key=obs_baselines.get)
        arr_base = master[f"detectado_{melhor}_k{k}"].to_numpy(dtype=float)
        linhas_delta.append(
            {
                "k": k,
                "melhor_baseline": melhor,
                **_delta_com_sensibilidade(arr_b, arr_a, "B_menos_A"),
                **_delta_com_sensibilidade(arr_a, arr_base, "A_vs_baseline"),
                **_delta_com_sensibilidade(arr_b, arr_base, "B_vs_baseline"),
            }
        )
    tabela_delta = pd.DataFrame(linhas_delta)
    escrever_csv_atomico(PASTA_RELATORIO / "clima_experimento_delta.csv", tabela_delta)
    resultado["delta"] = tabela_delta.to_dict("records")

    # ------------------------------------------------------------------
    # Estabilidade ano a ano
    # ------------------------------------------------------------------
    colunas_ano = [f"detectado_{m}_k5" for m in ("A_sem_clima", "B_com_clima_grade")] + [
        f"detectado_{m}_k10" for m in ("A_sem_clima", "B_com_clima_grade")
    ]
    por_ano = evidence_validation.agregar_recall_por_grupo(master, "inicio_ano", colunas_ano)
    escrever_csv_atomico(PASTA_RELATORIO / "clima_experimento_por_ano.csv", por_ano)
    resultado["por_ano"] = por_ano.to_dict("records")

    # ------------------------------------------------------------------
    # Onset genuíno x recaída · grandes episódios
    # ------------------------------------------------------------------
    genuinos = master[~master["ja_ativo_no_inicio_da_janela"]]
    recaidas = master[master["ja_ativo_no_inicio_da_janela"]]
    n_top = max(1, int(np.ceil(len(master) * 0.10)))
    grandes = master.sort_values("casos_totais_episodio", ascending=False).head(n_top)

    recortes = {"genuino": genuinos, "recaida": recaidas, "grandes_episodios": grandes}
    resultado["recortes"] = {}
    for nome_recorte, sub in recortes.items():
        bloco: dict[str, Any] = {"n": int(len(sub))}
        for variante in ("A_sem_clima", "B_com_clima_grade"):
            for k in (5, 10):
                bloco[f"recall{k}_{variante}"] = evidence_validation.bootstrap_recall(
                    sub[f"detectado_{variante}_k{k}"].to_numpy(dtype=float),
                    n_reamostragens=N_REAMOSTRAGENS, seed=SEED,
                )
        for k in (5, 10):
            bloco[f"delta_B_menos_A_k{k}"] = evidence_validation.bootstrap_delta(
                sub[f"detectado_B_com_clima_grade_k{k}"].to_numpy(dtype=float),
                sub[f"detectado_A_sem_clima_k{k}"].to_numpy(dtype=float),
                n_reamostragens=N_REAMOSTRAGENS, seed=SEED,
            )
        resultado["recortes"][nome_recorte] = bloco

    resultado["metricas_dataset"] = metricas_dataset

    # ------------------------------------------------------------------
    # Conclusão automática — critério declarado ANTES de olhar o número
    # ------------------------------------------------------------------
    delta5 = tabela_delta.loc[tabela_delta["k"] == 5].iloc[0]
    delta10 = tabela_delta.loc[tabela_delta["k"] == 10].iloc[0]
    ic_cruza_zero_k5 = bool(delta5["ic_baixo_B_menos_A"] <= 0 <= delta5["ic_alto_B_menos_A"])

    def _sinal_positivo_em_todos_os_anos(k: int) -> bool:
        col_a, col_b = f"detectado_A_sem_clima_k{k}", f"detectado_B_com_clima_grade_k{k}"
        return bool((por_ano[col_b] > por_ano[col_a]).all())

    resultado["conclusao"] = {
        "criterio": (
            "incorporar o clima ao modelo do produto só se o delta B-A em Recall@5 "
            "(a faixa em que o candidato congelado tem ganho defensável) tiver IC que "
            "não cruza zero E sinal positivo em todos os anos do teste"
        ),
        "delta5_observado": float(delta5["delta_B_menos_A"]),
        "delta5_ic": [float(delta5["ic_baixo_B_menos_A"]), float(delta5["ic_alto_B_menos_A"])],
        "delta5_ic_cruza_zero": ic_cruza_zero_k5,
        "delta5_positivo_em_todos_os_anos": _sinal_positivo_em_todos_os_anos(5),
        "incorporar_clima_ao_modelo": bool(
            not ic_cruza_zero_k5
            and delta5["delta_B_menos_A"] > 0
            and _sinal_positivo_em_todos_os_anos(5)
        ),
        # Achado secundário, reportado por honestidade e explicitamente NÃO
        # usado para reverter o critério acima (mudar o critério depois de ver
        # o resultado seria racionalização post-hoc).
        "achado_secundario_k10": {
            "delta10_B_menos_A": float(delta10["delta_B_menos_A"]),
            "delta10_ic": [float(delta10["ic_baixo_B_menos_A"]), float(delta10["ic_alto_B_menos_A"])],
            "delta10_ic_cluster_bairro": [
                float(delta10["ic_baixo_B_menos_A_cluster_bairro"]),
                float(delta10["ic_alto_B_menos_A_cluster_bairro"]),
            ],
            "delta10_ic_cluster_bairro_ano": [
                float(delta10["ic_baixo_B_menos_A_cluster_bairro_ano"]),
                float(delta10["ic_alto_B_menos_A_cluster_bairro_ano"]),
            ],
            "delta10_positivo_em_todos_os_anos": _sinal_positivo_em_todos_os_anos(10),
            "B_vs_baseline_k10": float(delta10["delta_B_vs_baseline"]),
            "B_vs_baseline_k10_ic": [
                float(delta10["ic_baixo_B_vs_baseline"]),
                float(delta10["ic_alto_B_vs_baseline"]),
            ],
            "observacao": (
                "K=10 nao e a faixa de claim do produto e esta variante nao passou pelo "
                "protocolo completo de validacao (leave-one-year-out, analise territorial). "
                "Fica registrada como candidata a uma versao futura, que exigiria validacao propria."
            ),
        },
    }

    escrever_json_atomico(PASTA_RELATORIO / "resultado_clima_experimento.json", resultado)
    logger.info("Conclusão: %s", resultado["conclusao"])
    print(json.dumps(resultado["conclusao"], ensure_ascii=False, indent=2))
    print(tabela_delta.to_string(index=False))
    print(por_ano.to_string(index=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
