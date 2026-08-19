"""Orquestra a transformação Silver do domínio Território.

Lê a última ingestão válida do recurso de bairros direto da Bronze/MinIO
(via `src.profiling.territory_profiler`, nunca baixa do CKAN de novo),
aplica `territorio.transformar_bairro_geo` e grava GeoParquet no MinIO, com
manifest de execução e área de rejeitados — no mesmo espírito de
rastreabilidade da Silver de arboviroses.

Este domínio é mantido independente da Silver de arboviroses nesta etapa:
nenhum join com `silver_arboviroses` é feito aqui (fica para a Gold).
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import geopandas as gpd

from src.clients.minio_client import MinioClient
from src.profiling.territory_profiler import selecionar_ultima_ingestao_valida_territorio
from src.silver.territorio import transformar_bairro_geo

logger = logging.getLogger(__name__)

PREFIXO_SILVER_TERRITORIO = "silver/recife/territorio"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _gdf_para_parquet_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    buffer = io.BytesIO()
    gdf.to_parquet(buffer)
    return buffer.getvalue()


def executar_transformacao_silver_territorio(minio_client: MinioClient) -> dict[str, Any]:
    """Executa uma rodada completa da transformação Silver território e retorna o manifest."""
    run_id = _gerar_run_id()
    logger.info("Iniciando transformação Silver território (run_id=%s)", run_id)

    recursos = selecionar_ultima_ingestao_valida_territorio(minio_client)
    if not recursos:
        raise ValueError(
            "Nenhum recurso SUCCESS encontrado nos manifests de território. "
            "Rode 'python -m src.ingest_territorio' antes da Silver território."
        )

    minio_client.garantir_bucket()

    metricas_por_recurso: list[dict[str, Any]] = []
    total_validas = 0
    total_rejeitadas = 0

    for entrada in recursos.values():
        if entrada.get("entidade") != "bairro":
            continue

        resource_id = entrada["resource_id"]
        conteudo = minio_client.download_bytes(entrada["object_key"])
        gdf_bruto = gpd.read_file(io.BytesIO(conteudo))

        gdf_valido, gdf_rejeitado, metricas = transformar_bairro_geo(
            gdf_bruto=gdf_bruto,
            resource_id=resource_id,
            ingestion_run_id=entrada.get("_manifest_run_id") or "",
        )
        metricas["resource_id"] = resource_id
        metricas_por_recurso.append(metricas)
        total_validas += metricas["linhas_validas"]
        total_rejeitadas += metricas["linhas_rejeitadas"]

        logger.info(
            "bairro_geo: %d lidas, %d validas, %d rejeitadas (CRS %s -> %s)",
            metricas["linhas_lidas"], metricas["linhas_validas"], metricas["linhas_rejeitadas"],
            metricas["crs_original_detectado"], metricas["crs_armazenamento"],
        )

        if not gdf_valido.empty:
            chave = f"{PREFIXO_SILVER_TERRITORIO}/bairro_geo/bairros.parquet"
            minio_client.upload_bytes(
                chave, _gdf_para_parquet_bytes(gdf_valido), content_type="application/octet-stream"
            )
            logger.info("Silver território salva: s3://%s/%s (%d linhas)", minio_client.bucket, chave, len(gdf_valido))

        if not gdf_rejeitado.empty:
            chave_rejeitados = f"{PREFIXO_SILVER_TERRITORIO}/_rejected/rejeitados_{run_id}.parquet"
            minio_client.upload_bytes(
                chave_rejeitados,
                _gdf_para_parquet_bytes(gdf_rejeitado),
                content_type="application/octet-stream",
            )
            logger.info(
                "Rejeitados território salvos: s3://%s/%s (%d linhas)",
                minio_client.bucket, chave_rejeitados, len(gdf_rejeitado),
            )

    manifest = {
        "run_id": run_id,
        "dominio": "territorio",
        "processado_em": datetime.now(timezone.utc).isoformat(),
        "metricas_por_recurso": metricas_por_recurso,
        "total_linhas_validas": total_validas,
        "total_linhas_rejeitadas": total_rejeitadas,
    }

    chave_manifest = f"{PREFIXO_SILVER_TERRITORIO}/_controle/manifest_silver_territorio_{run_id}.json"
    minio_client.upload_manifest(chave_manifest, manifest)
    logger.info("Manifest Silver território salvo em s3://%s/%s", minio_client.bucket, chave_manifest)

    logger.info("Transformação Silver território finalizada")
    logger.info("Válidas: %d | Rejeitadas: %d", total_validas, total_rejeitadas)

    return manifest
