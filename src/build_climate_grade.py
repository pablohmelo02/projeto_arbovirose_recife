"""Constrói a camada climática em grade (reanálise): ingestão → Silver.

Uso:
    python -m src.build_climate_grade                     # destino canônico (MinIO)
    python -m src.build_climate_grade --destino local     # ambiente sem MinIO
    python -m src.build_climate_grade --inicio 2013-01-01 --fim 2025-12-31

O intervalo padrão é derivado do **período epidemiológico realmente
presente na Gold publicada** — nunca de datas fixas no código (regra de
freshness do produto: nada de data hardcoded em texto ou lógica). Com
`--destino minio`, os centroides dos bairros vêm de `silver_bairro_geo`;
com `--destino local`, vêm das colunas `centroide_lat`/`centroide_lon` da
própria Gold publicada (são o mesmo dado, calculado uma única vez pela
camada de território em CRS métrico).
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from src.clients.gridded_climate_client import (
    GriddedClimateClientError,
    OpenMeteoArchiveClient,
)
from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.ingestion.gridded_climate_ingestion import (
    GRADES_CONFIGURADAS,
    JANELA_SONDAGEM_DIAS,
    executar_ingestao_clima_grade,
    sondar_celulas,
)
from src.logging_config import configurar_logging
from src.silver.pipeline_climate_grade import (
    executar_transformacao_silver_grade_local,
    executar_transformacao_silver_grade_minio,
)

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD_PUBLICADA = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
CHAVE_BAIRRO_GEO = "silver/recife/territorio/bairro_geo/bairros.parquet"

def _centroides_da_gold_publicada() -> pd.DataFrame:
    if not CAMINHO_GOLD_PUBLICADA.exists():
        raise FileNotFoundError(
            f"'{CAMINHO_GOLD_PUBLICADA}' não encontrada — rode "
            "'python -m src.export_dashboard_dataset' ou use --destino minio."
        )
    df = pd.read_parquet(
        CAMINHO_GOLD_PUBLICADA,
        columns=[
            "codigo_bairro", "nome_bairro", "centroide_lat", "centroide_lon",
            "semana_epi_data_inicio", "semana_epi_data_fim",
        ],
    )
    return df

def _intervalo_epidemiologico(df_gold: pd.DataFrame) -> tuple[str, str]:
    inicio = pd.Timestamp(df_gold["semana_epi_data_inicio"].min()).date()
    fim = pd.Timestamp(df_gold["semana_epi_data_fim"].max()).date()
    return str(inicio), str(fim)

def _data_mais_dias(data_iso: str, dias: int) -> str:
    from datetime import date, timedelta

    ano, mes, dia = (int(p) for p in data_iso.split("-"))
    return str(date(ano, mes, dia) + timedelta(days=dias))

def executar_local(cliente: OpenMeteoArchiveClient, inicio: str, fim: str) -> dict[str, Any]:
    """Ingestão + Silver sem MinIO: os payloads brutos são mantidos em
    memória entre as duas etapas (é a mesma execução), e só a Silver é
    persistida — o `run_id`/Bronze versionada só existe no destino
    canônico, e isso é declarado no manifest local (`destino: local`)."""
    df_gold = _centroides_da_gold_publicada()
    centroides_df = (
        df_gold[["codigo_bairro", "nome_bairro", "centroide_lat", "centroide_lon"]]
        .drop_duplicates("codigo_bairro")
        .reset_index(drop=True)
    )
    centroides = [
        (str(r["codigo_bairro"]), float(r["centroide_lat"]), float(r["centroide_lon"]))
        for _, r in centroides_df.iterrows()
    ]
    logger.info("Centroides carregados da Gold publicada: %d bairros", len(centroides))

    payloads: dict[str, bytes] = {}
    mapa: dict[tuple[str, str], str] = {}
    for grade, modelo, variaveis in GRADES_CONFIGURADAS:
        mapa_grade = sondar_celulas(
            cliente, centroides, modelo, variaveis,
            inicio, _data_mais_dias(inicio, JANELA_SONDAGEM_DIAS - 1),
        )
        for codigo, celula in mapa_grade.items():
            mapa[(codigo, grade)] = celula
        celulas = sorted(set(mapa_grade.values()))
        logger.info("Grade %s (%s): %d célula(s) distinta(s)", grade, modelo, len(celulas))
        pontos = [tuple(map(float, c.split("_"))) for c in celulas]
        payloads[grade] = cliente.baixar_series_diarias(pontos, inicio, fim, variaveis, modelo)

    return executar_transformacao_silver_grade_local(payloads, mapa, centroides_df)

def executar_minio(cliente: OpenMeteoArchiveClient, inicio: str | None, fim: str | None) -> dict[str, Any]:
    config = load_config()
    minio_client = MinioClient(
        endpoint=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket=config.minio_bucket,
    )
    gdf = pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_BAIRRO_GEO)))
    centroides_df = gdf[["codigo_bairro", "nome_bairro", "centroide_lat", "centroide_lon"]].drop_duplicates()
    centroides = [
        (str(r["codigo_bairro"]), float(r["centroide_lat"]), float(r["centroide_lon"]))
        for _, r in centroides_df.iterrows()
    ]
    if inicio is None or fim is None:
        raise ValueError("com --destino minio, informe --inicio e --fim explicitamente")

    manifest_bronze = executar_ingestao_clima_grade(cliente, minio_client, centroides, inicio, fim)
    if manifest_bronze["erros"]:
        logger.error("Ingestão em grade terminou com %d erro(s) — Silver não gerada", manifest_bronze["erros"])
        return manifest_bronze
    return executar_transformacao_silver_grade_minio(minio_client, centroides_df)

def main(argv: list[str] | None = None) -> int:
    configurar_logging()
    parser = argparse.ArgumentParser(description="Constrói a camada climática em grade (reanálise).")
    parser.add_argument("--destino", choices=("minio", "local"), default="minio")
    parser.add_argument("--inicio", default=None, help="AAAA-MM-DD (default: início da Gold publicada)")
    parser.add_argument("--fim", default=None, help="AAAA-MM-DD (default: fim da Gold publicada)")
    args = parser.parse_args(argv)

    cliente = OpenMeteoArchiveClient()
    try:
        if args.destino == "local":
            df_gold = _centroides_da_gold_publicada()
            inicio_padrao, fim_padrao = _intervalo_epidemiologico(df_gold)
            inicio = args.inicio or inicio_padrao
            fim = args.fim or fim_padrao
            logger.info("Janela: %s -> %s (destino local)", inicio, fim)
            manifest = executar_local(cliente, inicio, fim)
        else:
            manifest = executar_minio(cliente, args.inicio, args.fim)
    except (GriddedClimateClientError, MinioClientError, FileNotFoundError, RuntimeError, ValueError) as exc:
        logger.error("Falha ao construir a camada em grade: %s", exc)
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
