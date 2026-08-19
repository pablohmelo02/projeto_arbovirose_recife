"""Orquestra a transformação Silver.

Lê a última ingestão válida de cada recurso direto da Bronze/MinIO (via
`src.profiling.bronze_profiler`, nunca baixa do CKAN de novo), aplica
`arboviroses.transformar_fato` e `dimensoes.transformar_dimensao`, e escreve
os resultados em Parquet no MinIO — com manifest de execução e área de
rejeitados, no mesmo espírito de rastreabilidade da Bronze.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.clients.minio_client import MinioClient
from src.profiling.bronze_profiler import selecionar_ultima_ingestao_valida
from src.silver.arboviroses import transformar_fato
from src.silver.dimensoes import ENTIDADES_DIMENSAO, transformar_dimensao
from src.utils.csv_bruto import CsvBrutoError, ler_csv_bruto

logger = logging.getLogger(__name__)

PREFIXO_SILVER = "silver/recife/arboviroses"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _df_para_parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


def _processar_fatos(
    minio_client: MinioClient, recursos: dict[str, dict[str, Any]]
) -> tuple[dict[int, list[pd.DataFrame]], list[pd.DataFrame], list[dict[str, Any]], list[dict[str, Any]]]:
    dfs_validos_por_ano: dict[int, list[pd.DataFrame]] = {}
    rejeitados: list[pd.DataFrame] = []
    metricas_fatos: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []

    for entrada in recursos.values():
        if entrada.get("tipo") != "fato":
            continue

        resource_id = entrada["resource_id"]
        entidade = entrada["entidade"]
        ano = entrada["ano"]
        nome = entrada.get("nome")

        try:
            conteudo = minio_client.download_bytes(entrada["object_key"])
            df_bruto = ler_csv_bruto(conteudo)
        except CsvBrutoError as exc:
            logger.error("Falha ao ler '%s' para a Silver: %s", nome, exc)
            falhas.append({"resource_id": resource_id, "nome": nome, "erro": str(exc)})
            continue

        df_valido, df_rejeitado, metricas = transformar_fato(
            df_bruto=df_bruto,
            tipo_arbovirose=entidade.upper(),
            resource_id=resource_id,
            ano_fonte=ano,
            ingestion_run_id=entrada.get("_manifest_run_id") or "",
        )
        metricas.update({"entidade": entidade, "ano": ano, "resource_id": resource_id, "nome": nome})
        metricas_fatos.append(metricas)

        logger.info(
            "%s %s: %d lidas, %d validas, %d rejeitadas%s",
            entidade,
            ano,
            metricas["linhas_lidas"],
            metricas["linhas_validas"],
            metricas["linhas_rejeitadas"],
            " (ARQUIVO REJEITADO INTEGRALMENTE)" if metricas["arquivo_rejeitado_integralmente"] else "",
        )

        if not df_valido.empty:
            dfs_validos_por_ano.setdefault(ano, []).append(df_valido)
        if not df_rejeitado.empty:
            rejeitados.append(df_rejeitado)

    return dfs_validos_por_ano, rejeitados, metricas_fatos, falhas


def _processar_dimensoes(
    minio_client: MinioClient, recursos: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metricas_dimensoes: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []

    for entrada in recursos.values():
        if entrada.get("tipo") != "dimensao" or entrada.get("entidade") not in ENTIDADES_DIMENSAO:
            continue

        entidade = entrada["entidade"]
        try:
            conteudo = minio_client.download_bytes(entrada["object_key"])
            df_bruto = ler_csv_bruto(conteudo)
        except CsvBrutoError as exc:
            logger.error("Falha ao ler dimensão '%s': %s", entidade, exc)
            falhas.append({"resource_id": entrada["resource_id"], "nome": entrada.get("nome"), "erro": str(exc)})
            continue

        df_conformado, metricas = transformar_dimensao(df_bruto, entidade)
        metricas_dimensoes.append(metricas)
        logger.info(
            "Dimensão %s: %d lidas, %d validas (%d sem chave, %d duplicados)",
            entidade,
            metricas["linhas_lidas"],
            metricas["linhas_validas"],
            metricas["rejeitados_sem_chave_natural"],
            metricas["rejeitados_duplicados"],
        )

        chave = f"{PREFIXO_SILVER}/dimensoes/{entidade}/{entidade}.parquet"
        minio_client.upload_bytes(
            chave, _df_para_parquet_bytes(df_conformado), content_type="application/octet-stream"
        )
        logger.info("Dimensão salva: s3://%s/%s", minio_client.bucket, chave)

    return metricas_dimensoes, falhas


def executar_transformacao_silver(minio_client: MinioClient) -> dict[str, Any]:
    """Executa uma rodada completa da transformação Silver e retorna o manifest gerado."""
    run_id = _gerar_run_id()
    logger.info("Iniciando transformação Silver (run_id=%s)", run_id)

    recursos = selecionar_ultima_ingestao_valida(minio_client)
    if not recursos:
        raise ValueError(
            "Nenhum recurso SUCCESS encontrado nos manifests da Bronze. "
            "Rode 'python -m src.main' antes da Silver."
        )

    minio_client.garantir_bucket()

    dfs_validos_por_ano, rejeitados, metricas_fatos, falhas_fatos = _processar_fatos(
        minio_client, recursos
    )

    for ano, dfs in sorted(dfs_validos_por_ano.items()):
        df_ano = pd.concat(dfs, ignore_index=True)
        chave = f"{PREFIXO_SILVER}/fatos/arboviroses/ano={ano}/arboviroses_{ano}.parquet"
        minio_client.upload_bytes(
            chave, _df_para_parquet_bytes(df_ano), content_type="application/octet-stream"
        )
        logger.info("Silver salva: s3://%s/%s (%d linhas)", minio_client.bucket, chave, len(df_ano))

    total_rejeitados = 0
    if rejeitados:
        df_rejeitados = pd.concat(rejeitados, ignore_index=True)
        total_rejeitados = len(df_rejeitados)
        chave_rejeitados = f"{PREFIXO_SILVER}/_rejected/rejeitados_{run_id}.csv"
        minio_client.upload_bytes(
            chave_rejeitados,
            df_rejeitados.to_csv(index=False).encode("utf-8"),
            content_type="text/csv",
        )
        logger.info(
            "Rejeitados salvos: s3://%s/%s (%d linhas)",
            minio_client.bucket, chave_rejeitados, total_rejeitados,
        )

    metricas_dimensoes, falhas_dimensoes = _processar_dimensoes(minio_client, recursos)

    manifest = {
        "run_id": run_id,
        "processado_em": datetime.now(timezone.utc).isoformat(),
        "metricas_fatos": metricas_fatos,
        "metricas_dimensoes": metricas_dimensoes,
        "falhas_leitura": falhas_fatos + falhas_dimensoes,
        "total_linhas_lidas": sum(m["linhas_lidas"] for m in metricas_fatos),
        "total_linhas_validas": sum(m["linhas_validas"] for m in metricas_fatos),
        "total_linhas_rejeitadas": total_rejeitados,
        "arquivos_rejeitados_integralmente": [
            {"entidade": m["entidade"], "ano": m["ano"], "resource_id": m["resource_id"]}
            for m in metricas_fatos
            if m["arquivo_rejeitado_integralmente"]
        ],
    }

    chave_manifest = f"{PREFIXO_SILVER}/_controle/manifest_silver_{run_id}.json"
    minio_client.upload_manifest(chave_manifest, manifest)
    logger.info("Manifest Silver salvo em s3://%s/%s", minio_client.bucket, chave_manifest)

    logger.info("Transformação Silver finalizada")
    logger.info(
        "Linhas lidas: %d | válidas: %d | rejeitadas: %d",
        manifest["total_linhas_lidas"], manifest["total_linhas_validas"], manifest["total_linhas_rejeitadas"],
    )

    return manifest
