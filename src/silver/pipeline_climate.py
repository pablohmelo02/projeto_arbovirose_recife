"""Orquestra a transformação Silver do domínio Clima (INMET + APAC).

Lê a Bronze de clima (INMET: última ingestão válida por arquivo de estação;
APAC: todos os instantâneos já coletados — ver `climate_profiler.py` para o
porquê dessa diferença), aplica `src/silver/climate.py` e grava Parquet no
MinIO: uma `silver_estacao_climatica` combinando as duas fontes, e uma
`silver_clima_diario` particionada por ano.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.clients.minio_client import MinioClient
from src.ingestion.climate_ingestion import PREFIXO_BRONZE_CLIMA
from src.profiling.climate_profiler import (
    listar_todos_snapshots_apac,
    selecionar_ultima_ingestao_valida_inmet,
)
from src.silver.climate import (
    agregar_diario_inmet,
    transformar_diario_apac,
    transformar_estacoes_apac,
    transformar_estacoes_inmet,
)
from src.utils.inmet_csv import InmetCsvError, ler_estacao_inmet

logger = logging.getLogger(__name__)

PREFIXO_SILVER_CLIMA = "silver/recife/clima"


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _df_para_parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


def _processar_inmet(
    minio_client: MinioClient,
) -> tuple[pd.DataFrame, dict[int, list[pd.DataFrame]], list[pd.DataFrame], list[dict[str, Any]]]:
    arquivos = selecionar_ultima_ingestao_valida_inmet(minio_client)

    metadados_por_estacao: dict[str, dict[str, str]] = {}
    diarios_por_ano: dict[int, list[pd.DataFrame]] = {}
    rejeitados: list[pd.DataFrame] = []
    metricas: list[dict[str, Any]] = []

    for entrada in arquivos.values():
        nome = entrada.get("nome_recurso")
        ano = entrada.get("ano")
        try:
            conteudo = minio_client.download_bytes(entrada["object_key"])
            metadados, df_horario = ler_estacao_inmet(conteudo)
        except InmetCsvError as exc:
            logger.error("Falha ao ler '%s': %s", nome, exc)
            continue

        codigo_estacao = metadados.get("CODIGO (WMO)", nome)
        metadados_por_estacao[nome] = metadados

        df_valido, df_rejeitado, metricas_arquivo = agregar_diario_inmet(
            df_horario, codigo_estacao=codigo_estacao, resource_id=nome,
            ingestion_run_id=entrada.get("_manifest_run_id") or "",
        )
        metricas_arquivo.update({"estacao": codigo_estacao, "ano": ano, "arquivo": nome})
        metricas.append(metricas_arquivo)

        logger.info(
            "INMET %s (%s): %d dias validos, %d rejeitados",
            codigo_estacao, ano, metricas_arquivo["linhas_validas"], metricas_arquivo["linhas_rejeitadas"],
        )

        if not df_valido.empty and ano is not None:
            diarios_por_ano.setdefault(ano, []).append(df_valido)
        if not df_rejeitado.empty:
            rejeitados.append(df_rejeitado)

    df_estacoes, metricas_estacoes = transformar_estacoes_inmet(metadados_por_estacao)
    metricas.append({"tipo": "estacoes_inmet", **metricas_estacoes})

    return df_estacoes, diarios_por_ano, rejeitados, metricas


def _processar_apac(
    minio_client: MinioClient,
) -> tuple[pd.DataFrame, dict[int, list[pd.DataFrame]], list[pd.DataFrame], list[dict[str, Any]]]:
    snapshots = listar_todos_snapshots_apac(minio_client)

    dfs_estacoes: list[pd.DataFrame] = []
    diarios_por_ano: dict[int, list[pd.DataFrame]] = {}
    rejeitados: list[pd.DataFrame] = []
    metricas: list[dict[str, Any]] = []

    for entrada in snapshots:
        run_id = entrada.get("_manifest_run_id") or ""
        try:
            conteudo = minio_client.download_bytes(entrada["object_key"])
        except Exception as exc:  # salvaguarda: um instantâneo não pode travar o lote
            logger.error("Falha ao ler instantâneo APAC (run_id=%s): %s", run_id, exc)
            continue

        df_estacoes, metricas_estacoes = transformar_estacoes_apac(conteudo, entrada["object_key"])
        dfs_estacoes.append(df_estacoes)

        df_valido, df_rejeitado, metricas_diario = transformar_diario_apac(
            conteudo, entrada["object_key"], run_id
        )
        metricas.append({"run_id": run_id, **metricas_diario})
        logger.info(
            "APAC (run_id=%s): %d validas, %d rejeitadas", run_id,
            metricas_diario["linhas_validas"], metricas_diario["linhas_rejeitadas"],
        )

        if not df_valido.empty:
            for ano, grupo in df_valido.groupby(df_valido["data"].dt.year):
                diarios_por_ano.setdefault(int(ano), []).append(grupo)
        if not df_rejeitado.empty:
            rejeitados.append(df_rejeitado)

    df_estacoes_final = (
        pd.concat(dfs_estacoes, ignore_index=True).drop_duplicates(subset=["fonte", "codigo_estacao"])
        if dfs_estacoes
        else pd.DataFrame()
    )

    return df_estacoes_final, diarios_por_ano, rejeitados, metricas


def executar_transformacao_silver_climate(minio_client: MinioClient) -> dict[str, Any]:
    """Executa uma rodada completa da transformação Silver de clima e retorna o manifest."""
    run_id = _gerar_run_id()
    logger.info("Iniciando transformação Silver clima (run_id=%s)", run_id)

    minio_client.garantir_bucket()

    df_estacoes_inmet, diarios_inmet, rejeitados_inmet, metricas_inmet = _processar_inmet(minio_client)
    df_estacoes_apac, diarios_apac, rejeitados_apac, metricas_apac = _processar_apac(minio_client)

    if df_estacoes_inmet.empty and df_estacoes_apac.empty:
        raise ValueError(
            "Nenhum dado climático encontrado na Bronze. "
            "Rode 'python -m src.ingest_climate' antes da Silver clima."
        )

    df_estacoes = pd.concat([df_estacoes_inmet, df_estacoes_apac], ignore_index=True)
    if not df_estacoes.empty:
        chave_estacoes = f"{PREFIXO_SILVER_CLIMA}/estacoes/estacoes.parquet"
        minio_client.upload_bytes(
            chave_estacoes, _df_para_parquet_bytes(df_estacoes), content_type="application/octet-stream"
        )
        logger.info("Silver estações salva: s3://%s/%s (%d linhas)", minio_client.bucket, chave_estacoes, len(df_estacoes))

    diarios_por_ano: dict[int, list[pd.DataFrame]] = {}
    for ano, dfs in diarios_inmet.items():
        diarios_por_ano.setdefault(ano, []).extend(dfs)
    for ano, dfs in diarios_apac.items():
        diarios_por_ano.setdefault(ano, []).extend(dfs)

    total_validas = 0
    for ano, dfs in sorted(diarios_por_ano.items()):
        df_ano = pd.concat(dfs, ignore_index=True)
        total_validas += len(df_ano)
        chave = f"{PREFIXO_SILVER_CLIMA}/diario/ano={ano}/clima_diario_{ano}.parquet"
        minio_client.upload_bytes(
            chave, _df_para_parquet_bytes(df_ano), content_type="application/octet-stream"
        )
        logger.info("Silver diário salvo: s3://%s/%s (%d linhas)", minio_client.bucket, chave, len(df_ano))

    total_rejeitadas = 0
    todos_rejeitados = rejeitados_inmet + rejeitados_apac
    if todos_rejeitados:
        df_rejeitados = pd.concat(todos_rejeitados, ignore_index=True)
        total_rejeitadas = len(df_rejeitados)
        chave_rejeitados = f"{PREFIXO_SILVER_CLIMA}/_rejected/rejeitados_{run_id}.csv"
        minio_client.upload_bytes(
            chave_rejeitados, df_rejeitados.to_csv(index=False).encode("utf-8"), content_type="text/csv"
        )
        logger.info(
            "Rejeitados clima salvos: s3://%s/%s (%d linhas)",
            minio_client.bucket, chave_rejeitados, total_rejeitadas,
        )

    manifest = {
        "run_id": run_id,
        "dominio": "clima",
        "processado_em": datetime.now(timezone.utc).isoformat(),
        "metricas_inmet": metricas_inmet,
        "metricas_apac": metricas_apac,
        "total_estacoes": len(df_estacoes),
        "total_linhas_validas": total_validas,
        "total_linhas_rejeitadas": total_rejeitadas,
    }

    chave_manifest = f"{PREFIXO_SILVER_CLIMA}/_controle/manifest_silver_clima_{run_id}.json"
    minio_client.upload_manifest(chave_manifest, manifest)
    logger.info("Manifest Silver clima salvo em s3://%s/%s", minio_client.bucket, chave_manifest)

    logger.info("Transformação Silver clima finalizada")
    logger.info("Estações: %d | Válidas: %d | Rejeitadas: %d", len(df_estacoes), total_validas, total_rejeitadas)

    return manifest
