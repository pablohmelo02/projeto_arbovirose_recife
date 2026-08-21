"""Cliente para séries climáticas diárias em **grade** (reanálise ERA5 /
ERA5-Land), servidas pela Open-Meteo Historical Weather API.

## Por que esta fonte existe no projeto

A rede de estações (CEMADEN) só tem profundidade histórica útil a partir de
2024 (ver `reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`),
enquanto a série epidemiológica cobre 2013-2025. Esta fonte preenche
**exclusivamente a dimensão temporal** que nenhuma rede de estações do
projeto conseguiu cobrir — nunca substitui a estação onde ela existe.

## Isto NÃO é "a estação meteorológica do bairro"

`ERA5`/`ERA5-Land` são produtos de **reanálise em grade**: cada valor é a
estimativa de uma célula de grade, não a leitura de um sensor. A célula é
muito maior que um bairro do Recife (ver `RESOLUCAO_GRAUS_*` abaixo e
`src/silver/schema_climate_grade.py` para os números medidos). Qualquer
texto de UI/relatório deve chamar isto de *estimativa climática em grade /
reanálise*, com a resolução declarada — nunca de "estação do bairro".

## Provenância por variável (medida, não presumida)

Verificado por requisição real nesta implementação (ver
`reports/climate_source_analysis/gridded_climate_investigation.md`):

- `precipitation_sum` **não é servida** pelo modelo `era5_land` neste
  provedor (retorna nulo em toda a janela testada) — precipitação vem do
  modelo `era5`, resolução ~0,25 grau.
- `temperature_2m_*` e `relative_humidity_2m_mean` vêm do modelo
  `era5_land`, resolução ~0,1 grau.

Por isso o cliente pede **um modelo por requisição** e quem consome
registra a provenância de cada variável; nunca se usa o modelo "seamless"
(que mistura os dois silenciosamente sob um único rótulo).

## Timezone

Todas as requisições fixam `timezone=America/Recife` — a agregação diária
do provedor passa a usar o dia-calendário local, o mesmo referencial das
datas epidemiológicas do SINAN (`DT_NOTIFIC`) e das semanas
epidemiológicas da Gold. Nunca deixar o default (UTC), que deslocaria a
fronteira do dia em 3 horas.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Sequence

import requests

logger = logging.getLogger(__name__)

URL_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

MODELO_PRECIPITACAO = "era5"
MODELO_TEMPERATURA = "era5_land"

RESOLUCAO_GRAUS_ERA5 = 0.25
RESOLUCAO_GRAUS_ERA5_LAND = 0.1

TIMEZONE_REQUISICAO = "America/Recife"

VARIAVEIS_PRECIPITACAO = ("precipitation_sum",)
VARIAVEIS_TEMPERATURA = (
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "relative_humidity_2m_mean",
)

TENTATIVAS_PADRAO = 3
ESPERA_INICIAL_SEGUNDOS = 2.0


class GriddedClimateClientError(Exception):
    """Erro ao obter séries climáticas em grade."""


class OpenMeteoArchiveClient:
    """Baixa séries diárias de reanálise para uma lista de pontos.

    Devolve sempre os **bytes brutos** da resposta (JSON), como os outros
    clientes de clima do projeto — parsing/normalização é responsabilidade
    da Silver (`src/silver/climate_grade.py`), nunca do cliente.
    """

    def __init__(
        self,
        timeout: int = 120,
        url_archive: str = URL_ARCHIVE,
        tentativas: int = TENTATIVAS_PADRAO,
        espera_inicial: float = ESPERA_INICIAL_SEGUNDOS,
    ) -> None:
        if tentativas < 1:
            raise ValueError("tentativas deve ser >= 1")
        self._timeout = timeout
        self._url_archive = url_archive
        self._tentativas = tentativas
        self._espera_inicial = espera_inicial

    def baixar_series_diarias(
        self,
        pontos: Sequence[tuple[float, float]],
        data_inicio: str,
        data_fim: str,
        variaveis: Sequence[str],
        modelo: str,
    ) -> bytes:
        """`pontos` = sequência de `(latitude, longitude)`. A API aceita
        múltiplos pontos numa única requisição (latitudes/longitudes
        separadas por vírgula) e devolve uma **lista** de objetos, um por
        ponto, na mesma ordem — deduplicar pontos que caem na mesma célula
        é responsabilidade de quem chama (o provedor não deduplica: pontos
        distintos que caem na mesma célula devolvem a mesma série repetida).

        Levanta `GriddedClimateClientError` em falha de rede, HTTP fora de
        2xx, JSON inválido, resposta com erro declarado ou lista de tamanho
        diferente do número de pontos pedidos (schema drift).
        """
        if not pontos:
            raise ValueError("nenhum ponto informado")
        if not variaveis:
            raise ValueError("nenhuma variável informada")

        params = {
            "latitude": ",".join(f"{lat:.6f}" for lat, _ in pontos),
            "longitude": ",".join(f"{lon:.6f}" for _, lon in pontos),
            "start_date": data_inicio,
            "end_date": data_fim,
            "daily": ",".join(variaveis),
            "timezone": TIMEZONE_REQUISICAO,
            "models": modelo,
        }

        conteudo = self._get_com_retentativa(
            params, descricao=f"modelo={modelo}, {len(pontos)} ponto(s)"
        )
        self._validar_payload(conteudo, n_pontos=len(pontos), variaveis=variaveis, modelo=modelo)
        return conteudo

    # ------------------------------------------------------------------
    def _get_com_retentativa(self, params: dict[str, Any], descricao: str) -> bytes:
        espera = self._espera_inicial
        ultimo_erro: Exception | None = None
        for tentativa in range(1, self._tentativas + 1):
            try:
                response = requests.get(self._url_archive, params=params, timeout=self._timeout)
                response.raise_for_status()
                if not response.content:
                    raise GriddedClimateClientError("resposta vazia (0 bytes)")
                return response.content
            except (requests.RequestException, GriddedClimateClientError) as exc:
                ultimo_erro = exc
                if tentativa == self._tentativas:
                    break
                logger.warning(
                    "Tentativa %d/%d falhou (%s): %s -- nova tentativa em %.1fs",
                    tentativa, self._tentativas, descricao, exc, espera,
                )
                time.sleep(espera)
                espera *= 2
        raise GriddedClimateClientError(
            f"Falha ao baixar série em grade ({descricao}) após "
            f"{self._tentativas} tentativa(s): {ultimo_erro}"
        ) from ultimo_erro

    @staticmethod
    def _validar_payload(
        conteudo: bytes, n_pontos: int, variaveis: Sequence[str], modelo: str
    ) -> None:
        """Falha cedo em schema drift, em vez de deixar a Silver receber
        algo com forma inesperada (regra de robustez do projeto: nunca
        engolir erro silenciosamente)."""
        try:
            payload = json.loads(conteudo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise GriddedClimateClientError(f"resposta não é JSON UTF-8 válido: {exc}") from exc

        # 1 ponto -> objeto; N pontos -> lista de objetos.
        itens = payload if isinstance(payload, list) else [payload]

        if isinstance(payload, dict) and payload.get("error"):
            raise GriddedClimateClientError(f"API retornou erro: {payload.get('reason')!r}")

        if len(itens) != n_pontos:
            raise GriddedClimateClientError(
                f"schema inesperado: pedidos {n_pontos} ponto(s), recebidos {len(itens)}"
            )

        for i, item in enumerate(itens):
            if not isinstance(item, dict):
                raise GriddedClimateClientError(f"item {i} da resposta não é objeto JSON")
            if item.get("error"):
                raise GriddedClimateClientError(f"ponto {i} retornou erro: {item.get('reason')!r}")
            diario = item.get("daily")
            if not isinstance(diario, dict) or "time" not in diario:
                raise GriddedClimateClientError(
                    f"ponto {i} sem bloco 'daily.time' (modelo={modelo})"
                )
            n_dias = len(diario["time"])
            for variavel in variaveis:
                if variavel not in diario:
                    raise GriddedClimateClientError(
                        f"ponto {i}: variável {variavel!r} ausente na resposta (modelo={modelo})"
                    )
                if len(diario[variavel]) != n_dias:
                    raise GriddedClimateClientError(
                        f"ponto {i}: variável {variavel!r} com {len(diario[variavel])} valores "
                        f"para {n_dias} datas (modelo={modelo})"
                    )
