"""Gera os relatórios do mapeamento Silver `bairro -> estação climática`.

Lê o mapeamento já persistido em `silver/recife/clima/bairro_estacao/` (rode
`python -m src.transform_climate_bairro` antes) e grava CSV/JSON em
`reports/climate_neighborhood_mapping/` com os números reais de cobertura e
distância — não recalcula nada, só formata o que o pipeline Silver produziu.

Uso:
    python -m src.analyze_climate_neighborhood_mapping
"""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.ingestion.bronze_validation import carregar_manifest
from src.silver.pipeline_climate_bairro import PREFIXO_SILVER_BAIRRO_ESTACAO

PASTA_RELATORIOS = Path("reports") / "climate_neighborhood_mapping"


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
    )


def _carregar_ultimo_manifest(minio_client: MinioClient) -> dict:
    prefixo = f"{PREFIXO_SILVER_BAIRRO_ESTACAO}/_controle/manifest_silver_clima_bairro_"
    chaves = sorted(minio_client.listar_chaves(f"{PREFIXO_SILVER_BAIRRO_ESTACAO}/_controle/"))
    chaves_manifest = [c for c in chaves if c.startswith(prefixo)]
    if not chaves_manifest:
        raise MinioClientError(
            "Nenhum manifest do mapeamento bairro-estacao encontrado. "
            "Rode 'python -m src.transform_climate_bairro' antes."
        )
    return carregar_manifest(minio_client, chaves_manifest[-1])


def main() -> int:
    _configurar_logging()
    logger = logging.getLogger(__name__)

    try:
        config = load_config()
    except RuntimeError as exc:
        logger.error("Erro de configuração: %s", exc)
        return 1

    minio_client = MinioClient(
        endpoint=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket=config.minio_bucket,
    )

    try:
        conteudo_mapeamento = minio_client.download_bytes(
            f"{PREFIXO_SILVER_BAIRRO_ESTACAO}/bairro_estacao.parquet"
        )
        manifest = _carregar_ultimo_manifest(minio_client)
    except MinioClientError as exc:
        logger.error("%s", exc)
        return 1

    df_mapeamento = pd.read_parquet(io.BytesIO(conteudo_mapeamento))
    metricas = manifest["metricas"]

    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)

    df_mapeamento.to_csv(
        PASTA_RELATORIOS / "bairro_estacao_mapping.csv", index=False, encoding="utf-8"
    )

    (PASTA_RELATORIOS / "summary.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    logger.info("Relatórios salvos em %s", PASTA_RELATORIOS.resolve())
    logger.info(
        "Cobertura: %d/%d bairros (%.2f%%) | estações distintas usadas: %d",
        metricas["bairros_associados"], metricas["total_bairros"], metricas["percentual_cobertura"],
        metricas["estacoes_distintas_utilizadas"],
    )
    logger.info(
        "Distância (km) — média: %.3f | mediana: %.3f | p90: %.3f | p95: %.3f | max: %.3f | min: %.3f",
        metricas["distancia_km_media"], metricas["distancia_km_mediana"], metricas["distancia_km_p90"],
        metricas["distancia_km_p95"], metricas["distancia_km_maxima"], metricas["distancia_km_minima"],
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
