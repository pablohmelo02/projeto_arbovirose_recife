"""Log estruturado (com redação) e resiliência do pipeline.

Nenhum teste aqui acessa a rede: falhas de fonte são simuladas com
`responses`, e falhas de arquivo com arquivos temporários corrompidos de
propósito.
"""
from __future__ import annotations

import json
import logging

import pandas as pd
import pytest
import responses

from src.clients.ckan_client import CkanApiError, CkanClient
from src.clients.gridded_climate_client import (
    URL_ARCHIVE,
    GriddedClimateClientError,
    OpenMeteoArchiveClient,
)
from src.clients.inmet_client import InmetClient
from src.logging_config import (
    TEXTO_REDIGIDO,
    FiltroRedacao,
    FormatadorJson,
    configurar_logging,
    etapa,
    redigir,
    registrar_resultado_fonte,
)


# ===========================================================================
# Redação de segredo e dado pessoal
# ===========================================================================
@pytest.mark.parametrize(
    "entrada",
    [
        "MINIO_SECRET_KEY=abc123super",
        'minio_secret_key: "abc123super"',
        '{"secret_key": "abc123super"}',
        "password=abc123super",
        "token=abc123super",
        "Authorization: abc123super",
        "api_key = abc123super",
    ],
)
def test_redacao_remove_valor_de_chave_sensivel(entrada):
    saida = redigir(entrada)
    assert "abc123super" not in saida
    assert TEXTO_REDIGIDO in saida


def test_redacao_remove_credencial_de_url():
    saida = redigir("conectando em http://usuario:senha123@minio.local:9000/bucket")
    assert "senha123" not in saida
    assert "minio.local:9000/bucket" in saida, "o host deve continuar legível para diagnóstico"


@pytest.mark.parametrize("cpf", ["123.456.789-00", "12345678900"])
def test_redacao_mascara_cpf(cpf):
    assert cpf not in redigir(f"registro do paciente {cpf}")


def test_redacao_mascara_cns_de_15_digitos():
    assert "123456789012345" not in redigir("cns 123456789012345")


def test_redacao_preserva_texto_operacional():
    original = "fonte=CKAN | registros_obtidos=9187 | data_maxima=2025-12-31"
    assert redigir(original) == original


def test_filtro_redige_valor_vindo_de_argumento_de_formatacao(caplog):
    """O caso realista de vazamento: o valor sensível não está na mensagem,
    está num argumento (`logger.info("cfg=%s", config)`)."""
    logger = logging.getLogger("teste.redacao.args")
    logger.addFilter(FiltroRedacao())
    with caplog.at_level(logging.INFO, logger="teste.redacao.args"):
        logger.info("configuracao: minio_secret_key=%s", "segredoreal123")
    assert "segredoreal123" not in caplog.text
    assert TEXTO_REDIGIDO in caplog.text


def test_formatador_json_produz_uma_linha_valida_e_redigida():
    registro = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="password=segredo", args=(), exc_info=None,
    )
    linha = FormatadorJson().format(registro)
    bloco = json.loads(linha)
    assert bloco["nivel"] == "INFO"
    assert "segredo" not in bloco["mensagem"]


def test_configurar_logging_e_idempotente():
    """Vários entry points são orquestrados no mesmo processo — configurar
    duas vezes não pode duplicar handler (nem duplicar cada linha de log)."""
    raiz = configurar_logging()
    quantidade = len([h for h in raiz.handlers if getattr(h, "_recife_alerta", False)])
    configurar_logging()
    configurar_logging()
    depois = len([h for h in raiz.handlers if getattr(h, "_recife_alerta", False)])
    assert quantidade == depois == 1


