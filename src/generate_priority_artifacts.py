"""Gera os artefatos de priorização consumidos pelo dashboard — sem treinar.

Uso:
    python -m src.generate_priority_artifacts

Produz três coisas, e nunca treina modelo (o treino é
`python -m src.train_priority_model`, operação separada e controlada):

1. `dashboard/data/historical_priority_backtest.parquet` — o **backtest
   navegável**: para cada semana do período de teste, o ranking completo dos
   bairros no instante `t` e o que efetivamente aconteceu em `t+1..t+3`.
   É o que permite a página experimental mostrar "o que o sistema saberia
   naquele momento" contra "o que aconteceu depois", sem escolher só os
   exemplos bons.
2. `dashboard/data/latest_priority.parquet` — a priorização referente ao
   período **mais recente**, gerada **somente** se o portão de atualidade
   permitir (ver 3). Se não permitir, o arquivo não é escrito e um arquivo
   antigo é removido, para não existir artefato enganoso.
3. `dashboard/data/_priority_status.json` — o estado do portão:
   `current_projection_available`, `reason`, cutoff, versão do modelo e
   metadados de linhagem. A UI é obrigada a respeitar este arquivo.

## Score, não probabilidade

O artefato publica `ranking` (1 = maior prioridade da semana) e
`score_prioridade` (0-100, **posição relativa normalizada dentro da própria
semana**). A probabilidade bruta do modelo **não é publicada**: a validação
estatística mostrou que ela não deve ser comunicada como grau de confiança
absoluto (instabilidade entre anos e heterogeneidade territorial). Ver
`reports/ml/dengue_ranking_evidence_validation.md`.

## Corte temporal e leakage

Cada linha do backtest tem `cutoff_epi_year`/`cutoff_epi_week` iguais à
própria semana `t` da decisão. Nenhuma feature usa dado posterior a esse
corte — garantido pela construção do dataset (`src/ml/features.py`) e
verificado por teste adversarial dedicado.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.freshness import (
    MOTIVO_ARTEFATO_AUSENTE,
    MOTIVO_ARTEFATO_INCOMPATIVEL,
    avaliar_projecao_atual,
    freshness_epidemiologia,
)
from src.logging_config import configurar_logging
from src.ml import models, ranking
from src.ml import split as split_mod
from src.ml.artifacts import (
    ArtefatoAusenteError,
    ArtefatoIncompativelError,
    agora_iso,
    carregar_artefato_modelo,
)
from src.ml.dataset import montar_dataset_onset
from src.train_priority_model import HORIZONTE_ONSET, MODEL_VERSION
from src.utils.io_atomico import escrever_json_atomico, escrever_parquet_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dashboard" / "data"
CAMINHO_GOLD = PASTA_DADOS / "gold_arboviroses_clima_bairro.parquet"
CAMINHO_BACKTEST = PASTA_DADOS / "historical_priority_backtest.parquet"
CAMINHO_LATEST = PASTA_DADOS / "latest_priority.parquet"
CAMINHO_STATUS = PASTA_DADOS / "_priority_status.json"
CAMINHO_EVIDENCIA = PASTA_DADOS / "_evidence_summary.json"
PASTA_RELATORIO_ML = RAIZ / "reports" / "ml"

COLUNAS_BACKTEST = (
    "ano_epidemiologico",
    "semana_epidemiologica",
    "semana_epi_data_inicio",
    "semana_epi_data_fim",
    "codigo_bairro",
    "nome_bairro",
    "codigo_rpa",
    "ranking",
    "score_prioridade",
    "casos_t",
    "casos_proximas_3_semanas",
    "estado_alto_risco_t",
    "razao_limiar_historico",
    "taxa_crescimento_suavizada",
    "onset_real_em_3_semanas",
    "semanas_ate_onset",
    "ranking_baseline_razao_historica",
    "ranking_baseline_crescimento",
    "cutoff_epi_year",
    "cutoff_epi_week",
)

def _score_relativo(probabilidades: pd.Series, grupos: pd.Series) -> pd.Series:
    """0-100 dentro de cada semana: 100 = maior prioridade daquela semana.

    É explicitamente uma **posição relativa normalizada**, não uma
    probabilidade — usar `rank` (e não a probabilidade reescalada) impede
    que o número seja lido como "chance de surto"."""
    postos = probabilidades.groupby(grupos).rank(method="first", ascending=True)
    tamanhos = grupos.map(grupos.value_counts())
    return (100.0 * (postos - 1) / (tamanhos - 1).clip(lower=1)).round(1)

def construir_backtest(
    ctx_teste: pd.DataFrame, probabilidades: pd.Series, y_teste: pd.Series
) -> pd.DataFrame:
    """Uma linha por (bairro, semana) do período de teste, com o ranking do
    instante `t` e o desfecho observado em `t+1..t+3`."""
    df = ctx_teste.copy()
    df["probabilidade"] = probabilidades.to_numpy()
    df["onset_real_em_3_semanas"] = y_teste.to_numpy()

    df["ranking"] = df.groupby("indice_semana_alvo")["probabilidade"].rank(
        method="first", ascending=False
    ).astype(int)
    df["score_prioridade"] = _score_relativo(df["probabilidade"], df["indice_semana_alvo"])
    df["ranking_baseline_razao_historica"] = df.groupby("indice_semana_alvo")[
        "razao_limiar_historico"
    ].rank(method="first", ascending=False).astype(int)
    df["ranking_baseline_crescimento"] = df.groupby("indice_semana_alvo")[
        "taxa_crescimento_suavizada"
    ].rank(method="first", ascending=False).astype(int)

    # Desfecho observado: casos das 3 semanas seguintes do MESMO bairro.
    df = df.sort_values(["codigo_bairro", "indice_semana_global"])
    grupo = df.groupby("codigo_bairro", sort=False)["casos"]
    df["casos_proximas_3_semanas"] = sum(grupo.shift(-h) for h in (1, 2, 3))

    # Distância até o próximo onset dentro da janela (1, 2 ou 3 semanas).
    onset_por_bairro_semana = _mapear_onsets(df)
    df["semanas_ate_onset"] = [
        _distancia_ate_onset(onset_por_bairro_semana, bairro, idx)
        for bairro, idx in zip(df["codigo_bairro"], df["indice_semana_global"])
    ]

    df["cutoff_epi_year"] = df["ano_epidemiologico"]
    df["cutoff_epi_week"] = df["semana_epidemiologica"]
    return df[list(COLUNAS_BACKTEST)].sort_values(
        ["ano_epidemiologico", "semana_epidemiologica", "ranking"]
    ).reset_index(drop=True)

def _mapear_onsets(df: pd.DataFrame) -> dict[str, set[int]]:
    """Semanas em que cada bairro **entrou** em estado de risco elevado
    (transição 0 -> 1) dentro do próprio recorte disponível."""
    mapa: dict[str, set[int]] = {}
    for bairro, sub in df.groupby("codigo_bairro", sort=False):
        sub = sub.sort_values("indice_semana_global")
        estado = sub["estado_alto_risco_t"].to_numpy(dtype=float)
        indices = sub["indice_semana_global"].to_numpy()
        entradas = {
            int(indices[i])
            for i in range(1, len(estado))
            if estado[i] == 1 and estado[i - 1] == 0
        }
        mapa[bairro] = entradas
    return mapa

def _distancia_ate_onset(mapa: dict[str, set[int]], bairro: str, indice: int) -> float:
    for h in (1, 2, 3):
        if (indice + h) in mapa.get(bairro, set()):
            return float(h)
    return float("nan")

def construir_latest_priority(
    backtest: pd.DataFrame, metadados: dict[str, Any], gerado_em: str
) -> pd.DataFrame:
    """Recorte da semana mais recente do backtest, no contrato de
    `latest_priority`. Só é chamado se o portão de atualidade permitir."""
    ultima = backtest.sort_values(["ano_epidemiologico", "semana_epidemiologica"]).iloc[-1]
    recorte = backtest[
        (backtest["ano_epidemiologico"] == ultima["ano_epidemiologico"])
        & (backtest["semana_epidemiologica"] == ultima["semana_epidemiologica"])
    ].copy()
    recorte = recorte.rename(
        columns={
            "ano_epidemiologico": "reference_year",
            "semana_epidemiologica": "reference_week",
            "nome_bairro": "bairro",
            "codigo_rpa": "rpa",
        }
    )
    recorte["forecast_horizon"] = HORIZONTE_ONSET
    recorte["model_version"] = metadados["model_version"]
    recorte["generated_at"] = gerado_em
    recorte["data_cutoff"] = str(ultima["semana_epi_data_fim"])[:10]
    return recorte[
        [
            "reference_year", "reference_week", "forecast_horizon", "bairro", "codigo_bairro",
            "rpa", "score_prioridade", "ranking", "model_version", "generated_at", "data_cutoff",
        ]
    ].sort_values("ranking").reset_index(drop=True)

def resumir_evidencia_validada() -> Optional[dict[str, Any]]:
    """Compacta os artefatos da validação estatística já publicados em
    `reports/ml/` num único JSON dentro de `dashboard/data/`.

    **Não recalcula nada.** É uma cópia resumida, para que o dashboard tenha
    um contrato de dados numa única pasta (`dashboard/data/`) e não dependa
    do layout interno de `reports/`. Se os artefatos não existirem, devolve
    `None` e a página experimental mostra apenas o backtest.
    """
    caminho_resumo = PASTA_RELATORIO_ML / "resultado_evidence_validation_completo.json"
    if not caminho_resumo.exists():
        logger.warning("Evidência validada ausente em %s — página experimental sem seção de desempenho.", caminho_resumo)
        return None

    resumo = json.loads(caminho_resumo.read_text(encoding="utf-8"))
    bloco: dict[str, Any] = {
        "id_candidato": resumo.get("id_candidato"),
        "configuracao": resumo.get("configuracao"),
        "seed": resumo.get("seed"),
        "n_reamostragens": resumo.get("n_reamostragens"),
        "recall_ic": resumo.get("recall_ic"),
        "delta_vs_melhor_baseline": resumo.get("delta_vs_melhor_baseline"),
        "por_ano": resumo.get("por_ano"),
        "leave_one_year_out": resumo.get("leave_one_year_out"),
        "por_rpa": resumo.get("por_rpa"),
        "grandes_episodios": resumo.get("grandes_episodios"),
        "genuino_vs_recaida": resumo.get("genuino_vs_recaida"),
        "lead_time_k10": resumo.get("lead_time_k10"),
        "estabilidade_top10": resumo.get("estabilidade_top10"),
        "carga_operacional": resumo.get("carga_operacional"),
        "bairros_criticos": resumo.get("bairros_criticos"),
        "ipsep": resumo.get("ipsep"),
    }

    caminho_por_bairro = PASTA_RELATORIO_ML / "evidence_por_bairro.csv"
    if caminho_por_bairro.exists():
        bloco["por_bairro"] = pd.read_csv(caminho_por_bairro).to_dict("records")

    caminho_clima = PASTA_RELATORIO_ML / "resultado_clima_experimento.json"
    if caminho_clima.exists():
        clima = json.loads(caminho_clima.read_text(encoding="utf-8"))
        bloco["experimento_clima"] = {
            "conclusao": clima.get("conclusao"),
            "delta": clima.get("delta"),
            "por_ano": clima.get("por_ano"),
            "metricas_dataset": clima.get("metricas_dataset"),
        }
    return bloco

def main() -> int:
    configurar_logging()

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrada.", CAMINHO_GOLD)
        return 1

    gerado_em = agora_iso()
    df_gold = pd.read_parquet(CAMINHO_GOLD)
    gold_schema_version = (
        str(df_gold["versao_schema_gold"].iloc[0]) if "versao_schema_gold" in df_gold.columns else None
    )

    ctx, X, y, _ = montar_dataset_onset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET)

    # ---------------- fail closed: artefato ausente/incompatível ----------------
    try:
        modelo, metadados = carregar_artefato_modelo(
            MODEL_VERSION,
            feature_names_esperadas=list(X.columns),
            gold_schema_version_esperada=gold_schema_version,
        )
    except (ArtefatoAusenteError, ArtefatoIncompativelError) as exc:
        motivo = (
            MOTIVO_ARTEFATO_AUSENTE
            if isinstance(exc, ArtefatoAusenteError)
            else MOTIVO_ARTEFATO_INCOMPATIVEL
        )
        logger.error("Priorização indisponível (%s): %s", motivo, exc)
        escrever_json_atomico(
            CAMINHO_STATUS,
            {
                "gerado_em": gerado_em,
                "current_projection_available": False,
                "backtest_available": False,
                "reason": motivo,
                "detalhe": str(exc),
                "model_version": MODEL_VERSION,
            },
        )
        for caminho in (CAMINHO_LATEST, CAMINHO_BACKTEST):
            if caminho.exists():
                caminho.unlink()
                logger.warning("Artefato removido por incompatibilidade: %s", caminho)
        return 1

    _, _, idx_teste = split_mod.split_temporal(ctx)
    proba_teste = models.prever_probabilidade(modelo, X.loc[idx_teste])
    backtest = construir_backtest(ctx.loc[idx_teste], proba_teste, y.loc[idx_teste])
    escrever_parquet_atomico(CAMINHO_BACKTEST, backtest)
    logger.info(
        "Backtest gravado: %d linhas · %d semanas · %s a %s",
        len(backtest),
        backtest[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0],
        backtest["ano_epidemiologico"].min(), backtest["ano_epidemiologico"].max(),
    )

    # ---------------- portão de atualidade da projeção "atual" ----------------
    fresh_epi = freshness_epidemiologia(df_gold)
    portao = avaliar_projecao_atual(fresh_epi)

    status: dict[str, Any] = {
        "gerado_em": gerado_em,
        "backtest_available": True,
        "backtest_periodo": {
            "ano_inicio": int(backtest["ano_epidemiologico"].min()),
            "ano_fim": int(backtest["ano_epidemiologico"].max()),
            "semanas": int(backtest[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0]),
            "linhas": int(len(backtest)),
        },
        "model_version": metadados["model_version"],
        "feature_schema_version": metadados["feature_schema_version"],
        "trained_until": metadados["trained_until"],
        "target_definition": metadados["target_definition"],
        "horizon": metadados["horizon"],
        "git_commit": metadados["git_commit"],
        "gold_schema_version": metadados["gold_schema_version"],
        "epidemiologia": {
            "semana_epi_maxima": fresh_epi.semana_epi_maxima,
            "data_maxima_evento": fresh_epi.data_maxima_evento,
            "atraso_dias": fresh_epi.atraso_dias,
            "status": fresh_epi.status,
        },
        **portao,
    }

    if portao["current_projection_available"]:
        latest = construir_latest_priority(backtest, metadados, gerado_em)
        escrever_parquet_atomico(CAMINHO_LATEST, latest)
        status["latest_priority_linhas"] = int(len(latest))
        logger.info("latest_priority gravado (%d bairros).", len(latest))
    else:
        if CAMINHO_LATEST.exists():
            CAMINHO_LATEST.unlink()
            logger.warning("latest_priority removido — dados epidemiológicos desatualizados.")
        logger.warning(
            "Priorização do período atual INDISPONÍVEL: %s (%s)",
            portao["reason"], portao["detalhe"],
        )

    evidencia = resumir_evidencia_validada()
    if evidencia is not None:
        escrever_json_atomico(CAMINHO_EVIDENCIA, evidencia)
        status["evidencia_validada_disponivel"] = True
        status["id_candidato_validado"] = evidencia.get("id_candidato")
    else:
        status["evidencia_validada_disponivel"] = False
        if CAMINHO_EVIDENCIA.exists():
            CAMINHO_EVIDENCIA.unlink()
            logger.warning("Resumo de evidência removido (artefato de origem ausente).")

    escrever_json_atomico(CAMINHO_STATUS, status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
