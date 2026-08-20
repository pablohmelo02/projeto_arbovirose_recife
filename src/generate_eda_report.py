"""Gera o relatório reproduzível de EDA em `reports/eda/`.

Uso:
    python -m src.generate_eda_report

Lê o mesmo dataset estático que o dashboard usa
(`dashboard/data/gold_arboviroses_clima_bairro.parquet`, ver
`src/export_dashboard_dataset.py`) — o relatório e o dashboard nunca
divergem por lerem fontes diferentes.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.eda.relatorio import gerar_relatorio_eda

logger = logging.getLogger(__name__)

CAMINHO_GOLD_EXPORTADA = Path(__file__).resolve().parent.parent / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO_EDA = Path(__file__).resolve().parent.parent / "reports" / "eda"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)

    if not CAMINHO_GOLD_EXPORTADA.exists():
        logger.error(
            "'%s' não encontrado. Rode 'python -m src.export_dashboard_dataset' primeiro.",
            CAMINHO_GOLD_EXPORTADA,
        )
        return 1

    import pandas as pd

    df_gold = pd.read_parquet(CAMINHO_GOLD_EXPORTADA)
    resultado = gerar_relatorio_eda(df_gold, PASTA_RELATORIO_EDA)

    logger.info("Relatório de EDA gerado em %s", PASTA_RELATORIO_EDA)
    logger.info("Achados: %d", len(resultado["achados"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
