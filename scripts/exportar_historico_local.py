"""Exporta o histórico completo das tabelas fato e as dimensões para o disco local.

Diferente de `scripts/preview_bronze.py` (que baixa só uma amostra pequena
para inspeção rápida), este script baixa TODOS os anos disponíveis de
Dengue, Zika e Chikungunya, além das 5 dimensões, direto da API do CKAN —
sem depender do MinIO/Docker.

IMPORTANTE: isso não é a camada Bronze oficial. Não há manifest, run_id nem
rastreabilidade de execução — é um espelho local temporário para começar
análises (ex.: propensão a surto por bairro) enquanto o ambiente com
Docker/MinIO não está disponível. Quando o MinIO estiver disponível, rode
`python -m src.main` para a ingestão oficial da Bronze.

Uso:
    python -m scripts.exportar_historico_local
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.clients.ckan_client import CkanClient, ResourceDownloadError
from src.config import load_config
from src.ingestion.classifier import classificar_recurso

logger = logging.getLogger(__name__)

PASTA_HISTORICO = Path("historico")


def _configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
    )


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

    selecionados = []
    for recurso in recursos:
        classificacao = classificar_recurso(recurso)
        if classificacao is not None:
            selecionados.append((recurso, classificacao))

    logger.info(
        "%d recursos serão baixados (todo o histórico de fatos + dimensões)",
        len(selecionados),
    )

    PASTA_HISTORICO.mkdir(exist_ok=True)

    sucessos = 0
    erros = 0

    for recurso, classificacao in selecionados:
        nome = recurso.get("name") or ""

        try:
            logger.info("Baixando: %s", nome)
            conteudo = ckan_client.baixar_recurso(recurso)
        except ResourceDownloadError as exc:
            logger.error("Falha ao baixar '%s': %s", nome, exc)
            erros += 1
            continue

        if classificacao.tipo == "fato":
            subpasta = PASTA_HISTORICO / "fatos" / classificacao.entidade
            nome_arquivo = f"ano={classificacao.ano}.csv"
        else:
            subpasta = PASTA_HISTORICO / "dimensoes"
            nome_arquivo = f"{classificacao.entidade}.csv"

        subpasta.mkdir(parents=True, exist_ok=True)
        caminho = subpasta / nome_arquivo
        caminho.write_bytes(conteudo)
        logger.info("Salvo: %s (%d bytes)", caminho, len(conteudo))
        sucessos += 1

    logger.info("Exportação finalizada")
    logger.info("Sucessos: %d | Erros: %d", sucessos, erros)
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
