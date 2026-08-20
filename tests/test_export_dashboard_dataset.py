import io
import json
import uuid
from pathlib import Path
from typing import Iterator

import geopandas as gpd
import pandas as pd
import pytest
from moto.server import ThreadedMotoServer
from shapely.geometry import Polygon

from src.clients.minio_client import MinioClient
from src.export_dashboard_dataset import (
    ARQUIVO_BAIRRO_GEO,
    ARQUIVO_GOLD,
    ARQUIVO_PROFILING,
    CHAVE_BAIRRO_GEO,
    CHAVE_GOLD,
    exportar_dataset_dashboard,
)


@pytest.fixture()
def minio_client() -> Iterator[MinioClient]:
    server = ThreadedMotoServer(port=0)
    server.start()
    try:
        _, port = server.get_host_and_port()
        bucket = f"datalake-{uuid.uuid4().hex[:8]}"
        cliente = MinioClient(
            endpoint=f"http://127.0.0.1:{port}", access_key="admin", secret_key="admin123", bucket=bucket
        )
        cliente.garantir_bucket()
        yield cliente
    finally:
        server.stop()


def _gold_minima() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "codigo_bairro": "1", "nome_bairro": "A", "agravo": "DENGUE",
                "ano_epidemiologico": 2024, "semana_epidemiologica": 1, "casos": 3,
                "dias_com_dado_valido_semana": 7, "precipitacao_total_semana_mm": 10.0,
            },
            {
                "codigo_bairro": "2", "nome_bairro": "B", "agravo": "ZIKA",
                "ano_epidemiologico": 2024, "semana_epidemiologica": 1, "casos": 0,
                "dias_com_dado_valido_semana": None, "precipitacao_total_semana_mm": None,
            },
        ]
    )


def _bairro_geo_minima() -> gpd.GeoDataFrame:
    poligono = Polygon([(-35.0, -8.0), (-35.0, -8.01), (-34.99, -8.01), (-34.99, -8.0)])
    return gpd.GeoDataFrame(
        {
            "codigo_bairro": ["1", "2"], "nome_bairro": ["A", "B"], "area_km2": [1.0, 2.0],
            "codigo_rpa": ["1", "2"], "codigo_microrregiao": ["1.1", "2.1"],
        },
        geometry=[poligono, poligono],
        crs="EPSG:4326",
    )


def _preparar_bronze_gold(minio_client: MinioClient, df_gold: pd.DataFrame, gdf_bairros: gpd.GeoDataFrame) -> None:
    buffer_gold = io.BytesIO()
    df_gold.to_parquet(buffer_gold, engine="pyarrow", index=False)
    minio_client.upload_bytes(CHAVE_GOLD, buffer_gold.getvalue())

    buffer_geo = io.BytesIO()
    gdf_bairros.to_parquet(buffer_geo)
    minio_client.upload_bytes(CHAVE_BAIRRO_GEO, buffer_geo.getvalue())


def test_exportar_dataset_dashboard_grava_parquet_e_geojson(minio_client: MinioClient, tmp_path: Path):
    _preparar_bronze_gold(minio_client, _gold_minima(), _bairro_geo_minima())

    profiling = exportar_dataset_dashboard(minio_client, pasta_saida=tmp_path)

    assert (tmp_path / ARQUIVO_GOLD).exists()
    assert (tmp_path / ARQUIVO_BAIRRO_GEO).exists()
    assert (tmp_path / ARQUIVO_PROFILING).exists()
    assert profiling["linhas_gold"] == 2
    assert profiling["bairros_geo"] == 2
    assert profiling["chave_gold_duplicadas"] == 0

    df_exportado = pd.read_parquet(tmp_path / ARQUIVO_GOLD)
    assert len(df_exportado) == 2
    assert set(df_exportado["codigo_bairro"]) == {"1", "2"}

    with open(tmp_path / ARQUIVO_BAIRRO_GEO, encoding="utf-8") as f:
        geo = json.load(f)
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == 2
    assert "codigo_bairro" in geo["features"][0]["properties"]


def test_exportar_dataset_dashboard_rejeita_coluna_identificavel(minio_client: MinioClient, tmp_path: Path):
    df_com_id = _gold_minima()
    df_com_id["nome"] = "PACIENTE X"
    _preparar_bronze_gold(minio_client, df_com_id, _bairro_geo_minima())

    with pytest.raises(ValueError, match="identificável"):
        exportar_dataset_dashboard(minio_client, pasta_saida=tmp_path)

    assert not (tmp_path / ARQUIVO_GOLD).exists()
