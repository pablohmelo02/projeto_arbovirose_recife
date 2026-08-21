"""Gera `dashboard/data/_freshness.json` — a atualidade de cada conjunto de
dados do produto.

Uso:
    python -m src.generate_freshness              # consulta a fonte (CKAN)
    python -m src.generate_freshness --offline    # só o que dá para derivar do dado local

O dashboard **lê** este arquivo; nunca consulta a fonte em tempo de
renderização. Se a fonte estiver fora do ar, o campo
`ultima_atualizacao_fonte` fica nulo com `status=DESCONHECIDO` — nunca é
preenchido por suposição, e o restante do artefato continua utilizável
(modo degradado).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.clients.ckan_client import CkanApiError, CkanClient
from src.freshness import (
    avaliar_projecao_atual,
    freshness_clima_estacao,
    freshness_clima_grade,
    freshness_epidemiologia,
    freshness_modelo,
    freshness_territorio,
    montar_artefato_freshness,
)
from src.logging_config import configurar_logging
from src.ml.artifacts import ArtefatoAusenteError, carregar_metadados
from src.train_priority_model import MODEL_VERSION
from src.utils.io_atomico import escrever_json_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dashboard" / "data"
CAMINHO_GOLD = PASTA_DADOS / "gold_arboviroses_clima_bairro.parquet"
CAMINHO_FRESHNESS = PASTA_DADOS / "_freshness.json"
CAMINHO_MANIFEST_GRADE = PASTA_DADOS / "_gold_clima_grade.json"

CKAN_BASE_URL_PADRAO = "https://dados.recife.pe.gov.br"
CKAN_DATASET_EPIDEMIOLOGIA_PADRAO = "casos-de-dengue-zika-e-chikungunya"
CKAN_DATASET_TERRITORIO_PADRAO = "mapas-de-limites-e-divisoes-territoriais"

def consultar_metadata_modified(base_url: str, dataset: str, timeout: int = 30) -> Optional[dict[str, Any]]:
    """`metadata_modified` + periodicidade declarada do dataset no CKAN.

    Devolve `None` (nunca levanta) se a fonte estiver inacessível — a
    indisponibilidade da fonte não pode derrubar a geração do artefato."""
    try:
        cliente = CkanClient(base_url=base_url, dataset=dataset, timeout=timeout)
        recursos = cliente.listar_recursos()
    except CkanApiError as exc:
        logger.warning("CKAN inacessível para %r: %s", dataset, exc)
        return None

    ultima_modificacao = None
    for recurso in recursos:
        for campo in ("last_modified", "created"):
            valor = recurso.get(campo)
            if valor and (ultima_modificacao is None or str(valor) > str(ultima_modificacao)):
                ultima_modificacao = str(valor)
    return {
        "ultima_modificacao_recurso": ultima_modificacao,
        "n_recursos": len(recursos),
    }

def _periodicidade_declarada(base_url: str, dataset: str, timeout: int = 30) -> Optional[str]:
    """Periodicidade que a própria fonte declara (`extras` do CKAN). Sem
    isso, o painel não pode explicar por que o dado está atrasado."""
    import requests

    try:
        resposta = requests.get(
            f"{base_url.rstrip('/')}/api/3/action/package_show",
            params={"id": dataset}, timeout=timeout,
        )
        resposta.raise_for_status()
        resultado = resposta.json().get("result") or {}
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Não foi possível ler os extras do CKAN para %r: %s", dataset, exc)
        return None

    for extra in resultado.get("extras", []):
        chave = str(extra.get("key", "")).lower()
        if "frequ" in chave or "atualiza" in chave:
            return str(extra.get("value"))
    return resultado.get("metadata_modified")

def gerar_freshness(offline: bool = False) -> dict[str, Any]:
    if not CAMINHO_GOLD.exists():
        raise FileNotFoundError(
            f"'{CAMINHO_GOLD}' não encontrada — rode 'python -m src.export_dashboard_dataset'."
        )
    df_gold = pd.read_parquet(CAMINHO_GOLD)

    pipeline_em = None
    if "_processed_at" in df_gold.columns and len(df_gold):
        pipeline_em = str(df_gold["_processed_at"].iloc[0])

    base_url = os.getenv("CKAN_BASE_URL", CKAN_BASE_URL_PADRAO)
    dataset_epi = os.getenv("CKAN_DATASET", CKAN_DATASET_EPIDEMIOLOGIA_PADRAO)
    dataset_terr = os.getenv("CKAN_TERRITORIO_DATASET", CKAN_DATASET_TERRITORIO_PADRAO)

    fonte_epi: Optional[dict[str, Any]] = None
    fonte_terr: Optional[dict[str, Any]] = None
    periodicidade = None
    if not offline:
        fonte_epi = consultar_metadata_modified(base_url, dataset_epi)
        fonte_terr = consultar_metadata_modified(base_url, dataset_terr)
        periodicidade = _periodicidade_declarada(base_url, dataset_epi)

    fresh_epi = freshness_epidemiologia(
        df_gold,
        ultima_atualizacao_fonte=(fonte_epi or {}).get("ultima_modificacao_recurso"),
        pipeline_executado_em=pipeline_em,
    )
    if periodicidade:
        fresh_epi.detalhe["periodicidade_declarada_pela_fonte"] = periodicidade

    fresh_terr = freshness_territorio(
        df_gold, ultima_atualizacao_fonte=(fonte_terr or {}).get("ultima_modificacao_recurso")
    )
    fresh_estacao = freshness_clima_estacao(df_gold)
    fresh_grade = freshness_clima_grade(df_gold)
    if CAMINHO_MANIFEST_GRADE.exists():
        manifest = json.loads(CAMINHO_MANIFEST_GRADE.read_text(encoding="utf-8"))
        fresh_grade.pipeline_executado_em = manifest.get("antes", {}).get("_gerado_em")
        fresh_grade.detalhe["resolucao_graus"] = manifest.get("resolucao_graus")

    try:
        metadados_modelo = carregar_metadados(MODEL_VERSION)
    except (ArtefatoAusenteError, ValueError):
        metadados_modelo = None
    fresh_modelo = freshness_modelo(metadados_modelo)

    artefato = montar_artefato_freshness(
        [fresh_epi, fresh_terr, fresh_estacao, fresh_grade, fresh_modelo],
        projecao=avaliar_projecao_atual(fresh_epi),
    )
    artefato["consulta_a_fonte"] = "offline (nao consultada)" if offline else "realizada"
    return artefato

def main(argv: list[str] | None = None) -> int:
    configurar_logging()
    parser = argparse.ArgumentParser(description="Gera os metadados de atualidade dos dados.")
    parser.add_argument("--offline", action="store_true", help="não consultar a fonte (CKAN)")
    args = parser.parse_args(argv)

    try:
        artefato = gerar_freshness(offline=args.offline)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    escrever_json_atomico(CAMINHO_FRESHNESS, artefato)
    print(json.dumps(artefato, ensure_ascii=False, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
