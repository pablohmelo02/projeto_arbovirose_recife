"""Ponto de entrada da validação da camada Bronze.

Relê os dados já gravados no MinIO para uma execução de ingestão e verifica
se são plausíveis (não vazios, não HTML de erro, sem lacunas de anos nas
séries de fatos). Não altera nenhum dado da Bronze.

Uso:
    python -m src.validate
    python -m src.validate --manifest bronze/recife/arboviroses/_controle/manifest_20260819T150500Z.json
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.ingestion.bronze_validation import executar_validacao_bronze


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida os dados já ingeridos na camada Bronze."
    )
    parser.add_argument(
        "--manifest",
        dest="manifest_key",
        default=None,
        help="Chave do manifest a validar. Se omitido, usa o manifest mais recente.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    _configurar_logging()
    logger = logging.getLogger(__name__)
    args = _parse_args(argv if argv is not None else sys.argv[1:])

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
        relatorio = executar_validacao_bronze(minio_client, manifest_key=args.manifest_key)
    except (MinioClientError, ValueError) as exc:
        logger.error("Validação interrompida: %s", exc)
        return 1

    resumo = relatorio["resumo"]
    logger.info("Validação concluída para run_id=%s", relatorio["run_id"])
    logger.info(
        "OK: %d | Avisos: %d | Erros: %d",
        resumo["ok"],
        resumo["avisos"],
        resumo["erros"],
    )

    if relatorio["lacunas_de_anos"]:
        for entidade, anos in relatorio["lacunas_de_anos"].items():
            logger.warning("Lacuna de anos em '%s': %s", entidade, anos)
    else:
        logger.info("Nenhuma lacuna de anos detectada nas séries de fatos")

    for check in relatorio["checks"]:
        if check["status"] != "OK":
            logger.warning(
                "%s [%s/%s ano=%s]: %s",
                check["status"],
                check["tipo"],
                check["entidade"],
                check["ano"],
                "; ".join(check["problemas"]),
            )

    return 0 if resumo["erros"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
