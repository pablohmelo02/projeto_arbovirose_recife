import uuid
from typing import Any, Iterator

import pytest
from moto.server import ThreadedMotoServer

from src.clients.minio_client import MinioClient
from src.ingestion.territory_ingestion import executar_ingestao_territorio


class _FakeCkanClient:
    """Dublê do CkanClient: mesma interface, sem tocar a rede."""

    def __init__(self, recursos: list[dict[str, Any]], conteudo_por_id: dict[str, bytes]):
        self._recursos = recursos
        self._conteudo_por_id = conteudo_por_id

    def listar_recursos(self) -> list[dict[str, Any]]:
        return self._recursos

    def baixar_recurso(self, resource: dict[str, Any]) -> bytes:
        return self._conteudo_por_id[resource["id"]]


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


def test_executar_ingestao_territorio_baixa_e_classifica_apenas_bairros(minio_client: MinioClient):
    recursos = [
        {
            "id": "res-bairros",
            "name": "Limites dos Bairros - 2023",
            "format": "GeoJSON",
            "url": "http://x/bairros.geojson",
            "datastore_active": False,
        },
        {
            "id": "res-rpa",
            "name": "Limites por RPA - 2023",
            "format": "GeoJSON",
            "url": "http://x/rpa.geojson",
            "datastore_active": False,
        },
    ]
    conteudo_por_id = {"res-bairros": b'{"type": "FeatureCollection", "features": []}'}
    ckan_client = _FakeCkanClient(recursos, conteudo_por_id)

    manifest = executar_ingestao_territorio(
        ckan_client, minio_client, fonte="https://dados.recife.pe.gov.br", dataset="mapas-de-limites-e-divisoes-territoriais"
    )

    assert manifest["dominio"] == "territorio"
    assert manifest["quantidade_recursos_encontrados"] == 2
    assert manifest["quantidade_recursos_processados"] == 1  # RPA foi ignorado, fora do escopo
    assert manifest["sucessos"] == 1
    assert manifest["erros"] == 0

    entrada = manifest["recursos"][0]
    assert entrada["resource_id"] == "res-bairros"
    assert entrada["entidade"] == "bairro"
    assert entrada["status"] == "SUCCESS"

    # lineage: o run_id da execução aparece no object_key (ingestion=<run_id>/)
    assert f"ingestion={manifest['run_id']}/" in entrada["object_key"]
    assert entrada["object_key"].startswith("bronze/recife/territorio/bairro/")

    conteudo_gravado = minio_client.download_bytes(entrada["object_key"])
    assert conteudo_gravado == conteudo_por_id["res-bairros"]

    chave_manifest = f"bronze/recife/territorio/_controle/manifest_{manifest['run_id']}.json"
    assert minio_client.download_bytes(chave_manifest) is not None


def test_executar_ingestao_territorio_continua_apos_falha_de_download(minio_client: MinioClient):
    from src.clients.ckan_client import ResourceDownloadError

    class _CkanClientComFalha(_FakeCkanClient):
        def baixar_recurso(self, resource: dict[str, Any]) -> bytes:
            raise ResourceDownloadError("timeout simulado")

    recursos = [
        {
            "id": "res-bairros",
            "name": "Limites dos Bairros - 2023",
            "format": "GeoJSON",
            "url": "http://x/bairros.geojson",
            "datastore_active": False,
        },
    ]
    ckan_client = _CkanClientComFalha(recursos, {})

    manifest = executar_ingestao_territorio(
        ckan_client, minio_client, fonte="https://dados.recife.pe.gov.br", dataset="mapas-de-limites-e-divisoes-territoriais"
    )

    assert manifest["sucessos"] == 0
    assert manifest["erros"] == 1
    assert manifest["recursos"][0]["status"] == "ERROR"
    assert "timeout simulado" in manifest["recursos"][0]["erro"]
