"""Profiling do domínio Território (limites de bairros do Recife).

Lê a última ingestão válida do recurso geográfico direto do MinIO (nunca do
CKAN de novo — mesma estratégia de `bronze_profiler.py`), analisa schema,
CRS, tipos de geometria, nulos/inválidos/duplicados, bounding box, e faz o
cross-check dos códigos de bairro contra a dimensão epidemiológica `bairro`.

Não corrige nada — é só diagnóstico, para orientar o contrato Silver
(`src/silver/territorio.py`).
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import pandas as pd

from src.clients.minio_client import MinioClient
from src.ingestion.bronze_ingestion import PREFIXO_BRONZE as PREFIXO_BRONZE_ARBOVIROSES
from src.ingestion.bronze_validation import carregar_manifest
from src.ingestion.territory_ingestion import PREFIXO_BRONZE_TERRITORIO
from src.utils.csv_bruto import ler_csv_bruto

logger = logging.getLogger(__name__)


def listar_manifests_territorio(minio_client: MinioClient) -> list[str]:
    """Lista as chaves de todos os manifests de ingestão de território, em ordem cronológica."""
    prefixo_controle = f"{PREFIXO_BRONZE_TERRITORIO}/_controle/"
    prefixo_manifest = f"{prefixo_controle}manifest_"
    chaves = minio_client.listar_chaves(prefixo_controle)
    return sorted(chave for chave in chaves if chave.startswith(prefixo_manifest))


def selecionar_ultima_ingestao_valida_territorio(
    minio_client: MinioClient,
) -> dict[str, dict[str, Any]]:
    """Para cada `resource_id` de território, retorna a entrada SUCCESS mais recente.

    Mesma estratégia de `bronze_profiler.selecionar_ultima_ingestao_valida`:
    manifests lidos em ordem cronológica, última atribuição sempre vence.
    """
    melhor_por_resource: dict[str, dict[str, Any]] = {}

    for chave_manifest in listar_manifests_territorio(minio_client):
        manifest = carregar_manifest(minio_client, chave_manifest)
        run_id = manifest.get("run_id")
        for entrada in manifest.get("recursos", []):
            if entrada.get("status") != "SUCCESS":
                continue
            resource_id = entrada.get("resource_id")
            if not resource_id:
                continue
            melhor_por_resource[resource_id] = {**entrada, "_manifest_run_id": run_id}

    return melhor_por_resource


def perfilar_geojson(conteudo: bytes) -> dict[str, Any]:
    """Perfila um GeoJSON bruto: schema, CRS, geometria, nulos, duplicados, bounding box."""
    gdf = gpd.read_file(io.BytesIO(conteudo))

    geometrias_nulas = int(gdf.geometry.isna().sum())
    geom_validas = gdf.geometry.dropna()
    geometrias_invalidas = int((~geom_validas.is_valid).sum())
    tipos_geometria = sorted(geom_validas.geom_type.unique().tolist())

    colunas_nao_geometria = [c for c in gdf.columns if c != "geometry"]
    colunas_sempre_nulas = [c for c in colunas_nao_geometria if gdf[c].isna().all()]

    bounds = geom_validas.total_bounds.tolist() if not geom_validas.empty else None

    return {
        "quantidade_features": len(gdf),
        "colunas": colunas_nao_geometria,
        "colunas_sempre_nulas": colunas_sempre_nulas,
        "crs": str(gdf.crs) if gdf.crs else None,
        "tipos_geometria": tipos_geometria,
        "geometrias_nulas": geometrias_nulas,
        "geometrias_invalidas": geometrias_invalidas,
        "bounding_box": (
            {"minx": bounds[0], "miny": bounds[1], "maxx": bounds[2], "maxy": bounds[3]}
            if bounds
            else None
        ),
    }


def _carregar_dimensao_bairro_bronze(minio_client: MinioClient) -> Optional[pd.DataFrame]:
    """Lê a dimensão `bairro` mais recente da Bronze de arboviroses (para o cross-check).

    Usa diretamente a Bronze (não a Silver) para o profiling territorial não
    depender de a Silver de arboviroses já ter sido rodada — a Silver de
    dimensões só normaliza texto e remove duplicatas, não altera os códigos,
    então o conjunto de `codigo_bairro` é o mesmo em ambas.
    """
    prefixo_controle = f"{PREFIXO_BRONZE_ARBOVIROSES}/_controle/"
    prefixo_manifest = f"{prefixo_controle}manifest_"
    chaves = sorted(
        chave
        for chave in minio_client.listar_chaves(prefixo_controle)
        if chave.startswith(prefixo_manifest)
    )

    for chave_manifest in reversed(chaves):
        manifest = carregar_manifest(minio_client, chave_manifest)
        for entrada in manifest.get("recursos", []):
            if (
                entrada.get("tipo") == "dimensao"
                and entrada.get("entidade") == "bairro"
                and entrada.get("status") == "SUCCESS"
                and entrada.get("object_key")
            ):
                conteudo = minio_client.download_bytes(entrada["object_key"])
                return ler_csv_bruto(conteudo)

    return None


def cross_check_bairro(
    gdf: gpd.GeoDataFrame, df_dimensao_bairro: Optional[pd.DataFrame]
) -> dict[str, Any]:
    """Compara os códigos de bairro do GeoJSON com os da dimensão epidemiológica.

    Nunca faz matching aproximado por nome — só por `codigo_bairro`. Quando os
    códigos divergem (ex.: mesmo bairro com código diferente em cada fonte),
    isso vira parte do relatório, não é resolvido silenciosamente.
    """
    codigos_geo = {int(c): nome for c, nome in zip(gdf["CBAIRRCODI"], gdf["EBAIRRNOME"])}

    if df_dimensao_bairro is None:
        return {
            "disponivel": False,
            "motivo": "dimensão bairro da Bronze de arboviroses não encontrada "
            "(rode 'python -m src.main' antes do profiling territorial)",
        }

    coluna_codigo = df_dimensao_bairro.columns[0]
    coluna_nome = df_dimensao_bairro.columns[1]
    codigos_dim: dict[int, str] = {}
    for codigo, nome in zip(df_dimensao_bairro[coluna_codigo], df_dimensao_bairro[coluna_nome]):
        if codigo is None:
            continue
        try:
            codigos_dim[int(codigo)] = (nome or "").strip()
        except ValueError:
            continue

    set_geo = set(codigos_geo)
    set_dim = set(codigos_dim)

    sem_dimensao = sorted(set_geo - set_dim)
    sem_geometria = sorted(set_dim - set_geo)
    matches = sorted(set_geo & set_dim)

    # diagnóstico extra: nomes iguais só que sob código diferente (não usado
    # para o match oficial, só para facilitar uma decisão humana depois)
    nomes_geo_por_codigo_ausente = {c: codigos_geo[c] for c in sem_dimensao}
    nomes_dim_por_codigo_ausente = {c: codigos_dim[c] for c in sem_geometria}
    possiveis_correspondencias_por_nome = []
    for codigo_geo, nome_geo in nomes_geo_por_codigo_ausente.items():
        for codigo_dim, nome_dim in nomes_dim_por_codigo_ausente.items():
            if nome_geo.strip().upper() == nome_dim.strip().upper():
                possiveis_correspondencias_por_nome.append(
                    {
                        "nome": nome_geo,
                        "codigo_geo": codigo_geo,
                        "codigo_dimensao": codigo_dim,
                    }
                )

    total_dim = len(set_dim)
    return {
        "disponivel": True,
        "bairros_dimensao": total_dim,
        "bairros_geo": len(set_geo),
        "matches": len(matches),
        "sem_geometria": [{"codigo_bairro": c, "nome": codigos_dim[c]} for c in sem_geometria],
        "sem_dimensao": [{"codigo_bairro": c, "nome": codigos_geo[c]} for c in sem_dimensao],
        "percentual_match": round(100 * len(matches) / total_dim, 2) if total_dim else 0.0,
        "possiveis_correspondencias_por_nome_com_codigo_diferente": possiveis_correspondencias_por_nome,
    }


def executar_profiling_territorio(minio_client: MinioClient) -> dict[str, Any]:
    """Executa o profiling completo do domínio território e retorna o resultado."""
    recursos = selecionar_ultima_ingestao_valida_territorio(minio_client)
    if not recursos:
        raise ValueError(
            "Nenhum recurso SUCCESS encontrado nos manifests de território. "
            "Rode 'python -m src.ingest_territorio' antes do profiling."
        )

    resultado_por_recurso: list[dict[str, Any]] = []
    for entrada in recursos.values():
        if entrada.get("entidade") != "bairro":
            continue

        object_key = entrada["object_key"]
        conteudo = minio_client.download_bytes(object_key)
        perfil = perfilar_geojson(conteudo)

        gdf = gpd.read_file(io.BytesIO(conteudo))
        df_dimensao_bairro = _carregar_dimensao_bairro_bronze(minio_client)
        crosscheck = cross_check_bairro(gdf, df_dimensao_bairro)

        resultado_por_recurso.append(
            {
                "resource_id": entrada["resource_id"],
                "nome_recurso": entrada.get("nome_recurso"),
                "object_key": object_key,
                "perfil": perfil,
                "crosscheck_dimensao_bairro": crosscheck,
            }
        )

        logger.info(
            "Território perfilado: %d features, CRS=%s, geometrias inválidas=%d, nulas=%d",
            perfil["quantidade_features"], perfil["crs"],
            perfil["geometrias_invalidas"], perfil["geometrias_nulas"],
        )
        if crosscheck.get("disponivel"):
            logger.info(
                "Cross-check com dim bairro: %d/%d match (%.2f%%)",
                crosscheck["matches"], crosscheck["bairros_dimensao"], crosscheck["percentual_match"],
            )

    return {"recursos": resultado_por_recurso}


def gravar_relatorios(resultado: dict[str, Any], pasta_saida: Path) -> None:
    """Grava os relatórios de profiling territorial em `pasta_saida`."""
    pasta_saida.mkdir(parents=True, exist_ok=True)

    schema_linhas = []
    geometry_linhas = []
    crosscheck_linhas = []

    for item in resultado["recursos"]:
        perfil = item["perfil"]
        crosscheck = item["crosscheck_dimensao_bairro"]

        for coluna in perfil["colunas"]:
            schema_linhas.append(
                {
                    "resource_id": item["resource_id"],
                    "coluna": coluna,
                    "sempre_nula": coluna in perfil["colunas_sempre_nulas"],
                }
            )

        geometry_linhas.append(
            {
                "resource_id": item["resource_id"],
                "quantidade_features": perfil["quantidade_features"],
                "crs": perfil["crs"],
                "tipos_geometria": ",".join(perfil["tipos_geometria"]),
                "geometrias_nulas": perfil["geometrias_nulas"],
                "geometrias_invalidas": perfil["geometrias_invalidas"],
            }
        )

        if crosscheck.get("disponivel"):
            for grupo, registros in (
                ("sem_geometria", crosscheck["sem_geometria"]),
                ("sem_dimensao", crosscheck["sem_dimensao"]),
            ):
                for registro in registros:
                    crosscheck_linhas.append(
                        {
                            "resource_id": item["resource_id"],
                            "situacao": grupo,
                            "codigo_bairro": registro["codigo_bairro"],
                            "nome": registro["nome"],
                        }
                    )

    pd.DataFrame(schema_linhas).to_csv(pasta_saida / "schema.csv", index=False, encoding="utf-8")
    pd.DataFrame(geometry_linhas).to_csv(
        pasta_saida / "geometry_quality.csv", index=False, encoding="utf-8"
    )
    pd.DataFrame(crosscheck_linhas).to_csv(
        pasta_saida / "bairro_crosscheck.csv", index=False, encoding="utf-8"
    )

    (pasta_saida / "summary.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
