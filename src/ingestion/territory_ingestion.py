"""Ingestão Bronze do domínio Território (limites de bairros do Recife).

Segue os mesmos princípios da Bronze de arboviroses (`bronze_ingestion.py`):
dado o mais próximo possível da fonte, `run_id` por execução, manifest,
tratamento de erro por recurso sem interromper o lote, logs claros. Reaproveita
`CkanClient` e `MinioClient` como estão — nenhuma lógica de HTTP/S3 é
duplicada aqui, só a orquestração específica do domínio território (que não
tem partição por ano, ao contrário de arboviroses).

Não reprojeta CRS, não renomeia campos, não corrige geometria, não calcula
área/centroide e não remove registros — isso pertence à Silver
(`src/silver/territorio.py`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.clients.ckan_client import CkanClient, ResourceDownloadError
from src.clients.minio_client import MinioClient, MinioClientError
from src.ingestion.territory_classifier import classificar_recurso_territorio

logger = logging.getLogger(__name__)

PREFIXO_BRONZE_TERRITORIO = "bronze/recife/territorio"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _extensao_arquivo(resource: dict[str, Any]) -> str:
    formato = (resource.get("format") or "").strip().lower()
    return "geojson" if formato in ("geojson", "json") else "dat"


def executar_ingestao_territorio(
    ckan_client: CkanClient,
    minio_client: MinioClient,
    fonte: str,
    dataset: str,
) -> dict[str, Any]:
    """Executa uma rodada de ingestão da Bronze território e retorna o manifest gerado."""
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": fonte,
        "dataset": dataset,
        "dominio": "territorio",
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "quantidade_recursos_encontrados": 0,
        "quantidade_recursos_processados": 0,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão de território (run_id=%s)", run_id)

    recursos = ckan_client.listar_recursos()
    manifest["quantidade_recursos_encontrados"] = len(recursos)

    minio_client.garantir_bucket()

    for resource in recursos:
        classificacao = classificar_recurso_territorio(resource)
        if classificacao is None:
            logger.info("Recurso ignorado (fora do escopo): %s", resource.get("name"))
            continue

        nome = resource.get("name") or ""
        resource_id = resource.get("id") or ""
        source_url = resource.get("url") or ""
        formato = resource.get("format") or ""
        datastore_active = bool(resource.get("datastore_active"))

        logger.info("%s identificado (territorio/%s)", nome, classificacao.entidade)

        entrada: dict[str, Any] = {
            "resource_id": resource_id,
            "nome_recurso": nome,
            "entidade": classificacao.entidade,
            "formato": formato,
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

            extensao = _extensao_arquivo(resource)
            object_key = (
                f"{PREFIXO_BRONZE_TERRITORIO}/{classificacao.entidade}/"
                f"ingestion={run_id}/{resource_id}.{extensao}"
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

    manifest_key = f"{PREFIXO_BRONZE_TERRITORIO}/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest: %s", exc)

    logger.info("Ingestão de território finalizada")
    logger.info("Sucessos: %d", manifest["sucessos"])
    logger.info("Erros: %d", manifest["erros"])

    return manifest
