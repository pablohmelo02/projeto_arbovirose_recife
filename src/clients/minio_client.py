"""Cliente responsável por interações com o MinIO (S3 compatível)."""
from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class MinioClientError(Exception):
    """Erro ao interagir com o MinIO."""


class MinioClient:
    """Encapsula criação de bucket, upload de objetos e do manifest de controle."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        try:
            self._s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=BotoConfig(signature_version="s3v4"),
            )
        except (BotoCoreError, ValueError) as exc:
            raise MinioClientError(f"Falha ao criar cliente MinIO: {exc}") from exc

    @property
    def bucket(self) -> str:
        return self._bucket

    def garantir_bucket(self) -> None:
        """Verifica se o bucket existe e cria caso não exista."""
        try:
            self._s3.head_bucket(Bucket=self._bucket)
            return
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code")
            if codigo not in ("404", "NoSuchBucket"):
                raise MinioClientError(
                    f"Falha ao verificar bucket '{self._bucket}': {exc}"
                ) from exc
        except BotoCoreError as exc:
            raise MinioClientError(
                f"Falha de conexão com o MinIO ao verificar bucket: {exc}"
            ) from exc

        logger.info("Bucket '%s' não existe. Criando...", self._bucket)
        try:
            self._s3.create_bucket(Bucket=self._bucket)
        except (ClientError, BotoCoreError) as exc:
            raise MinioClientError(
                f"Falha ao criar bucket '{self._bucket}': {exc}"
            ) from exc

    def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> int:
        """Envia `data` para `key` no bucket configurado e retorna o tamanho em bytes."""
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise MinioClientError(f"Falha ao enviar objeto '{key}': {exc}") from exc
        return len(data)

    def upload_manifest(self, key: str, manifest: dict[str, Any]) -> None:
        """Serializa o manifest em JSON e envia para a área de controle da Bronze."""
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        self.upload_bytes(key, payload, content_type="application/json")

    def download_bytes(self, key: str) -> bytes:
        """Lê e retorna o conteúdo bruto de um objeto do bucket configurado."""
        try:
            resposta = self._s3.get_object(Bucket=self._bucket, Key=key)
            return resposta["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            raise MinioClientError(f"Falha ao ler objeto '{key}': {exc}") from exc

    def listar_chaves(self, prefixo: str) -> list[str]:
        """Lista as chaves de objetos existentes sob um prefixo no bucket."""
        chaves: list[str] = []
        try:
            paginador = self._s3.get_paginator("list_objects_v2")
            for pagina in paginador.paginate(Bucket=self._bucket, Prefix=prefixo):
                for objeto in pagina.get("Contents", []):
                    chaves.append(objeto["Key"])
        except (ClientError, BotoCoreError) as exc:
            raise MinioClientError(
                f"Falha ao listar objetos com prefixo '{prefixo}': {exc}"
            ) from exc
        return chaves
