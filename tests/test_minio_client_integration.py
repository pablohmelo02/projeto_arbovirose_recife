"""Testes de integração do MinioClient contra um S3 simulado (moto), sem Docker.

Diferente dos testes de classificação e normalização (que são unitários e não
tocam rede), aqui o `MinioClient` real roda contra um servidor HTTP que fala o
protocolo S3 de verdade (moto), validando criação de bucket, upload, download
e listagem sem depender do MinIO estar no ar. É a forma de validar o cliente
S3 real enquanto o Docker não está disponível no ambiente de desenvolvimento.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient, MinioClientError


@pytest.fixture()
def minio_client() -> Iterator[MinioClient]:
    """Cliente contra um servidor moto novo, com bucket exclusivo por teste.

    O estado do moto é global ao processo (persiste entre instâncias do
    servidor), então cada teste usa um nome de bucket único para não herdar
    objetos gravados por outro teste.
    """
    server = ThreadedMotoServer(port=0)
    server.start()
    try:
        _, port = server.get_host_and_port()
        bucket = f"datalake-{uuid.uuid4().hex[:8]}"
        yield MinioClient(
            endpoint=f"http://127.0.0.1:{port}",
            access_key="admin",
            secret_key="admin123",
            bucket=bucket,
        )
    finally:
        server.stop()


def test_garantir_bucket_cria_quando_nao_existe_e_e_idempotente(minio_client: MinioClient):
    minio_client.garantir_bucket()
    minio_client.garantir_bucket()  # não deve levantar exceção na segunda chamada


def test_upload_e_download_bytes(minio_client: MinioClient):
    minio_client.garantir_bucket()
    conteudo = b"id;bairro\n1;boa viagem\n"

    tamanho = minio_client.upload_bytes("fatos/dengue/x.csv", conteudo)

    assert tamanho == len(conteudo)
    assert minio_client.download_bytes("fatos/dengue/x.csv") == conteudo


def test_upload_manifest_e_listar_chaves_por_prefixo(minio_client: MinioClient):
    minio_client.garantir_bucket()
    minio_client.upload_bytes("fatos/dengue/ano=2025/a.csv", b"a")
    minio_client.upload_bytes("fatos/zika/ano=2025/b.csv", b"b")
    minio_client.upload_manifest("_controle/manifest_teste.json", {"run_id": "teste"})

    assert minio_client.listar_chaves("fatos/dengue/") == ["fatos/dengue/ano=2025/a.csv"]
    assert set(minio_client.listar_chaves("")) == {
        "fatos/dengue/ano=2025/a.csv",
        "fatos/zika/ano=2025/b.csv",
        "_controle/manifest_teste.json",
    }


def test_download_bytes_chave_inexistente_levanta_erro(minio_client: MinioClient):
    minio_client.garantir_bucket()

    with pytest.raises(MinioClientError):
        minio_client.download_bytes("nao/existe.csv")
