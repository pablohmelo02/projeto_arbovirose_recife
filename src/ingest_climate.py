"""Ponto de entrada da ingestão Bronze do domínio Clima (INMET + APAC).

Uso:
    python -m src.ingest_climate
"""
from __future__ import annotations

import logging
import sys

from src.clients.apac_client import ApacClient
from src.clients.inmet_client import InmetClient
from src.clients.minio_client import MinioClient
from src.config import load_config
from src.ingestion.climate_ingestion import executar_ingestao_apac, executar_ingestao_inmet


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

    erros_totais = 0

    inmet_client = InmetClient(timeout=config.http_timeout)
    manifest_inmet = executar_ingestao_inmet(
        inmet_client, minio_client, anos=list(config.inmet_anos)
    )
    erros_totais += manifest_inmet["erros"]

    apac_client = ApacClient(timeout=config.http_timeout)
    manifest_apac = executar_ingestao_apac(apac_client, minio_client)
    erros_totais += manifest_apac["erros"]

    return 0 if erros_totais == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
