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


def _cadastro_cemaden(estacoes: list[dict]) -> bytes:
    features = [
        {
            "type": "Feature",
            "properties": e,
            "geometry": {"type": "Point", "coordinates": [e.get("longitude"), e.get("latitude")]},
        }
        for e in estacoes
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


def _serie_horaria_cemaden(datas: list[str], horarios: list[str], acumulados: list[list]) -> bytes:
    return json.dumps({"datas": datas, "horarios": horarios, "acumulados": acumulados}).encode("utf-8")


def _preparar_bronze_cemaden_com_execucoes_sobrepostas(minio_client: MinioClient) -> None:
    """Duas execuções CEMADEN cobrindo janelas que se sobrepõem no mesmo dia
    para a mesma estação, com um conflito deliberado na hora '1h' (run2 deve
    vencer, por ser a execução mais recente)."""
    cadastro = _cadastro_cemaden(
        [
            {
                "codestacao": "261160620A", "nome": "Porto", "latitude": -8.054,
                "longitude": -34.873, "cidade": "RECIFE", "uf": "PE",
            }
        ]
    )
    status = json.dumps(
        [{"idestacao": 6846, "cidade": "RECIFE", "nomeestacao": "Porto", "tipoestacao": 1}]
    ).encode("utf-8")

    minio_client.upload_bytes("bronze/recife/clima/cemaden/cadastro/ingestion=run1/cadastro.json", cadastro)
    minio_client.upload_bytes("bronze/recife/clima/cemaden/status/ingestion=run1/status.json", status)

    horario_run1 = _serie_horaria_cemaden(
        datas=["19/08/2026"], horarios=["0h", "1h"], acumulados=[[1.0, 2.0]]
    )
    minio_client.upload_bytes(
        "bronze/recife/clima/cemaden/horario/ingestion=run1/6846.json", horario_run1
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/cemaden/_controle/manifest_run1.json",
        {
            "run_id": "run1",
            "recursos": [
                {"tipo": "cadastro", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/cadastro/ingestion=run1/cadastro.json"},
                {"tipo": "status", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/status/ingestion=run1/status.json"},
                {"tipo": "horario", "id_estacao": "6846", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/horario/ingestion=run1/6846.json"},
            ],
        },
    )

    horario_run2 = _serie_horaria_cemaden(
        datas=["19/08/2026"], horarios=["1h", "2h"], acumulados=[[5.0, 3.0]]
    )
    minio_client.upload_bytes(
        "bronze/recife/clima/cemaden/horario/ingestion=run2/6846.json", horario_run2
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/cemaden/_controle/manifest_run2.json",
        {
            "run_id": "run2",
            "recursos": [
                {"tipo": "horario", "id_estacao": "6846", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/horario/ingestion=run2/6846.json"},
            ],
        },
    )


def test_executar_transformacao_silver_climate_cemaden_deduplica_execucoes_sobrepostas(
    minio_client: MinioClient,
):
    _preparar_bronze_cemaden_com_execucoes_sobrepostas(minio_client)

    manifest = executar_transformacao_silver_climate(minio_client)

    assert manifest["total_estacoes"] == 1
    conteudo_diario = minio_client.download_bytes(
        "silver/recife/clima/diario/ano=2026/clima_diario_2026.parquet"
    )
    df_diario = pd.read_parquet(io.BytesIO(conteudo_diario))
    assert len(df_diario) == 1
    linha = df_diario.iloc[0]
    assert linha["fonte"] == "CEMADEN"
    # hora "1h": run2 (mais recente) vence com 5.0, nao 2.0 do run1 -> soma = 1.0 + 5.0 + 3.0
    assert linha["precipitacao_mm"] == 9.0
    assert linha["horas_validas_dia"] == 3


def test_executar_transformacao_silver_climate_cemaden_estacao_sem_leitura_real_nao_gera_diario(
    minio_client: MinioClient,
):
    """Caso 'Dois Unidos': estacao presente em cadastro+status, mas a serie
    horaria nao tem nenhum valor real -- deve aparecer em silver_estacao_climatica,
    mas nao gerar nenhuma linha em silver_clima_diario."""
    cadastro = _cadastro_cemaden(
        [
            {
                "codestacao": "261160606A", "nome": "Dois Unidos", "latitude": -7.98,
                "longitude": -34.95, "cidade": "RECIFE", "uf": "PE",
            }
        ]
    )
    status = json.dumps(
        [{"idestacao": 3254, "cidade": "RECIFE", "nomeestacao": "Dois Unidos", "tipoestacao": 1}]
    ).encode("utf-8")
    minio_client.upload_bytes("bronze/recife/clima/cemaden/cadastro/ingestion=run1/cadastro.json", cadastro)
    minio_client.upload_bytes("bronze/recife/clima/cemaden/status/ingestion=run1/status.json", status)
    horario_vazio = _serie_horaria_cemaden(datas=["19/08/2026"], horarios=["10h"], acumulados=[[None]])
    minio_client.upload_bytes(
        "bronze/recife/clima/cemaden/horario/ingestion=run1/3254.json", horario_vazio
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/cemaden/_controle/manifest_run1.json",
        {
            "run_id": "run1",
            "recursos": [
                {"tipo": "cadastro", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/cadastro/ingestion=run1/cadastro.json"},
                {"tipo": "status", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/status/ingestion=run1/status.json"},
                {"tipo": "horario", "id_estacao": "3254", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/horario/ingestion=run1/3254.json"},
            ],
        },
    )

    manifest = executar_transformacao_silver_climate(minio_client)

    assert manifest["total_estacoes"] == 1
    conteudo_estacoes = minio_client.download_bytes("silver/recife/clima/estacoes/estacoes.parquet")
    df_estacoes = pd.read_parquet(io.BytesIO(conteudo_estacoes))
    assert df_estacoes.iloc[0]["codigo_estacao"] == "3254"

    chaves_diario = minio_client.listar_chaves("silver/recife/clima/diario/")
    assert chaves_diario == []


def test_executar_transformacao_silver_climate_combina_backfill_historico_com_operacional(
    minio_client: MinioClient,
):
    """O backfill histórico (`src/ingestion/cemaden_backfill.py`) grava em um
    prefixo distinto (`horario_backfill/`) mas com o mesmo `tipo="horario"`
    no manifest -- a Silver deve acumular e deduplicar os dois exatamente
    como já faz entre execuções operacionais sobrepostas, sem precisar de
    nenhum código novo (ver docstring de `_processar_cemaden`)."""
    cadastro = _cadastro_cemaden(
        [
            {
                "codestacao": "261160620A", "nome": "Porto", "latitude": -8.054,
                "longitude": -34.873, "cidade": "RECIFE", "uf": "PE",
            }
        ]
    )
    status = json.dumps(
        [{"idestacao": 6846, "cidade": "RECIFE", "nomeestacao": "Porto", "tipoestacao": 1}]
    ).encode("utf-8")
    minio_client.upload_bytes("bronze/recife/clima/cemaden/cadastro/ingestion=run_op/cadastro.json", cadastro)
    minio_client.upload_bytes("bronze/recife/clima/cemaden/status/ingestion=run_op/status.json", status)

    # operacional: janela recente (48h), cobre 2026
    horario_operacional = _serie_horaria_cemaden(
        datas=["19/08/2026", "20/08/2026"], horarios=["23h", "0h"], acumulados=[[2.0, None], [None, 1.0]]
    )
    minio_client.upload_bytes(
        "bronze/recife/clima/cemaden/horario/ingestion=run_op/6846.json", horario_operacional
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/cemaden/_controle/manifest_run_op.json",
        {
            "run_id": "run_op",
            "dataset": "pcd-pluviometrica",
            "recursos": [
                {"tipo": "cadastro", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/cadastro/ingestion=run_op/cadastro.json"},
                {"tipo": "status", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/status/ingestion=run_op/status.json"},
                {"tipo": "horario", "id_estacao": "6846", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/horario/ingestion=run_op/6846.json"},
            ],
        },
    )

    # backfill historico: um dia de 2021, bem fora da janela operacional
    horario_backfill = _serie_horaria_cemaden(
        datas=["21/08/2021"], horarios=["12h"], acumulados=[[7.5]]
    )
    minio_client.upload_bytes(
        "bronze/recife/clima/cemaden/horario_backfill/ingestion=run_backfill/6846.json", horario_backfill
    )
    minio_client.upload_manifest(
        "bronze/recife/clima/cemaden/_controle/manifest_run_backfill.json",
        {
            "run_id": "run_backfill",
            "dataset": "pcd-pluviometrica-backfill-historico",
            "dias_profundidade": 1825,
            "recursos": [
                {"tipo": "horario", "id_estacao": "6846", "status": "SUCCESS", "object_key": "bronze/recife/clima/cemaden/horario_backfill/ingestion=run_backfill/6846.json"},
            ],
        },
    )

    manifest = executar_transformacao_silver_climate(minio_client)

    assert manifest["total_estacoes"] == 1

    df_2021 = pd.read_parquet(
        io.BytesIO(minio_client.download_bytes("silver/recife/clima/diario/ano=2021/clima_diario_2021.parquet"))
    )
    df_2026 = pd.read_parquet(
        io.BytesIO(minio_client.download_bytes("silver/recife/clima/diario/ano=2026/clima_diario_2026.parquet"))
    )

    assert len(df_2021) == 1
    assert df_2021.iloc[0]["precipitacao_mm"] == 7.5
    assert len(df_2026) == 2
    assert set(df_2026["precipitacao_mm"]) == {2.0, 1.0}
