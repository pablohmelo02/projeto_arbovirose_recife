"""Exporta o dataset de publicação do dashboard a partir da Gold pronta.

Ponto de entrada:

    python -m src.export_dashboard_dataset

Lê `gold_arboviroses_clima_bairro` (Silver/Gold já processadas, ver
`src/gold/`) e `silver_bairro_geo` direto do MinIO e grava versões estáticas
em `dashboard/data/` — o dashboard (Streamlit) lê só esses arquivos, nunca
o MinIO/Data Lake diretamente (ver `dashboard/utils/data_loader.py`), para
funcionar também no Streamlit Community Cloud, onde o Data Lake local não
está disponível (ver README.md, seção "Dashboard").

## Por que é seguro publicar este dataset

`gold_arboviroses_clima_bairro` já é uma agregação por
`bairro × semana epidemiológica × agravo` — não existe nenhuma coluna de
identificação individual (sem `id_notificacao`, sem nome/CPF/data de
nascimento de paciente; ver `src/gold/schema_gold_arboviroses_clima.py`).
`silver_bairro_geo` é geometria oficial pública dos 94 bairros do Recife.
Nenhum dado da Bronze (CSV bruto do SINAN) é exportado. Este script grava
um profiling (`dashboard/data/_profiling_export.json`) confirmando isso a
cada execução, para nunca depender de memória/confiança silenciosa.
"""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from src.clients.minio_client import MinioClient
from src.config import load_config

logger = logging.getLogger(__name__)

CHAVE_GOLD = "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"
CHAVE_BAIRRO_GEO = "silver/recife/territorio/bairro_geo/bairros.parquet"

PASTA_DASHBOARD_DATA = Path(__file__).resolve().parent.parent / "dashboard" / "data"

ARQUIVO_GOLD = "gold_arboviroses_clima_bairro.parquet"
ARQUIVO_BAIRRO_GEO = "bairro_geo.geojson"
ARQUIVO_PROFILING = "_profiling_export.json"

# Colunas que, se um dia aparecessem na Gold, indicariam vazamento de dado
# individual -- checagem defensiva, não uma lista do que a Gold tem hoje.
COLUNAS_PROIBIDAS = (
    "id_notificacao", "nome", "cpf", "data_nascimento", "endereco", "cns",
)


def _configurar_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)


def _checar_ausencia_de_dado_individual(df_gold: pd.DataFrame) -> None:
    colunas_normalizadas = {c.lower() for c in df_gold.columns}
    encontradas = colunas_normalizadas.intersection(COLUNAS_PROIBIDAS)
    if encontradas:
        raise ValueError(
            f"Dataset de publicação contém coluna(s) potencialmente identificável(is): {encontradas} — "
            "abortando exportação. A Gold deve conter só dado agregado por bairro/semana/agravo."
        )


def exportar_dataset_dashboard(minio_client: MinioClient, pasta_saida: Path = PASTA_DASHBOARD_DATA) -> dict[str, Any]:
    pasta_saida.mkdir(parents=True, exist_ok=True)

    df_gold = pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_GOLD)))
    _checar_ausencia_de_dado_individual(df_gold)

    gdf_bairros = gpd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_BAIRRO_GEO)))
    colunas_geo = [
        c for c in ("codigo_bairro", "nome_bairro", "area_km2", "codigo_rpa", "codigo_microrregiao", "geometry")
        if c in gdf_bairros.columns
    ]
    gdf_bairros_publicavel = gdf_bairros[colunas_geo]

    caminho_gold = pasta_saida / ARQUIVO_GOLD
    df_gold.to_parquet(caminho_gold, engine="pyarrow", index=False)

    caminho_geo = pasta_saida / ARQUIVO_BAIRRO_GEO
    gdf_bairros_publicavel.to_file(caminho_geo, driver="GeoJSON")

    profiling = {
        "linhas_gold": len(df_gold),
        "colunas_gold": list(df_gold.columns),
        "bairros_geo": len(gdf_bairros_publicavel),
        "tamanho_gold_bytes": caminho_gold.stat().st_size,
        "tamanho_geo_bytes": caminho_geo.stat().st_size,
        "chave_gold_duplicadas": int(
            df_gold.duplicated(subset=["codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica"]).sum()
        ),
        "colunas_proibidas_encontradas": [],
    }
    (pasta_saida / ARQUIVO_PROFILING).write_text(
        json.dumps(profiling, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(
        "Dataset do dashboard exportado: %s (%d linhas, %.2f MB) + %s (%d bairros, %.2f MB)",
        caminho_gold, len(df_gold), profiling["tamanho_gold_bytes"] / 1e6,
        caminho_geo, len(gdf_bairros_publicavel), profiling["tamanho_geo_bytes"] / 1e6,
    )
    return profiling


def main() -> int:
    _configurar_logging()
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
    exportar_dataset_dashboard(minio_client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
