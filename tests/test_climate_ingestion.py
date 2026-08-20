import io
import json
import uuid
import zipfile
from typing import Iterator

import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.ingestion.climate_ingestion import (
    executar_ingestao_apac,
    executar_ingestao_cemaden,
    executar_ingestao_inmet,
)


class _FakeInmetClient:
    def __init__(self, zips_por_ano: dict[int, bytes], falhar_anos: set[int] | None = None):
        self._zips = zips_por_ano
        self._falhar = falhar_anos or set()

    def baixar_zip_ano(self, ano: int) -> bytes:
        if ano in self._falhar:
            from src.clients.inmet_client import InmetClientError

            raise InmetClientError("falha simulada")
        return self._zips[ano]

    def extrair_estacoes_uf(self, conteudo_zip: bytes, uf: str = "PE") -> list[tuple[str, bytes]]:
        marcador = f"_{uf}_"
        with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as zf:
            nomes = [n for n in zf.namelist() if marcador in n]
            return [(n, zf.read(n)) for n in nomes]


class _FakeApacClient:
    def __init__(self, conteudo: bytes):
        self._conteudo = conteudo

    def baixar_instantaneo_pcds(self) -> bytes:
        return self._conteudo


def _zip_com_estacoes(anos: list[int]) -> dict[int, bytes]:
    zips = {}
    for ano in anos:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr(f"INMET_NE_PE_A999_TESTE_01-01-{ano}_A_31-12-{ano}.CSV", "conteudo")
        zips[ano] = buffer.getvalue()
    return zips


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
        yield cliente
    finally:
        server.stop()


def test_executar_ingestao_inmet_grava_um_arquivo_por_estacao_e_ano(minio_client: MinioClient):
    inmet_client = _FakeInmetClient(_zip_com_estacoes([2023, 2024]))

    manifest = executar_ingestao_inmet(inmet_client, minio_client, anos=[2023, 2024])

    assert manifest["fonte"] == "INMET"
    assert manifest["sucessos"] == 2
    assert manifest["erros"] == 0
    assert len(manifest["recursos"]) == 2

    for entrada in manifest["recursos"]:
        assert entrada["status"] == "SUCCESS"
        # lineage: run_id aparece no object_key
        assert f"ingestion={manifest['run_id']}/" in entrada["object_key"]
        assert entrada["object_key"].startswith(f"bronze/recife/clima/inmet/ano={entrada['ano']}/")
        assert minio_client.download_bytes(entrada["object_key"]) == b"conteudo"

    chave_manifest = f"bronze/recife/clima/inmet/_controle/manifest_{manifest['run_id']}.json"
    assert minio_client.download_bytes(chave_manifest) is not None


def test_executar_ingestao_inmet_continua_apos_falha_de_um_ano(minio_client: MinioClient):
    inmet_client = _FakeInmetClient(_zip_com_estacoes([2024]), falhar_anos={2023})

    manifest = executar_ingestao_inmet(inmet_client, minio_client, anos=[2023, 2024])

    assert manifest["sucessos"] == 1
    assert manifest["erros"] == 1
    falha = next(r for r in manifest["recursos"] if r["ano"] == 2023)
    assert falha["status"] == "ERROR"
    assert "falha simulada" in falha["erro"]


def test_executar_ingestao_apac_grava_instantaneo(minio_client: MinioClient):
    apac_client = _FakeApacClient(b'{"pontos": {}}')

    manifest = executar_ingestao_apac(apac_client, minio_client)

    assert manifest["fonte"] == "APAC"
    assert manifest["sucessos"] == 1
    entrada = manifest["recursos"][0]
    assert entrada["status"] == "SUCCESS"
    assert f"ingestion={manifest['run_id']}/" in entrada["object_key"]
    assert minio_client.download_bytes(entrada["object_key"]) == b'{"pontos": {}}'