def test_registrar_resultado_fonte_inclui_os_campos_exigidos(caplog):
    logger = logging.getLogger("teste.fonte")
    with caplog.at_level(logging.INFO, logger="teste.fonte"):
        registrar_resultado_fonte(
            logger, fonte="CKAN", obtidos=9187, rejeitados=3,
            motivos_rejeicao={"semana invalida": 3}, data_maxima="2025-12-31", duracao_s=1.5,
        )
    texto = caplog.text
    for esperado in ("fonte=CKAN", "registros_obtidos=9187", "registros_rejeitados=3",
                     "data_maxima=2025-12-31", "duracao_s=1.50", "semana invalida"):
        assert esperado in texto


def test_etapa_registra_inicio_fim_e_duracao(caplog):
    logger = logging.getLogger("teste.etapa")
    with caplog.at_level(logging.INFO, logger="teste.etapa"):
        with etapa(logger, "carga") as contexto:
            contexto["linhas"] = 42
    assert "etapa=carga | status=iniciou" in caplog.text
    assert "status=concluiu" in caplog.text
    assert "linhas=42" in caplog.text


def test_etapa_registra_falha_e_propaga(caplog):
    logger = logging.getLogger("teste.etapa.falha")
    with caplog.at_level(logging.ERROR, logger="teste.etapa.falha"):
        with pytest.raises(RuntimeError):
            with etapa(logger, "carga"):
                raise RuntimeError("fonte fora do ar")
    assert "status=falhou" in caplog.text
    assert "fonte fora do ar" in caplog.text, "o erro tem de ir para o log, não ser engolido"


# ===========================================================================
# Resiliência dos clientes HTTP
# ===========================================================================
@responses.activate
def test_ckan_erro_500_levanta_erro_de_dominio():
    responses.add(
        responses.GET, "https://exemplo.local/api/3/action/package_show", status=500
    )
    cliente = CkanClient(base_url="https://exemplo.local", dataset="x", timeout=5)
    with pytest.raises(CkanApiError):
        cliente.listar_recursos()


@responses.activate
def test_ckan_json_invalido_levanta_erro_de_dominio():
    responses.add(
        responses.GET, "https://exemplo.local/api/3/action/package_show",
        body="nao eh json", status=200,
    )
    cliente = CkanClient(base_url="https://exemplo.local", dataset="x", timeout=5)
    with pytest.raises(CkanApiError, match="JSON"):
        cliente.listar_recursos()


@responses.activate
def test_ckan_resposta_sem_recursos_levanta():
    responses.add(
        responses.GET, "https://exemplo.local/api/3/action/package_show",
        json={"success": True, "result": {}}, status=200,
    )
    cliente = CkanClient(base_url="https://exemplo.local", dataset="x", timeout=5)
    with pytest.raises(CkanApiError, match="resources"):
        cliente.listar_recursos()


@responses.activate
def test_grade_timeout_e_tratado_como_erro_de_dominio():
    from requests.exceptions import ConnectTimeout

    responses.add(responses.GET, URL_ARCHIVE, body=ConnectTimeout("estourou"))
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(GriddedClimateClientError):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9)], "2024-01-01", "2024-01-02", ("precipitation_sum",), "era5"
        )


@responses.activate
def test_grade_payload_de_erro_declarado_pela_api():
    responses.add(
        responses.GET, URL_ARCHIVE,
        json={"error": True, "reason": "data fora do intervalo"}, status=200,
    )
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(GriddedClimateClientError, match="data fora do intervalo"):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9)], "1800-01-01", "1800-01-02", ("precipitation_sum",), "era5"
        )


def test_inmet_rejeita_timeout_invalido():
    """Cliente sem timeout pode travar o pipeline indefinidamente."""
    for invalido in (0, -1, None):
        with pytest.raises(ValueError):
            InmetClient(timeout=invalido)


def test_cliente_de_grade_rejeita_tentativas_invalidas():
    with pytest.raises(ValueError):
        OpenMeteoArchiveClient(tentativas=0)


