"""Ponto de entrada da Silver do mapeamento `bairro -> estação climática`.

Uso:
    python -m src.transform_climate_bairro

Depende de `silver_bairro_geo`, `silver_estacao_climatica` e
`silver_clima_diario` já existirem no MinIO — rode as seções 13 e 14 do
README (`transform_territorio` e `transform_climate`) antes.
"""
from __future__ import annotations

import logging
import sys

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.silver.pipeline_climate_bairro import executar_transformacao_silver_climate_bairro


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
        executar_transformacao_silver_climate_bairro(minio_client)
    except (MinioClientError, ValueError) as exc:
        logger.error("Mapeamento bairro-estacao interrompido: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
