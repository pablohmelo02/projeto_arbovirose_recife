"""Cliente para o download histórico em massa do INMET (BDMEP).

Diferente do CKAN (usado por arboviroses e território), o INMET distribui
seus dados históricos como arquivos ZIP estáticos anuais — não há API REST
documentada e estável (a API não-documentada `apitempo.inmet.gov.br` foi
testada em 2026-08-19 e respondeu erro 500/502 de forma reproduzível; ver
`reports/climate_source_analysis/source_analysis.md`). Por isso este cliente
não tenta reusar `CkanClient` (não é um dataset CKAN) nem a API instável —
baixa diretamente o ZIP oficial.

Cada ZIP contém um CSV por estação automática convencional do Brasil inteiro
para aquele ano (~560 arquivos, ~100MB). Este cliente extrai só os arquivos
de Pernambuco (`_PE_` no nome) — não por economia arbitrária, mas porque o
projeto é sobre Recife/PE; os demais estados não são relevantes aqui.
"""
from __future__ import annotations

import io
import logging
import zipfile
from typing import Optional

import requests

logger = logging.getLogger(__name__)

URL_BASE = "https://portal.inmet.gov.br/uploads/dadoshistoricos"


class InmetClientError(Exception):
    """Erro ao interagir com a distribuição de dados históricos do INMET."""


class InmetClient:
    def __init__(self, timeout: int = 60, url_base: str = URL_BASE) -> None:
        self._timeout = timeout
        self._url_base = url_base.rstrip("/")

    def baixar_zip_ano(self, ano: int) -> bytes:
        """Baixa o ZIP anual oficial de dados históricos (todas as estações do Brasil)."""
        url = f"{self._url_base}/{ano}.zip"
        try:
            response = requests.get(
                url, timeout=self._timeout, headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InmetClientError(f"Falha ao baixar {url}: {exc}") from exc
        return response.content

    def extrair_estacoes_uf(
        self, conteudo_zip: bytes, uf: str = "PE"
    ) -> list[tuple[str, bytes]]:
        """Extrai, do ZIP anual, apenas os CSVs de uma UF (por padrão, Pernambuco).

        Retorna uma lista de (nome_arquivo_original, conteudo_bytes) — o
        conteúdo de cada CSV não é alterado, só filtrado por UF.
        """
        marcador = f"_{uf}_"
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as zf:
                nomes = [n for n in zf.namelist() if marcador in n]
                return [(nome, zf.read(nome)) for nome in nomes]
        except zipfile.BadZipFile as exc:
            raise InmetClientError(f"ZIP inválido ou corrompido: {exc}") from exc

    def baixar_catalogo_estacoes(self, timeout: Optional[int] = None) -> bytes:
        """Baixa o catálogo oficial de estações (normais climatológicas 1991-2020).

        Fonte: portal.inmet.gov.br/uploads/normais/Normal-Climatologica-ESTAÇÕES.xlsx
        Contém código, nome, UF, lat/lon, altitude, período de operação e
        situação (ativa/fechada) de cada estação — inclusive a única que já
        existiu em Recife (código 82900, "RECIFE (CURADO)", fechada em 2020).
        """
        url = (
            "https://portal.inmet.gov.br/uploads/normais/"
            "Normal-Climatologica-ESTA%C3%87%C3%95ES.xlsx"
        )
        try:
            response = requests.get(
                url, timeout=timeout or self._timeout, headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InmetClientError(f"Falha ao baixar catálogo de estações: {exc}") from exc
        return response.content
