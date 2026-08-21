"""Carregamento (com cache) dos artefatos estáticos do dashboard.

O dashboard **nunca** lê o Data Lake/MinIO, nunca acessa a rede e nunca
treina modelo. Ele lê apenas os arquivos de `dashboard/data/`, gerados pelo
pipeline (`python -m src.update_recife_alerta`). É isso que permite
publicá-lo no Streamlit Community Cloud sem nenhuma infraestrutura.

## Obrigatórios × opcionais (modo degradado)

| artefato | ausência |
|---|---|
| `gold_arboviroses_clima_bairro.parquet` | erro explícito — sem ele não há painel |
| `bairro_geo.geojson` | só o mapa deixa de funcionar |
| `_freshness.json` | o bloco de atualização mostra "indeterminado" |
| `_priority_status.json`, `historical_priority_backtest.parquet` | o módulo experimental fica indisponível; o resto funciona |
| `latest_priority.parquet` | esperado ausente quando o portão de atualidade bloqueia |

Todo carregador opcional devolve `None` (nunca um DataFrame vazio
disfarçado de sucesso) para que a UI possa dizer com precisão o que falta.

## Cache

`st.cache_data` com a assinatura do arquivo (caminho + `mtime` + tamanho)
como parte da chave: se o pipeline regravar o artefato, o cache é
invalidado sem precisar reiniciar a aplicação. Sem isso, um `Parquet`
atualizado continuaria sendo servido da versão antiga.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ARQUIVO_GOLD = DATA_DIR / "gold_arboviroses_clima_bairro.parquet"
ARQUIVO_BAIRRO_GEO = DATA_DIR / "bairro_geo.geojson"
ARQUIVO_PROFILING = DATA_DIR / "_profiling_export.json"
ARQUIVO_FRESHNESS = DATA_DIR / "_freshness.json"
ARQUIVO_STATUS_PRIORIZACAO = DATA_DIR / "_priority_status.json"
ARQUIVO_BACKTEST = DATA_DIR / "historical_priority_backtest.parquet"
ARQUIVO_LATEST_PRIORITY = DATA_DIR / "latest_priority.parquet"
ARQUIVO_MANIFEST_GRADE = DATA_DIR / "_gold_clima_grade.json"
ARQUIVO_ULTIMA_ATUALIZACAO = DATA_DIR / "_ultima_atualizacao.json"
ARQUIVO_EVIDENCIA = DATA_DIR / "_evidence_summary.json"

COLUNAS_DATA = ("semana_epi_data_inicio", "semana_epi_data_fim")


class DatasetNaoEncontradoError(RuntimeError):
    """Artefato obrigatório ausente em `dashboard/data/`."""


def _assinatura(caminho: Path) -> Optional[tuple[str, int, int]]:
    """Identidade do arquivo para a chave de cache. `None` se não existir."""
    if not caminho.exists():
        return None
    stat = caminho.stat()
    return (str(caminho), int(stat.st_mtime_ns), int(stat.st_size))


@st.cache_data(show_spinner="Carregando dados epidemiológicos...")
def _ler_parquet(assinatura: tuple[str, int, int]) -> pd.DataFrame:
    df = pd.read_parquet(assinatura[0])
    for coluna in COLUNAS_DATA:
        if coluna in df.columns:
            df[coluna] = pd.to_datetime(df[coluna])
    return df


@st.cache_data(show_spinner=False)
def _ler_json(assinatura: tuple[str, int, int]) -> Any:
    return json.loads(Path(assinatura[0]).read_text(encoding="utf-8"))


def load_gold_data() -> pd.DataFrame:
    """Tabela analítica principal — obrigatória."""
    assinatura = _assinatura(ARQUIVO_GOLD)
    if assinatura is None:
        raise DatasetNaoEncontradoError(
            f"'{ARQUIVO_GOLD.name}' não encontrado em dashboard/data/. "
            "Rode 'python -m src.update_recife_alerta' antes de iniciar o dashboard."
        )
    return _ler_parquet(assinatura)


@st.cache_data(show_spinner="Carregando geometria dos bairros...")
def _ler_geojson(assinatura: tuple[str, int, int]) -> dict[str, Any]:
    return json.loads(Path(assinatura[0]).read_text(encoding="utf-8"))


def load_bairro_geojson() -> Optional[dict[str, Any]]:
    """Geometria oficial dos 94 bairros. `None` habilita o modo degradado
    (o painel funciona sem mapa)."""
    assinatura = _assinatura(ARQUIVO_BAIRRO_GEO)
    return None if assinatura is None else _ler_geojson(assinatura)


def load_export_profiling() -> dict[str, Any]:
    assinatura = _assinatura(ARQUIVO_PROFILING)
    return {} if assinatura is None else _ler_json(assinatura)


def load_freshness() -> Optional[dict[str, Any]]:
    assinatura = _assinatura(ARQUIVO_FRESHNESS)
    return None if assinatura is None else _ler_json(assinatura)


def load_priority_status() -> Optional[dict[str, Any]]:
    assinatura = _assinatura(ARQUIVO_STATUS_PRIORIZACAO)
    return None if assinatura is None else _ler_json(assinatura)


def load_priority_backtest() -> Optional[pd.DataFrame]:
    assinatura = _assinatura(ARQUIVO_BACKTEST)
    return None if assinatura is None else _ler_parquet(assinatura)


def load_latest_priority() -> Optional[pd.DataFrame]:
    """Priorização do período mais recente. Ausência é o estado **esperado**
    quando o portão de atualidade bloqueia (ver `_priority_status.json`)."""
    assinatura = _assinatura(ARQUIVO_LATEST_PRIORITY)
    return None if assinatura is None else _ler_parquet(assinatura)


def load_evidence_summary() -> Optional[dict[str, Any]]:
    """Resumo da validação estatística do candidato, copiado de
    `reports/ml/` pelo pipeline. `None` = a página experimental mostra
    apenas o backtest, sem a seção de desempenho."""
    assinatura = _assinatura(ARQUIVO_EVIDENCIA)
    return None if assinatura is None else _ler_json(assinatura)


def load_manifest_clima_grade() -> Optional[dict[str, Any]]:
    assinatura = _assinatura(ARQUIVO_MANIFEST_GRADE)
    return None if assinatura is None else _ler_json(assinatura)


def load_ultima_atualizacao() -> Optional[dict[str, Any]]:
    assinatura = _assinatura(ARQUIVO_ULTIMA_ATUALIZACAO)
    return None if assinatura is None else _ler_json(assinatura)


def inventario_artefatos() -> list[dict[str, Any]]:
    """Situação de cada artefato — usado na página de qualidade para que a
    ausência de um módulo seja sempre explicável ao usuário."""
    itens = [
        (ARQUIVO_GOLD, "Tabela analítica (bairro × semana × agravo)", True),
        (ARQUIVO_BAIRRO_GEO, "Geometria dos 94 bairros", True),
        (ARQUIVO_FRESHNESS, "Metadados de atualização dos dados", False),
        (ARQUIVO_STATUS_PRIORIZACAO, "Estado do módulo experimental", False),
        (ARQUIVO_BACKTEST, "Backtest histórico de priorização", False),
        (ARQUIVO_EVIDENCIA, "Resumo da validação estatística do modelo", False),
        (ARQUIVO_LATEST_PRIORITY, "Priorização do período mais recente", False),
        (ARQUIVO_MANIFEST_GRADE, "Manifest do bloco climático em grade", False),
        (ARQUIVO_PROFILING, "Proveniência da exportação", False),
        (ARQUIVO_ULTIMA_ATUALIZACAO, "Registro da última atualização", False),
    ]
    inventario = []
    for caminho, descricao, obrigatorio in itens:
        existe = caminho.exists()
        inventario.append(
            {
                "arquivo": caminho.name,
                "descricao": descricao,
                "obrigatorio": obrigatorio,
                "presente": existe,
                "tamanho_mb": round(caminho.stat().st_size / 1e6, 3) if existe else None,
            }
        )
    return inventario
