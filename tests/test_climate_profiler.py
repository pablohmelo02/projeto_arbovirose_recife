import json
import uuid
from typing import Iterator

import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.profiling.climate_profiler import (
    listar_todos_snapshots_apac,
    perfilar_cobertura_temporal_inmet,
    perfilar_estacao_inmet,
    perfilar_snapshot_apac,
    selecionar_ultima_ingestao_valida_inmet,
)


def _csv_inmet(dias: int = 3) -> bytes:
    cabecalho = [
        "REGIAO:;NE",
        "UF:;PE",
        "ESTACAO:;TESTE",
        "CODIGO (WMO):;A999",
        "LATITUDE:;-8,05",
        "LONGITUDE:;-34,90",
        "ALTITUDE:;10,5",
        "DATA DE FUNDACAO:;01/01/20",
        "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);UMIDADE RELATIVA DO AR, HORARIA (%);",
    ]
    linhas = list(cabecalho)
    for dia in range(1, dias + 1):
        linhas.append(f"2024/01/{dia:02d};0000 UTC;0;25,0;80;")
    return ("\n".join(linhas)).encode("latin-1")


def test_perfilar_estacao_inmet():
    perfil = perfilar_estacao_inmet("teste.csv", _csv_inmet(dias=3))

    assert perfil["estacao"] == "TESTE"
    assert perfil["codigo_wmo"] == "A999"
    assert perfil["quantidade_registros"] == 3
    assert perfil["dias_distintos"] == 3
    assert perfil["duplicados"] == 0


def test_perfilar_cobertura_temporal_sem_lacuna():
    perfil = perfilar_estacao_inmet("teste.csv", _csv_inmet(dias=3))
    cobertura = perfilar_cobertura_temporal_inmet(perfil)

    assert cobertura["dias_esperados"] == 3
    assert cobertura["dias_disponiveis"] == 3
    assert cobertura["cobertura_percentual"] == 100.0


def test_perfilar_cobertura_temporal_com_lacuna():
    # dias 1 e 3, faltando o dia 2 -> período esperado é 3 dias, disponíveis só 2
    linhas = _csv_inmet(dias=1).decode("latin-1").splitlines()
    linhas.append("2024/01/03;0000 UTC;0;25,0;80;")
    perfil = perfilar_estacao_inmet("teste.csv", ("\n".join(linhas)).encode("latin-1"))
    cobertura = perfilar_cobertura_temporal_inmet(perfil)

    assert cobertura["dias_esperados"] == 3
    assert cobertura["dias_disponiveis"] == 2
    assert round(cobertura["cobertura_percentual"], 2) == round(200 / 3, 2)


def _snapshot_apac(negativo: bool = False, sem_coordenada: bool = False) -> bytes:
    valor_24h = "-1.0" if negativo else "0.62"
    ponto = {
        "ponto": {
            "id": "1",
            "nome": "Teste",
            "latitude": None if sem_coordenada else "-8.0",
            "longitude": None if sem_coordenada else "-34.9",
        },
        "dados_monitorados": {"dados": [{"titulo": "24 Horas", "valor": valor_24h}]},
    }
    return json.dumps({"pontos": {"0": ponto}}).encode("utf-8")


def test_perfilar_snapshot_apac_normal():
    perfil = perfilar_snapshot_apac(_snapshot_apac())
    assert perfil["quantidade_estacoes"] == 1
    assert perfil["sem_coordenada"] == 0
    assert perfil["valores_precipitacao_negativos"] == 0


def test_perfilar_snapshot_apac_detecta_precipitacao_negativa():
    perfil = perfilar_snapshot_apac(_snapshot_apac(negativo=True))
    assert perfil["valores_precipitacao_negativos"] == 1


def test_perfilar_snapshot_apac_detecta_sem_coordenada():
    perfil = perfilar_snapshot_apac(_snapshot_apac(sem_coordenada=True))
    assert perfil["sem_coordenada"] == 1


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


def test_selecionar_ultima_ingestao_valida_inmet_usa_manifest_mais_recente(minio_client: MinioClient):
    minio_client.upload_manifest(
        "bronze/recife/clima/inmet/_controle/manifest_20250101T000000Z.json",
        {"run_id": "20250101T000000Z", "recursos": [{"nome_recurso": "a.csv", "status": "SUCCESS", "object_key": "antigo.csv", "ano": 2024}]},
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/inmet/_controle/manifest_20250601T000000Z.json",
        {"run_id": "20250601T000000Z", "recursos": [{"nome_recurso": "a.csv", "status": "SUCCESS", "object_key": "novo.csv", "ano": 2024}]},
    )

    selecionados = selecionar_ultima_ingestao_valida_inmet(minio_client)
    assert selecionados["a.csv"]["object_key"] == "novo.csv"


def test_listar_todos_snapshots_apac_nao_deduplica(minio_client: MinioClient):
    minio_client.upload_manifest(
        "bronze/recife/clima/apac/_controle/manifest_20250101T000000Z.json",
        {"run_id": "20250101T000000Z", "recursos": [{"nome_recurso": "pcds.json", "status": "SUCCESS", "object_key": "snap1.json"}]},
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/apac/_controle/manifest_20250601T000000Z.json",
        {"run_id": "20250601T000000Z", "recursos": [{"nome_recurso": "pcds.json", "status": "SUCCESS", "object_key": "snap2.json"}]},
    )

    snapshots = listar_todos_snapshots_apac(minio_client)
    # ao contrário do INMET, os DOIS instantâneos devem ser mantidos (cada um é um ponto no tempo)
    assert len(snapshots) == 2
    chaves = {s["object_key"] for s in snapshots}
    assert chaves == {"snap1.json", "snap2.json"}
