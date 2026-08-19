"""Profiling do domínio Clima (INMET + APAC).

As duas fontes têm semânticas de "última versão" bem diferentes:

- **INMET**: cada arquivo de estação é um recurso estável (um ano completo
  por estação) — igual a arboviroses/território, usamos a última ingestão
  SUCCESS por arquivo.
- **APAC**: cada execução grava um instantâneo novo (não uma nova versão do
  mesmo dado) — o profiling olha **todos** os instantâneos já coletados,
  porque cada um é um ponto de série temporal, não uma correção do anterior.

Não corrige nada — só diagnóstico, para orientar o contrato Silver
(`src/silver/schema_clima.py`).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.clients.minio_client import MinioClient
from src.ingestion.bronze_validation import carregar_manifest
from src.ingestion.climate_ingestion import PREFIXO_BRONZE_CLIMA
from src.utils.inmet_csv import InmetCsvError, ler_estacao_inmet

logger = logging.getLogger(__name__)


def _listar_manifests(minio_client: MinioClient, fonte: str) -> list[str]:
    prefixo_controle = f"{PREFIXO_BRONZE_CLIMA}/{fonte}/_controle/"
    prefixo_manifest = f"{prefixo_controle}manifest_"
    chaves = minio_client.listar_chaves(prefixo_controle)
    return sorted(chave for chave in chaves if chave.startswith(prefixo_manifest))


def selecionar_ultima_ingestao_valida_inmet(minio_client: MinioClient) -> dict[str, dict[str, Any]]:
    """Para cada arquivo de estação (por nome), retorna a entrada SUCCESS mais recente."""
    melhor_por_arquivo: dict[str, dict[str, Any]] = {}

    for chave_manifest in _listar_manifests(minio_client, "inmet"):
        manifest = carregar_manifest(minio_client, chave_manifest)
        run_id = manifest.get("run_id")
        for entrada in manifest.get("recursos", []):
            if entrada.get("status") != "SUCCESS":
                continue
            nome = entrada.get("nome_recurso")
            if not nome:
                continue
            melhor_por_arquivo[nome] = {**entrada, "_manifest_run_id": run_id}

    return melhor_por_arquivo


def listar_todos_snapshots_apac(minio_client: MinioClient) -> list[dict[str, Any]]:
    """Retorna TODAS as entradas SUCCESS de todos os manifests da APAC (não deduplicado)."""
    snapshots: list[dict[str, Any]] = []

    for chave_manifest in _listar_manifests(minio_client, "apac"):
        manifest = carregar_manifest(minio_client, chave_manifest)
        run_id = manifest.get("run_id")
        for entrada in manifest.get("recursos", []):
            if entrada.get("status") != "SUCCESS":
                continue
            snapshots.append({**entrada, "_manifest_run_id": run_id})

    return snapshots


def perfilar_estacao_inmet(nome_arquivo: str, conteudo: bytes) -> dict[str, Any]:
    """Perfila um CSV de estação do INMET: metadados, período, frequência, nulos."""
    metadados, df = ler_estacao_inmet(conteudo)

    datas = pd.to_datetime(df["Data"], format="%Y/%m/%d", errors="coerce")

    colunas_numericas = [
        c for c in df.columns if c not in ("Data", "Hora UTC")
    ]
    nulos = {
        coluna: {
            "quantidade_null": int(df[coluna].isna().sum()),
            "percentual_null": round(100 * df[coluna].isna().sum() / len(df), 2) if len(df) else 0.0,
        }
        for coluna in colunas_numericas
    }

    return {
        "nome_arquivo": nome_arquivo,
        "estacao": metadados.get("ESTACAO"),
        "codigo_wmo": metadados.get("CODIGO (WMO)"),
        "uf": metadados.get("UF"),
        "latitude": metadados.get("LATITUDE"),
        "longitude": metadados.get("LONGITUDE"),
        "altitude": metadados.get("ALTITUDE"),
        "data_fundacao": metadados.get("DATA DE FUNDACAO"),
        "quantidade_registros": len(df),
        "periodo_min": str(datas.min()) if datas.notna().any() else None,
        "periodo_max": str(datas.max()) if datas.notna().any() else None,
        "dias_distintos": int(datas.dt.date.nunique()) if datas.notna().any() else 0,
        "frequencia": "horaria",
        "duplicados": int(df.duplicated(subset=["Data", "Hora UTC"]).sum()),
        "colunas": colunas_numericas,
        "nulos_por_coluna": nulos,
    }


def perfilar_cobertura_temporal_inmet(perfil: dict[str, Any]) -> dict[str, Any]:
    """Calcula a lacuna entre dias esperados (todo o período) e dias com pelo menos 1 registro."""
    if not perfil["periodo_min"] or not perfil["periodo_max"]:
        return {"dias_esperados": 0, "dias_disponiveis": 0, "cobertura_percentual": 0.0}

    inicio = pd.Timestamp(perfil["periodo_min"]).normalize()
    fim = pd.Timestamp(perfil["periodo_max"]).normalize()
    dias_esperados = (fim - inicio).days + 1
    dias_disponiveis = perfil["dias_distintos"]

    return {
        "dias_esperados": dias_esperados,
        "dias_disponiveis": dias_disponiveis,
        "cobertura_percentual": round(100 * dias_disponiveis / dias_esperados, 2) if dias_esperados else 0.0,
    }


def perfilar_snapshot_apac(conteudo: bytes) -> dict[str, Any]:
    """Perfila um instantâneo da rede PCD da APAC: estações, coordenadas, valores suspeitos."""
    dados = json.loads(conteudo.decode("utf-8", errors="replace"))
    pontos = dict(dados.get("pontos", {}))
    pontos.pop("metadados", None)

    estacoes = []
    valores_negativos = 0
    sem_coordenada = 0

    for ponto in pontos.values():
        info = ponto.get("ponto", {})
        lat = info.get("latitude")
        lon = info.get("longitude")
        if lat is None or lon is None:
            sem_coordenada += 1

        valor_24h = None
        for item in ponto.get("dados_monitorados", {}).get("dados", []):
            if item.get("titulo") == "24 Horas":
                try:
                    valor_24h = float(str(item.get("valor", "")).replace(",", "."))
                except ValueError:
                    valor_24h = None

        if valor_24h is not None and valor_24h < 0:
            valores_negativos += 1

        estacoes.append(
            {
                "id": info.get("id"),
                "nome": info.get("nome"),
                "latitude": lat,
                "longitude": lon,
                "precipitacao_24h_mm": valor_24h,
            }
        )

    return {
        "quantidade_estacoes": len(estacoes),
        "sem_coordenada": sem_coordenada,
        "valores_precipitacao_negativos": valores_negativos,
        "estacoes": estacoes,
    }


def executar_profiling_clima(minio_client: MinioClient) -> dict[str, Any]:
    """Executa o profiling completo do domínio clima (INMET + APAC)."""
    resultado: dict[str, Any] = {"inmet": [], "apac": []}

    arquivos_inmet = selecionar_ultima_ingestao_valida_inmet(minio_client)
    for entrada in arquivos_inmet.values():
        try:
            conteudo = minio_client.download_bytes(entrada["object_key"])
            perfil = perfilar_estacao_inmet(entrada["nome_recurso"], conteudo)
        except InmetCsvError as exc:
            logger.error("Falha ao perfilar '%s': %s", entrada.get("nome_recurso"), exc)
            continue
        perfil["cobertura_temporal"] = perfilar_cobertura_temporal_inmet(perfil)
        perfil["ano"] = entrada.get("ano")
        resultado["inmet"].append(perfil)
        logger.info(
            "INMET perfilado: %s (%d registros, cobertura %.1f%%)",
            perfil["estacao"], perfil["quantidade_registros"], perfil["cobertura_temporal"]["cobertura_percentual"],
        )

    snapshots_apac = listar_todos_snapshots_apac(minio_client)
    for entrada in snapshots_apac:
        conteudo = minio_client.download_bytes(entrada["object_key"])
        perfil = perfilar_snapshot_apac(conteudo)
        perfil["run_id"] = entrada.get("_manifest_run_id")
        resultado["apac"].append(perfil)
        logger.info(
            "APAC perfilado (run_id=%s): %d estações, %d sem coordenada, %d valores negativos",
            perfil["run_id"], perfil["quantidade_estacoes"], perfil["sem_coordenada"], perfil["valores_precipitacao_negativos"],
        )

    return resultado


def gravar_relatorios(resultado: dict[str, Any], pasta_saida: Path) -> None:
    """Grava os relatórios de profiling climático em `pasta_saida`."""
    pasta_saida.mkdir(parents=True, exist_ok=True)

    schema_linhas = []
    cobertura_linhas = []
    duplicados_linhas = []
    nulos_linhas = []

    for perfil in resultado["inmet"]:
        for coluna in perfil["colunas"]:
            schema_linhas.append({"fonte": "INMET", "estacao": perfil["estacao"], "coluna": coluna})
            nulo = perfil["nulos_por_coluna"][coluna]
            nulos_linhas.append(
                {
                    "fonte": "INMET", "estacao": perfil["estacao"], "coluna": coluna,
                    "quantidade_null": nulo["quantidade_null"], "percentual_null": nulo["percentual_null"],
                }
            )
        cobertura_linhas.append(
            {
                "fonte": "INMET",
                "estacao": perfil["estacao"],
                "inicio": perfil["periodo_min"],
                "fim": perfil["periodo_max"],
                **perfil["cobertura_temporal"],
            }
        )
        duplicados_linhas.append(
            {"fonte": "INMET", "estacao": perfil["estacao"], "registros": perfil["quantidade_registros"], "duplicados": perfil["duplicados"]}
        )

    estacoes_linhas = []
    for perfil in resultado["apac"]:
        for estacao in perfil["estacoes"]:
            estacoes_linhas.append({"fonte": "APAC", "run_id": perfil["run_id"], **estacao})

    pd.DataFrame(schema_linhas).to_csv(pasta_saida / "schema.csv", index=False, encoding="utf-8")
    pd.DataFrame(estacoes_linhas).to_csv(pasta_saida / "stations.csv", index=False, encoding="utf-8")
    pd.DataFrame(nulos_linhas).to_csv(pasta_saida / "missing_values.csv", index=False, encoding="utf-8")
    pd.DataFrame(cobertura_linhas).to_csv(pasta_saida / "temporal_coverage.csv", index=False, encoding="utf-8")
    pd.DataFrame(duplicados_linhas).to_csv(pasta_saida / "duplicates.csv", index=False, encoding="utf-8")

    achados = []
    for perfil in resultado["apac"]:
        if perfil["sem_coordenada"]:
            achados.append(f"APAC run {perfil['run_id']}: {perfil['sem_coordenada']} estação(ões) sem coordenada")
        if perfil["valores_precipitacao_negativos"]:
            achados.append(f"APAC run {perfil['run_id']}: {perfil['valores_precipitacao_negativos']} valor(es) de precipitação negativos")
    LIMIAR_NULL_RELEVANTE = 20.0  # % — acima disso, vira achado explícito (não só linha no CSV)
    COLUNAS_CRITICAS = ("PRECIPITAÇÃO", "TEMPERATURA DO AR", "UMIDADE RELATIVA")

    for perfil in resultado["inmet"]:
        cobertura = perfil["cobertura_temporal"]["cobertura_percentual"]
        if cobertura < 100:
            achados.append(f"INMET {perfil['estacao']}: cobertura temporal de {cobertura}% (há dias sem nenhum registro)")

        for coluna, stats in perfil["nulos_por_coluna"].items():
            if any(marcador in coluna for marcador in COLUNAS_CRITICAS) and stats["percentual_null"] > LIMIAR_NULL_RELEVANTE:
                achados.append(
                    f"INMET {perfil['estacao']}: {stats['percentual_null']}% de valores ausentes em '{coluna}'"
                )

    pd.DataFrame({"achado": achados}).to_csv(pasta_saida / "quality_findings.csv", index=False, encoding="utf-8")

    resumo = {
        "total_estacoes_inmet": len(resultado["inmet"]),
        "total_snapshots_apac": len(resultado["apac"]),
        "achados_qualidade": achados,
    }
    (pasta_saida / "summary.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
