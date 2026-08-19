"""Cliente para a rede de telemetria pluviométrica (PCD) da APAC.

Testado em 2026-08-19 (ver `reports/climate_source_analysis/source_analysis.md`):
o painel visual (`www.apac.pe.gov.br/monitoramento`) usa, por baixo, este
endpoint JSON público, sem autenticação. Não há mecanismo de consulta
histórica em lote que funcione (o endpoint de estações convencionais existe
mas devolveu tabelas vazias nos testes, e o geoportal ArcGIS respondeu
HTTP 500) — por isso este cliente só busca o instantâneo atual; o histórico
é construído acumulando execuções da Bronze ao longo do tempo (ver
`src/ingestion/climate_ingestion.py`).
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

URL_PCDS = (
    "https://barramento.apac.pe.gov.br:443/BarramentoServicosApac/"
    "Servicos/Site/PainelMapaGoogle/ServicoMonitoramentoPCDs.php"
)


class ApacClientError(Exception):
    """Erro ao interagir com a API de telemetria da APAC."""


class ApacClient:
    def __init__(self, timeout: int = 30, url_pcds: str = URL_PCDS) -> None:
        self._timeout = timeout
        self._url_pcds = url_pcds

    def baixar_instantaneo_pcds(self) -> bytes:
        """Baixa o instantâneo atual de todas as estações PCD (pluviômetros) de Pernambuco."""
        try:
            response = requests.get(
                self._url_pcds, timeout=self._timeout, headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApacClientError(f"Falha ao baixar instantâneo PCD: {exc}") from exc
        return response.content