# ===========================================================================
# Resiliência de arquivo / artefato
# ===========================================================================
def test_dashboard_reporta_ausencia_de_dataset_com_instrucao(tmp_path, monkeypatch):
    import dashboard.utils.data_loader as loader

    monkeypatch.setattr(loader, "ARQUIVO_GOLD", tmp_path / "inexistente.parquet")
    with pytest.raises(loader.DatasetNaoEncontradoError, match="update_recife_alerta"):
        loader.load_gold_data()


def test_carregadores_opcionais_devolvem_none_em_vez_de_vazio(tmp_path, monkeypatch):
    import dashboard.utils.data_loader as loader

    for atributo in (
        "ARQUIVO_FRESHNESS", "ARQUIVO_STATUS_PRIORIZACAO", "ARQUIVO_BACKTEST",
        "ARQUIVO_LATEST_PRIORITY", "ARQUIVO_EVIDENCIA", "ARQUIVO_MANIFEST_GRADE",
        "ARQUIVO_ULTIMA_ATUALIZACAO", "ARQUIVO_BAIRRO_GEO", "ARQUIVO_PROFILING",
    ):
        monkeypatch.setattr(loader, atributo, tmp_path / f"{atributo}.ausente")

    assert loader.load_freshness() is None
    assert loader.load_priority_status() is None
    assert loader.load_priority_backtest() is None
    assert loader.load_latest_priority() is None
    assert loader.load_evidence_summary() is None
    assert loader.load_manifest_clima_grade() is None
    assert loader.load_ultima_atualizacao() is None
    assert loader.load_bairro_geojson() is None
    assert loader.load_export_profiling() == {}


def test_inventario_marca_obrigatorio_e_ausente(tmp_path, monkeypatch):
    import dashboard.utils.data_loader as loader

    monkeypatch.setattr(loader, "ARQUIVO_GOLD", tmp_path / "ausente.parquet")
    itens = {i["arquivo"]: i for i in loader.inventario_artefatos()}
    assert itens["ausente.parquet"]["obrigatorio"] is True
    assert itens["ausente.parquet"]["presente"] is False


def test_silver_em_grade_ausente_levanta_com_instrucao(tmp_path, monkeypatch):
    import src.silver.pipeline_climate_grade as pipeline

    monkeypatch.setattr(pipeline, "ARQUIVO_LOCAL_GRADE_DIARIO", tmp_path / "a.parquet")
    monkeypatch.setattr(pipeline, "ARQUIVO_LOCAL_BAIRRO_CELULA", tmp_path / "b.parquet")
    with pytest.raises(FileNotFoundError, match="build_climate_grade"):
        pipeline.carregar_silver_grade_local()


def test_silver_em_grade_vazia_nao_sobrescreve(tmp_path, monkeypatch):
    """Se a transformação produzir Silver vazia, nada é gravado."""
    import src.silver.pipeline_climate_grade as pipeline

    monkeypatch.setattr(pipeline, "ARQUIVO_LOCAL_GRADE_DIARIO", tmp_path / "a.parquet")
    monkeypatch.setattr(pipeline, "ARQUIVO_LOCAL_BAIRRO_CELULA", tmp_path / "b.parquet")
    monkeypatch.setattr(pipeline, "ARQUIVO_LOCAL_MANIFEST", tmp_path / "m.json")
    centroides = pd.DataFrame(
        [{"codigo_bairro": "1", "nome_bairro": "A", "centroide_lat": -8.0, "centroide_lon": -34.9}]
    )
    with pytest.raises(RuntimeError, match="vazia"):
        pipeline.executar_transformacao_silver_grade_local({}, {}, centroides)
    assert not (tmp_path / "a.parquet").exists()


def test_selecao_de_ingestao_em_grade_sem_manifest_devolve_none():
    import src.silver.pipeline_climate_grade as pipeline

    class MinioVazio:
        def listar_chaves(self, prefixo):  # noqa: D102
            return []

    assert pipeline.selecionar_ultima_ingestao_grade(MinioVazio()) is None
