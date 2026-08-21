"""Exporta o dataset de publicação do dashboard a partir da Gold pronta.

Ponto de entrada:

    python -m src.export_dashboard_dataset

Lê `gold_arboviroses_clima_bairro` (Silver/Gold já processadas, ver
`src/gold/`) e `silver_bairro_geo` direto do MinIO e grava versões estáticas
em `dashboard/data/` — o dashboard (Streamlit) lê só esses arquivos, nunca
o MinIO/Data Lake diretamente (ver `dashboard/utils/data_loader.py`), para
funcionar também no Streamlit Community Cloud, onde o Data Lake local não
está disponível (ver `docs/arquitetura_e_pipeline.md`, seção "Dashboard").

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
from src.logging_config import configurar_logging
from src.quality_gates import (
    QualityGateError,
    exigir_aprovacao,
    validar_dataset_publicavel,
    validar_gold,
)

logger = logging.getLogger(__name__)

CHAVE_GOLD = "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"
CHAVE_BAIRRO_GEO = "silver/recife/territorio/bairro_geo/bairros.parquet"

PASTA_DASHBOARD_DATA = Path(__file__).resolve().parent.parent / "dashboard" / "data"

ARQUIVO_GOLD = "gold_arboviroses_clima_bairro.parquet"
ARQUIVO_BAIRRO_GEO = "bairro_geo.geojson"
ARQUIVO_PROFILING = "_profiling_export.json"

# Colunas que, se um dia aparecessem na Gold, indicariam vazamento de dado
# individual -- checagem defensiva, não uma lista do que a Gold tem hoje.
# Mesma lista usada por `scripts/verificar_deploy_dashboard.py`, para que a
# barreira da exportação e a da verificação de deploy não divirjam.
COLUNAS_PROIBIDAS = (
    "id_notificacao", "nu_notific", "nome", "nome_paciente", "cpf", "cns",
    "data_nascimento", "dt_nasc", "endereco", "logradouro", "numero_casa",
    "telefone", "email", "prontuario", "latitude_paciente", "longitude_paciente",
)


def exportar_dataset_dashboard(minio_client: MinioClient, pasta_saida: Path = PASTA_DASHBOARD_DATA) -> dict[str, Any]:
    pasta_saida.mkdir(parents=True, exist_ok=True)

    df_gold = pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_GOLD)))

    gdf_bairros = gpd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_BAIRRO_GEO)))
    colunas_geo = [
        c for c in ("codigo_bairro", "nome_bairro", "area_km2", "codigo_rpa", "codigo_microrregiao", "geometry")
        if c in gdf_bairros.columns
    ]
    gdf_bairros_publicavel = gdf_bairros[colunas_geo]

    # Portões antes de publicar: privacidade primeiro (bloqueia por si só),
    # depois a integridade da Gold contra os códigos de bairro do território.
    # Se qualquer crítico falhar, nada é escrito e o artefato anterior
    # permanece intacto.
    achados = validar_dataset_publicavel(df_gold, COLUNAS_PROIBIDAS)
    achados += validar_gold(
        df_gold,
        codigos_bairro_territorio=gdf_bairros_publicavel["codigo_bairro"].astype(str).tolist(),
    )
    avisos = exigir_aprovacao(achados, contexto="exportacao_dashboard")

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
        "avisos_qualidade": [a.mensagem for a in avisos],
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
    configurar_logging()
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
        exportar_dataset_dashboard(minio_client)
    except QualityGateError as exc:
        logger.error("Exportação abortada pelos portões de qualidade: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
