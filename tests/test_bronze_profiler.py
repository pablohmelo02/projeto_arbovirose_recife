import uuid
from typing import Iterator

import pandas as pd
import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.profiling.bronze_profiler import (
    construir_resumo_schemas,
    inferir_tipo_coluna,
    selecionar_ultima_ingestao_valida,
)


def test_inferir_tipo_coluna_inteiro():
    assert inferir_tipo_coluna(pd.Series(["1", "2", "3"])) == "inteiro"


def test_inferir_tipo_coluna_decimal():
    assert inferir_tipo_coluna(pd.Series(["1.0", "2.5"])) == "decimal"


def test_inferir_tipo_coluna_data():
    assert inferir_tipo_coluna(pd.Series(["04/03/2025", "05/03/2025"])) == "data"


def test_inferir_tipo_coluna_texto_quando_misto():
    assert inferir_tipo_coluna(pd.Series(["abc", "123"])) == "texto"


def test_inferir_tipo_coluna_vazio():
    assert inferir_tipo_coluna(pd.Series([None, None], dtype=object)) == "vazio"


def test_construir_resumo_schemas_colunas_comuns_e_exclusivas():
    perfil_colunas = [
        {"tipo": "fato", "entidade": "dengue", "ano": 2024, "coluna_normalizada": "A", "dtype_inferido": "inteiro"},
        {"tipo": "fato", "entidade": "dengue", "ano": 2024, "coluna_normalizada": "B", "dtype_inferido": "inteiro"},
        {"tipo": "fato", "entidade": "dengue", "ano": 2025, "coluna_normalizada": "A", "dtype_inferido": "texto"},
        {"tipo": "fato", "entidade": "zika", "ano": 2025, "coluna_normalizada": "A", "dtype_inferido": "inteiro"},
        {"tipo": "fato", "entidade": "zika", "ano": 2025, "coluna_normalizada": "C", "dtype_inferido": "inteiro"},
        {"tipo": "fato", "entidade": "chikungunya", "ano": 2025, "coluna_normalizada": "A", "dtype_inferido": "inteiro"},
    ]

    resumo = construir_resumo_schemas(perfil_colunas)

    assert resumo["colunas_comuns_as_tres_doencas"] == ["A"]
    assert resumo["colunas_presentes_em_todos_os_anos"]["dengue"] == ["A"]
    assert "B" in resumo["colunas_ausentes_em_algum_ano"]["dengue"]
    assert resumo["colunas_exclusivas_por_doenca"]["dengue"] == ["B"]
    assert resumo["colunas_exclusivas_por_doenca"]["zika"] == ["C"]
    assert resumo["colunas_com_tipo_aparente_inconsistente"] == {"A": ["inteiro", "texto"]}


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


def _manifest(run_id: str, recursos: list[dict]) -> dict:
    return {"run_id": run_id, "recursos": recursos}


def test_selecionar_ultima_ingestao_valida_usa_o_manifest_mais_recente(minio_client: MinioClient):
    minio_client.upload_manifest(
        "bronze/recife/arboviroses/_controle/manifest_20250101T000000Z.json",
        _manifest(
            "20250101T000000Z",
            [{"resource_id": "r1", "status": "SUCCESS", "object_key": "antigo.csv", "tipo": "fato"}],
        ),
    )
    minio_client.upload_manifest(
        "bronze/recife/arboviroses/_controle/manifest_20250601T000000Z.json",
        _manifest(
            "20250601T000000Z",
            [{"resource_id": "r1", "status": "SUCCESS", "object_key": "novo.csv", "tipo": "fato"}],
        ),
    )

    selecionados = selecionar_ultima_ingestao_valida(minio_client)

    assert selecionados["r1"]["object_key"] == "novo.csv"
    assert selecionados["r1"]["_manifest_run_id"] == "20250601T000000Z"


def test_selecionar_ultima_ingestao_valida_ignora_falhas(minio_client: MinioClient):
    minio_client.upload_manifest(
        "bronze/recife/arboviroses/_controle/manifest_20250101T000000Z.json",
        _manifest(
            "20250101T000000Z",
            [{"resource_id": "r1", "status": "SUCCESS", "object_key": "ok.csv", "tipo": "fato"}],
        ),
    )
    minio_client.upload_manifest(
        "bronze/recife/arboviroses/_controle/manifest_20250601T000000Z.json",
        _manifest(
            "20250601T000000Z",
            [{"resource_id": "r1", "status": "ERROR", "object_key": None, "tipo": "fato"}],
        ),
    )

    selecionados = selecionar_ultima_ingestao_valida(minio_client)

    # a execução mais recente falhou; a última SUCCESS ainda é a de janeiro
    assert selecionados["r1"]["object_key"] == "ok.csv"


def test_selecionar_ultima_ingestao_valida_sem_manifests_retorna_vazio(minio_client: MinioClient):
    assert selecionar_ultima_ingestao_valida(minio_client) == {}
