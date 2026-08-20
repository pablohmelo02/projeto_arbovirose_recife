"""Ponto de entrada da Gold `gold_arboviroses_clima_bairro`.

Uso:
    python -m src.transform_gold_arboviroses_clima

Depende de `silver_arboviroses`, `silver_bairro_geo`, `silver_clima_diario`
e (opcionalmente, para features climáticas) `silver_bairro_estacao` já
existirem no MinIO — rode as transformações Silver correspondentes antes.
"""
from __future__ import annotations

import logging
import sys

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.gold.pipeline_gold_arboviroses_clima import executar_transformacao_gold_arboviroses_clima


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
    )


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
        executar_transformacao_gold_arboviroses_clima(minio_client)
    except (MinioClientError, ValueError) as exc:
        logger.error("Transformação Gold interrompida: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
