"""Backfill histórico da série horária do CEMADEN.

Complementar a `climate_ingestion.executar_ingestao_cemaden` (que cobre uma
janela operacional curta, tipicamente 48h, repetida a cada execução). Este
módulo faz uma busca profunda (múltiplos anos) por estação, pensada para
rodar como um backfill pontual, não como parte do agendamento periódico.

## Por que não existe "chunking" por intervalo de datas

Investigado explicitamente antes de implementar (ver
`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`):
o endpoint `horario/{id}/{horas}` não aceita data inicial/final — só "as
últimas `horas` horas a partir de agora". Não há parâmetro de offset. Por
isso não é possível pedir "o bloco de 2015", só "os últimos N dias", que
sempre incluem tudo que é mais recente. A profundidade histórica alcançável
é limitada pelo tamanho da MAIOR requisição bem-sucedida por estação — pedir
vários blocos não estende o passado além do que uma única requisição grande
já alcançaria; só multiplicaria chamadas redundantes. Por isso este módulo
faz **uma** requisição por estação (não várias), com `dias_profundidade`
como o único parâmetro de tamanho de janela.

## Retentativa (não é chunking, é tolerância a "cold start" do servidor)

Achado empírico da investigação: para janelas grandes (>= ~2 anos), a
*primeira* requisição a uma estação pode exceder um timeout de 60s
(hipótese: o backend precisa montar a matriz de resposta sob demanda), mas
uma repetição da MESMA requisição, minutos depois, tipicamente responde em
poucos segundos (visto em 5/5 tentativas nesta investigação, para 3
estações diferentes). Por isso `executar_backfill_cemaden` usa um timeout
alto (`TIMEOUT_BACKFILL_S`) e faz até `MAX_TENTATIVAS` tentativas com
espera entre elas antes de desistir de uma estação — sem isso, o backfill
reportaria falso-negativo ("sem histórico") para estações que só precisavam
de mais tempo/uma segunda tentativa.

## Checkpoint / retomada

Cada execução grava um manifest de backfill (mesma pasta `_controle/` do
CEMADEN operacional, distinguível pelo campo `dataset` e pelo prefixo do
`object_key`, ver `PREFIXO_HORARIO_BACKFILL`). Antes de buscar uma estação,
`estacoes_com_backfill_suficiente` varre os manifests já existentes: se essa
estação já tem uma entrada `SUCCESS` com `dias_profundidade` >= a
profundidade desejada, ela é pulada (não gera nova chamada HTTP). Uma falha
numa estação não impede as demais (mesmo padrão do resto do domínio clima).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from src.clients.cemaden_client import CemadenClient, CemadenClientError
from src.clients.minio_client import MinioClient, MinioClientError
from src.ingestion.bronze_validation import carregar_manifest
from src.ingestion.climate_ingestion import PREFIXO_BRONZE_CLIMA

logger = logging.getLogger(__name__)

PREFIXO_HORARIO_BACKFILL = f"{PREFIXO_BRONZE_CLIMA}/cemaden/horario_backfill"
DATASET_BACKFILL = "pcd-pluviometrica-backfill-historico"

# Maior janela validada na investigacao (ver relatorio): 1825 dias (5 anos)
# respondeu 200 OK para a estacao Porto (400 MB, 13s na segunda tentativa).
# O valor efetivamente usado como padrao operacional aqui e mais conservador
# (ver docstring de `executar_backfill_cemaden`) -- quem chama pode passar
# um valor maior explicitamente se quiser se aproximar do limite validado.
DIAS_BACKFILL_MAXIMO_VALIDADO = 1825
DIAS_BACKFILL_PADRAO = 1095  # 3 anos — ver relatorio, secao "profundidade aplicada"

TIMEOUT_BACKFILL_S = 180
MAX_TENTATIVAS = 2
ESPERA_ENTRE_TENTATIVAS_S = 5.0
ESPERA_ENTRE_ESTACOES_S = 1.0


def _gerar_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _listar_manifests_cemaden(minio_client: MinioClient) -> list[str]:
    prefixo_controle = f"{PREFIXO_BRONZE_CLIMA}/cemaden/_controle/"
    prefixo_manifest = f"{prefixo_controle}manifest_"
    chaves = minio_client.listar_chaves(prefixo_controle)
    return sorted(chave for chave in chaves if chave.startswith(prefixo_manifest))


def estacoes_com_backfill_suficiente(
    minio_client: MinioClient, dias_profundidade: int
) -> dict[str, int]:
    """Para cada estação com backfill histórico já concluído com sucesso,
    a maior `dias_profundidade` já alcançada. Usado para pular estações que
    já têm profundidade suficiente (checkpoint/retomada) — nunca decide
    isso a partir de arquivos no disco/objeto, só do manifest declarado,
    igual ao resto do domínio clima (nenhuma inferência silenciosa)."""
    melhor_por_estacao: dict[str, int] = {}
    for chave_manifest in _listar_manifests_cemaden(minio_client):
        manifest = carregar_manifest(minio_client, chave_manifest)
        if manifest.get("dataset") != DATASET_BACKFILL:
            continue
        profundidade_run = manifest.get("dias_profundidade", 0)
        for entrada in manifest.get("recursos", []):
            if entrada.get("status") != "SUCCESS":
                continue
            id_estacao = entrada.get("id_estacao")
            if not id_estacao:
                continue
            atual = melhor_por_estacao.get(id_estacao, 0)
            if profundidade_run > atual:
                melhor_por_estacao[id_estacao] = profundidade_run
    return melhor_por_estacao


def _baixar_com_retentativa(
    cemaden_client: CemadenClient, id_estacao: str, horas: int
) -> tuple[Optional[bytes], list[dict[str, Any]]]:
    """Tenta baixar a série horária de uma estação até `MAX_TENTATIVAS`
    vezes, com espera entre tentativas. Retorna `(conteudo, tentativas)` —
    `conteudo` é `None` se todas as tentativas falharem; `tentativas` é o
    log de cada uma (nunca escondido, mesmo quando a estação acaba tendo
    sucesso na segunda tentativa)."""
    tentativas: list[dict[str, Any]] = []
    for numero in range(1, MAX_TENTATIVAS + 1):
        inicio = time.monotonic()
        try:
            conteudo = cemaden_client.baixar_serie_horaria(id_estacao, horas)
            tentativas.append(
                {"numero": numero, "sucesso": True, "tempo_s": round(time.monotonic() - inicio, 2)}
            )
            return conteudo, tentativas
        except CemadenClientError as exc:
            tentativas.append(
                {
                    "numero": numero,
                    "sucesso": False,
                    "tempo_s": round(time.monotonic() - inicio, 2),
                    "erro": str(exc),
                }
            )
            if numero < MAX_TENTATIVAS:
                logger.warning(
                    "Tentativa %d/%d falhou para estação %s (%s) — retentando em %.0fs",
                    numero, MAX_TENTATIVAS, id_estacao, exc, ESPERA_ENTRE_TENTATIVAS_S,
                )
                time.sleep(ESPERA_ENTRE_TENTATIVAS_S)
    return None, tentativas


def executar_backfill_cemaden(
    cemaden_client: CemadenClient,
    minio_client: MinioClient,
    id_estacoes: list[str],
    dias_profundidade: int = DIAS_BACKFILL_PADRAO,
    pular_se_ja_existe: bool = True,
) -> dict[str, Any]:
    """Busca, para cada estação em `id_estacoes`, a maior série horária
    possível dentro de `dias_profundidade` dias — uma única requisição por
    estação (ver docstring do módulo sobre por que não há chunking real).

    Grava cada resposta em `PREFIXO_HORARIO_BACKFILL` (prefixo distinto do
    CEMADEN operacional, nunca sobrescrevendo `.../cemaden/horario/...`) e
    um manifest com `dataset=DATASET_BACKFILL` e `dias_profundidade` no
    nível da execução — é isso que permite `estacoes_com_backfill_suficiente`
    distinguir "coleta atual" de "backfill histórico" (ver README/CLAUDE.md,
    seção de rastreabilidade da Bronze).

    Não gera nenhuma exceção fatal: uma estação sem histórico real (resposta
    200 com matriz vazia/só nulos) ou uma estação que falha todas as
    tentativas é registrada como tal no manifest, nunca derruba o lote.
    """
    run_id = _gerar_run_id()
    inicio = datetime.now(timezone.utc)
    horas = dias_profundidade * 24

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "fonte": "CEMADEN",
        "dataset": DATASET_BACKFILL,
        "dominio": "clima",
        "dias_profundidade": dias_profundidade,
        "dias_profundidade_maximo_validado": DIAS_BACKFILL_MAXIMO_VALIDADO,
        "inicio_execucao": inicio.isoformat(),
        "fim_execucao": None,
        "sucessos": 0,
        "puladas_checkpoint": 0,
        "erros": 0,
        "recursos": [],
    }

    logger.info(
        "Iniciando backfill histórico CEMADEN (run_id=%s, dias_profundidade=%d, %d estação(ões) candidatas)",
        run_id, dias_profundidade, len(id_estacoes),
    )
    minio_client.garantir_bucket()

    ja_com_backfill = (
        estacoes_com_backfill_suficiente(minio_client, dias_profundidade)
        if pular_se_ja_existe
        else {}
    )

    for id_estacao in id_estacoes:
        if pular_se_ja_existe and ja_com_backfill.get(id_estacao, 0) >= dias_profundidade:
            manifest["puladas_checkpoint"] += 1
            manifest["recursos"].append(
                {
                    "tipo": "horario", "id_estacao": id_estacao, "status": "SKIPPED_CHECKPOINT",
                    "object_key": None, "bytes": 0, "erro": None, "tentativas": [],
                }
            )
            logger.info(
                "Estação %s já tem backfill >= %d dias — pulando (checkpoint)", id_estacao, dias_profundidade
            )
            continue

        nome_recurso = f"{id_estacao}.json"
        entrada: dict[str, Any] = {
            "tipo": "horario", "id_estacao": id_estacao, "nome_recurso": nome_recurso,
            "object_key": None, "bytes": 0, "status": "ERROR", "erro": None,
        }

        conteudo, tentativas = _baixar_com_retentativa(cemaden_client, id_estacao, horas)
        entrada["tentativas"] = tentativas

        if conteudo is None:
            entrada["erro"] = tentativas[-1]["erro"] if tentativas else "falha desconhecida"
            manifest["erros"] += 1
            logger.error(
                "Backfill falhou para estação %s após %d tentativa(s): %s",
                id_estacao, len(tentativas), entrada["erro"],
            )
        else:
            object_key = f"{PREFIXO_HORARIO_BACKFILL}/ingestion={run_id}/{nome_recurso}"
            try:
                tamanho = minio_client.upload_bytes(object_key, conteudo)
                entrada.update({"object_key": object_key, "bytes": tamanho, "status": "SUCCESS"})
                manifest["sucessos"] += 1
                logger.info(
                    "Backfill OK: estação %s, %d bytes, s3://%s/%s",
                    id_estacao, tamanho, minio_client.bucket, object_key,
                )
            except MinioClientError as exc:
                entrada["erro"] = str(exc)
                manifest["erros"] += 1
                logger.error("Falha ao gravar backfill da estação %s: %s", id_estacao, exc)

        manifest["recursos"].append(entrada)
        time.sleep(ESPERA_ENTRE_ESTACOES_S)

    manifest["fim_execucao"] = datetime.now(timezone.utc).isoformat()

    manifest_key = f"{PREFIXO_BRONZE_CLIMA}/cemaden/_controle/manifest_{run_id}.json"
    try:
        minio_client.upload_manifest(manifest_key, manifest)
        logger.info("Manifest de backfill CEMADEN salvo em s3://%s/%s", minio_client.bucket, manifest_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar manifest de backfill CEMADEN: %s", exc)

    logger.info(
        "Backfill CEMADEN finalizado. Sucessos: %d | Puladas (checkpoint): %d | Erros: %d",
        manifest["sucessos"], manifest["puladas_checkpoint"], manifest["erros"],
    )
    return manifest
