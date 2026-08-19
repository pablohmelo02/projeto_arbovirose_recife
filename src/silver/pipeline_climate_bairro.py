"""Orquestra a Silver do mapeamento `bairro -> estação climática` (Estratégia A).

Lê `silver_bairro_geo`, `silver_estacao_climatica` e todas as partições de
`silver_clima_diario` direto do MinIO (nunca reingesta nada da Bronze),
aplica `src/silver/climate_bairro.py` e grava o mapeamento em Parquet, com
manifest de execução contendo as métricas reais de cobertura/distância.

Não materializa uma tabela "clima por bairro" (isso duplicaria dado de
`silver_clima_diario`) — só o mapeamento em si; a junção conceitual é feita
sob demanda por `climate_bairro.associar_clima_diario_a_bairro`.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import geopandas as gpd
import pandas as pd

from src.clients.minio_client import MinioClient
from src.silver.climate_bairro import montar_mapeamento_bairro_estacao

logger = logging.getLogger(__name__)

CHAVE_BAIRRO_GEO = "silver/recife/territorio/bairro_geo/bairros.parquet"
CHAVE_ESTACOES = "silver/recife/clima/estacoes/estacoes.parquet"
PREFIXO_CLIMA_DIARIO = "silver/recife/clima/diario/"
PREFIXO_SILVER_BAIRRO_ESTACAO = "silver/recife/clima/bairro_estacao"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _carregar_todo_clima_diario(minio_client: MinioClient) -> pd.DataFrame:
    """Concatena todas as partições `ano=<ano>` de `silver_clima_diario` já
    gravadas — a atividade de uma estação (última leitura) só pode ser
    avaliada olhando o histórico completo acumulado, não só o ano corrente.
    """
    chaves = [
        chave
        for chave in minio_client.listar_chaves(PREFIXO_CLIMA_DIARIO)
        if chave.endswith(".parquet")
    ]
    if not chaves:
        return pd.DataFrame()

    dfs = [pd.read_parquet(io.BytesIO(minio_client.download_bytes(chave))) for chave in chaves]
    return pd.concat(dfs, ignore_index=True)


def executar_transformacao_silver_climate_bairro(minio_client: MinioClient) -> dict[str, Any]:
    """Executa uma rodada completa do mapeamento Silver bairro-estação e
    retorna o manifest."""
    run_id = _gerar_run_id()
    logger.info("Iniciando mapeamento Silver bairro-estacao (run_id=%s)", run_id)

    minio_client.garantir_bucket()

    gdf_bairros = gpd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_BAIRRO_GEO)))
    df_estacoes = pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_ESTACOES)))
    df_clima_diario = _carregar_todo_clima_diario(minio_client)

    df_mapeamento, metricas = montar_mapeamento_bairro_estacao(
        gdf_bairros, df_estacoes, df_clima_diario
    )

    chave_mapeamento = f"{PREFIXO_SILVER_BAIRRO_ESTACAO}/bairro_estacao.parquet"
    buffer = io.BytesIO()
    df_mapeamento.to_parquet(buffer, engine="pyarrow", index=False)
    minio_client.upload_bytes(
        chave_mapeamento, buffer.getvalue(), content_type="application/octet-stream"
    )
    logger.info(
        "Mapeamento bairro-estacao salvo: s3://%s/%s (%d linhas)",
        minio_client.bucket, chave_mapeamento, len(df_mapeamento),
    )

    manifest = {
        "run_id": run_id,
        "dominio": "clima_bairro",
        "processado_em": datetime.now(timezone.utc).isoformat(),
        "metricas": metricas,
    }
    chave_manifest = (
        f"{PREFIXO_SILVER_BAIRRO_ESTACAO}/_controle/manifest_silver_clima_bairro_{run_id}.json"
    )
    minio_client.upload_manifest(chave_manifest, manifest)
    logger.info("Manifest salvo em s3://%s/%s", minio_client.bucket, chave_manifest)

    logger.info(
        "Mapeamento bairro-estacao finalizado: %d/%d bairros associados (%.2f%%)",
        metricas["bairros_associados"], metricas["total_bairros"], metricas["percentual_cobertura"],
    )
    return manifest
