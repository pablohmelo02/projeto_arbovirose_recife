"""Contrato de dados da camada climática **em grade** (reanálise).

Esta camada existe por um motivo único e delimitado: a série epidemiológica
do projeto cobre 2013-2025, mas a rede de estações real (CEMADEN) só produz
leitura utilizável a partir de 2024 (ver
`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`).
Nenhuma rede de estações investigada (APAC, CEMADEN, ANA/Hidroweb, INMET
dentro do Recife) resolve 2013-2023. A reanálise em grade resolve a
**dimensão temporal** — e só ela.

## Grade não é estação (regra de linguagem, não só de dado)

Cada valor é a estimativa de uma **célula de grade** de um modelo de
reanálise, não a leitura de um sensor num bairro. As duas coisas coexistem
na Gold em colunas separadas e nunca são somadas, mediadas ou usadas uma
como substituta silenciosa da outra. Qualquer texto de UI/relatório deve
dizer *estimativa climática em grade (reanálise)* com a resolução
declarada; dizer "estação meteorológica do bairro" seria falso.

## Duas grades, resoluções diferentes — medido, não presumido

Verificado por requisição real (ver
`reports/climate_source_analysis/gridded_climate_investigation.md`): o
provedor não serve `precipitation_sum` para o modelo `era5_land` (devolve
nulo em toda a janela testada), então precipitação e temperatura/umidade
vêm de **grades diferentes**, com resoluções diferentes. Isso é modelado
explicitamente (uma linha por `grade`), nunca escondido atrás de um único
rótulo "ERA5".

| grade       | resolução | variáveis                                        |
|-------------|-----------|--------------------------------------------------|
| `ERA5`      | 0,25°     | `precipitacao_mm`                                |
| `ERA5-LAND` | 0,10°     | temperatura média/mín/máx, umidade relativa média |

## Quantas células cobrem o Recife (medido)

Os centroides dos 94 bairros ocupam apenas ~0,19° de latitude por ~0,12° de
longitude. Consequência direta, medida sobre os centroides reais:
`ERA5` (0,25°) resolve **3** células distintas e `ERA5-LAND` (0,10°)
resolve **5** — contra 16 estações CEMADEN distintas usadas pela Estratégia
A. Portanto o sinal em grade é, na prática, **quase municipal**: ele
informa *quando*, não *onde dentro do Recife*. Essa é a limitação central
desta fonte e precisa aparecer em qualquer análise que a use.

## Regra de ausência preservada

`precipitacao_mm` ausente continua sendo ausente (`None`), nunca `0` — a
mesma regra inegociável da camada de estações (CLAUDE.md §5). Reanálise
raramente tem lacuna, mas quando o provedor devolve nulo isso é propagado
como nulo, e o número de dias válidos é contado explicitamente.
"""
from __future__ import annotations

VERSAO_SCHEMA_CLIMA_GRADE = "1.0"

FONTE_CLIMA_GRADE = "ERA5/ERA5-LAND (reanalise em grade, via Open-Meteo Archive)"

GRADE_PRECIPITACAO = "ERA5"
GRADE_TEMPERATURA = "ERA5-LAND"

GRADES = (GRADE_PRECIPITACAO, GRADE_TEMPERATURA)

RESOLUCAO_GRAUS_POR_GRADE = {
    GRADE_PRECIPITACAO: 0.25,
    GRADE_TEMPERATURA: 0.10,
}

#: Variáveis diárias que cada grade efetivamente fornece (medido, ver
#: docstring). Uma variável fora desta lista fica `None` na linha daquela
#: grade — nunca preenchida a partir da outra grade.
VARIAVEIS_POR_GRADE = {
    GRADE_PRECIPITACAO: ("precipitacao_mm",),
    GRADE_TEMPERATURA: (
        "temperatura_media_c",
        "temperatura_minima_c",
        "temperatura_maxima_c",
        "umidade_relativa_media_pct",
    ),
}

#: Mapa nome-da-API -> nome-canônico-do-projeto. Mantido aqui (contrato) e
#: não no cliente, porque é decisão de modelagem, não de transporte.
MAPA_VARIAVEIS_API = {
    "precipitation_sum": "precipitacao_mm",
    "temperature_2m_mean": "temperatura_media_c",
    "temperature_2m_min": "temperatura_minima_c",
    "temperature_2m_max": "temperatura_maxima_c",
    "relative_humidity_2m_mean": "umidade_relativa_media_pct",
}

COLUNAS_SILVER_CLIMA_GRADE_DIARIO = (
    "grade",
    "celula_id",
    "latitude_celula",
    "longitude_celula",
    "data",
    "precipitacao_mm",
    "temperatura_media_c",
    "temperatura_minima_c",
    "temperatura_maxima_c",
    "umidade_relativa_media_pct",
    "versao_schema_clima_grade",
    "_processed_at",
)

#: Chave única da Silver diária em grade. `celula_id` sozinho NÃO é chave
#: (a mesma coordenada pode existir em duas grades diferentes) — mesma
#: lição já aprendida com `(fonte, codigo_estacao)` na camada de estações.
CHAVE_SILVER_CLIMA_GRADE_DIARIO = ("grade", "celula_id", "data")

COLUNAS_SILVER_BAIRRO_CELULA_GRADE = (
    "codigo_bairro",
    "nome_bairro",
    "grade",
    "celula_id",
    "latitude_celula",
    "longitude_celula",
    "resolucao_graus",
    "distancia_centroide_celula_km",
    "metodo_associacao",
    "versao_schema_clima_grade",
    "_processed_at",
)

CHAVE_SILVER_BAIRRO_CELULA_GRADE = ("codigo_bairro", "grade")

#: A associação bairro -> célula NÃO é "estação mais próxima" (Estratégia
#: A). É "a célula da grade cujo valor o provedor devolve para o centroide
#: do bairro" — ou seja, a célula que **contém** o ponto representativo do
#: bairro. Nome distinto de propósito, para nunca ser confundido com o
#: método da camada de estações em relatório/UI.
METODO_ASSOCIACAO_GRADE = "celula_que_contem_o_centroide"

#: Limites físicos plausíveis, usados pela validação de schema. Fora deles
#: a linha é rejeitada e contada (nunca corrigida silenciosamente).
LIMITES_PLAUSIVEIS = {
    "precipitacao_mm": (0.0, 500.0),
    "temperatura_media_c": (-5.0, 50.0),
    "temperatura_minima_c": (-10.0, 45.0),
    "temperatura_maxima_c": (0.0, 55.0),
    "umidade_relativa_media_pct": (0.0, 100.0),
}
