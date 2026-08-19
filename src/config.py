"""Carrega e expõe as configurações do projeto a partir do arquivo .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


CKAN_TERRITORIO_DATASET_PADRAO = "mapas-de-limites-e-divisoes-territoriais"
INMET_ANOS_PADRAO = (2024,)


@dataclass(frozen=True)
class Config:
    ckan_base_url: str
    ckan_dataset: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    http_timeout: int = 30
    ckan_territorio_dataset: str = CKAN_TERRITORIO_DATASET_PADRAO
    inmet_anos: tuple[int, ...] = INMET_ANOS_PADRAO


def load_config() -> Config:
    """Lê e valida as variáveis de ambiente necessárias para a ingestão."""
    obrigatorias = {
        "CKAN_BASE_URL": os.getenv("CKAN_BASE_URL"),
        "CKAN_DATASET": os.getenv("CKAN_DATASET"),
        "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT"),
        "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY"),
        "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY"),
        "MINIO_BUCKET": os.getenv("MINIO_BUCKET"),
    }

    faltando = [chave for chave, valor in obrigatorias.items() if not valor]
    if faltando:
        raise RuntimeError(
            f"Variáveis de ambiente ausentes: {', '.join(faltando)}. "
            "Copie .env.example para .env e preencha os valores."
        )

    return Config(
        ckan_base_url=obrigatorias["CKAN_BASE_URL"].rstrip("/"),
        ckan_dataset=obrigatorias["CKAN_DATASET"],
        minio_endpoint=obrigatorias["MINIO_ENDPOINT"],
        minio_access_key=obrigatorias["MINIO_ACCESS_KEY"],
        minio_secret_key=obrigatorias["MINIO_SECRET_KEY"],
        minio_bucket=obrigatorias["MINIO_BUCKET"],
        http_timeout=int(os.getenv("HTTP_TIMEOUT", "30")),
        ckan_territorio_dataset=os.getenv(
            "CKAN_TERRITORIO_DATASET", CKAN_TERRITORIO_DATASET_PADRAO
        ),
        inmet_anos=_parse_anos(os.getenv("INMET_ANOS")),
    )


def _parse_anos(valor: str | None) -> tuple[int, ...]:
    if not valor:
        return INMET_ANOS_PADRAO
    return tuple(int(parte.strip()) for parte in valor.split(",") if parte.strip())
