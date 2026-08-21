"""Ponto de entrada da transformação Silver de população por bairro.

Lê o Bronze estático em `data/bronze/populacao/` (ver
`src/ingestion/population_ingestion.py` para a proveniência) e a dimensão
territorial da Gold publicada, aplica o contrato de
`src/silver/schema_population.py` e grava
`data/silver/populacao_bairro_ano/populacao_bairro_ano.parquet`.

Uso:
    python -m src.transform_population
"""
from __future__ import annotations

import json
import logging
import sys

from src.logging_config import configurar_logging
from src.silver.pipeline_population import executar_transformacao_silver_populacao_local


def main() -> int:
    configurar_logging()
    logger = logging.getLogger(__name__)

    try:
        manifest = executar_transformacao_silver_populacao_local()
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Transformação Silver de população interrompida: %s", exc)
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
