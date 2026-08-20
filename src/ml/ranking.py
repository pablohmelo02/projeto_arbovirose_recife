"""Ranking territorial — "mesmo quando a classificação binária erra, o
bairro aparece perto do topo do ranking de risco?" (seção 20 do pedido).

Um cutoff binário perde informação: um bairro com probabilidade 0,45
(abaixo de um threshold de 0,50) pode ainda estar entre os 5 bairros de
maior risco da cidade naquela semana — operacionalmente relevante para
priorizar equipes de controle vetorial mesmo quando a classificação erra.
Este módulo mede exatamente isso: Recall@K (top-K bairros por semana) e a
posição do bairro no ranking antes do início real de um episódio.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def construir_ranking_semanal(df_alertas: pd.DataFrame) -> pd.DataFrame:
    """`df_alertas` precisa ter `codigo_bairro`, `indice_semana_alvo`,
    `probabilidade`. Adiciona `posicao` (1 = maior probabilidade daquela
    semana-alvo, ranking entre os bairros com previsão disponível naquela
    semana — nem sempre os 94, ver `dataset.py` para linhas excluídas)."""
    df = df_alertas.copy()
    df["posicao"] = df.groupby("indice_semana_alvo")["probabilidade"].rank(method="first", ascending=False)
    return df


def recall_em_k(
    df_ranking_com_estado: pd.DataFrame,
    k_valores: Sequence[int] = (5, 10, 20),
    coluna_estado: str = "estado_real",
) -> pd.DataFrame:
    """`df_ranking_com_estado` = saída de `construir_ranking_semanal` + uma
    coluna `coluna_estado` (0/1, estado real na semana-alvo, NÃO o target
    binário do modelo). Para cada `k`: `recall_micro` = positivos capturados
    no Top-K / total de positivos (agrega todas as semanas); `recall_macro`
    = média do recall por semana (cada semana pesa igual, independente de
    quantos positivos teve)."""
    positivos = df_ranking_com_estado[df_ranking_com_estado[coluna_estado] == 1]
    linhas = []
    for k in k_valores:
        if len(positivos) == 0:
            linhas.append({"k": k, "recall_micro": None, "recall_macro": None, "n_positivos_totais": 0, "n_semanas_com_positivo": 0})
            continue
        capturados = positivos["posicao"] <= k
        recall_micro = float(capturados.mean())
        recall_por_semana = positivos.groupby("indice_semana_alvo").apply(lambda g: (g["posicao"] <= k).mean())
        linhas.append(
            {
                "k": k,
                "recall_micro": recall_micro,
                "recall_macro": float(recall_por_semana.mean()),
                "n_positivos_totais": int(len(positivos)),
                "n_semanas_com_positivo": int(positivos["indice_semana_alvo"].nunique()),
            }
        )
    return pd.DataFrame(linhas)


def posicao_antes_de_episodios(
    df_ranking: pd.DataFrame,
    df_episodios: pd.DataFrame,
    janela: int = 4,
) -> pd.DataFrame:
    """Para cada episódio real, procura a MELHOR (menor) posição que o
    bairro alcançou no ranking semanal nas até `janela` semanas ANTES do
    início real (`indice_semana_alvo` em `[inicio-janela, inicio-1]`) —
    nunca durante ou depois, para não confundir "ranking alto porque já
    está em surto" com antecipação real. Também registra a posição na
    própria semana de início, para contraste."""
    ranking_indexado = df_ranking.set_index(["codigo_bairro", "indice_semana_alvo"])["posicao"]
    resultados = []
    for _, ep in df_episodios.iterrows():
        bairro = ep["codigo_bairro"]
        inicio = int(ep["inicio_indice"])
        melhor_posicao = None
        melhor_semana = None
        for w in range(inicio - janela, inicio):
            chave = (bairro, w)
            if chave in ranking_indexado.index:
                pos = ranking_indexado.loc[chave]
                if melhor_posicao is None or pos < melhor_posicao:
                    melhor_posicao = pos
                    melhor_semana = w
        posicao_inicio = ranking_indexado.get((bairro, inicio))
        resultados.append(
            {
                "codigo_bairro": bairro,
                "inicio_indice": inicio,
                "inicio_ano": ep.get("inicio_ano"),
                "melhor_posicao_antes_do_inicio": melhor_posicao,
                "semanas_antecedencia_melhor_posicao": (inicio - melhor_semana) if melhor_semana is not None else None,
                "posicao_na_semana_de_inicio": posicao_inicio,
            }
        )
    return pd.DataFrame(resultados)


def precision_em_k(
    df_ranking_com_estado: pd.DataFrame,
    k_valores: Sequence[int] = (5, 10, 15, 20),
    coluna_estado: str = "estado_real",
) -> pd.DataFrame:
    """Precision@K: dos K bairros priorizados numa semana, que fração
    realmente tinha o evento positivo (`coluna_estado=1`)? Complementar ao
    Recall@K — mede o trade-off "capacidade operacional x acerto", não só
    cobertura (seção 17 do pedido). Uma semana só entra na média se tiver
    ao menos 1 bairro com posição `<= k` (evita diluir com semanas sem
    dado suficiente)."""
    linhas = []
    for k in k_valores:
        topk = df_ranking_com_estado[df_ranking_com_estado["posicao"] <= k]
        if topk.empty:
            linhas.append({"k": k, "precision_media": None, "precision_mediana": None, "n_semanas": 0})
            continue
        precisao_por_semana = topk.groupby("indice_semana_alvo")[coluna_estado].mean()
        linhas.append(
            {
                "k": k,
                "precision_media": float(precisao_por_semana.mean()),
                "precision_mediana": float(precisao_por_semana.median()),
                "n_semanas": int(len(precisao_por_semana)),
            }
        )
    return pd.DataFrame(linhas)


def estabilidade_ranking(df_ranking: pd.DataFrame, k: int = 10) -> dict:
    """Sobreposição (Jaccard) do conjunto Top-K entre semanas consecutivas
    — mede se o ranking muda completamente de uma semana para a seguinte
    (seção 23: "não queremos ranking completamente caótico"). Jaccard
    próximo de 1 = ranking estável; próximo de 0 = troca quase total."""
    semanas = sorted(df_ranking["indice_semana_alvo"].unique())
    topk_por_semana = {
        s: set(df_ranking.loc[(df_ranking["indice_semana_alvo"] == s) & (df_ranking["posicao"] <= k), "codigo_bairro"])
        for s in semanas
    }
    jaccards = []
    for s in semanas:
        if (s + 1) in topk_por_semana:
            a, b = topk_por_semana[s], topk_por_semana[s + 1]
            uniao = a | b
            if uniao:
                jaccards.append(len(a & b) / len(uniao))
    return {
        "k": k,
        "n_pares_consecutivos": len(jaccards),
        "jaccard_medio": float(np.mean(jaccards)) if jaccards else None,
        "jaccard_mediano": float(np.median(jaccards)) if jaccards else None,
    }


def persistencia_consecutiva_antes_de_onset(
    df_ranking: pd.DataFrame,
    df_episodios: pd.DataFrame,
    k: int = 10,
    janela: int = 4,
) -> pd.DataFrame:
    """Para cada episódio, conta quantas semanas CONSECUTIVAS
    imediatamente antes do início (`inicio_indice-1`, `inicio_indice-2`,
    ...) o bairro esteve continuamente no Top-K — para na primeira semana
    em que sair do Top-K ou não tiver ranking disponível (seção 14: uma
    única aparição isolada não conta como sinal persistente). Se o bairro
    já não estava no Top-K na semana imediatamente anterior ao início,
    `semanas_consecutivas_topk_antes = 0`."""
    ranking_indexado = df_ranking.set_index(["codigo_bairro", "indice_semana_alvo"])["posicao"]
    resultados = []
    for _, ep in df_episodios.iterrows():
        bairro = ep["codigo_bairro"]
        inicio = int(ep["inicio_indice"])
        consecutivas = 0
        for w in range(inicio - 1, inicio - janela - 1, -1):
            pos = ranking_indexado.get((bairro, w))
            if pos is not None and pos <= k:
                consecutivas += 1
            else:
                break
        resultados.append(
            {
                "codigo_bairro": bairro,
                "inicio_indice": inicio,
                "inicio_ano": ep.get("inicio_ano"),
                "semanas_consecutivas_topk_antes": consecutivas,
            }
        )
    return pd.DataFrame(resultados)


def resumo_posicao_antes_de_episodios(
    df_posicoes: pd.DataFrame,
    k_valores: Sequence[int] = (5, 10, 20),
) -> dict:
    """KPIs agregados de `posicao_antes_de_episodios`: percentual de
    episódios cujo bairro entrou no Top-K em algum momento antes do
    início, e estatísticas de posição/antecedência."""
    disponivel = df_posicoes.dropna(subset=["melhor_posicao_antes_do_inicio"])
    resultado: dict = {
        "n_episodios": len(df_posicoes),
        "n_com_ranking_disponivel_antes": len(disponivel),
    }
    if len(disponivel):
        resultado["posicao_media_antes"] = float(disponivel["melhor_posicao_antes_do_inicio"].mean())
        resultado["posicao_mediana_antes"] = float(disponivel["melhor_posicao_antes_do_inicio"].median())
        resultado["antecedencia_media_semanas"] = float(disponivel["semanas_antecedencia_melhor_posicao"].mean())
        for k in k_valores:
            resultado[f"pct_top_{k}_antes"] = float((disponivel["melhor_posicao_antes_do_inicio"] <= k).mean() * 100)
    else:
        resultado["posicao_media_antes"] = None
        resultado["posicao_mediana_antes"] = None
        resultado["antecedencia_media_semanas"] = None
        for k in k_valores:
            resultado[f"pct_top_{k}_antes"] = None
    return resultado
