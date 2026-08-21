"""Ingestão Bronze do clima em **grade** (reanálise ERA5 / ERA5-Land).

Segue exatamente os mesmos princípios da Bronze das outras fontes de clima
(`climate_ingestion.py`): preserva o payload original byte a byte, usa
`run_id`, grava `ingestion=<run_id>/`, escreve um manifest próprio e trata
erro por recurso sem interromper o lote.

## Diferença de lineage frente às fontes de estação

Uma estação tem identidade própria (código, nome, coordenada de sensor).
Uma **célula de grade** não: ela é definida pelo alinhamento da grade do
modelo, e é o provedor que decide qual célula cobre um ponto pedido. Por
isso a ingestão faz duas coisas explicitamente separadas:

1. **Sondagem** (`sondar_celulas`): uma requisição minúscula (2 dias) com
   os 94 centroides, só para descobrir — medindo, não arredondando — qual
   célula o provedor devolve para cada bairro. O resultado é gravado na
   Bronze como um recurso próprio (`celulas/`), porque é dado observado da
   fonte, não configuração nossa.
2. **Série histórica** (`baixar_series`): uma requisição por grade, com
   apenas as células **distintas** (2 e 3 células para os 94 bairros — ver
   `src/silver/schema_climate_grade.py`). Pedir 94 pontos devolveria a
   mesma série repetida dezenas de vezes.

## Idempotência

Cada execução grava sob um `run_id` novo, e a Silver reconstrói a tabela
inteira a partir da última execução com sucesso (nunca por append) — rodar
duas vezes com a mesma janela produz a mesma Silver.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from src.clients.gridded_climate_client import (
    MODELO_PRECIPITACAO,
    MODELO_TEMPERATURA,
    VARIAVEIS_PRECIPITACAO,
    VARIAVEIS_TEMPERATURA,
    GriddedClimateClientError,
    OpenMeteoArchiveClient,
)
from src.clients.minio_client import MinioClient, MinioClientError
from src.silver.climate_grade import identificador_celula
from src.silver.schema_climate_grade import GRADE_PRECIPITACAO, GRADE_TEMPERATURA

logger = logging.getLogger(__name__)

PREFIXO_BRONZE_CLIMA_GRADE = "bronze/recife/clima/grade"

#: Janela mínima usada só para descobrir a célula de cada bairro.
JANELA_SONDAGEM_DIAS = 2

GRADES_CONFIGURADAS = (
    (GRADE_PRECIPITACAO, MODELO_PRECIPITACAO, VARIAVEIS_PRECIPITACAO),
    (GRADE_TEMPERATURA, MODELO_TEMPERATURA, VARIAVEIS_TEMPERATURA),
)


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sondar_celulas(
    cliente: OpenMeteoArchiveClient,
    centroides: Sequence[tuple[str, float, float]],
    modelo: str,
    variaveis: Sequence[str],
    data_sondagem_inicio: str,
    data_sondagem_fim: str,
) -> dict[str, str]:
    """`codigo_bairro -> celula_id`, medido pelas coordenadas devolvidas
    pelo provedor. Levanta `GriddedClimateClientError` se a fonte estiver
    indisponível — nunca devolve um mapa parcial silencioso."""
    pontos = [(lat, lon) for _, lat, lon in centroides]
    conteudo = cliente.baixar_series_diarias(
        pontos, data_sondagem_inicio, data_sondagem_fim, variaveis, modelo
    )
    payload = json.loads(conteudo.decode("utf-8"))
    itens = payload if isinstance(payload, list) else [payload]
    if len(itens) != len(centroides):
        raise GriddedClimateClientError(
            f"sondagem devolveu {len(itens)} pontos para {len(centroides)} bairros"
        )
    return {
        codigo: identificador_celula(float(item["latitude"]), float(item["longitude"]))
        for (codigo, _, _), item in zip(centroides, itens)
    }


def executar_ingestao_clima_grade(
    cliente: OpenMeteoArchiveClient,
    minio_client: MinioClient,
    centroides: Sequence[tuple[str, float, float]],
    data_inicio: str,
    data_fim: str,
) -> dict[str, Any]:
    """Ingere, para cada grade configurada: o mapa bairro→célula (sondagem)
    e a série diária completa das células distintas.

    `centroides`: sequência de `(codigo_bairro, latitude, longitude)` —
    vem de `silver_bairro_geo` (`centroide_lat`/`centroide_lon`, calculados
    em CRS métrico pela camada de território, nunca recalculados aqui).
    """
    if not centroides:
        raise ValueError("nenhum centroide de bairro informado")

    run_id = _gerar_run_id()
    minio_client.garantir_bucket()

    manifest: dict[str, Any] = {
        "dominio": "clima",
        "fonte": "grade (reanalise ERA5 / ERA5-LAND via Open-Meteo Archive)",
        "run_id": run_id,
        "inicio_execucao": datetime.now(timezone.utc).isoformat(),
        "janela": {"data_inicio": data_inicio, "data_fim": data_fim},
        "n_bairros": len(centroides),
        "recursos": [],
        "sucessos": 0,
        "erros": 0,
    }

    for grade, modelo, variaveis in GRADES_CONFIGURADAS:
        # ---------------- 1. sondagem das células ----------------
        entrada_celulas: dict[str, Any] = {
            "tipo": "celulas",
            "grade": grade,
            "modelo": modelo,
            "status": "erro",
        }
        mapa: dict[str, str] = {}
        try:
            mapa = sondar_celulas(
                cliente, centroides, modelo, variaveis, data_inicio,
                _data_mais_dias(data_inicio, JANELA_SONDAGEM_DIAS - 1),
            )
            payload_celulas = json.dumps(
                {"grade": grade, "modelo": modelo, "bairro_para_celula": mapa},
                ensure_ascii=False,
            ).encode("utf-8")
            object_key = (
                f"{PREFIXO_BRONZE_CLIMA_GRADE}/celulas/grade={grade}/ingestion={run_id}/celulas.json"
            )
            minio_client.upload_bytes(object_key, payload_celulas, content_type="application/json")
            entrada_celulas.update(
                status="sucesso",
                object_key=object_key,
                n_bairros_mapeados=len(mapa),
                n_celulas_distintas=len(set(mapa.values())),
                tamanho_bytes=len(payload_celulas),
            )
            manifest["sucessos"] += 1
            logger.info(
                "Sondagem %s: %d bairros -> %d célula(s) distinta(s)",
                grade, len(mapa), len(set(mapa.values())),
            )
        except (GriddedClimateClientError, MinioClientError, ValueError) as exc:
            entrada_celulas["erro"] = str(exc)
            manifest["erros"] += 1
            logger.error("Falha na sondagem de células (%s): %s", grade, exc)
        manifest["recursos"].append(entrada_celulas)

        if not mapa:
            continue

        # ---------------- 2. séries das células distintas ----------------
        celulas_distintas = sorted(set(mapa.values()))
        pontos = [tuple(map(float, cid.split("_"))) for cid in celulas_distintas]
        entrada_serie: dict[str, Any] = {
            "tipo": "serie_diaria",
            "grade": grade,
            "modelo": modelo,
            "celulas": celulas_distintas,
            "status": "erro",
        }
        try:
            conteudo = cliente.baixar_series_diarias(
                pontos, data_inicio, data_fim, variaveis, modelo
            )
            object_key = (
                f"{PREFIXO_BRONZE_CLIMA_GRADE}/serie/grade={grade}/ingestion={run_id}/serie_diaria.json"
            )
            minio_client.upload_bytes(object_key, conteudo, content_type="application/json")
            entrada_serie.update(
                status="sucesso",
                object_key=object_key,
                n_celulas=len(celulas_distintas),
                tamanho_bytes=len(conteudo),
            )
            manifest["sucessos"] += 1
            logger.info(
                "Série %s: %d célula(s), %s -> %s (%.1f KB)",
                grade, len(celulas_distintas), data_inicio, data_fim, len(conteudo) / 1024,
            )
        except (GriddedClimateClientError, MinioClientError) as exc:
            entrada_serie["erro"] = str(exc)
            manifest["erros"] += 1
            logger.error("Falha ao baixar série em grade (%s): %s", grade, exc)
        manifest["recursos"].append(entrada_serie)

    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()
    manifest_key = f"{PREFIXO_BRONZE_CLIMA_GRADE}/_controle/manifest_{run_id}.json"
    minio_client.upload_manifest(manifest_key, manifest)
    logger.info(
        "Ingestão clima em grade finalizada. Sucessos: %d | Erros: %d",
        manifest["sucessos"], manifest["erros"],
    )
    return manifest


def _data_mais_dias(data_iso: str, dias: int) -> str:
    from datetime import date, timedelta

    ano, mes, dia = (int(p) for p in data_iso.split("-"))
    return str(date(ano, mes, dia) + timedelta(days=dias))
