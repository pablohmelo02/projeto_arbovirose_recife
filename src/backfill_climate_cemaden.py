"""Ponto de entrada do backfill histórico do CEMADEN (série horária).

Complementar a `python -m src.ingest_climate` (janela operacional curta).
Busca profundidade histórica (anos, não horas) para as estações
pluviométricas candidatas da Grande Recife — mesmo recorte espacial já
usado pela ingestão operacional (`candidatos_pluviometricos_grande_recife`),
para não inventar um segundo critério de seleção de estações.

Uso:
    python -m src.backfill_climate_cemaden [--dias N]

Rode depois de `python -m src.ingest_climate` (a ingestão operacional já
grava um status CEMADEN recente na Bronze) ou isoladamente — este script
baixa seu próprio status fresco se preferir não depender de uma ingestão
anterior, já que o status é um recurso barato (1 chamada).
"""
from __future__ import annotations

import argparse
import logging
import sys

from src.clients.cemaden_client import CemadenClient
from src.clients.minio_client import MinioClient
from src.config import load_config
from src.ingestion.climate_ingestion import candidatos_pluviometricos_grande_recife
from src.ingestion.cemaden_backfill import (
    DIAS_BACKFILL_PADRAO,
    TIMEOUT_BACKFILL_S,
    executar_backfill_cemaden,
)


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dias", type=int, default=DIAS_BACKFILL_PADRAO,
        help=f"Profundidade do backfill em dias (padrão: {DIAS_BACKFILL_PADRAO})",
    )
    return parser.parse_args()


def main() -> int:
    _configurar_logging()
    logger = logging.getLogger(__name__)
    args = _parse_args()

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

    # timeout maior que o operacional: janelas de anos podem exigir um
    # "cold start" do backend do CEMADEN antes de responder (ver
    # cemaden_backfill.py e o relatório da investigação de profundidade).
    cemaden_client = CemadenClient(
        timeout=TIMEOUT_BACKFILL_S,
        url_wfs=config.cemaden_wfs_url,
        url_status=config.cemaden_status_url,
        url_horario_base=config.cemaden_horario_url,
    )

    logger.info("Buscando status CEMADEN (PE) para identificar candidatas...")
    conteudo_status = cemaden_client.baixar_status_estacoes()
    candidatos = candidatos_pluviometricos_grande_recife(conteudo_status)
    id_estacoes = sorted({str(c["idestacao"]) for c in candidatos})
    logger.info("%d estação(ões) pluviométrica(s) candidatas na Grande Recife", len(id_estacoes))

    manifest = executar_backfill_cemaden(
        cemaden_client, minio_client, id_estacoes, dias_profundidade=args.dias
    )

    return 0 if manifest["erros"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
