"""Ponto de entrada da transformação Silver do domínio Território.

Lê a última ingestão válida direto do MinIO (nunca baixa do CKAN novamente),
aplica o contrato canônico de `src/silver/schema_territorio.py` e grava
GeoParquet em `silver/recife/territorio/` no MinIO.

Uso:
    python -m src.transform_territorio
"""
from __future__ import annotations

import logging
import sys

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.silver.pipeline_territorio import executar_transformacao_silver_territorio


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
        executar_transformacao_silver_territorio(minio_client)
    except (MinioClientError, ValueError) as exc:
        logger.error("Transformação Silver território interrompida: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
