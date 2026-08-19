"""Contrato canônico da Silver de clima (`silver_estacao_climatica` e
`silver_clima_diario`).

Definido depois do profiling real de ambas as fontes (ver
`reports/climate_profile/` e `reports/climate_source_analysis/source_analysis.md`).
Achados que sustentam este desenho:

- INMET: cada CSV de estação tem 8 linhas de metadados confiáveis
  (`REGIAO`, `UF`, `ESTACAO`, `CODIGO (WMO)`, `LATITUDE`, `LONGITUDE`,
  `ALTITUDE`, `DATA DE FUNDACAO`) e uma série **horária** completa (ex.:
  Palmares/2024 teve 8.784 registros = 366 dias × 24h, cobertura 100%).
  Não há campo de município nem de data de fim de operação nesse arquivo —
  por isso `municipio` e `data_fim` ficam nulos para o INMET nesta etapa
  (existe um catálogo oficial separado com essas informações para as
  estações convencionais, mas cruzá-lo não está automatizado ainda — ver
  README, seção de limitações).
- APAC: cada instantâneo da rede PCD dá `id`, `nome`, `latitude`,
  `longitude` e o município (campo posicional "3"), mas não dá altitude,
  data de início/fim de operação, nem temperatura/umidade — só
  precipitação acumulada em janelas de tempo (15min a 24h). Por isso
  `silver_clima_diario` da APAC tem `temperatura_*`/`umidade_*` sempre
  nulos — não inventamos esses valores.
- Datas do INMET usam formato `DD/MM/AA` com ano de 2 dígitos (ex.:
  "04/09/08") — assumimos a regra POSIX padrão (`%y`): 00-68 -> 2000-2068,
  69-99 -> 1969-1999. Documentado porque é uma decisão, não um fato óbvio.
- Valores numéricos do INMET usam vírgula decimal (formato brasileiro,
  ex.: "25,5") — convertidos explicitamente, nunca via inferência automática
  do pandas (que trataria como string ou geraria erro).
"""
from __future__ import annotations

FONTES_CLIMA = ("INMET", "APAC")

COLUNAS_SILVER_ESTACAO_CLIMATICA = (
    "codigo_estacao",
    "nome_estacao",
    "fonte",
    "latitude",
    "longitude",
    "altitude",
    "municipio",
    "uf",
    "data_inicio",
    "data_fim",
    "_source",
    "_processed_at",
)

COLUNAS_SILVER_CLIMA_DIARIO = (
    "data",
    "codigo_estacao",
    "fonte",
    "precipitacao_mm",
    "temperatura_min_c",
    "temperatura_max_c",
    "temperatura_media_c",
    "umidade_min_pct",
    "umidade_max_pct",
    "umidade_media_pct",
    "_source_resource",
    "_ingestion_run_id",
    "_processed_at",
)

# Nomes de coluna reais do CSV horário do INMET usados na agregação diária
# (verificados contra arquivos reais — ver docstring do módulo).
COLUNA_INMET_PRECIPITACAO = "PRECIPITAÇÃO TOTAL, HORÁRIO (mm)"
COLUNA_INMET_TEMPERATURA = "TEMPERATURA DO AR - BULBO SECO, HORARIA (°C)"
COLUNA_INMET_UMIDADE = "UMIDADE RELATIVA DO AR, HORARIA (%)"

# Limites plausíveis de temperatura para o Nordeste do Brasil (contexto:
# Recife/PE nunca registrou geada nem calor extremo continental). Usado só
# para GERAR AVISO em quality.py — nunca para rejeitar/descartar a linha
# automaticamente (ver README, "não excluir outliers com regra arbitrária").
TEMPERATURA_MIN_PLAUSIVEL_C = 10.0
TEMPERATURA_MAX_PLAUSIVEL_C = 42.0
