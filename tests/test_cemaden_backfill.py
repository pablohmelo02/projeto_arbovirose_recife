import json
import uuid
from typing import Iterator

import pytest
from moto.server import ThreadedMotoServer

from src.clients.cemaden_client import CemadenClientError
from src.clients.minio_client import MinioClient
from src.ingestion.cemaden_backfill import (
    DATASET_BACKFILL,
    _baixar_com_retentativa,
    estacoes_com_backfill_suficiente,
    executar_backfill_cemaden,
)


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


class _FakeCemadenClient:
    """Simula o cliente CEMADEN: cada estação pode ter uma sequência de
    comportamentos (sucesso ou exceção) — uma entrada por tentativa. Registra
    todas as chamadas feitas, para permitir asserts sobre chamadas evitadas
    (checkpoint)."""

    def __init__(self, comportamento_por_estacao: dict[str, list]):
        self._comportamento = {k: list(v) for k, v in comportamento_por_estacao.items()}
        self.chamadas: list[tuple[str, int]] = []

    def baixar_serie_horaria(self, id_estacao: str, horas: int) -> bytes:
        self.chamadas.append((id_estacao, horas))
        fila = self._comportamento.get(id_estacao, [])
        if not fila:
            raise CemadenClientError(f"nenhum comportamento configurado para {id_estacao}")
        resultado = fila.pop(0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def _serie(datas: list[str], horarios: list[str], acumulados: list[list]) -> bytes:
    return json.dumps({"datas": datas, "horarios": horarios, "acumulados": acumulados}).encode("utf-8")


def test_executar_backfill_grava_uma_estacao_com_sucesso(minio_client: MinioClient, monkeypatch):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo = _serie(["01/01/2024"], ["10h"], [[3.5]])
    client = _FakeCemadenClient({"100": [conteudo]})

    manifest = executar_backfill_cemaden(client, minio_client, ["100"], dias_profundidade=30)

    assert manifest["dataset"] == DATASET_BACKFILL
    assert manifest["dias_profundidade"] == 30
    assert manifest["sucessos"] == 1
    assert manifest["erros"] == 0
    entrada = manifest["recursos"][0]
    assert entrada["status"] == "SUCCESS"
    assert "horario_backfill" in entrada["object_key"]
    assert minio_client.download_bytes(entrada["object_key"]) == conteudo
    # requisitou 30 dias em horas, uma unica chamada (sem chunking)
    assert client.chamadas == [("100", 30 * 24)]


def test_executar_backfill_retenta_apos_falha_e_registra_as_duas_tentativas(
    minio_client: MinioClient, monkeypatch
):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_TENTATIVAS_S", 0.0)
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo = _serie(["01/01/2024"], ["10h"], [[1.0]])
    client = _FakeCemadenClient(
        {"200": [CemadenClientError("Read timed out"), conteudo]}
    )

    manifest = executar_backfill_cemaden(client, minio_client, ["200"], dias_profundidade=365)

    entrada = manifest["recursos"][0]
    assert entrada["status"] == "SUCCESS"
    assert len(entrada["tentativas"]) == 2
    assert entrada["tentativas"][0]["sucesso"] is False
    assert entrada["tentativas"][1]["sucesso"] is True
    assert manifest["sucessos"] == 1
    assert manifest["erros"] == 0


def test_executar_backfill_estacao_falha_em_todas_as_tentativas_nao_derruba_lote(
    minio_client: MinioClient, monkeypatch
):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_TENTATIVAS_S", 0.0)
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo_ok = _serie(["01/01/2024"], ["10h"], [[1.0]])
    client = _FakeCemadenClient(
        {
            "300": [CemadenClientError("timeout 1"), CemadenClientError("timeout 2")],
            "301": [conteudo_ok],
        }
    )

    manifest = executar_backfill_cemaden(client, minio_client, ["300", "301"], dias_profundidade=365)

    falha = next(r for r in manifest["recursos"] if r["id_estacao"] == "300")
    sucesso = next(r for r in manifest["recursos"] if r["id_estacao"] == "301")
    assert falha["status"] == "ERROR"
    assert len(falha["tentativas"]) == 2
    assert sucesso["status"] == "SUCCESS"
    assert manifest["sucessos"] == 1
    assert manifest["erros"] == 1


def test_estacoes_com_backfill_suficiente_reflete_apenas_sucessos_do_dataset_backfill(
    minio_client: MinioClient, monkeypatch
):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo = _serie(["01/01/2024"], ["10h"], [[1.0]])
    client = _FakeCemadenClient({"400": [conteudo]})
    executar_backfill_cemaden(client, minio_client, ["400"], dias_profundidade=1095)

    resultado = estacoes_com_backfill_suficiente(minio_client, dias_profundidade=1095)
    assert resultado == {"400": 1095}

    # profundidade maior que a ja alcancada: nao deve contar como suficiente
    resultado_maior = estacoes_com_backfill_suficiente(minio_client, dias_profundidade=1825)
    assert resultado_maior.get("400", 0) < 1825


def test_executar_backfill_pula_estacao_com_checkpoint_suficiente(
    minio_client: MinioClient, monkeypatch
):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo = _serie(["01/01/2024"], ["10h"], [[1.0]])
    client_primeira_execucao = _FakeCemadenClient({"500": [conteudo]})
    executar_backfill_cemaden(client_primeira_execucao, minio_client, ["500"], dias_profundidade=1095)

    # segunda execucao: cliente sem nenhum comportamento configurado --
    # qualquer chamada real levantaria erro "nenhum comportamento configurado"
    client_segunda_execucao = _FakeCemadenClient({})
    manifest2 = executar_backfill_cemaden(
        client_segunda_execucao, minio_client, ["500"], dias_profundidade=1095
    )

    assert client_segunda_execucao.chamadas == []  # nenhuma chamada HTTP nova
    assert manifest2["puladas_checkpoint"] == 1
    assert manifest2["sucessos"] == 0
    entrada = manifest2["recursos"][0]
    assert entrada["status"] == "SKIPPED_CHECKPOINT"


def test_executar_backfill_nao_pula_quando_profundidade_pedida_e_maior_que_checkpoint(
    minio_client: MinioClient, monkeypatch
):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo_365 = _serie(["01/01/2024"], ["10h"], [[1.0]])
    conteudo_1095 = _serie(["01/01/2024"], ["10h"], [[1.0]])
    client1 = _FakeCemadenClient({"600": [conteudo_365]})
    executar_backfill_cemaden(client1, minio_client, ["600"], dias_profundidade=365)

    client2 = _FakeCemadenClient({"600": [conteudo_1095]})
    manifest2 = executar_backfill_cemaden(client2, minio_client, ["600"], dias_profundidade=1095)

    assert client2.chamadas == [("600", 1095 * 24)]
    assert manifest2["puladas_checkpoint"] == 0
    assert manifest2["sucessos"] == 1


def test_executar_backfill_pular_checkpoint_desabilitado_sempre_rebusca(
    minio_client: MinioClient, monkeypatch
):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_ESTACOES_S", 0.0)
    conteudo = _serie(["01/01/2024"], ["10h"], [[1.0]])
    client1 = _FakeCemadenClient({"700": [conteudo]})
    executar_backfill_cemaden(client1, minio_client, ["700"], dias_profundidade=1095)

    client2 = _FakeCemadenClient({"700": [conteudo]})
    manifest2 = executar_backfill_cemaden(
        client2, minio_client, ["700"], dias_profundidade=1095, pular_se_ja_existe=False
    )

    assert client2.chamadas == [("700", 1095 * 24)]
    assert manifest2["sucessos"] == 1
    assert manifest2["puladas_checkpoint"] == 0


def test_baixar_com_retentativa_retorna_none_apos_esgotar_tentativas(monkeypatch):
    monkeypatch.setattr("src.ingestion.cemaden_backfill.ESPERA_ENTRE_TENTATIVAS_S", 0.0)
    client = _FakeCemadenClient({"800": [CemadenClientError("a"), CemadenClientError("b")]})

    conteudo, tentativas = _baixar_com_retentativa(client, "800", horas=8760)

    assert conteudo is None
    assert len(tentativas) == 2
    assert all(t["sucesso"] is False for t in tentativas)
