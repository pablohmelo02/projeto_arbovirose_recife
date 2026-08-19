import io
import uuid
from typing import Iterator

import geopandas as gpd
import pytest
from moto.server import ThreadedMotoServer
from shapely.geometry import Polygon

from src.clients.minio_client import MinioClient
from src.silver.pipeline_territorio import executar_transformacao_silver_territorio


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


def _quadrado(lon: float, lat: float, lado: float = 0.01) -> Polygon:
    return Polygon([(lon, lat), (lon + lado, lat), (lon + lado, lat + lado), (lon, lat + lado)])


def _geojson_bairros_bytes() -> bytes:
    gdf = gpd.GeoDataFrame(
        {
            "CBAIRRCODI": [1, 2],
            "EBAIRRNOME": ["BAIRRO A", "BAIRRO B"],
            "EBAIRRNOMEOF": ["Bairro A", "Bairro B"],
            "CRPAAACODI": [1, 2],
            "CMICROCODI": [1, 1],
        },
        geometry=[_quadrado(-34.9, -8.05), _quadrado(-34.8, -8.04)],
        crs="EPSG:4326",
    )
    return gdf.to_json().encode("utf-8")


def _manifest_bronze_territorio() -> dict:
    return {
        "run_id": "20260101T000000Z",
        "dominio": "territorio",
        "recursos": [
            {
                "resource_id": "res-bairros",
                "entidade": "bairro",
                "status": "SUCCESS",
                "object_key": "bronze/territorio/bairro/res-bairros.geojson",
                "nome_recurso": "Limites dos Bairros - 2023",
            }
        ],
    }


def test_executar_transformacao_silver_territorio_ponta_a_ponta(minio_client: MinioClient):
    minio_client.upload_bytes("bronze/territorio/bairro/res-bairros.geojson", _geojson_bairros_bytes())
    minio_client.upload_manifest(
        "bronze/recife/territorio/_controle/manifest_20260101T000000Z.json",
        _manifest_bronze_territorio(),
    )

    manifest = executar_transformacao_silver_territorio(minio_client)

    assert manifest["total_linhas_validas"] == 2
    assert manifest["total_linhas_rejeitadas"] == 0

    conteudo_parquet = minio_client.download_bytes(
        "silver/recife/territorio/bairro_geo/bairros.parquet"
    )
    gdf = gpd.read_parquet(io.BytesIO(conteudo_parquet))
    assert len(gdf) == 2
    assert gdf.crs.to_string() == "EPSG:4326"
    assert set(gdf["codigo_bairro"]) == {"1", "2"}
    assert (gdf["area_km2"] > 0).all()

    chaves_manifest = minio_client.listar_chaves(
        "silver/recife/territorio/_controle/manifest_silver_territorio_"
    )
    assert len(chaves_manifest) == 1

    # nada deveria ter ido para rejeitados neste cenário
    chaves_rejeitados = minio_client.listar_chaves("silver/recife/territorio/_rejected/")
    assert chaves_rejeitados == []


def test_executar_transformacao_silver_territorio_sem_manifests_levanta_erro(
    minio_client: MinioClient,
):
    with pytest.raises(ValueError):
        executar_transformacao_silver_territorio(minio_client)
