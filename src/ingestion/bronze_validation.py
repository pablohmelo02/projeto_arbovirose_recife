"""Validação de qualidade da camada Bronze.

Não faz parte da ingestão em si: lê o manifest de uma execução já concluída,
relê os objetos gravados no MinIO e verifica se o conteúdo é plausível
(não vazio, não é uma página HTML de erro, decodificável, com delimitador
reconhecível) e se as séries de anos de cada doença não têm lacunas.

Não altera, corrige ou reprocessa nenhum dado — é somente diagnóstico.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.clients.minio_client import MinioClient, MinioClientError
from src.ingestion.bronze_ingestion import PREFIXO_BRONZE

logger = logging.getLogger(__name__)

ENTIDADES_FATO = ("dengue", "zika", "chikungunya")
ENCODINGS_TENTATIVAS = ("utf-8", "latin-1")


def encontrar_manifest_mais_recente(minio_client: MinioClient) -> str:
    """Retorna a chave do manifest mais recente com base no run_id (UTC, ordenável)."""
    prefixo_controle = f"{PREFIXO_BRONZE}/_controle/"
    prefixo_manifest = f"{prefixo_controle}manifest_"

    chaves = minio_client.listar_chaves(prefixo_controle)
    manifestos = sorted(chave for chave in chaves if chave.startswith(prefixo_manifest))

    if not manifestos:
        raise ValueError(f"Nenhum manifest encontrado em '{prefixo_controle}'")

    return manifestos[-1]


def carregar_manifest(minio_client: MinioClient, manifest_key: str) -> dict[str, Any]:
    """Baixa e desserializa o manifest de uma execução da Bronze."""
    conteudo = minio_client.download_bytes(manifest_key)
    return json.loads(conteudo.decode("utf-8"))


def checar_conteudo(conteudo: bytes) -> list[tuple[str, str]]:
    """Analisa o conteúdo bruto de um recurso e retorna problemas encontrados.

    Cada problema é uma tupla (nivel, mensagem), com nivel em {"erro", "aviso"}.
    Lista vazia significa que o conteúdo passou em todas as checagens.
    """
    problemas: list[tuple[str, str]] = []

    if len(conteudo) == 0:
        problemas.append(("erro", "arquivo vazio (0 bytes)"))
        return problemas

    texto: Optional[str] = None
    for encoding in ENCODINGS_TENTATIVAS:
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if texto is None:
        problemas.append(
            ("erro", f"não foi possível decodificar o conteúdo ({'/'.join(ENCODINGS_TENTATIVAS)})")
        )
        return problemas

    amostra = texto[:500].strip().lower()
    if amostra.startswith("<!doctype") or "<html" in amostra:
        problemas.append(("erro", "conteúdo parece ser HTML, não um CSV"))
        return problemas

    linhas = texto.splitlines()
    if len(linhas) < 2:
        problemas.append(("aviso", "arquivo possui menos de 2 linhas (sem dados após o cabeçalho?)"))

    primeira_linha = linhas[0] if linhas else ""
    if ";" not in primeira_linha and "," not in primeira_linha:
        problemas.append(
            ("aviso", "nenhum delimitador comum (',' ou ';') encontrado na primeira linha")
        )

    return problemas


def validar_resource(minio_client: MinioClient, entrada: dict[str, Any]) -> dict[str, Any]:
    """Valida um recurso registrado no manifest, relendo seu objeto no MinIO."""
    resultado: dict[str, Any] = {
        "resource_id": entrada.get("resource_id"),
        "nome": entrada.get("nome"),
        "tipo": entrada.get("tipo"),
        "entidade": entrada.get("entidade"),
        "ano": entrada.get("ano"),
        "object_key": entrada.get("object_key"),
        "status": "OK",
        "problemas": [],
    }

    if entrada.get("status") != "SUCCESS":
        resultado["status"] = "ERRO"
        resultado["problemas"] = [
            f"recurso falhou na ingestão: {entrada.get('erro') or 'motivo desconhecido'}"
        ]
        return resultado

    object_key = entrada.get("object_key")
    if not object_key:
        resultado["status"] = "ERRO"
        resultado["problemas"] = ["recurso marcado como sucesso mas sem object_key"]
        return resultado

    try:
        conteudo = minio_client.download_bytes(object_key)
    except MinioClientError as exc:
        resultado["status"] = "ERRO"
        resultado["problemas"] = [f"falha ao ler objeto do MinIO: {exc}"]
        return resultado

    problemas = checar_conteudo(conteudo)
    resultado["problemas"] = [mensagem for _, mensagem in problemas]

    niveis = {nivel for nivel, _ in problemas}
    if "erro" in niveis:
        resultado["status"] = "ERRO"
    elif "aviso" in niveis:
        resultado["status"] = "AVISO"

    return resultado


def detectar_lacunas_anos(manifest: dict[str, Any]) -> dict[str, list[int]]:
    """Identifica anos ausentes entre o menor e o maior ano ingerido com sucesso, por doença."""
    lacunas: dict[str, list[int]] = {}

    for entidade in ENTIDADES_FATO:
        anos = sorted(
            recurso["ano"]
            for recurso in manifest.get("recursos", [])
            if recurso.get("tipo") == "fato"
            and recurso.get("entidade") == entidade
            and recurso.get("status") == "SUCCESS"
            and recurso.get("ano") is not None
        )
        if not anos:
            continue

        intervalo_completo = set(range(anos[0], anos[-1] + 1))
        faltando = sorted(intervalo_completo - set(anos))
        if faltando:
            lacunas[entidade] = faltando

    return lacunas


def executar_validacao_bronze(
    minio_client: MinioClient, manifest_key: Optional[str] = None
) -> dict[str, Any]:
    """Executa a validação de uma execução da Bronze e retorna o relatório gerado.

    Se `manifest_key` não for informado, valida o manifest mais recente.
    O relatório também é salvo em `_controle/validacao_<run_id>.json`.
    """
    if manifest_key is None:
        manifest_key = encontrar_manifest_mais_recente(minio_client)
        logger.info("Manifest mais recente selecionado: %s", manifest_key)

    manifest = carregar_manifest(minio_client, manifest_key)
    run_id = manifest.get("run_id", "desconhecido")
    logger.info("Validando run_id=%s (%d recursos no manifest)", run_id, len(manifest.get("recursos", [])))

    checks: list[dict[str, Any]] = []
    contagem = {"ok": 0, "avisos": 0, "erros": 0}

    for entrada in manifest.get("recursos", []):
        resultado = validar_resource(minio_client, entrada)
        checks.append(resultado)

        if resultado["status"] == "OK":
            contagem["ok"] += 1
        elif resultado["status"] == "AVISO":
            contagem["avisos"] += 1
        else:
            contagem["erros"] += 1

    lacunas = detectar_lacunas_anos(manifest)

    relatorio = {
        "run_id": run_id,
        "manifest_key": manifest_key,
        "validado_em": datetime.now(timezone.utc).isoformat(),
        "resumo": {
            "total_recursos_validados": len(checks),
            **contagem,
        },
        "lacunas_de_anos": lacunas,
        "checks": checks,
    }

    relatorio_key = f"{PREFIXO_BRONZE}/_controle/validacao_{run_id}.json"
    try:
        payload = json.dumps(relatorio, ensure_ascii=False, indent=2).encode("utf-8")
        minio_client.upload_bytes(relatorio_key, payload, content_type="application/json")
        logger.info("Relatório de validação salvo em s3://%s/%s", minio_client.bucket, relatorio_key)
    except MinioClientError as exc:
        logger.error("Falha ao salvar relatório de validação: %s", exc)

    return relatorio
