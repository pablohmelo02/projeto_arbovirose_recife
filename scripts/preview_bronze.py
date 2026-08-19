"""Prévia dos dados do CKAN sem depender do MinIO/Docker.

Consulta a API real do CKAN, baixa uma amostra pequena (o ano mais recente de
cada doença + as 5 dimensões), salva localmente em `preview/` (fora do
versionamento) e imprime as primeiras linhas de cada arquivo no terminal.

Não escreve nada no MinIO nem participa do pipeline de ingestão — é somente
uma ferramenta de inspeção manual dos dados de origem.

Uso:
    python -m scripts.preview_bronze
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from src.clients.ckan_client import CkanClient
from src.config import load_config
from src.ingestion.classifier import ResourceClassification, classificar_recurso

logger = logging.getLogger(__name__)

PASTA_PREVIEW = Path("preview")
ENCODINGS_TENTATIVAS = ("utf-8", "latin-1")
LINHAS_EXIBIDAS = 5


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
    )


def _selecionar_amostra(
    recursos: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], ResourceClassification]]:
    """Seleciona o ano mais recente de cada doença e todas as dimensões."""
    mais_recente_por_entidade: dict[str, tuple[dict[str, Any], ResourceClassification]] = {}
    dimensoes: list[tuple[dict[str, Any], ResourceClassification]] = []

    for recurso in recursos:
        classificacao = classificar_recurso(recurso)
        if classificacao is None:
            continue

        if classificacao.tipo == "dimensao":
            dimensoes.append((recurso, classificacao))
            continue

        atual = mais_recente_por_entidade.get(classificacao.entidade)
        ano_atual = atual[1].ano if atual else None
        if atual is None or (classificacao.ano or 0) > (ano_atual or 0):
            mais_recente_por_entidade[classificacao.entidade] = (recurso, classificacao)

    return list(mais_recente_por_entidade.values()) + dimensoes


def _decodificar(conteudo: bytes) -> tuple[Optional[str], Optional[str]]:
    for encoding in ENCODINGS_TENTATIVAS:
        try:
            return conteudo.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, None


def main() -> int:
    _configurar_logging()
    logger.info("Consultando catálogo CKAN...")

    config = load_config()
    ckan_client = CkanClient(
        base_url=config.ckan_base_url,
        dataset=config.ckan_dataset,
        timeout=config.http_timeout,
    )

    recursos = ckan_client.listar_recursos()
    amostra = _selecionar_amostra(recursos)
    logger.info(
        "%d recursos selecionados para prévia (ano mais recente por doença + dimensões)",
        len(amostra),
    )

    PASTA_PREVIEW.mkdir(exist_ok=True)

    for recurso, classificacao in amostra:
        nome = recurso.get("name") or ""
        logger.info("Baixando: %s", nome)
        conteudo = ckan_client.baixar_recurso(recurso)

        if classificacao.tipo == "fato":
            subpasta = PASTA_PREVIEW / "fatos" / classificacao.entidade
            nome_arquivo = f"ano={classificacao.ano}.csv"
        else:
            subpasta = PASTA_PREVIEW / "dimensoes"
            nome_arquivo = f"{classificacao.entidade}.csv"

        subpasta.mkdir(parents=True, exist_ok=True)
        caminho = subpasta / nome_arquivo
        caminho.write_bytes(conteudo)

        texto, encoding = _decodificar(conteudo)
        linhas = texto.splitlines() if texto else []

        rotulo_ano = f" ano={classificacao.ano}" if classificacao.ano else ""
        print("\n" + "=" * 80)
        print(f"{nome}  ({classificacao.tipo}/{classificacao.entidade}{rotulo_ano})")
        print(
            f"Tamanho: {len(conteudo)} bytes | Encoding: {encoding or 'desconhecido'} | "
            f"Linhas: {len(linhas)}"
        )
        print(f"Salvo em: {caminho}")
        print("-" * 80)
        for linha in linhas[:LINHAS_EXIBIDAS]:
            print(linha)

    print("\n" + "=" * 80)
    print(f"Prévia completa. Arquivos salvos em: {PASTA_PREVIEW.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
