import io
import uuid
from typing import Iterator

import pandas as pd
import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.silver.pipeline import executar_transformacao_silver


@pytest.fixture()
def minio_client() -> Iterator[MinioClient]:
    server = ThreadedMotoServer(port=0)
    server.start()
    try:
        _, port = server.get_host_and_port()
        bucket = f"datalake-{uuid.uuid4().hex[:8]}"
        cliente = MinioClient(
            endpoint=f"http://127.0.0.1:{port}",
            access_key="admin",
            secret_key="admin123",
            bucket=bucket,
        )
        cliente.garantir_bucket()
        yield cliente
    finally:
        server.stop()


def _csv_dengue_2025() -> bytes:
    return (
        '"NU_NOTIFIC";"ID_AGRAVO";"DT_NOTIFIC";"NU_ANO";"NM_BAIRRO";"ID_BAIRRO"\n'
        '"1";"A90";"04/03/2025";"2025";"PINA";"24"\n'
        '"2";"A90";"05/03/2025";"2025";"PINA";"24"\n'
    ).encode("utf-8")


def _csv_zika_2021_contaminado() -> bytes:
    # Reproduz o problema real: recurso "Zika 2021" com codigo_agravo de
    # Chikungunya em todas as linhas.
    return (
        '"NU_NOTIFIC";"ID_AGRAVO";"DT_NOTIFIC";"NU_ANO";"NM_BAIRRO";"ID_BAIRRO"\n'
        '"10";"A92.0";"04/03/2021";"2021";"PINA";"24"\n'
        '"11";"A92.0";"05/03/2021";"2021";"PINA";"24"\n'
    ).encode("utf-8")


def _csv_bairro() -> bytes:
    return (
        '"Nº Localidade";"Nome Localidade";"Nome Município"\n'
        '"24";"PINA";"RECIFE"\n'
    ).encode("utf-8")


def _manifest_bronze() -> dict:
    return {
        "run_id": "20260101T000000Z",
        "recursos": [
            {
                "resource_id": "res-dengue-2025",
                "tipo": "fato",
                "entidade": "dengue",
                "ano": 2025,
                "status": "SUCCESS",
                "object_key": "bronze/fatos/dengue/ano=2025/res-dengue-2025.csv",
                "nome": "Casos de Dengue 2025",
            },
            {
                "resource_id": "res-zika-2021",
                "tipo": "fato",
                "entidade": "zika",
                "ano": 2021,
                "status": "SUCCESS",
                "object_key": "bronze/fatos/zika/ano=2021/res-zika-2021.csv",
                "nome": "Casos confirmados de Zika 2021",
            },
            {
                "resource_id": "res-bairro",
                "tipo": "dimensao",
                "entidade": "bairro",
                "ano": None,
                "status": "SUCCESS",
                "object_key": "bronze/dimensoes/bairro/res-bairro.csv",
                "nome": "Tabela de Bairros",
            },
        ],
    }


def _preparar_bronze(minio_client: MinioClient) -> None:
    minio_client.upload_bytes("bronze/fatos/dengue/ano=2025/res-dengue-2025.csv", _csv_dengue_2025())
    minio_client.upload_bytes("bronze/fatos/zika/ano=2021/res-zika-2021.csv", _csv_zika_2021_contaminado())
    minio_client.upload_bytes("bronze/dimensoes/bairro/res-bairro.csv", _csv_bairro())
    minio_client.upload_manifest(
        "bronze/recife/arboviroses/_controle/manifest_20260101T000000Z.json", _manifest_bronze()
    )


def test_executar_transformacao_silver_ponta_a_ponta(minio_client: MinioClient):
    _preparar_bronze(minio_client)

    manifest = executar_transformacao_silver(minio_client)

    assert manifest["total_linhas_validas"] == 2  # só o dengue_2025 é válido
    assert manifest["total_linhas_rejeitadas"] == 2  # zika_2021 contaminado, rejeitado inteiro
    assert len(manifest["arquivos_rejeitados_integralmente"]) == 1
    assert manifest["arquivos_rejeitados_integralmente"][0]["resource_id"] == "res-zika-2021"

    conteudo_parquet = minio_client.download_bytes(
        "silver/recife/arboviroses/fatos/arboviroses/ano=2025/arboviroses_2025.parquet"
    )
    df = pd.read_parquet(io.BytesIO(conteudo_parquet))
    assert len(df) == 2
    assert set(df["tipo_arbovirose"]) == {"DENGUE"}
    assert df["nome_bairro"].tolist() == ["PINA", "PINA"]

    # o ano de 2021 não deveria ter sido gravado: a única linha (zika) foi
    # rejeitada integralmente, então não há dados válidos para esse ano
    chaves_2021 = minio_client.listar_chaves("silver/recife/arboviroses/fatos/arboviroses/ano=2021/")
    assert chaves_2021 == []

    conteudo_rejeitados = minio_client.download_bytes(
        [k for k in minio_client.listar_chaves("silver/recife/arboviroses/_rejected/") if k.endswith(".csv")][0]
    )
    df_rejeitados = pd.read_csv(io.BytesIO(conteudo_rejeitados))
    assert len(df_rejeitados) == 2
    assert "rejeitado integralmente" in df_rejeitados["_motivo_rejeicao"].iloc[0]

    conteudo_bairro = minio_client.download_bytes("silver/recife/arboviroses/dimensoes/bairro/bairro.parquet")
    df_bairro = pd.read_parquet(io.BytesIO(conteudo_bairro))
    assert df_bairro.iloc[0]["nome_bairro"] == "PINA"

    chaves_manifest = minio_client.listar_chaves("silver/recife/arboviroses/_controle/manifest_silver_")
    assert len(chaves_manifest) == 1


def test_executar_transformacao_silver_sem_manifests_levanta_erro(minio_client: MinioClient):
    with pytest.raises(ValueError):
        executar_transformacao_silver(minio_client)
