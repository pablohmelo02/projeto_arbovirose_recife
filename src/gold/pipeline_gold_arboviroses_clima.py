"""Orquestra a Gold `gold_arboviroses_clima_bairro`.

Lê Silver de arboviroses (todos os anos), território (`silver_bairro_geo`),
mapeamento bairro-estação (Estratégia A, `silver_bairro_estacao`) e todas as
partições de `silver_clima_diario` — todas direto do MinIO — aplica
`src/gold/arboviroses_clima.py`, e grava o resultado em Parquet com um
manifest de execução contendo as métricas reais de cardinalidade/cobertura
(nunca inventadas). Não faz nenhuma transformação de negócio aqui — só
I/O e orquestração (ver `arboviroses_clima.py` para a lógica).
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import geopandas as gpd
import pandas as pd

from src.clients.minio_client import MinioClient, MinioClientError
from src.gold.arboviroses_clima import montar_gold_arboviroses_clima

logger = logging.getLogger(__name__)

CHAVE_BAIRRO_GEO = "silver/recife/territorio/bairro_geo/bairros.parquet"
CHAVE_BAIRRO_ESTACAO = "silver/recife/clima/bairro_estacao/bairro_estacao.parquet"
PREFIXO_ARBOVIROSES_FATOS = "silver/recife/arboviroses/fatos/arboviroses/"
PREFIXO_CLIMA_DIARIO = "silver/recife/clima/diario/"
PREFIXO_GOLD_ARBOVIROSES_CLIMA = "gold/recife/arboviroses_clima"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ler_parquet(minio_client: MinioClient, chave: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(minio_client.download_bytes(chave)))


def _ler_todas_particoes(minio_client: MinioClient, prefixo: str) -> pd.DataFrame:
    chaves = [c for c in minio_client.listar_chaves(prefixo) if c.endswith(".parquet")]
    if not chaves:
        return pd.DataFrame()
    return pd.concat([_ler_parquet(minio_client, c) for c in chaves], ignore_index=True)


def executar_transformacao_gold_arboviroses_clima(minio_client: MinioClient) -> dict[str, Any]:
    """Executa uma rodada completa da Gold arboviroses+clima+território e
    retorna o manifest com as métricas reais desta execução."""
    run_id = _gerar_run_id()
    logger.info("Iniciando Gold arboviroses+clima (run_id=%s)", run_id)

    minio_client.garantir_bucket()

    df_arboviroses = _ler_todas_particoes(minio_client, PREFIXO_ARBOVIROSES_FATOS)
    if df_arboviroses.empty:
        raise ValueError(
            "Nenhum dado de arboviroses encontrado na Silver. "
            "Rode 'python -m src.ingest' + 'python -m src.transform' antes da Gold."
        )

    gdf_bairros = gpd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_BAIRRO_GEO)))

    try:
        df_bairro_estacao = _ler_parquet(minio_client, CHAVE_BAIRRO_ESTACAO)
    except MinioClientError:
        logger.warning(
            "silver_bairro_estacao ausente — Gold será gerada sem nenhuma feature climática "
            "(rode 'python -m src.transform_climate_bairro' para habilitar)"
        )
        df_bairro_estacao = pd.DataFrame(columns=["codigo_bairro", "codigo_estacao", "fonte", "distancia_km", "metodo_associacao"])

    df_clima_diario = _ler_todas_particoes(minio_client, PREFIXO_CLIMA_DIARIO)

    df_gold, metricas = montar_gold_arboviroses_clima(
        df_arboviroses, gdf_bairros, df_bairro_estacao, df_clima_diario
    )

    chave_gold = f"{PREFIXO_GOLD_ARBOVIROSES_CLIMA}/gold_arboviroses_clima_bairro.parquet"
    buffer = io.BytesIO()
    df_gold.to_parquet(buffer, engine="pyarrow", index=False)
    minio_client.upload_bytes(chave_gold, buffer.getvalue(), content_type="application/octet-stream")
    logger.info(
        "Gold arboviroses+clima salva: s3://%s/%s (%d linhas)",
        minio_client.bucket, chave_gold, len(df_gold),
    )

    manifest = {
        "run_id": run_id,
        "dominio": "gold_arboviroses_clima",
        "processado_em": datetime.now(timezone.utc).isoformat(),
        "metricas": metricas,
    }
    chave_manifest = f"{PREFIXO_GOLD_ARBOVIROSES_CLIMA}/_controle/manifest_gold_arboviroses_clima_{run_id}.json"
    minio_client.upload_manifest(chave_manifest, manifest)
    logger.info("Manifest salvo em s3://%s/%s", minio_client.bucket, chave_manifest)

    logger.info(
        "Gold finalizada: %d linhas, %d bairros, agravos=%s, %.4f%% com clima real",
        metricas["total_linhas_gold"],
        metricas["grao_completo"]["total_bairros"],
        metricas["grao_completo"]["total_agravos"],
        metricas["features_climaticas"]["percentual_linhas_com_clima_real"],
    )
    return manifest