class _FakeCemadenClient:
    def __init__(
        self,
        conteudo_cadastro: bytes = b'{"features": []}',
        conteudo_status: bytes = b"[]",
        series_por_estacao: dict[str, bytes] | None = None,
        falhar_cadastro: bool = False,
        falhar_status: bool = False,
        estacoes_que_falham: set[str] | None = None,
    ):
        self._cadastro = conteudo_cadastro
        self._status = conteudo_status
        self._series = series_por_estacao or {}
        self._falhar_cadastro = falhar_cadastro
        self._falhar_status = falhar_status
        self._falham = estacoes_que_falham or set()

    def baixar_cadastro_estacoes(self, uf: str = "PE") -> bytes:
        if self._falhar_cadastro:
            from src.clients.cemaden_client import CemadenClientError

            raise CemadenClientError("falha simulada de cadastro")
        return self._cadastro

    def baixar_status_estacoes(self, uf: str = "PE") -> bytes:
        if self._falhar_status:
            from src.clients.cemaden_client import CemadenClientError

            raise CemadenClientError("falha simulada de status")
        return self._status

    def baixar_serie_horaria(self, id_estacao: str, horas: int) -> bytes:
        if id_estacao in self._falham:
            from src.clients.cemaden_client import CemadenClientError

            raise CemadenClientError(f"falha simulada na estacao {id_estacao}")
        return self._series.get(id_estacao, b'{"datas": [], "horarios": [], "acumulados": []}')


def _status_cemaden(registros: list[dict]) -> bytes:
    return json.dumps(registros).encode("utf-8")


def test_executar_ingestao_cemaden_busca_serie_so_das_candidatas_pluviometricas_grande_recife(
    minio_client: MinioClient,
):
    status = _status_cemaden(
        [
            {"idestacao": 1, "cidade": "RECIFE", "tipoestacao": 1},  # candidata valida
            {"idestacao": 2, "cidade": "OLINDA", "tipoestacao": 1},  # candidata valida (grande recife)
            {"idestacao": 3, "cidade": "RECIFE", "tipoestacao": 5},  # tipo errado, nao e pluviometrica
            {"idestacao": 4, "cidade": "GARANHUNS", "tipoestacao": 1},  # fora da grande recife
        ]
    )
    cemaden_client = _FakeCemadenClient(conteudo_status=status)

    manifest = executar_ingestao_cemaden(cemaden_client, minio_client, horas=24)

    assert manifest["fonte"] == "CEMADEN"
    tipos = [r["tipo"] for r in manifest["recursos"]]
    assert tipos.count("cadastro") == 1
    assert tipos.count("status") == 1
    ids_horario = sorted(r["id_estacao"] for r in manifest["recursos"] if r["tipo"] == "horario")
    assert ids_horario == ["1", "2"]
    assert manifest["sucessos"] == 4  # cadastro + status + 2 series horarias
    assert manifest["erros"] == 0


def test_executar_ingestao_cemaden_status_falha_nao_busca_serie_horaria(minio_client: MinioClient):
    cemaden_client = _FakeCemadenClient(falhar_status=True)

    manifest = executar_ingestao_cemaden(cemaden_client, minio_client, horas=24)

    assert manifest["sucessos"] == 1  # so o cadastro
    assert manifest["erros"] == 1  # status falhou
    tipos_horario = [r for r in manifest["recursos"] if r["tipo"] == "horario"]
    assert tipos_horario == []


def test_executar_ingestao_cemaden_continua_apos_falha_de_uma_estacao(minio_client: MinioClient):
    status = _status_cemaden(
        [
            {"idestacao": 10, "cidade": "RECIFE", "tipoestacao": 1},
            {"idestacao": 11, "cidade": "RECIFE", "tipoestacao": 1},
        ]
    )
    cemaden_client = _FakeCemadenClient(conteudo_status=status, estacoes_que_falham={"10"})

    manifest = executar_ingestao_cemaden(cemaden_client, minio_client, horas=24)

    falha = next(r for r in manifest["recursos"] if r.get("id_estacao") == "10")
    sucesso = next(r for r in manifest["recursos"] if r.get("id_estacao") == "11")
    assert falha["status"] == "ERROR"
    assert "falha simulada" in falha["erro"]
    assert sucesso["status"] == "SUCCESS"
    assert manifest["erros"] == 1
    assert manifest["sucessos"] == 3  # cadastro + status + estacao 11
