"""Ponto de entrada do profiling da camada Bronze.

Lê a última ingestão válida de cada recurso direto do MinIO (nunca baixa do
CKAN novamente) e gera relatórios de schema em `reports/bronze_profile/`.

Uso:
    python -m src.profile
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.profiling.bronze_profiler import executar_profiling, gravar_relatorios

PASTA_RELATORIOS = Path("reports") / "bronze_profile"


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
        resultado = executar_profiling(minio_client)
    except (MinioClientError, ValueError) as exc:
        logger.error("Profiling interrompido: %s", exc)
        return 1

    gravar_relatorios(resultado, PASTA_RELATORIOS)
    logger.info("Relatórios salvos em %s", PASTA_RELATORIOS.resolve())

    logger.info(
        "Recursos selecionados: %d | perfilados: %d | falhas de leitura: %d",
        resultado["total_recursos_selecionados"],
        resultado["total_recursos_perfilados"],
        len(resultado["falhas_leitura"]),
    )

    resumo = resultado["resumo_schemas"]
    for entidade, anos in resumo["anos_disponiveis_por_entidade"].items():
        logger.info("%s: %d ano(s) disponível(is) -> %s", entidade, len(anos), anos)

    logger.info(
        "Colunas comuns às três doenças: %d", len(resumo["colunas_comuns_as_tres_doencas"])
    )
    for entidade, colunas in resumo["colunas_exclusivas_por_doenca"].items():
        logger.info("Colunas exclusivas de %s: %d", entidade, len(colunas))

    if resumo["colunas_com_tipo_aparente_inconsistente"]:
        logger.warning(
            "%d coluna(s) com tipo aparente inconsistente entre arquivos",
            len(resumo["colunas_com_tipo_aparente_inconsistente"]),
        )

    if resultado["falhas_leitura"]:
        for falha in resultado["falhas_leitura"]:
            logger.warning("Não foi possível perfilar: %s (%s)", falha["nome"], falha["resource_id"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
