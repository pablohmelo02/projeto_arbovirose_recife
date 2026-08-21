"""Bronze → Silver do clima em grade (reanálise), com dois destinos.

## Por que dois destinos, e qual é o canônico

O destino **canônico** é o Data Lake (MinIO), igual a todas as outras
camadas do projeto: `silver/recife/clima/grade/...`.

O destino **local** (`data/silver/clima_grade/*.parquet`) existe porque o
ambiente de desenvolvimento deste projeto não tem MinIO/Docker: a Silver
anterior só existiu dentro de um processo `moto` efêmero, e reconstruir a
cadeia inteira hoje mudaria a janela do backfill CEMADEN (que é sempre
"últimos N dias a partir de agora"), alterando as colunas climáticas de
estação e, por consequência, invalidando os números do candidato de ML
já congelado. O artefato local é versionado exatamente para que a Gold
possa ser reconstruída sem infraestrutura e sem mexer no que está
congelado.

Os dois destinos usam **as mesmas funções de transformação**
(`src/silver/climate_grade.py`) — não há lógica duplicada, só I/O
diferente.

## Idempotência

A Silver é sempre **regravada por inteiro** a partir da última ingestão com
sucesso, nunca por append. Rodar duas vezes com a mesma janela produz o
mesmo arquivo (exceto `_processed_at`, que é metadado de execução).
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.clients.minio_client import MinioClient
from src.ingestion.gridded_climate_ingestion import PREFIXO_BRONZE_CLIMA_GRADE
from src.silver.climate_grade import (
    montar_mapeamento_bairro_celula,
    normalizar_clima_grade_diario,
    extrair_series_diarias_grade,
)
from src.silver.schema_climate_grade import GRADES

logger = logging.getLogger(__name__)

PREFIXO_SILVER_CLIMA_GRADE = "silver/recife/clima/grade"
CHAVE_SILVER_GRADE_DIARIO = f"{PREFIXO_SILVER_CLIMA_GRADE}/diario/clima_grade_diario.parquet"
CHAVE_SILVER_BAIRRO_CELULA = f"{PREFIXO_SILVER_CLIMA_GRADE}/bairro_celula/bairro_celula_grade.parquet"

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_LOCAL_SILVER_GRADE = RAIZ / "data" / "silver" / "clima_grade"
ARQUIVO_LOCAL_GRADE_DIARIO = PASTA_LOCAL_SILVER_GRADE / "clima_grade_diario.parquet"
ARQUIVO_LOCAL_BAIRRO_CELULA = PASTA_LOCAL_SILVER_GRADE / "bairro_celula_grade.parquet"
ARQUIVO_LOCAL_MANIFEST = PASTA_LOCAL_SILVER_GRADE / "_manifest.json"


def selecionar_ultima_ingestao_grade(minio_client: MinioClient) -> Optional[dict[str, Any]]:
    """Manifest da última execução de ingestão em grade com pelo menos um
    recurso de série baixado com sucesso. Mesmo padrão de "última versão
    válida" já usado para INMET/CEMADEN (`profiling/climate_profiler.py`)."""
    chaves = sorted(minio_client.listar_chaves(f"{PREFIXO_BRONZE_CLIMA_GRADE}/_controle/"))
    for chave in reversed(chaves):
        manifest = json.loads(minio_client.download_bytes(chave).decode("utf-8"))
        tem_serie = any(
            r.get("tipo") == "serie_diaria" and r.get("status") == "sucesso"
            for r in manifest.get("recursos", [])
        )
        if tem_serie:
            return manifest
    return None


