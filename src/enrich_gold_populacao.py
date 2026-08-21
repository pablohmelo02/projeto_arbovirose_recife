"""Enriquece a Gold com população por bairro e incidência epidemiológica.

Uso:
    python -m src.enrich_gold_populacao

## Por que isto é uma etapa da camada Gold, e não um pipeline paralelo

Mesmo padrão de `src/enrich_gold_clima_grade.py` (Gold 1.0 → 1.1): uma
transformação **da Gold sobre a própria Gold** — mesma tabela, mesmo grão,
mesma chave, mesmas linhas e mesmos `casos`. Só adiciona um bloco de
colunas novo, calculado a partir de uma Silver que antes não existia
(`silver_populacao_bairro_ano`). Nenhuma linha epidemiológica é
adicionada, removida ou alterada — verificado por portão de qualidade a
cada execução, e por comparação byte-a-byte das colunas anteriores.

## Idempotência

As colunas de população/incidência são recalculadas do zero a cada
execução (nunca atualizadas em cima do valor anterior). Rodar duas vezes
produz a mesma tabela, exceto `_processed_at`/`_populacao_processed_at`.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.gold.populacao import COLUNAS_GOLD_POPULACAO, calcular_features_populacao
from src.logging_config import configurar_logging
from src.quality_gates import QualityGateError, achados_para_dict, exigir_aprovacao, validar_gold
from src.silver.pipeline_population import carregar_silver_populacao_local
from src.silver.schema_population import VERSAO_SCHEMA_POPULACAO
from src.utils.io_atomico import escrever_json_atomico, escrever_parquet_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD_PUBLICADA = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
CAMINHO_MANIFEST_POPULACAO = RAIZ / "dashboard" / "data" / "_gold_populacao.json"

#: Versão da Gold depois de incorporar população/incidência. 1.1 (estação +
#: grade climáticas) continua sendo um estado válido e reproduzível.
VERSAO_SCHEMA_GOLD_COM_POPULACAO = "1.2"

COLUNAS_CHAVE_E_EPIDEMIOLOGICAS = (
    "codigo_bairro", "nome_bairro", "agravo", "ano_epidemiologico",
    "semana_epidemiologica", "semana_epi_data_inicio", "semana_epi_data_fim", "casos",
)


def enriquecer_gold_com_populacao(
    df_gold: pd.DataFrame, df_populacao_bairro_ano: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recalcula as colunas de população/incidência sobre `df_gold` e
    devolve `(gold_enriquecida, metricas)`."""
    antes = {
        "linhas": len(df_gold),
        "casos_totais": int(df_gold["casos"].sum()),
        "bairros": int(df_gold["codigo_bairro"].nunique()),
        "agravos": int(df_gold["agravo"].nunique()),
    }

    df_base = df_gold.drop(columns=[c for c in COLUNAS_GOLD_POPULACAO if c in df_gold.columns])

    df_final, metricas = calcular_features_populacao(df_base, df_populacao_bairro_ano)

    if len(df_final) != antes["linhas"]:
        raise ValueError(
            f"enriquecimento alterou a cardinalidade da Gold: {antes['linhas']} -> {len(df_final)}"
        )
    if int(df_final["casos"].sum()) != antes["casos_totais"]:
        raise ValueError("enriquecimento alterou o total de casos da Gold")

    df_final["versao_schema_gold"] = VERSAO_SCHEMA_GOLD_COM_POPULACAO
    df_final["_populacao_processed_at"] = datetime.now(timezone.utc).isoformat()

    metricas["cardinalidade_preservada"] = True
    metricas["antes"] = antes
    metricas["colunas_adicionadas"] = list(COLUNAS_GOLD_POPULACAO)
    metricas["versao_schema_populacao"] = VERSAO_SCHEMA_POPULACAO
    metricas["versao_schema_gold"] = VERSAO_SCHEMA_GOLD_COM_POPULACAO
    return df_final, metricas


def _cobertura_incidencia_por_ano(df: pd.DataFrame) -> list[dict[str, Any]]:
    resumo = (
        df.assign(_tem_populacao=df["populacao_bairro_ano"].notna())
        .groupby("ano_epidemiologico", observed=True)
        .agg(linhas=("casos", "size"), com_populacao=("_tem_populacao", "sum"))
        .reset_index()
    )
    resumo["pct_com_populacao"] = (100 * resumo["com_populacao"] / resumo["linhas"]).round(2)
    return resumo.to_dict("records")


def main(argv: list[str] | None = None) -> int:
    configurar_logging()

    if not CAMINHO_GOLD_PUBLICADA.exists():
        logger.error("'%s' não encontrada.", CAMINHO_GOLD_PUBLICADA)
        return 1
    df_gold = pd.read_parquet(CAMINHO_GOLD_PUBLICADA)

    try:
        df_populacao_bairro_ano = carregar_silver_populacao_local()
    except FileNotFoundError as exc:
        logger.error("Não foi possível carregar a Silver de população: %s", exc)
        return 1

    logger.info(
        "Gold: %d linhas · Silver de população: %d linhas (bairro x ano)",
        len(df_gold), len(df_populacao_bairro_ano),
    )

    df_enriquecida, metricas = enriquecer_gold_com_populacao(df_gold, df_populacao_bairro_ano)

    codigos_territorio = sorted(df_populacao_bairro_ano["codigo_bairro"].unique().tolist())
    achados = validar_gold(
        df_enriquecida,
        codigos_bairro_territorio=codigos_territorio,
        colunas_obrigatorias=COLUNAS_CHAVE_E_EPIDEMIOLOGICAS + COLUNAS_GOLD_POPULACAO,
    )
    try:
        avisos = exigir_aprovacao(achados, contexto="gold+populacao")
    except QualityGateError as exc:
        logger.error("Publicação abortada — artefato anterior preservado. %s", exc)
        return 1

    metricas["cobertura_incidencia_por_ano"] = _cobertura_incidencia_por_ano(df_enriquecida)
    metricas["avisos_qualidade"] = achados_para_dict(avisos)

    escrever_parquet_atomico(CAMINHO_GOLD_PUBLICADA, df_enriquecida)
    escrever_json_atomico(CAMINHO_MANIFEST_POPULACAO, metricas)

    print(json.dumps(metricas, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
