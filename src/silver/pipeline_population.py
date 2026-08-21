"""Bronze → Silver de população por bairro.

## Por que só existe destino local (ao contrário de clima/território)

As fontes de população (`data/bronze/populacao/`) não são um feed que se
reingere periodicamente: são três documentos oficiais estáticos (Censo
2010 via CIEVS, Censo 2022 via IBGE, série municipal via SIDRA) que não
mudam de execução para execução — ver `src/ingestion/population_ingestion.py`
para como foram obtidos e como as duas fontes automatizáveis podem ser
re-baixadas se necessário. Por isso não há um "run_id" de ingestão nem um
destino MinIO: a Silver é recalculada a partir dos arquivos Bronze
versionados no próprio repositório, do mesmo jeito que
`data/silver/clima_grade/` (ver CLAUDE.md §19.1) resolve a ausência de
MinIO/Docker neste ambiente.

## Idempotência

A Silver é sempre regravada por inteiro a partir do Bronze, nunca por
append. Rodar duas vezes produz o mesmo arquivo (exceto `_processed_at`).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.population.reconstruction import carregar_dimensao_bairro, construir_serie_populacao
from src.silver.schema_population import COLUNAS_SILVER_POPULACAO_BAIRRO_ANO
from src.utils.io_atomico import escrever_json_atomico, escrever_parquet_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent.parent
CAMINHO_GOLD_PUBLICADA = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"

PASTA_BRONZE_POPULACAO = RAIZ / "data" / "bronze" / "populacao"
CAMINHO_BRONZE_CIEVS = PASTA_BRONZE_POPULACAO / "cievs_populacao_bairro_2010_2017.json"
CAMINHO_BRONZE_CENSO2022 = PASTA_BRONZE_POPULACAO / "censo2022_ibge_bairro_recife.csv"
CAMINHO_BRONZE_MUNICIPAL = PASTA_BRONZE_POPULACAO / "estimativas_municipais_ibge.json"

PASTA_SILVER_POPULACAO = RAIZ / "data" / "silver" / "populacao_bairro_ano"
ARQUIVO_SILVER_POPULACAO = PASTA_SILVER_POPULACAO / "populacao_bairro_ano.parquet"
ARQUIVO_MANIFEST_POPULACAO = PASTA_SILVER_POPULACAO / "_manifest.json"


def executar_transformacao_silver_populacao_local() -> dict[str, Any]:
    """Lê o Bronze local e grava `silver_populacao_bairro_ano` em
    `data/silver/populacao_bairro_ano/`, de forma atômica."""
    if not CAMINHO_GOLD_PUBLICADA.exists():
        raise FileNotFoundError(
            f"'{CAMINHO_GOLD_PUBLICADA}' não encontrada — rode "
            "'python -m src.export_dashboard_dataset' primeiro (fonte da dimensão territorial)."
        )
    faltando = [
        str(p)
        for p in (CAMINHO_BRONZE_CIEVS, CAMINHO_BRONZE_CENSO2022, CAMINHO_BRONZE_MUNICIPAL)
        if not p.exists()
    ]
    if faltando:
        raise FileNotFoundError(f"Bronze de população ausente: {faltando}")

    df_territorio = carregar_dimensao_bairro(CAMINHO_GOLD_PUBLICADA)
    df_populacao, metricas = construir_serie_populacao(
        CAMINHO_BRONZE_CIEVS, CAMINHO_BRONZE_CENSO2022, CAMINHO_BRONZE_MUNICIPAL, df_territorio
    )

    df_populacao = df_populacao[list(COLUNAS_SILVER_POPULACAO_BAIRRO_ANO)]

    if df_populacao["codigo_bairro"].nunique() != 94:
        raise ValueError(
            f"cobertura incompleta: {df_populacao['codigo_bairro'].nunique()}/94 bairros na Silver de população"
        )
    if (df_populacao["populacao"] <= 0).any():
        raise ValueError("população não-positiva encontrada na Silver de população")

    escrever_parquet_atomico(ARQUIVO_SILVER_POPULACAO, df_populacao)

    manifest = {
        "dominio": "territorio",
        "subdominio": "populacao_bairro_ano",
        "camada": "silver",
        "destino": "local",
        "arquivo": str(ARQUIVO_SILVER_POPULACAO.relative_to(RAIZ)),
        "metricas": metricas,
    }
    escrever_json_atomico(ARQUIVO_MANIFEST_POPULACAO, manifest)
    logger.info(
        "Silver de população gravada: %d bairros x %d anos",
        df_populacao["codigo_bairro"].nunique(),
        df_populacao["ano"].nunique(),
    )
    return manifest


def carregar_silver_populacao_local() -> pd.DataFrame:
    """Lê `silver_populacao_bairro_ano`. Levanta `FileNotFoundError` com
    instrução acionável se ainda não foi gerada (nunca devolve DataFrame
    vazio disfarçado de sucesso)."""
    if not ARQUIVO_SILVER_POPULACAO.exists():
        raise FileNotFoundError(
            f"'{ARQUIVO_SILVER_POPULACAO}' ausente — rode "
            "'python -m src.silver.pipeline_population' primeiro."
        )
    return pd.read_parquet(ARQUIVO_SILVER_POPULACAO)


__all__ = [
    "CAMINHO_BRONZE_CIEVS",
    "CAMINHO_BRONZE_CENSO2022",
    "CAMINHO_BRONZE_MUNICIPAL",
    "ARQUIVO_SILVER_POPULACAO",
    "carregar_silver_populacao_local",
    "executar_transformacao_silver_populacao_local",
]
