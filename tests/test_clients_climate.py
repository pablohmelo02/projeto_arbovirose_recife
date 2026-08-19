import io
import zipfile

import pytest
import responses

from src.clients.apac_client import ApacClient, ApacClientError
from src.clients.inmet_client import InmetClient, InmetClientError


def _zip_sintetico() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("INMET_NE_PE_A999_TESTE_01-01-2024_A_31-12-2024.CSV", "conteudo-pe")
        zf.writestr("INMET_CO_DF_A001_BRASILIA_01-01-2024_A_31-12-2024.CSV", "conteudo-df")
    return buffer.getvalue()


def test_extrair_estacoes_uf_filtra_por_uf():
    cliente = InmetClient()
    estacoes = cliente.extrair_estacoes_uf(_zip_sintetico(), uf="PE")

    assert len(estacoes) == 1
    nome, conteudo = estacoes[0]
    assert nome == "INMET_NE_PE_A999_TESTE_01-01-2024_A_31-12-2024.CSV"
    assert conteudo == b"conteudo-pe"


def test_extrair_estacoes_uf_zip_invalido_levanta_erro():
    cliente = InmetClient()
    with pytest.raises(InmetClientError):
        cliente.extrair_estacoes_uf(b"isso nao e um zip", uf="PE")


@responses.activate
def test_inmet_client_baixar_zip_ano_propaga_erro_http():
    responses.add(
        responses.GET,
        "https://portal.inmet.gov.br/uploads/dadoshistoricos/2024.zip",
        status=500,
    )
    cliente = InmetClient()
    with pytest.raises(InmetClientError):
        cliente.baixar_zip_ano(2024)


@responses.activate
def test_apac_client_baixar_instantaneo_sucesso():
    responses.add(
        responses.GET,
        "https://barramento.apac.pe.gov.br:443/BarramentoServicosApac/Servicos/Site/PainelMapaGoogle/ServicoMonitoramentoPCDs.php",
        json={"pontos": {}},
        status=200,
    )
    cliente = ApacClient()
    conteudo = cliente.baixar_instantaneo_pcds()
    assert b"pontos" in conteudo


@responses.activate
def test_apac_client_baixar_instantaneo_propaga_erro_http():
    responses.add(
        responses.GET,
        "https://barramento.apac.pe.gov.br:443/BarramentoServicosApac/Servicos/Site/PainelMapaGoogle/ServicoMonitoramentoPCDs.php",
        status=502,
    )
    cliente = ApacClient()
    with pytest.raises(ApacClientError):
        cliente.baixar_instantaneo_pcds()
