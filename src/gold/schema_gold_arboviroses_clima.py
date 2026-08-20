"""Contrato canônico da primeira camada Gold analítica:
`gold_arboviroses_clima_bairro` — arboviroses + território + clima
integrados, grão `bairro × semana epidemiológica × agravo`.

## Por que este grão (não `bairro + mês`)

Decisão tomada depois de inspecionar os dados reais da Silver (não
presumida): `semana_notificacao` (formato `AAAASS`) já existe no SINAN,
nativo, com apenas 75/162.537 nulos (0,05%) — os casos JÁ têm resolução
semanal confiável, sem precisar inventar distribuição diária/semanal a
partir de um agregado mensal. Usar mês jogaria fora precisão que os dados
já sustentam. O join climático é feito por agregação de `silver_clima_diario`
(diário) para o mesmo intervalo semanal — nunca o contrário (nunca se
distribui caso semanal em dias). Ver `reports/gold_analysis/` para a
comparação completa A/B documentada.

## Por que `agravo` em linhas, não em colunas

`tipo_arbovirose` já é tratado como valor de linha em toda a Silver (nunca
uma coluna por doença) — manter o mesmo formato "longo" na Gold evita
misturar Dengue/Zika/Chikungunya sob o mesmo nome de coluna (o que exigiria
inventar uma convenção de nome tipo `casos_dengue`/`casos_zika` só para
esta camada) e mantém a tabela pivotável sob demanda por quem for consumir.

## Junção arboviroses × território: por `nome_bairro`, não `codigo_bairro`

Verificado nos dados reais antes de decidir (não presumido): o
`codigo_bairro` da Silver de arboviroses (`ID_BAIRRO`/`CO_BAIRRO_RESIDENCIA`
do SINAN) **não é o mesmo espaço de códigos** do `codigo_bairro` oficial de
`silver_bairro_geo` — só 21/94 códigos coincidem (provavelmente por
coincidência numérica), e 93 dos 94 bairros oficiais têm mais de um
`codigo_bairro` distinto associado na Silver de arboviroses. Já
`nome_bairro` (normalizado por `limpar_texto` nos dois lados) bate 94/94 —
inclusive contra a própria dimensão `bairro` do domínio arboviroses. Por
isso o join primário é por nome normalizado, com todas as linhas cujo nome
não bate contra os 94 bairros oficiais **excluídas do grão espacial, mas
contadas** (nunca descartadas silenciosamente) — ver
`arboviroses_clima.py::juntar_bairro_oficial`.

## `casos = 0` é materializado, não deixado ausente

Decisão explícita (não assumida): para o grão (bairro, ano_epi, semana_epi,
agravo), a ausência de notificação SINAN significa genuinamente "nenhum
caso notificado naquela semana" — é um sistema de notificação compulsória,
e a Silver já validou que a ingestão de cada ano é completa (100% dos
recursos com sucesso). Por isso a Gold materializa o produto cartesiano
completo (94 bairros × todas as semanas epidemiológicas do intervalo real
dos dados × 3 agravos), com `casos=0` onde não há notificação — necessário
para qualquer modelagem futura de série temporal (sem isso, nenhum modelo
veria "semana sem caso", só teria a distribuição enviesada nas semanas
com caso). Isso é diferente da regra de missing climático (abaixo) porque a
semântica da fonte é diferente: ausência de leitura de sensor é falha de
telemetria (`None`), ausência de notificação compulsória é informação real
(`0`).

## `incidencia_por_100k` NÃO existe nesta versão

Verificado nos dados reais: **nenhuma fonte do projeto (território, SINAN,
dimensões) tem população por bairro** — `silver_bairro_geo` só tem
`area_km2`, não `populacao`/`densidade`. Calcular incidência exigiria uma
nova fonte de dados (ex.: IBGE/Censo), fora do escopo desta etapa e não
implementada sem autorização. `casos` (contagem absoluta) é o único target
epidemiológico disponível.

## Limitação crítica de cobertura climática (ver relatório para detalhe)

O CEMADEN (fonte hoje usada por 100% das associações bairro-estação, ver
Silver `bairro_estacao`) só tem leituras reais em 2026-08-18 a 2026-08-20 —
**depois** do fim da série epidemiológica (`ano_notificacao` até 2025). A
sobreposição temporal real entre clima com dado real e semanas com caso
notificado é, portanto, ~0% nesta execução. As colunas climáticas existem e
são calculadas corretamente (mecanismo validado com teste dedicado), mas
ficam `None` para praticamente todas as linhas históricas — isso não é bug,
é o estado real dos dados hoje (ver §10 do CLAUDE.md e o relatório desta
etapa). Não foi implementada mistura de fontes (INMET regional como proxy
histórico) para preencher esse vazio — decisão explícita, não omissão (ver
relatório, seção "Cobertura temporal").

## Leakage temporal: regra única, testável

Toda feature climática de uma linha (bairro, ano_epi, semana_epi, agravo)
usa **somente** dias de `silver_clima_diario` com `data <= semana_epi_data_fim`
dessa própria linha. Nunca um dia posterior. As janelas retrospectivas
(`chuva_7d_mm` etc.) são janelas móveis **terminando em** `semana_epi_data_fim`
(incluem a própria semana-alvo, não são "estritamente antes dela" — a
precipitação da própria semana não é informação do futuro em relação aos
casos notificados nela). Testado explicitamente em
`tests/test_gold_epidemiologia.py`/`tests/test_gold_arboviroses_clima.py`
injetando um dia de chuva futuro e confirmando que ele nunca entra em
nenhuma feature de uma semana anterior.
"""
from __future__ import annotations

VERSAO_SCHEMA_GOLD = "1.0"

AGRAVOS = ("DENGUE", "ZIKA", "CHIKUNGUNYA")

JANELAS_RETROSPECTIVAS_DIAS = (7, 14, 21, 28)

COLUNAS_GOLD_ARBOVIROSES_CLIMA = (
    # Identificação / grão
    "codigo_bairro",
    "nome_bairro",
    "agravo",
    "ano_epidemiologico",
    "semana_epidemiologica",
    "semana_epi_data_inicio",
    "semana_epi_data_fim",
    # Target epidemiológico
    "casos",
    # Território
    "area_km2",
    "codigo_rpa",
    "codigo_microrregiao",
    "centroide_lat",
    "centroide_lon",
    # Clima — rastreabilidade da estação/fonte usada (Estratégia A)
    "fonte_clima",
    "codigo_estacao_clima",
    "distancia_estacao_km",
    "metodo_associacao_clima",
    # Clima — features da própria semana
    "precipitacao_total_semana_mm",
    "precipitacao_media_diaria_mm",
    "precipitacao_maxima_diaria_mm",
    "dias_com_chuva",
    "dias_com_dado_valido_semana",
    "completude_climatica_semana",
    # Clima — janelas retrospectivas (trailing, terminando no fim da própria semana)
    "chuva_7d_mm",
    "chuva_14d_mm",
    "chuva_21d_mm",
    "chuva_28d_mm",
    "dias_com_dado_valido_7d",
    "dias_com_dado_valido_28d",
    # Rastreabilidade
    "versao_schema_gold",
    "_processed_at",
)
