import io
import json
import uuid
from typing import Iterator

import pandas as pd
import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.silver.pipeline_climate import executar_transformacao_silver_climate


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


def _csv_inmet() -> bytes:
    linhas = [
        "REGIAO:;NE", "UF:;PE", "ESTACAO:;TESTE", "CODIGO (WMO):;A999",
        "LATITUDE:;-8,05", "LONGITUDE:;-34,90", "ALTITUDE:;10,5", "DATA DE FUNDACAO:;01/01/20",
        "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);UMIDADE RELATIVA DO AR, HORARIA (%);",
        "2024/01/01;0000 UTC;0;25,0;80;",
        "2024/01/01;0100 UTC;1,0;26,0;82;",
    ]
    return ("\n".join(linhas)).encode("latin-1")


def _snapshot_apac() -> bytes:
    ponto = {
        "ponto": {"id": "10", "nome": "Estacao Teste", "latitude": "-8.0", "longitude": "-34.9"},
        "3": {"titulo": "Município", "valor": "RECIFE"},
        "dados_monitorados": {
            "dados": [
                {"titulo": "Data último dado", "valor": "15-01-2024"},
                {"titulo": "24 Horas", "valor": "0.5"},
            ]
        },
    }
    return json.dumps({"pontos": {"0": ponto}}).encode("utf-8")


def _preparar_bronze(minio_client: MinioClient) -> None:
    minio_client.upload_bytes(
        "bronze/recife/clima/inmet/ano=2024/ingestion=run1/A999.csv", _csv_inmet()
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/inmet/_controle/manifest_run1.json",
        {
            "run_id": "run1",
            "recursos": [
                {
                    "nome_recurso": "A999.csv",
                    "ano": 2024,
                    "status": "SUCCESS",
                    "object_key": "bronze/recife/clima/inmet/ano=2024/ingestion=run1/A999.csv",
                }
            ],
        },
    )

    minio_client.upload_bytes("bronze/recife/clima/apac/pcd/ingestion=run2/pcds.json", _snapshot_apac())
    minio_client.upload_manifest(
        "bronze/recife/clima/apac/_controle/manifest_run2.json",
        {
            "run_id": "run2",
            "recursos": [
                {
                    "nome_recurso": "pcds.json",
                    "status": "SUCCESS",
                    "object_key": "bronze/recife/clima/apac/pcd/ingestion=run2/pcds.json",
                }
            ],
        },
    )


def test_executar_transformacao_silver_climate_ponta_a_ponta(minio_client: MinioClient):
    _preparar_bronze(minio_client)

    manifest = executar_transformacao_silver_climate(minio_client)

    assert manifest["total_estacoes"] == 2  # 1 INMET + 1 APAC
    assert manifest["total_linhas_validas"] == 2  # 1 dia do INMET + 1 snapshot da APAC

    conteudo_estacoes = minio_client.download_bytes("silver/recife/clima/estacoes/estacoes.parquet")
    df_estacoes = pd.read_parquet(io.BytesIO(conteudo_estacoes))
    assert set(df_estacoes["fonte"]) == {"INMET", "APAC"}

    conteudo_diario_2024 = minio_client.download_bytes(
        "silver/recife/clima/diario/ano=2024/clima_diario_2024.parquet"
    )
    df_diario = pd.read_parquet(io.BytesIO(conteudo_diario_2024))
    assert len(df_diario) == 2
    assert set(df_diario["fonte"]) == {"INMET", "APAC"}

    inmet_row = df_diario[df_diario["fonte"] == "INMET"].iloc[0]
    assert inmet_row["precipitacao_mm"] == 1.0  # 0 + 1.0

    chaves_manifest = minio_client.listar_chaves(
        "silver/recife/clima/_controle/manifest_silver_clima_"
    )
    assert len(chaves_manifest) == 1


def test_executar_transformacao_silver_climate_sem_dados_levanta_erro(minio_client: MinioClient):
    with pytest.raises(ValueError):
        executar_transformacao_silver_climate(minio_client)
