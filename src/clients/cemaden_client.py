"""Cliente para a rede de telemetria pluviométrica do CEMADEN.

Investigado e validado em 2026-08-19/20 (ver
`reports/climate_source_analysis/cemaden_precipitation_endpoint_investigation.md`
e `reports/climate_source_analysis/cemaden_integration_results.md`): três
acessos HTTP reais, sem autenticação, sem CAPTCHA, sem cookie/sessão.

- **Cadastro geoespacial** (GeoServer WFS, layer `view_pcds_pluviometrica_cemaden`,
  já restrita a estações pluviométricas pelo nome da própria camada): dá
  coordenadas reais, mas não o `idEstacao` numérico usado pela API de
  valores — só um `codestacao` alfanumérico.
- **Status atual** (`getJson2.php`, JSON — uma lista plana, não um objeto
  com chave de topo): dá o `idestacao` numérico e `datahoraUltimovalor`,
  mas não coordenadas, e mistura **vários tipos de estação** (`tipoestacao`)
  — não só pluviométrica. Quem consome isto precisa filtrar
  `tipoestacao == 1` (ver `TIPOESTACAO_PLUVIOMETRICA` em
  `src/ingestion/climate_ingestion.py`).
- **Série horária real de precipitação** (`MapaInterativoWS/resources/horario/{id}/{horas}`):
  o mesmo endpoint que o próprio painel público (`mapainterativo.cemaden.gov.br`)
  usa para desenhar o gráfico interativo — não é uma API "escondida"
  concorrente, é a real, descoberta lendo o JavaScript do painel oficial.

Este cliente só baixa bytes brutos — parsing/normalização semântica (juntar
cadastro com status pelo nome da estação, extrair a matriz de acumulados)
é responsabilidade da Silver (`src/silver/climate.py`), igual aos outros
clientes de clima deste projeto.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

URL_WFS = "https://gsc.cemaden.gov.br/geoserver/cemaden_dev/wfs"
TYPENAME_PLUVIOMETRICA = "cemaden_dev:view_pcds_pluviometrica_cemaden"
URL_STATUS = "https://resources.cemaden.gov.br/graficos/interativo/getJson2.php"
URL_HORARIO_BASE = "https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario"


class CemadenClientError(Exception):
    """Erro ao interagir com os serviços do CEMADEN."""


class CemadenClient:
    def __init__(
        self,
        timeout: int = 30,
        url_wfs: str = URL_WFS,
        url_status: str = URL_STATUS,
        url_horario_base: str = URL_HORARIO_BASE,
    ) -> None:
        self._timeout = timeout
        self._url_wfs = url_wfs
        self._url_status = url_status
        self._url_horario_base = url_horario_base.rstrip("/")

    def baixar_cadastro_estacoes(self, uf: str = "PE") -> bytes:
        """Baixa o cadastro geoespacial (GeoJSON, via WFS) das estações
        pluviométricas de uma UF, filtrado no próprio servidor (`CQL_FILTER`)."""
        try:
            response = requests.get(
                self._url_wfs,
                params={
                    "service": "WFS",
                    "version": "2.0.0",
                    "request": "GetFeature",
                    "typeName": TYPENAME_PLUVIOMETRICA,
                    "outputFormat": "application/json",
                    "CQL_FILTER": f"uf='{uf}'",
                },
                timeout=self._timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CemadenClientError(
                f"Falha ao baixar cadastro de estações CEMADEN: {exc}"
            ) from exc
        return response.content

    def baixar_status_estacoes(self, uf: str = "PE") -> bytes:
        """Baixa o status atual de todas as estações de uma UF (mistura tipos
        de estação diferentes — filtragem por `tipoestacao` é responsabilidade
        de quem consome)."""
        try:
            response = requests.get(
                self._url_status,
                params={"uf": uf},
                timeout=self._timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CemadenClientError(
                f"Falha ao baixar status de estações CEMADEN: {exc}"
            ) from exc
        return response.content

    def baixar_serie_horaria(self, id_estacao: str, horas: int) -> bytes:
        """Baixa a série horária real de precipitação (mm) de uma estação,
        cobrindo as últimas `horas` horas (testado até 8760 = 365 dias em
        uma única chamada, sem paginação nem limite detectado)."""
        url = f"{self._url_horario_base}/{id_estacao}/{horas}"
        try:
            response = requests.get(
                url, timeout=self._timeout, headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CemadenClientError(
                f"Falha ao baixar série horária da estação {id_estacao}: {exc}"
            ) from exc
        return response.content
