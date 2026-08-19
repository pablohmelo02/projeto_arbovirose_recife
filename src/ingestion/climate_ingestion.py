"""Ingestão Bronze do domínio Clima (INMET + APAC).

Duas fontes com formas de acesso e granularidade de lineage bem diferentes
(ver `reports/climate_source_analysis/source_analysis.md`):

- **INMET**: ZIP anual estático (histórico real). Cada execução baixa um ou
  mais anos e grava um CSV por estação de Pernambuco encontrada no ZIP.
- **APAC**: API de telemetria em tempo real, sem histórico em lote
  disponível. Cada execução grava o instantâneo atual — o histórico é a
  soma de execuções ao longo do tempo, não um backfill.

Ambas seguem os mesmos princípios da Bronze de arboviroses/território:
preservação do dado original, `run_id`, manifest, `ingestion=<run_id>/`,
tratamento de erro que não interrompe o lote, logs claros. Cada fonte grava
seu próprio manifest, deixando claro qual delas o gerou.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.clients.apac_client import ApacClient, ApacClientError
from src.clients.inmet_client import InmetClient, InmetClientError
from src.clients.minio_client import MinioClient, MinioClientError

logger = logging.getLogger(__name__)

PREFIXO_BRONZE_CLIMA = "bronze/recife/clima"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def executar_ingestao_inmet(
    inmet_client: InmetClient,
    minio_client: MinioClient,
    anos: list[int],
    uf: str = "PE",
) -> dict[str, Any]:
    """Baixa o(s) ZIP(s) anual(is) do INMET e grava um CSV por estação de `uf` na Bronze."""
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": "INMET",
        "dataset": "dadoshistoricos",
        "dominio": "clima",
        "anos_solicitados": anos,
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão INMET (run_id=%s, anos=%s)", run_id, anos)
    minio_client.garantir_bucket()

    for ano in anos:
        try:
            logger.info("Baixando ZIP do INMET para %d...", ano)
            conteudo_zip = inmet_client.baixar_zip_ano(ano)
            estacoes = inmet_client.extrair_estacoes_uf(conteudo_zip, uf=uf)
        except InmetClientError as exc:
            logger.error("Falha ao processar o ano %d: %s", ano, exc)
            manifest["recursos"].append(
                {
                    "ano": ano,
                    "nome_recurso": f"{ano}.zip",
                    "status": "ERROR",
                    "erro": str(exc),
                    "object_key": None,
                    "bytes": 0,
                }
            )
            manifest["erros"] += 1
            continue

        logger.info("%d estação(ões) de %s encontradas no ZIP de %d", len(estacoes), uf, ano)

        for nome_arquivo, conteudo in estacoes:
            object_key = (
                f"{PREFIXO_BRONZE_CLIMA}/inmet/ano={ano}/ingestion={run_id}/{nome_arquivo}"
            )
            entrada: dict[str, Any] = {
                "ano": ano,
                "nome_recurso": nome_arquivo,
                "object_key": None,
                "bytes": 0,
                "status": "ERROR",
                "erro": None,
            }
            try:
                tamanho = minio_client.upload_bytes(object_key, conteudo)
                entrada.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
                manifest["sucessos"] += 1
                logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
            except MinioClientError as exc:
                logger.error("Falha no upload de '%s': %s", nome_arquivo, exc)
                entrada["erro"] = str(exc)
                manifest["erros"] += 1

            manifest["recursos"].append(entrada)

    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE_CLIMA}/inmet/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest INMET salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest INMET: %s", exc)

    logger.info("Ingestão INMET finalizada. Sucessos: %d | Erros: %d", manifest["sucessos"], manifest["erros"])
    return manifest


def executar_ingestao_apac(
    apac_client: ApacClient,
    minio_client: MinioClient,
) -> dict[str, Any]:
    """Baixa o instantâneo atual da rede de telemetria PCD da APAC e grava na Bronze."""
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": "APAC",
        "dataset": "pcd-pluviometria",
        "dominio": "clima",
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão APAC (run_id=%s)", run_id)
    minio_client.garantir_bucket()

    entrada: dict[str, Any] = {
        "nome_recurso": "pcds.json",
        "object_key": None,
        "bytes": 0,
        "status": "ERROR",
        "erro": None,
    }

    try:
        conteudo = apac_client.baixar_instantaneo_pcds()
        object_key = f"{PREFIXO_BRONZE_CLIMA}/apac/pcd/ingestion={run_id}/pcds.json"
        tamanho = minio_client.upload_bytes(object_key, conteudo)
        entrada.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
        manifest["sucessos"] += 1
        logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
    except (ApacClientError, MinioClientError) as exc:
        logger.error("Falha na ingestão APAC: %s", exc)
        entrada["erro"] = str(exc)
        manifest["erros"] += 1

    manifest["recursos"].append(entrada)
    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE_CLIMA}/apac/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest APAC salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest APAC: %s", exc)

    logger.info("Ingestão APAC finalizada. Sucessos: %d | Erros: %d", manifest["sucessos"], manifest["erros"])
    return manifest
