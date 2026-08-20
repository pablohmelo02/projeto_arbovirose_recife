import io
import uuid
from typing import Iterator

import geopandas as gpd
import pandas as pd
import pytest
from moto.server import ThreadedMotoServer
from shapely.geometry import Point

from src.clients.minio_client import MinioClient
from src.gold.pipeline_gold_arboviroses_clima import (
    executar_transformacao_gold_arboviroses_clima,
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


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


def _geoparquet_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    buffer = io.BytesIO()
    gdf.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _preparar_silver(minio_client: MinioClient, com_bairro_estacao: bool = True) -> None:
    arbo = pd.DataFrame(
        {
            "id_notificacao": ["a", "b", "c"],
            "tipo_arbovirose": ["DENGUE", "DENGUE", "ZIKA"],
            "semana_notificacao": ["202002", "202002", "202002"],
            "nome_bairro": ["BOA VIAGEM", "BOA VIAGEM", "CASA FORTE"],
            "codigo_bairro": ["x", "x", "y"],
            "_source_resource_id": ["r1", "r1", "r2"],
        }
    )
    minio_client.upload_bytes(
        "silver/recife/arboviroses/fatos/arboviroses/ano=2020/arboviroses_2020.parquet", _parquet_bytes(arbo)
    )

    gdf = gpd.GeoDataFrame(
        {
            "codigo_bairro": ["1", "2"],
            "nome_bairro": ["BOA VIAGEM", "CASA FORTE"],
            "area_km2": [5.0, 3.0],
            "codigo_rpa": [1, 2],
            "codigo_microrregiao": [1, 1],
            "centroide_lat": [-8.1, -8.05],
            "centroide_lon": [-34.9, -34.92],
            "geometry": [Point(-34.9, -8.1), Point(-34.92, -8.05)],
        },
        crs="EPSG:4326",
    )
    minio_client.upload_bytes(
        "silver/recife/territorio/bairro_geo/bairros.parquet", _geoparquet_bytes(gdf)
    )

    clima = pd.DataFrame(
        {
            "data": pd.to_datetime(["2020-01-06", "2020-01-07"]),
            "codigo_estacao": ["E1", "E1"],
            "fonte": ["CEMADEN", "CEMADEN"],
            "precipitacao_mm": [1.0, 2.5],
        }
    )
    minio_client.upload_bytes(
        "silver/recife/clima/diario/ano=2020/clima_diario_2020.parquet", _parquet_bytes(clima)
    )

    if com_bairro_estacao:
        bairro_estacao = pd.DataFrame(
            {
                "codigo_bairro": ["1", "2"],
                "codigo_estacao": ["E1", "E2"],
                "fonte": ["CEMADEN", "CEMADEN"],
                "distancia_km": [0.5, 0.9],
                "metodo_associacao": ["nearest_station", "nearest_station"],
            }
        )
        minio_client.upload_bytes(
            "silver/recife/clima/bairro_estacao/bairro_estacao.parquet", _parquet_bytes(bairro_estacao)
        )


def test_pipeline_gold_ponta_a_ponta(minio_client: MinioClient):
    _preparar_silver(minio_client)

    manifest = executar_transformacao_gold_arboviroses_clima(minio_client)

    assert manifest["dominio"] == "gold_arboviroses_clima"
    metricas = manifest["metricas"]
    assert metricas["chave_gold_unica"] is True
    assert metricas["grao_completo"]["total_bairros"] == 2
    assert metricas["grao_completo"]["total_casos_no_grao"] == 3

    conteudo = minio_client.download_bytes(
        "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"
    )
    df_gold = pd.read_parquet(io.BytesIO(conteudo))
    assert len(df_gold) == metricas["total_linhas_gold"]
    assert not df_gold.duplicated(
        subset=["codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica"]
    ).any()

    # A semana 2 de 2020 (2020-01-05 a 2020-01-11) tem os 2 dias de chuva reais
    linha = df_gold[
        (df_gold["codigo_bairro"] == "1")
        & (df_gold["agravo"] == "DENGUE")
        & (df_gold["semana_epidemiologica"] == 2)
    ].iloc[0]
    assert linha["casos"] == 2
    assert linha["precipitacao_total_semana_mm"] == 3.5
    assert linha["dias_com_dado_valido_semana"] == 2
    assert linha["fonte_clima"] == "CEMADEN"

    chaves_manifest = minio_client.listar_chaves(
        "gold/recife/arboviroses_clima/_controle/manifest_gold_arboviroses_clima_"
    )
    assert len(chaves_manifest) == 1


def test_pipeline_gold_idempotente_duas_execucoes_mesmo_resultado(minio_client: MinioClient):
    _preparar_silver(minio_client)

    executar_transformacao_gold_arboviroses_clima(minio_client)
    conteudo1 = minio_client.download_bytes(
        "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"
    )
    executar_transformacao_gold_arboviroses_clima(minio_client)
    conteudo2 = minio_client.download_bytes(
        "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"
    )

    df1 = pd.read_parquet(io.BytesIO(conteudo1)).drop(columns=["_processed_at"])
    df2 = pd.read_parquet(io.BytesIO(conteudo2)).drop(columns=["_processed_at"])
    pd.testing.assert_frame_equal(df1, df2)


def test_pipeline_gold_sem_bairro_estacao_gera_gold_sem_features_climaticas(minio_client: MinioClient):
    _preparar_silver(minio_client, com_bairro_estacao=False)

    manifest = executar_transformacao_gold_arboviroses_clima(minio_client)

    conteudo = minio_client.download_bytes(
        "gold/recife/arboviroses_clima/gold_arboviroses_clima_bairro.parquet"
    )
    df_gold = pd.read_parquet(io.BytesIO(conteudo))
    assert df_gold["precipitacao_total_semana_mm"].isna().all()
    assert manifest["metricas"]["features_climaticas"]["percentual_linhas_com_clima_real"] == 0.0
    # casos continuam corretos mesmo sem clima
    assert df_gold["casos"].sum() == 3


def test_pipeline_gold_sem_arboviroses_levanta_erro(minio_client: MinioClient):
    with pytest.raises(ValueError):
        executar_transformacao_gold_arboviroses_clima(minio_client)