def montar_silver_grade(
    payloads_por_grade: dict[str, bytes],
    mapa_bairro_celula: dict[tuple[str, str], str],
    df_centroides: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Núcleo puro compartilhado pelos dois destinos: payloads brutos por
    grade + mapa bairro→célula + centroides → (`silver_clima_grade_diario`,
    `silver_bairro_celula_grade`, métricas)."""
    partes = [
        extrair_series_diarias_grade(conteudo, grade=grade)
        for grade, conteudo in payloads_por_grade.items()
    ]
    df_bruto = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    df_diario, metricas = normalizar_clima_grade_diario(df_bruto)
    df_bairro_celula = montar_mapeamento_bairro_celula(
        df_centroides, df_diario, mapa_bairro_celula
    )
    metricas["bairros_mapeados"] = int(df_bairro_celula["codigo_bairro"].nunique())
    metricas["grades"] = sorted(df_diario["grade"].unique().tolist()) if len(df_diario) else []
    return df_diario, df_bairro_celula, metricas


def executar_transformacao_silver_grade_minio(
    minio_client: MinioClient, df_centroides: pd.DataFrame
) -> dict[str, Any]:
    """Destino canônico: lê a Bronze e grava a Silver no Data Lake."""
    minio_client.garantir_bucket()
    manifest_bronze = selecionar_ultima_ingestao_grade(minio_client)
    if manifest_bronze is None:
        raise RuntimeError(
            "nenhuma ingestão de clima em grade com sucesso encontrada na Bronze — "
            "rode 'python -m src.build_climate_grade' antes"
        )

    payloads: dict[str, bytes] = {}
    mapa: dict[tuple[str, str], str] = {}
    for recurso in manifest_bronze["recursos"]:
        if recurso.get("status") != "sucesso":
            continue
        conteudo = minio_client.download_bytes(recurso["object_key"])
        if recurso["tipo"] == "serie_diaria":
            payloads[recurso["grade"]] = conteudo
        elif recurso["tipo"] == "celulas":
            bloco = json.loads(conteudo.decode("utf-8"))
            for codigo, celula in bloco["bairro_para_celula"].items():
                mapa[(str(codigo), bloco["grade"])] = celula

    df_diario, df_bairro_celula, metricas = montar_silver_grade(payloads, mapa, df_centroides)

    minio_client.upload_bytes(
        CHAVE_SILVER_GRADE_DIARIO, _parquet_bytes(df_diario), content_type="application/octet-stream"
    )
    minio_client.upload_bytes(
        CHAVE_SILVER_BAIRRO_CELULA, _parquet_bytes(df_bairro_celula), content_type="application/octet-stream"
    )
    manifest = {
        "dominio": "clima",
        "camada": "silver",
        "fonte": "grade (reanalise)",
        "destino": "minio",
        "run_id_bronze": manifest_bronze["run_id"],
        "metricas": metricas,
    }
    minio_client.upload_manifest(f"{PREFIXO_SILVER_CLIMA_GRADE}/_controle/manifest.json", manifest)
    logger.info("Silver em grade gravada no Data Lake: %s", metricas)
    return manifest


def executar_transformacao_silver_grade_local(
    payloads_por_grade: dict[str, bytes],
    mapa_bairro_celula: dict[tuple[str, str], str],
    df_centroides: pd.DataFrame,
) -> dict[str, Any]:
    """Destino local (ambiente sem MinIO): grava os mesmos dois Parquets em
    `data/silver/clima_grade/`, de forma atômica."""
    from src.utils.io_atomico import escrever_json_atomico, escrever_parquet_atomico

    df_diario, df_bairro_celula, metricas = montar_silver_grade(
        payloads_por_grade, mapa_bairro_celula, df_centroides
    )
    if df_diario.empty:
        raise RuntimeError("Silver em grade vazia — nada gravado (destino anterior preservado)")

    escrever_parquet_atomico(ARQUIVO_LOCAL_GRADE_DIARIO, df_diario)
    escrever_parquet_atomico(ARQUIVO_LOCAL_BAIRRO_CELULA, df_bairro_celula)
    manifest = {
        "dominio": "clima",
        "camada": "silver",
        "fonte": "grade (reanalise)",
        "destino": "local",
        "arquivos": {
            "diario": str(ARQUIVO_LOCAL_GRADE_DIARIO.relative_to(RAIZ)),
            "bairro_celula": str(ARQUIVO_LOCAL_BAIRRO_CELULA.relative_to(RAIZ)),
        },
        "metricas": metricas,
    }
    escrever_json_atomico(ARQUIVO_LOCAL_MANIFEST, manifest)
    logger.info("Silver em grade gravada localmente: %s", metricas)
    return manifest


def carregar_silver_grade_local() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê os artefatos locais da Silver em grade. Levanta `FileNotFoundError`
    com instrução acionável se não existirem (nunca devolve DataFrame vazio
    disfarçado de sucesso)."""
    faltando = [
        str(p) for p in (ARQUIVO_LOCAL_GRADE_DIARIO, ARQUIVO_LOCAL_BAIRRO_CELULA) if not p.exists()
    ]
    if faltando:
        raise FileNotFoundError(
            f"Silver em grade ausente: {faltando}. Rode "
            "'python -m src.build_climate_grade --destino local' primeiro."
        )
    return (
        pd.read_parquet(ARQUIVO_LOCAL_GRADE_DIARIO),
        pd.read_parquet(ARQUIVO_LOCAL_BAIRRO_CELULA),
    )


def carregar_silver_grade_minio(minio_client: MinioClient) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_SILVER_GRADE_DIARIO))),
        pd.read_parquet(io.BytesIO(minio_client.download_bytes(CHAVE_SILVER_BAIRRO_CELULA))),
    )


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


__all__ = [
    "GRADES",
    "PREFIXO_SILVER_CLIMA_GRADE",
    "ARQUIVO_LOCAL_GRADE_DIARIO",
    "ARQUIVO_LOCAL_BAIRRO_CELULA",
    "carregar_silver_grade_local",
    "carregar_silver_grade_minio",
    "executar_transformacao_silver_grade_local",
    "executar_transformacao_silver_grade_minio",
    "montar_silver_grade",
    "selecionar_ultima_ingestao_grade",
]
