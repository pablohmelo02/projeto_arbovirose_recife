"""Ponto de entrada da análise espacial de cobertura climática.

Lê `silver_bairro_geo` e `silver_estacao_climatica` direto do MinIO (ambos
já devem ter sido gerados: `python -m src.transform_territorio` e
`python -m src.transform_climate`) e produz relatórios de cobertura em
`reports/climate_spatial/`. Não atribui clima a bairro — só analisa.

Uso:
    python -m src.analyze_climate_coverage
"""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.clients.minio_client import MinioClient, MinioClientError
from src.config import load_config
from src.silver.climate_spatial import (
    calcular_cobertura_bairros,
    calcular_estacao_mais_proxima_por_bairro,
    construir_geodataframe_estacoes,
    estacoes_dentro_do_recife,
)

PASTA_RELATORIOS = Path("reports") / "climate_spatial"


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
        conteudo_bairros = minio_client.download_bytes(
            "silver/recife/territorio/bairro_geo/bairros.parquet"
        )
        conteudo_estacoes = minio_client.download_bytes(
            "silver/recife/clima/estacoes/estacoes.parquet"
        )
    except MinioClientError as exc:
        logger.error(
            "Não foi possível ler a Silver de território/clima: %s. "
            "Rode 'python -m src.transform_territorio' e 'python -m src.transform_climate' antes.",
            exc,
        )
        return 1

    gdf_bairros = gpd.read_parquet(io.BytesIO(conteudo_bairros))
    df_estacoes = pd.read_parquet(io.BytesIO(conteudo_estacoes))

    total_estacoes = len(df_estacoes)
    gdf_estacoes = construir_geodataframe_estacoes(df_estacoes)
    sem_coordenada = total_estacoes - len(gdf_estacoes)

    join_resultado = estacoes_dentro_do_recife(gdf_estacoes, gdf_bairros)
    dentro = int(join_resultado["codigo_bairro"].notna().sum())
    fora = int(join_resultado["codigo_bairro"].isna().sum())

    cobertura = calcular_cobertura_bairros(join_resultado, gdf_bairros)
    distancias = calcular_estacao_mais_proxima_por_bairro(gdf_bairros, gdf_estacoes)

    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)

    colunas_join = [
        "codigo_estacao", "nome_estacao", "fonte", "latitude", "longitude",
        "codigo_bairro", "nome_bairro",
    ]
    join_resultado[colunas_join].to_csv(
        PASTA_RELATORIOS / "stations_inside_recife.csv", index=False, encoding="utf-8"
    )

    pd.DataFrame(
        {"codigo_bairro": cobertura["bairros_com_estacao"]}
    ).to_csv(PASTA_RELATORIOS / "bairros_with_station.csv", index=False, encoding="utf-8")

    distancias.to_csv(PASTA_RELATORIOS / "nearest_station_by_bairro.csv", index=False, encoding="utf-8")

    resumo = {
        "total_estacoes": total_estacoes,
        "estacoes_sem_coordenada": sem_coordenada,
        "estacoes_dentro_do_recife": dentro,
        "estacoes_fora_do_recife": fora,
        **cobertura,
        "distancia_media_km": round(float(distancias["distancia_km"].mean()), 3) if not distancias.empty else None,
        "distancia_maxima_km": round(float(distancias["distancia_km"].max()), 3) if not distancias.empty else None,
        "distancia_minima_km": round(float(distancias["distancia_km"].min()), 3) if not distancias.empty else None,
    }
    (PASTA_RELATORIOS / "summary.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    logger.info("Relatórios salvos em %s", PASTA_RELATORIOS.resolve())
    logger.info(
        "Estações dentro do Recife: %d | fora: %d | bairros com estação: %d/%d",
        dentro, fora, cobertura["quantidade_bairros_com_estacao"], cobertura["total_bairros"],
    )
    if not distancias.empty:
        logger.info(
            "Distância ao vizinho mais próximo — média: %.2f km | máxima: %.2f km",
            resumo["distancia_media_km"], resumo["distancia_maxima_km"],
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
