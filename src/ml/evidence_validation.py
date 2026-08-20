"""Validação estatística da evidência do candidato congelado
`dengue_onset_ranking_candidate_v1` — bootstrap ao nível de EPISÓDIO
(nunca semana), pareado quando comparando dois métodos sobre o mesmo
conjunto de episódios.

Esta etapa **não retreina nada**: os arrays `detectado`/`valores` passados
aqui já vêm de rankings/posições calculados pelas etapas anteriores
(`src/ml/ranking.py`) — este módulo só reamostra o resultado já obtido
para quantificar incerteza, nunca recalcula o modelo.

## Por que bootstrap por episódio, não por semana

Semanas de um mesmo episódio (ou de um mesmo bairro em anos diferentes)
não são observações independentes — tratar cada linha semanal como uma
amostra i.i.d. infla artificialmente a confiança do intervalo. O bootstrap
aqui sempre reamostra **episódios inteiros** (uma linha = um episódio real,
já a granularidade correta de "evento" desta etapa).

## Bootstrap por cluster (bairro)

Passando `cluster_ids` (ex.: `codigo_bairro` de cada episódio), a
reamostragem escolhe CLUSTERS inteiros com reposição (nunca episódios
individuais dentro de um cluster) — preserva a correlação entre episódios
do mesmo bairro (um bairro "fácil"/"difícil" de rankear tende a ficar
fácil/difícil em vários dos seus próprios episódios). Isso tende a produzir
intervalos mais largos (mais conservadores) que o bootstrap por episódio
simples — reportado como análise de sensibilidade, não substituindo o
IC principal.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


def _indices_bootstrap(
    n: int,
    cluster_ids: np.ndarray | None,
    n_reamostragens: int,
    seed: int,
) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    indices_lista: list[np.ndarray] = []

    if cluster_ids is None:
        for _ in range(n_reamostragens):
            indices_lista.append(rng.integers(0, n, size=n))
        return indices_lista

    clusters_unicos = np.unique(cluster_ids)
    posicoes_por_cluster = {c: np.where(cluster_ids == c)[0] for c in clusters_unicos}
    n_clusters = len(clusters_unicos)
    for _ in range(n_reamostragens):
        escolhidos = rng.choice(clusters_unicos, size=n_clusters, replace=True)
        idx = np.concatenate([posicoes_por_cluster[c] for c in escolhidos])
        indices_lista.append(idx)
    return indices_lista


def bootstrap_recall(
    detectado: np.ndarray,
    cluster_ids: np.ndarray | None = None,
    n_reamostragens: int = 2000,
    seed: int = 42,
    alfa: float = 0.05,
) -> dict:
    """IC bootstrap (percentil) para a taxa de detecção (Recall@K de um
    único método/K). `detectado` é um array booleano/0-1, um valor por
    episódio."""
    n = len(detectado)
    if n == 0:
        return {"observado": None, "n": 0, "n_reamostragens": n_reamostragens, "ic_baixo": None, "ic_alto": None}
    indices_lista = _indices_bootstrap(n, cluster_ids, n_reamostragens, seed)
    distribuicao = np.array([detectado[idx].mean() for idx in indices_lista])
    return {
        "observado": float(np.mean(detectado)),
        "n": n,
        "n_reamostragens": n_reamostragens,
        "ic_baixo": float(np.percentile(distribuicao, 100 * alfa / 2)),
        "ic_alto": float(np.percentile(distribuicao, 100 * (1 - alfa / 2))),
    }


def bootstrap_delta(
    detectado_a: np.ndarray,
    detectado_b: np.ndarray,
    cluster_ids: np.ndarray | None = None,
    n_reamostragens: int = 2000,
    seed: int = 42,
    alfa: float = 0.05,
) -> dict:
    """IC bootstrap PAREADO para `delta = recall(a) - recall(b)`, sobre o
    MESMO conjunto de episódios avaliado pelos dois métodos — usa os
    MESMOS índices reamostrados nos dois lados a cada repetição (nunca
    reamostra `a` e `b` de forma independente, o que inflaria a variância
    do delta e poderia até inverter o sinal por acaso)."""
    n = len(detectado_a)
    if n == 0 or len(detectado_b) != n:
        raise ValueError("detectado_a e detectado_b precisam ter o mesmo tamanho (mesmos episódios)")
    indices_lista = _indices_bootstrap(n, cluster_ids, n_reamostragens, seed)
    distribuicao = np.array([detectado_a[idx].mean() - detectado_b[idx].mean() for idx in indices_lista])
    return {
        "observado": float(np.mean(detectado_a) - np.mean(detectado_b)),
        "n": n,
        "n_reamostragens": n_reamostragens,
        "ic_baixo": float(np.percentile(distribuicao, 100 * alfa / 2)),
        "ic_alto": float(np.percentile(distribuicao, 100 * (1 - alfa / 2))),
    }


def bootstrap_mediana(
    valores: np.ndarray,
    cluster_ids: np.ndarray | None = None,
    n_reamostragens: int = 2000,
    seed: int = 42,
    alfa: float = 0.05,
) -> dict:
    """IC bootstrap para a MEDIANA de uma métrica contínua (ex.: lead
    time, só sobre episódios detectados) — mesma lógica de reamostragem
    de `bootstrap_recall`."""
    n = len(valores)
    if n == 0:
        return {"observado": None, "n": 0, "n_reamostragens": n_reamostragens, "ic_baixo": None, "ic_alto": None}
    indices_lista = _indices_bootstrap(n, cluster_ids, n_reamostragens, seed)
    distribuicao = np.array([np.median(valores[idx]) for idx in indices_lista])
    return {
        "observado": float(np.median(valores)),
        "n": n,
        "n_reamostragens": n_reamostragens,
        "ic_baixo": float(np.percentile(distribuicao, 100 * alfa / 2)),
        "ic_alto": float(np.percentile(distribuicao, 100 * (1 - alfa / 2))),
    }


def agregar_recall_por_grupo(
    master: pd.DataFrame,
    coluna_grupo: str,
    colunas_deteccao: list[str],
) -> pd.DataFrame:
    """Recall médio (fração de episódios detectados) por valor de
    `coluna_grupo` (ex.: `inicio_ano`, `codigo_rpa`), para cada coluna de
    detecção 0/1 em `colunas_deteccao` — usado tanto para "por ano" quanto
    para "por RPA" (mesma lógica, evita duplicar código). Sempre inclui
    `n_episodios` — nunca reporte um percentual territorial/anual sem o N
    que o sustenta."""
    agrupado = master.groupby(coluna_grupo).agg(n_episodios=(colunas_deteccao[0], "size"))
    for col in colunas_deteccao:
        agrupado[col] = master.groupby(coluna_grupo)[col].mean()
    return agrupado.reset_index()


def leave_one_group_out(
    master: pd.DataFrame,
    coluna_grupo: str,
    coluna_deteccao_modelo: str,
    coluna_deteccao_baseline: str,
) -> pd.DataFrame:
    """Para cada valor único de `coluna_grupo` (ex.: cada ano), recalcula
    o Recall (modelo e melhor baseline) EXCLUINDO esse valor — nunca
    retreina nada, só filtra o dataset de avaliação já calculado. Objetivo:
    checar se a conclusão de que o modelo supera o baseline depende
    excessivamente de um único grupo (ano/bairro)."""
    linhas = []
    for valor in sorted(master[coluna_grupo].unique()):
        sub = master[master[coluna_grupo] != valor]
        linhas.append(
            {
                f"{coluna_grupo}_excluido": valor,
                "n_episodios": len(sub),
                "recall_modelo": float(sub[coluna_deteccao_modelo].mean()) if len(sub) else None,
                "recall_melhor_baseline": float(sub[coluna_deteccao_baseline].mean()) if len(sub) else None,
            }
        )
    return pd.DataFrame(linhas)


def carregar_artefatos_evidencia(pasta: Path) -> dict:
    """Lê os artefatos de backtest já calculados (CSVs + JSON de
    `src/validate_dengue_onset_ranking_evidence.py`) para consumo pela
    página técnica de validação (`tools/model_validation_app.py`) — NUNCA
    treina modelo, NUNCA gera previsão nova, só lê o que já foi salvo em
    disco. Devolve `{}` (sem levantar exceção) para qualquer artefato
    ausente, permitindo que a página mostre um aviso em vez de quebrar."""
    resultado: dict = {}

    caminho_json = pasta / "resultado_evidence_validation_completo.json"
    if caminho_json.exists():
        with open(caminho_json, encoding="utf-8") as f:
            resultado["resumo"] = json.load(f)
    else:
        resultado["resumo"] = None

    arquivos_csv = {
        "recall_ic": "evidence_recall_ic.csv",
        "delta_vs_baseline": "evidence_delta_vs_baseline.csv",
        "por_ano": "evidence_por_ano.csv",
        "leave_one_year_out": "evidence_leave_one_year_out.csv",
        "por_rpa": "evidence_por_rpa.csv",
        "por_bairro": "evidence_por_bairro.csv",
        "carga_operacional": "evidence_carga_operacional.csv",
        "master_episodios": "evidence_master_episodios.csv",
    }
    for chave, nome_arquivo in arquivos_csv.items():
        caminho = pasta / nome_arquivo
        resultado[chave] = pd.read_csv(caminho) if caminho.exists() else None

    return resultado


def calcular_carga_priorizacao(
    df_ranking_com_onset: pd.DataFrame,
    k_valores: Sequence[int] = (5, 10, 15, 20),
    coluna_onset: str = "onset_futuro",
) -> pd.DataFrame:
    """Traduz cada `K` em carga operacional real (seção 14 do pedido):
    quantas priorizações (bairro x semana) o cenário "priorizar até K
    bairros por semana" gera, e quantas dessas priorizações **não** foram
    seguidas por um episódio novo na janela do target (`t+1..t+3`).

    `coluna_onset` é o TARGET REAL de onset da própria linha (0/1), não a
    previsão — logo `priorizacoes_sem_episodio_futuro` é a contagem de
    priorizações que, retrospectivamente, não precederam nenhum início de
    episódio naquele bairro. Linhas com target indefinido (`NaN`) são
    contadas em `priorizacoes_alvo_indefinido` e excluídas do
    numerador/denominador do percentual — nunca forçadas a 0.

    Complementar (não substituto) do Recall@K: Recall@K mede cobertura de
    episódios; isto mede o custo de olhar K bairros toda semana.
    """
    linhas = []
    for k in k_valores:
        topk = df_ranking_com_onset[df_ranking_com_onset["posicao"] <= k]
        n_semanas = int(topk["indice_semana_alvo"].nunique())
        alvo = topk[coluna_onset]
        n_indefinido = int(alvo.isna().sum())
        alvo_definido = alvo.dropna()
        com_episodio = int((alvo_definido == 1).sum())
        sem_episodio = int((alvo_definido == 0).sum())
        linhas.append(
            {
                "k": k,
                "n_semanas_avaliadas": n_semanas,
                "priorizacoes_total": int(len(topk)),
                "bairros_priorizados_por_semana_medio": float(len(topk) / n_semanas) if n_semanas else None,
                "priorizacoes_com_episodio_futuro": com_episodio,
                "priorizacoes_sem_episodio_futuro": sem_episodio,
                "priorizacoes_alvo_indefinido": n_indefinido,
                "pct_priorizacoes_sem_episodio_futuro": float(sem_episodio / (com_episodio + sem_episodio) * 100)
                if (com_episodio + sem_episodio)
                else None,
            }
        )
    return pd.DataFrame(linhas)


def serie_jaccard_consecutivo(df_ranking: pd.DataFrame, k: int = 10) -> pd.DataFrame:
    """Série semana a semana do Jaccard do Top-K entre semanas
    CONSECUTIVAS — versão detalhada de `ranking.estabilidade_ranking`
    (que devolve só média/mediana), necessária para visualizar se a
    instabilidade é uniforme ou concentrada em alguns períodos. Pares não
    consecutivos (lacunas no índice de semanas) são ignorados, nunca
    tratados como consecutivos."""
    semanas = sorted(df_ranking["indice_semana_alvo"].unique())
    topk_por_semana = {
        s: set(df_ranking.loc[(df_ranking["indice_semana_alvo"] == s) & (df_ranking["posicao"] <= k), "codigo_bairro"])
        for s in semanas
    }
    linhas = []
    for s in semanas:
        if (s + 1) not in topk_por_semana:
            continue
        a, b = topk_por_semana[s], topk_por_semana[s + 1]
        uniao = a | b
        if not uniao:
            continue
        linhas.append(
            {
                "indice_semana_alvo": int(s),
                "indice_semana_seguinte": int(s + 1),
                "jaccard": float(len(a & b) / len(uniao)),
                "n_bairros_mantidos": int(len(a & b)),
                "k": k,
            }
        )
    return pd.DataFrame(linhas)
