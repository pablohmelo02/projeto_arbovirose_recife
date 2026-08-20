"""Ingestão Bronze do domínio Clima (INMET + APAC + CEMADEN).

Três fontes com formas de acesso e granularidade de lineage bem diferentes
(ver `reports/climate_source_analysis/source_analysis.md` e
`reports/climate_source_analysis/cemaden_integration_results.md`):

- **INMET**: ZIP anual estático (histórico real). Cada execução baixa um ou
  mais anos e grava um CSV por estação de Pernambuco encontrada no ZIP.
- **APAC**: API de telemetria em tempo real, sem histórico em lote
  disponível. Cada execução grava o instantâneo atual — o histórico é a
  soma de execuções ao longo do tempo, não um backfill. Congelada desde
  2024-04-09 (ver `apac_freshness_investigation.md`) — a ingestão continua
  rodando (não removida), só não produz mais estações elegíveis.
- **CEMADEN**: dois recursos quase-estáticos (cadastro geoespacial + status
  atual, baixados inteiros a cada execução) mais uma série horária real de
  precipitação por estação — buscada só para as estações da Grande Recife
  (`MUNICIPIOS_GRANDE_RECIFE`, ver docstring de
  `_candidatos_pluviometricos_grande_recife`), não as 437 de Pernambuco
  inteira, para não gerar uma carga de rede desproporcional a cada execução.
  Cada execução cobre uma janela recente (`horas`, tipicamente 48h) que se
  sobrepõe com a anterior — a Silver acumula e deduplica pela chave
  (estação, data, hora) ao montar o histórico real (ver
  `pipeline_climate.py::_processar_cemaden`), o mesmo princípio já usado
  para os instantâneos da APAC.

Todas seguem os mesmos princípios da Bronze de arboviroses/território:
preservação do dado original, `run_id`, manifest, `ingestion=<run_id>/`,
tratamento de erro que não interrompe o lote, logs claros. Cada fonte grava
seu próprio manifest, deixando claro qual delas o gerou.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.clients.apac_client import ApacClient, ApacClientError
from src.clients.cemaden_client import CemadenClient, CemadenClientError
from src.clients.inmet_client import InmetClient, InmetClientError
from src.clients.minio_client import MinioClient, MinioClientError
from src.silver.quality import limpar_texto

logger = logging.getLogger(__name__)

PREFIXO_BRONZE_CLIMA = "bronze/recife/clima"

TIPOESTACAO_PLUVIOMETRICA = 1  # ver docstring de cemaden_client.py

# Recorte pragmático da Grande Recife para a série horária (recurso caro:
# 1 chamada HTTP por estação por execução) -- o cadastro e o status
# continuam sendo baixados inteiros para Pernambuco (2 chamadas baratas),
# só a busca de série horária é restrita a este recorte. Município textual
# não é confiável sozinho para decidir *associação* bairro-estação (a
# Estratégia A já faz o join geométrico real, ver `climate_spatial.py`) --
# aqui ele só decide *quais estações vale a pena consultar*, com folga
# suficiente para cobrir casos de borda já observados (ex.: estação
# fisicamente perto do Recife mas cadastrada em município vizinho).
MUNICIPIOS_GRANDE_RECIFE = (
    "RECIFE",
    "OLINDA",
    "JABOATAO DOS GUARARAPES",
    "CAMARAGIBE",
    "SAO LOURENCO DA MATA",
    "PAULISTA",
    "ABREU E LIMA",
)


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def executar_ingestao_inmet(
    inmet_client: InmetClient,
    minio_client: MinioClient,
    anos: list[int],
    uf: str = "PE",
) -> dict[str, Any]:
    """Baixa o(s) ZIP(s) anual(is) do INMET e grava um CSV por estação de `uf` na Bronze."""
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": "INMET",
        "dataset": "dadoshistoricos",
        "dominio": "clima",
        "anos_solicitados": anos,
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão INMET (run_id=%s, anos=%s)", run_id, anos)
    minio_client.garantir_bucket()

    for ano in anos:
        try:
            logger.info("Baixando ZIP do INMET para %d...", ano)
            conteudo_zip = inmet_client.baixar_zip_ano(ano)
            estacoes = inmet_client.extrair_estacoes_uf(conteudo_zip, uf=uf)
        except InmetClientError as exc:
            logger.error("Falha ao processar o ano %d: %s", ano, exc)
            manifest["recursos"].append(
                {
                    "ano": ano,
                    "nome_recurso": f"{ano}.zip",
                    "status": "ERROR",
                    "erro": str(exc),
                    "object_key": None,
                    "bytes": 0,
                }
            )
            manifest["erros"] += 1
            continue

        logger.info("%d estação(ões) de %s encontradas no ZIP de %d", len(estacoes), uf, ano)

        for nome_arquivo, conteudo in estacoes:
            object_key = (
                f"{PREFIXO_BRONZE_CLIMA}/inmet/ano={ano}/ingestion={run_id}/{nome_arquivo}"
            )
            entrada: dict[str, Any] = {
                "ano": ano,
                "nome_recurso": nome_arquivo,
                "object_key": None,
                "bytes": 0,
                "status": "ERROR",
                "erro": None,
            }
            try:
                tamanho = minio_client.upload_bytes(object_key, conteudo)
                entrada.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
                manifest["sucessos"] += 1
                logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
            except MinioClientError as exc:
                logger.error("Falha no upload de '%s': %s", nome_arquivo, exc)
                entrada["erro"] = str(exc)
                manifest["erros"] += 1

            manifest["recursos"].append(entrada)

    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE_CLIMA}/inmet/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest INMET salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest INMET: %s", exc)

    logger.info("Ingestão INMET finalizada. Sucessos: %d | Erros: %d", manifest["sucessos"], manifest["erros"])
    return manifest


def executar_ingestao_apac(
    apac_client: ApacClient,
    minio_client: MinioClient,
) -> dict[str, Any]:
    """Baixa o instantâneo atual da rede de telemetria PCD da APAC e grava na Bronze."""
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": "APAC",
        "dataset": "pcd-pluviometria",
        "dominio": "clima",
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão APAC (run_id=%s)", run_id)
    minio_client.garantir_bucket()

    entrada: dict[str, Any] = {
        "nome_recurso": "pcds.json",
        "object_key": None,
        "bytes": 0,
        "status": "ERROR",
        "erro": None,
    }

    try:
        conteudo = apac_client.baixar_instantaneo_pcds()
        object_key = f"{PREFIXO_BRONZE_CLIMA}/apac/pcd/ingestion={run_id}/pcds.json"
        tamanho = minio_client.upload_bytes(object_key, conteudo)
        entrada.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
        manifest["sucessos"] += 1
        logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
    except (ApacClientError, MinioClientError) as exc:
        logger.error("Falha na ingestão APAC: %s", exc)
        entrada["erro"] = str(exc)
        manifest["erros"] += 1

    manifest["recursos"].append(entrada)
    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE_CLIMA}/apac/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest APAC salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest APAC: %s", exc)

    logger.info("Ingestão APAC finalizada. Sucessos: %d | Erros: %d", manifest["sucessos"], manifest["erros"])
    return manifest


def _candidatos_pluviometricos_grande_recife(conteudo_status: bytes) -> list[dict[str, Any]]:
    """Filtra o status bruto do CEMADEN (todos os tipos de estação, PE
    inteiro) para as candidatas a busca de série horária: só pluviométricas
    (`tipoestacao == 1`) e só município na Grande Recife (`MUNICIPIOS_GRANDE_RECIFE`).
    """
    registros = json.loads(conteudo_status.decode("utf-8", errors="replace"))
    candidatos = []
    for registro in registros:
        if registro.get("tipoestacao") != TIPOESTACAO_PLUVIOMETRICA:
            continue
        cidade = limpar_texto(registro.get("cidade"))
        if cidade in MUNICIPIOS_GRANDE_RECIFE:
            candidatos.append(registro)
    return candidatos


def executar_ingestao_cemaden(
    cemaden_client: CemadenClient,
    minio_client: MinioClient,
    horas: int = 48,
) -> dict[str, Any]:
    """Baixa cadastro + status pluviométrico de Pernambuco inteira, e a série
    horária real de precipitação só das estações candidatas da Grande Recife
    (ver `_candidatos_pluviometricos_grande_recife`) — grava tudo na Bronze.

    Uma falha em cadastro ou status não impede a tentativa do outro; se o
    status falhar, nenhuma série horária é buscada nesta execução (não há
    como saber `idEstacao` sem ele) — registrado como aviso, não erro fatal
    do lote.
    """
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": "CEMADEN",
        "dataset": "pcd-pluviometrica",
        "dominio": "clima",
        "horas_solicitadas": horas,
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "sucessos": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info("Iniciando ingestão CEMADEN (run_id=%s, horas=%d)", run_id, horas)
    minio_client.garantir_bucket()

    conteudo_cadastro: bytes | None = None
    entrada_cadastro: dict[str, Any] = {
        "tipo": "cadastro", "nome_recurso": "cadastro.json",
        "object_key": None, "bytes": 0, "status": "ERROR", "erro": None,
    }
    try:
        conteudo_cadastro = cemaden_client.baixar_cadastro_estacoes()
        object_key = f"{PREFIXO_BRONZE_CLIMA}/cemaden/cadastro/ingestion={run_id}/cadastro.json"
        tamanho = minio_client.upload_bytes(object_key, conteudo_cadastro)
        entrada_cadastro.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
        manifest["sucessos"] += 1
        logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
    except (CemadenClientError, MinioClientError) as exc:
        logger.error("Falha ao obter/gravar cadastro CEMADEN: %s", exc)
        entrada_cadastro["erro"] = str(exc)
        manifest["erros"] += 1
    manifest["recursos"].append(entrada_cadastro)

    conteudo_status: bytes | None = None
    entrada_status: dict[str, Any] = {
        "tipo": "status", "nome_recurso": "status.json",
        "object_key": None, "bytes": 0, "status": "ERROR", "erro": None,
    }
    try:
        conteudo_status = cemaden_client.baixar_status_estacoes()
        object_key = f"{PREFIXO_BRONZE_CLIMA}/cemaden/status/ingestion={run_id}/status.json"
        tamanho = minio_client.upload_bytes(object_key, conteudo_status)
        entrada_status.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
        manifest["sucessos"] += 1
        logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
    except (CemadenClientError, MinioClientError) as exc:
        logger.error("Falha ao obter/gravar status CEMADEN: %s", exc)
        entrada_status["erro"] = str(exc)
        manifest["erros"] += 1
    manifest["recursos"].append(entrada_status)

    if conteudo_status is None:
        logger.error(
            "Status CEMADEN indisponível nesta execução — nenhuma série horária foi buscada"
        )
    else:
        candidatos = _candidatos_pluviometricos_grande_recife(conteudo_status)
        logger.info(
            "%d estação(ões) pluviométrica(s) candidatas na Grande Recife", len(candidatos)
        )
        for registro in candidatos:
            id_estacao = str(registro["idestacao"])
            nome_recurso = f"{id_estacao}.json"
            entrada_horario: dict[str, Any] = {
                "tipo": "horario", "id_estacao": id_estacao, "nome_recurso": nome_recurso,
                "object_key": None, "bytes": 0, "status": "ERROR", "erro": None,
            }
            try:
                conteudo_horario = cemaden_client.baixar_serie_horaria(id_estacao, horas)
                object_key = f"{PREFIXO_BRONZE_CLIMA}/cemaden/horario/ingestion={run_id}/{nome_recurso}"
                tamanho = minio_client.upload_bytes(object_key, conteudo_horario)
                entrada_horario.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
                manifest["sucessos"] += 1
                logger.info("Upload realizado: s3://%s/%s", minio_client.bucket, object_key)
            except (CemadenClientError, MinioClientError) as exc:
                logger.error("Falha ao obter/gravar série horária da estação %s: %s", id_estacao, exc)
                entrada_horario["erro"] = str(exc)
                manifest["erros"] += 1
            manifest["recursos"].append(entrada_horario)

    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE_CLIMA}/cemaden/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest CEMADEN salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest CEMADEN: %s", exc)

    logger.info(
        "Ingestão CEMADEN finalizada. Sucessos: %d | Erros: %d", manifest["sucessos"], manifest["erros"]
    )
    return manifest
