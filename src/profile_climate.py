"""Ponto de entrada do profiling do domínio Clima.

Uso:
    python -m src.profile_climate
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.profiling.climate_profiler import executar_profiling_clima, gravar_relatorios

PASTA_RELATORIOS = Path("reports") / "climate_profile"


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
        resultado = executar_profiling_clima(minio_client)
    except MinioClientError as exc:
        logger.error("Profiling climático interrompido: %s", exc)
        return 1

    gravar_relatorios(resultado, PASTA_RELATORIOS)
    logger.info("Relatórios salvos em %s", PASTA_RELATORIOS.resolve())

    return 0


if __name__ == "__main__":
    sys.exit(main())
