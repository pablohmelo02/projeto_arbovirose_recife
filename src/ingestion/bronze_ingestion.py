"""Orquestra a ingestão da camada Bronze: classificação, download e upload.

Fluxo por recurso: classificar → baixar → montar object key → upload → registrar
no manifest. Uma falha em um recurso não interrompe o processamento dos demais.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.clients.ckan_client import CkanApiError, CkanClient, ResourceDownloadError
from src.clients.minio_client import MinioClient, MinioClientError
from src.ingestion.classifier import classificar_recurso

logger = logging.getLogger(__name__)

PREFIXO_BRONZE = "bronze/recife/arboviroses"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _montar_object_key(
    tipo: str, entidade: str, ano: Optional[int], run_id: str, resource_id: str
) -> str:
    if tipo == "fato":
        particao_ano = f"ano={ano}" if ano is not None else "ano=desconhecido"
        return (
            f"{PREFIXO_BRONZE}/fatos/{entidade}/{particao_ano}"
            f"/ingestion={run_id}/{resource_id}.csv"
        )
    return f"{PREFIXO_BRONZE}/dimensoes/{entidade}/ingestion={run_id}/{resource_id}.csv"


def executar_ingestao_bronze(
    ckan_client: CkanClient,
    minio_client: MinioClient,
    fonte: str,
    dataset: str,
) -> dict[str, Any]:
    """Executa uma rodada completa de ingestão e retorna o manifest gerado."""
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": fonte,
        "dataset": dataset,
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "quantidade_recursos_encontrados": 0,
        "quantidade_recursos_processados": 0,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão (run_id=%s)", run_id)

    recursos = ckan_client.listar_recursos()
    manifest["quantidade_recursos_encontrados"] = len(recursos)

    minio_client.garantir_bucket()

    for resource in recursos:
        classificacao = classificar_recurso(resource)
        if classificacao is None:
            logger.info("Recurso ignorado (fora do escopo): %s", resource.get("name"))
            continue

        nome = resource.get("name") or ""
        resource_id = resource.get("id") or ""
        source_url = resource.get("url") or ""
        datastore_active = bool(resource.get("datastore_active"))

        logger.info(
            "%s identificado (%s/%s)", nome, classificacao.tipo, classificacao.entidade
        )

        entrada: dict[str, Any] = {
            "resource_id": resource_id,
            "nome": nome,
            "tipo": classificacao.tipo,
            "entidade": classificacao.entidade,
            "ano": classificacao.ano,
            "source_url": source_url,
            "datastore_active": datastore_active,
            "object_key": None,
            "bytes": 0,
            "status": "ERROR",
            "erro": None,
        }

        try:
            logger.info("Baixando recurso...")
            conteudo = ckan_client.baixar_recurso(resource)

            object_key = _montar_object_key(
                classificacao.tipo,
                classificacao.entidade,
                classificacao.ano,
                run_id,
                resource_id,
            )
            tamanho = minio_client.upload_bytes(object_key, conteudo)

            logger.info("Upload realizado")
            logger.info("s3://%s/%s", minio_client.bucket, object_key)

            entrada.update(
                {"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"}
            )
            manifest["sucessos"] += 1
        except (ResourceDownloadError, MinioClientError) as exc:
            logger.error("Falha no recurso '%s': %s", nome, exc)
            entrada["erro"] = str(exc)
            manifest["erros"] += 1
        except Exception as exc:  # salvaguarda: um recurso não pode travar o lote
            logger.error("Falha inesperada no recurso '%s': %s", nome, exc)
            entrada["erro"] = str(exc)
            manifest["erros"] += 1

        manifest["recursos"].append(entrada)
        manifest["quantidade_recursos_processados"] += 1

    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE}/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest: %s", exc)

    logger.info("Ingestão finalizada")
    logger.info("Sucessos: %d", manifest["sucessos"])
    logger.info("Erros: %d", manifest["erros"])

    return manifest
