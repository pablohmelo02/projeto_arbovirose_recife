import io
import uuid
import zipfile
from typing import Iterator

import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.ingestion.climate_ingestion import executar_ingestao_apac, executar_ingestao_inmet


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
