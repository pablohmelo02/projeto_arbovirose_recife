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
from src.quality_gates import QualityGateError
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


#: A exportação passa pelos portões de qualidade da Gold (94 bairros, 3
#: agravos, chave única, integridade referencial com o território), então a
#: fixture tem de ser uma Gold **válida** — não um recorte de 2 linhas.
#: Publicar uma Gold incompleta é justamente o que os portões existem para
#: impedir, e o teste precisa refletir isso.
N_BAIRROS = 94
AGRAVOS = ("DENGUE", "ZIKA", "CHIKUNGUNYA")
LINHAS_ESPERADAS = N_BAIRROS * len(AGRAVOS)


def _gold_minima() -> pd.DataFrame:
    inicio = pd.Timestamp("2024-01-07")
    linhas = []
    for i in range(N_BAIRROS):
        for agravo in AGRAVOS:
            linhas.append(
                {
                    "codigo_bairro": str(i), "nome_bairro": f"BAIRRO {i}", "agravo": agravo,
                    "ano_epidemiologico": 2024, "semana_epidemiologica": 1,
                    "semana_epi_data_inicio": inicio,
                    "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                    "casos": i % 4,
                    "dias_com_dado_valido_semana": 7 if i % 2 == 0 else None,
                    "precipitacao_total_semana_mm": 10.0 if i % 2 == 0 else None,
                }
            )
    return pd.DataFrame(linhas)


def _bairro_geo_minima() -> gpd.GeoDataFrame:
    poligono = Polygon([(-35.0, -8.0), (-35.0, -8.01), (-34.99, -8.01), (-34.99, -8.0)])
    return gpd.GeoDataFrame(
        {
            "codigo_bairro": [str(i) for i in range(N_BAIRROS)],
            "nome_bairro": [f"BAIRRO {i}" for i in range(N_BAIRROS)],
            "area_km2": [1.0 + i for i in range(N_BAIRROS)],
            "codigo_rpa": [str(1 + i % 6) for i in range(N_BAIRROS)],
            "codigo_microrregiao": [f"{1 + i % 6}.1" for i in range(N_BAIRROS)],
        },
        geometry=[poligono] * N_BAIRROS,
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
    assert profiling["linhas_gold"] == LINHAS_ESPERADAS
    assert profiling["bairros_geo"] == N_BAIRROS
    assert profiling["chave_gold_duplicadas"] == 0

    df_exportado = pd.read_parquet(tmp_path / ARQUIVO_GOLD)
    assert len(df_exportado) == LINHAS_ESPERADAS
    assert df_exportado["codigo_bairro"].nunique() == N_BAIRROS

    with open(tmp_path / ARQUIVO_BAIRRO_GEO, encoding="utf-8") as f:
        geo = json.load(f)
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == N_BAIRROS
    assert "codigo_bairro" in geo["features"][0]["properties"]


def test_exportar_dataset_dashboard_rejeita_coluna_identificavel(minio_client: MinioClient, tmp_path: Path):
    df_com_id = _gold_minima()
    df_com_id["nome"] = "PACIENTE X"
    _preparar_bronze_gold(minio_client, df_com_id, _bairro_geo_minima())

    with pytest.raises(QualityGateError, match="identificável"):
        exportar_dataset_dashboard(minio_client, pasta_saida=tmp_path)

    assert not (tmp_path / ARQUIVO_GOLD).exists(), "nada deve ser escrito quando um portão crítico falha"


def test_exportar_dataset_dashboard_rejeita_gold_incompleta(minio_client: MinioClient, tmp_path: Path):
    """Publicar uma Gold sem os 94 bairros é bloqueio, não aviso."""
    df_incompleta = _gold_minima()
    df_incompleta = df_incompleta[df_incompleta["codigo_bairro"] != "0"]
    _preparar_bronze_gold(minio_client, df_incompleta, _bairro_geo_minima())

    with pytest.raises(QualityGateError):
        exportar_dataset_dashboard(minio_client, pasta_saida=tmp_path)

    assert not (tmp_path / ARQUIVO_GOLD).exists()


def test_exportar_dataset_dashboard_aceita_clima_todo_ausente(minio_client: MinioClient, tmp_path: Path):
    """`missing != 0`: uma Gold sem nenhuma leitura climática é válida."""
    df_sem_clima = _gold_minima()
    df_sem_clima["dias_com_dado_valido_semana"] = None
    df_sem_clima["precipitacao_total_semana_mm"] = None
    _preparar_bronze_gold(minio_client, df_sem_clima, _bairro_geo_minima())

    profiling = exportar_dataset_dashboard(minio_client, pasta_saida=tmp_path)
    assert profiling["linhas_gold"] == LINHAS_ESPERADAS
