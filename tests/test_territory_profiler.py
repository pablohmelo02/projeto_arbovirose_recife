import uuid
from typing import Iterator

import geopandas as gpd
import pandas as pd
import pytest
from moto.server import ThreadedMotoServer
from shapely.geometry import Polygon

from src.clients.minio_client import MinioClient
from src.profiling.territory_profiler import (
    cross_check_bairro,
    perfilar_geojson,
    selecionar_ultima_ingestao_valida_territorio,
)


def _poligono_valido(x: float = 0, y: float = 0) -> Polygon:
    return Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)])


def _poligono_invalido() -> Polygon:
    # "bowtie" auto-intersectante — geometria inválida clássica
    return Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])


def _geojson_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    return gdf.to_json().encode("utf-8")


def test_perfilar_geojson_sem_problemas():
    gdf = gpd.GeoDataFrame(
        {"CBAIRRCODI": [1, 2], "EBAIRRNOME": ["A", "B"]},
        geometry=[_poligono_valido(0), _poligono_valido(5)],
        crs="EPSG:4326",
    )
    perfil = perfilar_geojson(_geojson_bytes(gdf))

    assert perfil["quantidade_features"] == 2
    assert perfil["crs"] == "EPSG:4326"
    assert perfil["tipos_geometria"] == ["Polygon"]
    assert perfil["geometrias_nulas"] == 0
    assert perfil["geometrias_invalidas"] == 0
    assert "CBAIRRCODI" in perfil["colunas"]


def test_perfilar_geojson_detecta_geometria_invalida():
    gdf = gpd.GeoDataFrame({"CBAIRRCODI": [1]}, geometry=[_poligono_invalido()], crs="EPSG:4326")
    perfil = perfilar_geojson(_geojson_bytes(gdf))
    assert perfil["geometrias_invalidas"] == 1


def test_perfilar_geojson_detecta_colunas_sempre_nulas():
    gdf = gpd.GeoDataFrame(
        {"CBAIRRCODI": [1, 2], "CAMPO_VAZIO": [None, None]},
        geometry=[_poligono_valido(0), _poligono_valido(5)],
        crs="EPSG:4326",
    )
    perfil = perfilar_geojson(_geojson_bytes(gdf))
    assert "CAMPO_VAZIO" in perfil["colunas_sempre_nulas"]


def test_cross_check_bairro_identifica_matches_e_divergencias():
    gdf = gpd.GeoDataFrame(
        {"CBAIRRCODI": [1, 2, 906], "EBAIRRNOME": ["A", "B", "SANCHO"]},
        geometry=[_poligono_valido(0), _poligono_valido(5), _poligono_valido(10)],
        crs="EPSG:4326",
    )
    df_dim = pd.DataFrame(
        {"codigo": ["1", "2", "902", "999"], "nome": ["A", "B", "SANCHO", "BAIRRO IGNORADO"]}
    )

    resultado = cross_check_bairro(gdf, df_dim)

    assert resultado["disponivel"] is True
    assert resultado["matches"] == 2
    assert resultado["bairros_dimensao"] == 4
    assert {"codigo_bairro": 906, "nome": "SANCHO"} in resultado["sem_dimensao"]
    assert {"codigo_bairro": 902, "nome": "SANCHO"} in resultado["sem_geometria"]
    assert {"codigo_bairro": 999, "nome": "BAIRRO IGNORADO"} in resultado["sem_geometria"]

    correspondencias = resultado["possiveis_correspondencias_por_nome_com_codigo_diferente"]
    assert {"nome": "SANCHO", "codigo_geo": 906, "codigo_dimensao": 902} in correspondencias


def test_cross_check_bairro_sem_dimensao_disponivel():
    gdf = gpd.GeoDataFrame({"CBAIRRCODI": [1], "EBAIRRNOME": ["A"]}, geometry=[_poligono_valido(0)], crs="EPSG:4326")
    resultado = cross_check_bairro(gdf, None)
    assert resultado["disponivel"] is False


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


def _manifest_territorio(run_id: str, recursos: list[dict]) -> dict:
    return {"run_id": run_id, "dominio": "territorio", "recursos": recursos}


def test_selecionar_ultima_ingestao_valida_territorio_usa_manifest_mais_recente(
    minio_client: MinioClient,
):
    minio_client.upload_manifest(
        "bronze/recife/territorio/_controle/manifest_20250101T000000Z.json",
        _manifest_territorio(
            "20250101T000000Z",
            [{"resource_id": "r1", "status": "SUCCESS", "object_key": "antigo.geojson", "entidade": "bairro"}],
        ),
    )
    minio_client.upload_manifest(
        "bronze/recife/territorio/_controle/manifest_20250601T000000Z.json",
        _manifest_territorio(
            "20250601T000000Z",
            [{"resource_id": "r1", "status": "SUCCESS", "object_key": "novo.geojson", "entidade": "bairro"}],
        ),
    )

    selecionados = selecionar_ultima_ingestao_valida_territorio(minio_client)

    assert selecionados["r1"]["object_key"] == "novo.geojson"
    assert selecionados["r1"]["_manifest_run_id"] == "20250601T000000Z"


def test_selecionar_ultima_ingestao_valida_territorio_sem_manifests(minio_client: MinioClient):
    assert selecionar_ultima_ingestao_valida_territorio(minio_client) == {}
