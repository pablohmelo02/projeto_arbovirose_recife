"""Ponto de entrada da ingestão Bronze do domínio Território.

Uso:
    python -m src.ingest_territorio
"""
from __future__ import annotations

import logging
import sys

from src.clients.ckan_client import CkanApiError, CkanClient
from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.ingestion.territory_ingestion import executar_ingestao_territorio


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

    ckan_client = CkanClient(
        base_url=config.ckan_base_url,
        dataset=config.ckan_territorio_dataset,
        timeout=config.http_timeout,
    )
    minio_client = MinioClient(
        endpoint=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket=config.minio_bucket,
    )

    try:
        manifest = executar_ingestao_territorio(
            ckan_client=ckan_client,
            minio_client=minio_client,
            fonte=config.ckan_base_url,
            dataset=config.ckan_territorio_dataset,
        )
    except (CkanApiError, MinioClientError) as exc:
        logger.error("Ingestão de território interrompida: %s", exc)
        return 1

    return 0 if manifest["erros"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
