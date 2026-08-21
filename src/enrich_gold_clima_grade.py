"""Enriquece a Gold com as colunas climáticas em **grade** (reanálise).

Uso:
    python -m src.enrich_gold_clima_grade                  # Gold publicada + Silver local
    python -m src.enrich_gold_clima_grade --origem minio   # Gold e Silver no Data Lake

## Por que isto é uma etapa da camada Gold, e não um pipeline paralelo

É uma transformação **da camada Gold sobre a própria camada Gold**: mesma
tabela, mesmo grão, mesma chave, mesmas linhas. Ela apenas (re)calcula um
bloco de colunas derivado de uma Silver que antes não existia, usando
exatamente a mesma função (`src/gold/clima_grade.py::calcular_features_clima_grade`)
que o pipeline completo da Gold usa. Nenhuma linha epidemiológica é
adicionada, removida ou alterada — verificado por portão de qualidade a
cada execução.

## Idempotência

As colunas em grade são recalculadas do zero a cada execução (nunca
atualizadas em cima do valor anterior). Rodar duas vezes produz a mesma
tabela, exceto `_processed_at`/`_grade_processed_at`, que são metadados de
execução. Testado.

## Ausência continua sendo ausência

Nenhum `fillna(0)`. Uma semana sem dia válido na grade fica `None` nas
colunas de valor e `0` nos contadores de dias válidos, exatamente como já
acontece na família de colunas de estação.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.gold.clima_grade import COLUNAS_GOLD_CLIMA_GRADE, calcular_features_clima_grade
from src.logging_config import configurar_logging
from src.quality_gates import (
    QualityGateError,
    achados_para_dict,
    exigir_aprovacao,
    validar_gold,
)
from src.silver.pipeline_climate_grade import (
    carregar_silver_grade_local,
    carregar_silver_grade_minio,
)
from src.silver.schema_climate_grade import (
    GRADE_PRECIPITACAO,
    GRADE_TEMPERATURA,
    RESOLUCAO_GRAUS_POR_GRADE,
    VERSAO_SCHEMA_CLIMA_GRADE,
)
from src.utils.io_atomico import escrever_json_atomico, escrever_parquet_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD_PUBLICADA = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
CAMINHO_MANIFEST_GRADE = RAIZ / "dashboard" / "data" / "_gold_clima_grade.json"
CHAVE_GOLD_MINIO = "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"

#: Versão da Gold depois de incorporar o bloco climático em grade. A Gold
#: 1.0 (só estação) continua sendo um estado válido e reproduzível — esta
#: é uma versão nova, não uma correção da anterior.
VERSAO_SCHEMA_GOLD_COM_GRADE = "1.1"

COLUNAS_CHAVE_E_EPIDEMIOLOGICAS = (
    "codigo_bairro", "nome_bairro", "agravo", "ano_epidemiologico",
    "semana_epidemiologica", "semana_epi_data_inicio", "semana_epi_data_fim", "casos",
)

def enriquecer_gold_com_grade(
    df_gold: pd.DataFrame,
    df_grade_diario: pd.DataFrame,
    df_bairro_celula: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recalcula as colunas em grade sobre `df_gold` e devolve
    `(gold_enriquecida, metricas)`.

    O cálculo é feito no grão `bairro × semana` (o clima é o mesmo para os
    três agravos da mesma semana no mesmo bairro) e depois propagado para as
    linhas por agravo — evita repetir o mesmo `rolling` três vezes e garante
    por construção que os três agravos recebem valores idênticos.
    """
    antes = {
        "linhas": len(df_gold),
        "casos_totais": int(df_gold["casos"].sum()),
        "bairros": int(df_gold["codigo_bairro"].nunique()),
        "agravos": int(df_gold["agravo"].nunique()),
        "semanas": int(df_gold[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0]),
    }

    # Remove um bloco em grade pré-existente (idempotência: recalcula, nunca acumula).
    df_base = df_gold.drop(columns=[c for c in COLUNAS_GOLD_CLIMA_GRADE if c in df_gold.columns])

    chave_semana = ["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]
    grao_semana = (
        df_base[chave_semana + ["semana_epi_data_inicio", "semana_epi_data_fim"]]
        .drop_duplicates(subset=chave_semana)
        .reset_index(drop=True)
    )
    grao_com_grade, metricas = calcular_features_clima_grade(
        grao_semana, df_bairro_celula, df_grade_diario
    )

    colunas_para_juntar = chave_semana + list(COLUNAS_GOLD_CLIMA_GRADE)
    df_final = df_base.merge(
        grao_com_grade[colunas_para_juntar], on=chave_semana, how="left", validate="many_to_one"
    )

    if len(df_final) != antes["linhas"]:
        raise ValueError(
            f"enriquecimento alterou a cardinalidade da Gold: {antes['linhas']} -> {len(df_final)}"
        )
    if int(df_final["casos"].sum()) != antes["casos_totais"]:
        raise ValueError("enriquecimento alterou o total de casos da Gold")

    df_final["versao_schema_gold"] = VERSAO_SCHEMA_GOLD_COM_GRADE
    df_final["_grade_processed_at"] = datetime.now(timezone.utc).isoformat()

    metricas["cardinalidade_preservada"] = True
    metricas["antes"] = antes
    metricas["colunas_adicionadas"] = list(COLUNAS_GOLD_CLIMA_GRADE)
    metricas["resolucao_graus"] = {
        GRADE_PRECIPITACAO: RESOLUCAO_GRAUS_POR_GRADE[GRADE_PRECIPITACAO],
        GRADE_TEMPERATURA: RESOLUCAO_GRAUS_POR_GRADE[GRADE_TEMPERATURA],
    }
    metricas["versao_schema_clima_grade"] = VERSAO_SCHEMA_CLIMA_GRADE
    metricas["versao_schema_gold"] = VERSAO_SCHEMA_GOLD_COM_GRADE
    return df_final, metricas

def _cobertura_por_ano(df: pd.DataFrame) -> list[dict[str, Any]]:
    tem_grade = df["dias_validos_precipitacao_grade_semana"].fillna(0) > 0
    tem_estacao = df["dias_com_dado_valido_semana"].fillna(0) > 0
    resumo = (
        df.assign(_grade=tem_grade, _estacao=tem_estacao)
        .groupby("ano_epidemiologico", observed=True)
        .agg(linhas=("casos", "size"), com_grade=("_grade", "sum"), com_estacao=("_estacao", "sum"))
        .reset_index()
    )
    resumo["pct_com_grade"] = (100 * resumo["com_grade"] / resumo["linhas"]).round(2)
    resumo["pct_com_estacao"] = (100 * resumo["com_estacao"] / resumo["linhas"]).round(2)
    return resumo.to_dict("records")

def main(argv: list[str] | None = None) -> int:
    configurar_logging()
    parser = argparse.ArgumentParser(description="Adiciona o bloco climático em grade à Gold.")
    parser.add_argument("--origem", choices=("local", "minio"), default="local")
    args = parser.parse_args(argv)

    try:
        if args.origem == "minio":
            from src.clients.minio_client import MinioClient
            from src.config import load_config

            config = load_config()
            minio_client = MinioClient(
                endpoint=config.minio_endpoint, access_key=config.minio_access_key,
                secret_key=config.minio_secret_key, bucket=config.minio_bucket,
            )
            df_gold = pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_GOLD_MINIO)))
            df_grade_diario, df_bairro_celula = carregar_silver_grade_minio(minio_client)
        else:
            if not CAMINHO_GOLD_PUBLICADA.exists():
                logger.error("'%s' não encontrada.", CAMINHO_GOLD_PUBLICADA)
                return 1
            df_gold = pd.read_parquet(CAMINHO_GOLD_PUBLICADA)
            df_grade_diario, df_bairro_celula = carregar_silver_grade_local()
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Não foi possível carregar as entradas: %s", exc)
        return 1

    logger.info(
        "Gold: %d linhas · Silver em grade: %d dias-célula · mapeamento: %d linhas",
        len(df_gold), len(df_grade_diario), len(df_bairro_celula),
    )

    df_enriquecida, metricas = enriquecer_gold_com_grade(df_gold, df_grade_diario, df_bairro_celula)

    codigos_territorio = sorted(df_bairro_celula["codigo_bairro"].unique().tolist())
    achados = validar_gold(
        df_enriquecida,
        codigos_bairro_territorio=codigos_territorio,
        colunas_obrigatorias=COLUNAS_CHAVE_E_EPIDEMIOLOGICAS + COLUNAS_GOLD_CLIMA_GRADE,
    )
    try:
        avisos = exigir_aprovacao(achados, contexto="gold+clima_grade")
    except QualityGateError as exc:
        logger.error("Publicação abortada — artefato anterior preservado. %s", exc)
        return 1

    metricas["cobertura_por_ano"] = _cobertura_por_ano(df_enriquecida)
    metricas["avisos_qualidade"] = achados_para_dict(avisos)

    if args.origem == "minio":
        buffer = io.BytesIO()
        df_enriquecida.to_parquet(buffer, engine="pyarrow", index=False)
        minio_client.upload_bytes(CHAVE_GOLD_MINIO, buffer.getvalue())
        logger.info("Gold enriquecida gravada no Data Lake: %s", CHAVE_GOLD_MINIO)
    else:
        escrever_parquet_atomico(CAMINHO_GOLD_PUBLICADA, df_enriquecida)
        escrever_json_atomico(CAMINHO_MANIFEST_GRADE, metricas)

    print(json.dumps(metricas, ensure_ascii=False, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
