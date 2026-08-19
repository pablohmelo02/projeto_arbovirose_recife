"""Cliente HTTP para o catálogo CKAN do Portal de Dados Abertos do Recife."""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class CkanApiError(Exception):
    """Erro ao consultar a API do CKAN."""


class ResourceDownloadError(Exception):
    """Erro ao baixar o conteúdo de um recurso do CKAN."""


class CkanClient:
    """Encapsula as chamadas à API Action do CKAN necessárias para a Bronze."""

    def __init__(self, base_url: str, dataset: str, timeout: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._dataset = dataset
        self._timeout = timeout

    def listar_recursos(self) -> list[dict[str, Any]]:
        """Consulta `package_show` e retorna a lista de recursos do dataset."""
        url = f"{self._base_url}/api/3/action/package_show"
        logger.info("Consultando catálogo CKAN: %s", url)

        try:
            response = requests.get(
                url, params={"id": self._dataset}, timeout=self._timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CkanApiError(f"Falha ao consultar package_show: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CkanApiError("Resposta da API CKAN não é um JSON válido") from exc

        if not payload.get("success"):
            raise CkanApiError(
                f"API CKAN retornou success=false: {payload.get('error')}"
            )

        resultado = payload.get("result") or {}
        recursos = resultado.get("resources")
        if recursos is None:
            raise CkanApiError("Resposta da API CKAN não contém 'result.resources'")

        logger.info("%d recursos encontrados", len(recursos))
        return recursos

    def baixar_recurso(self, resource: dict[str, Any]) -> bytes:
        """Baixa o conteúdo bruto de um recurso a partir da sua URL original.

        Não depende do DataStore: sempre baixa o arquivo publicado em `url`,
        pois recursos históricos podem não ter DataStore ativo.
        """
        url = resource.get("url")
        if not url:
            raise ResourceDownloadError("Recurso não possui URL de download")

        try:
            response = requests.get(url, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ResourceDownloadError(f"Falha ao baixar recurso: {exc}") from exc

        return response.content
