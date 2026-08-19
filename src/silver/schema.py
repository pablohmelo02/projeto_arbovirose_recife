"""Contrato canônico da Silver de arboviroses (`silver_arboviroses`).

Definido a partir do profiling real da Bronze (rodar `python -m src.profile`
gera `reports/bronze_profile/`, que sustenta as afirmações abaixo), não de
suposição. Principais achados que motivam este desenho:

- Praticamente nenhuma coluna bruta é estável em TODOS os anos de uma mesma
  doença: os arquivos até ~2020 usam nomes em português minúsculo
  (`nu_notificacao`, `no_bairro_residencia`, `notificacao_ano`/`ano_notificacao`),
  enquanto 2021 em diante usa os códigos padrão do SINAN (`NU_NOTIFIC`,
  `NM_BAIRRO`, `NU_ANO`). Por isso o contrato é definido por ALIAS: cada
  campo canônico lista as variantes de nome conhecidas e verificadas
  manualmente contra `reports/bronze_profile/schema_comparison.csv`
  (`ALIASES_FATO` abaixo) — não um único nome fixo.
- O código de doença dentro do próprio arquivo (`ID_AGRAVO`/`co_cid`) NÃO é
  confiável como fonte da verdade: o recurso "Zika 2021" do CKAN contém, na
  prática, 100% de registros de Chikungunya (mesmo código CID `A92.0`,
  mesmos `NU_NOTIFIC` do arquivo de Chikungunya 2021 — a fonte publicou o
  arquivo errado sob esse nome). Por isso `tipo_arbovirose` vem da
  classificação já feita na Bronze (`entidade`, obtida do nome do recurso no
  CKAN), e o código do arquivo é usado só para VALIDAR essa classificação
  (ver `quality.py` e `arboviroses.py`), nunca para defini-la.
- `chikungunya_2017` tem o cabeçalho corrompido: a 3ª coluna, que em todo
  outro ano é `co_cid`, contém o literal `"A92"` — um valor de dado vazou
  para dentro do nome da coluna na fonte. `codigo_agravo` fica nulo nesse
  arquivo especificamente.
- `chikungunya_2024` tem 17 colunas de cabeçalho vazio no final do arquivo
  (sobra de `;` no cabeçalho) — viram colunas sem alias e são ignoradas.
- Datas aparecem em 3 formatos diferentes dependendo do ano de origem:
  `DD/MM/AAAA` (maioria dos anos), `AAAA-MM-DD` (ex.: chikungunya 2017) e
  `AAAA/MM/DD HH:MM:SS` (ex.: dengue 2013) — `quality.parsear_data` tenta os
  três, nessa ordem.
- Semana epidemiológica é estável no formato `AAAASS` (6 dígitos, ano+semana)
  em todos os anos verificados.
- `hospitalizado` está ausente em `dengue_2014` e em TODOS os anos de Zika
  de 2021 em diante (a fonte parou de publicar esse campo para Zika nesse
  período) — o campo fica nulo nesses casos; não é um erro do pipeline.
- `SG_UF`/`co_uf_residencia` é o código IBGE da UF (ex.: `26` = Pernambuco),
  não a sigla — confirmado batendo com a dimensão `uf` da própria Bronze
  (`codigo=26` -> `sigla=PE`).
- Chikungunya usa DOIS códigos CID legítimos conforme o ano: a categoria
  CID-10 de 3 caracteres `A92` em 2015-2019, e a subcategoria completa
  `A92.0` (normalizada para `A920`) a partir de 2020. Verificado nos dados
  reais: cada ano usa consistentemente um ou outro em 100% das linhas — não
  é erro de dado, é só uma mudança de precisão de codificação ao longo do
  tempo. Por isso `CODIGO_AGRAVO_ESPERADO["CHIKUNGUNYA"]` aceita as duas
  formas. Dengue (`A90`) e Zika (`A928`) foram verificados como consistentes
  em 100% dos anos, sem essa ambiguidade.
"""
from __future__ import annotations

TIPOS_ARBOVIROSE = ("DENGUE", "ZIKA", "CHIKUNGUNYA")

# Códigos CID esperados por doença (normalizados: sem pontuação, maiúsculo),
# conforme a própria dimensão `agravo` da Bronze (A90=Dengue, A928=Zika,
# A920=Chikungunya). Usado só para VALIDAR `tipo_arbovirose` — nunca para
# defini-lo (ver docstring do módulo). Mais de um código por doença é
# permitido (ver nota sobre Chikungunya acima).
CODIGO_AGRAVO_ESPERADO: dict[str, tuple[str, ...]] = {
    "DENGUE": ("A90",),
    "ZIKA": ("A928",),
    "CHIKUNGUNYA": ("A920", "A92"),
}

# Aliases verificados manualmente contra reports/bronze_profile/schema_comparison.csv
# (gerado a partir de uma ingestão real dos 40 recursos da Bronze).
ALIASES_FATO: dict[str, tuple[str, ...]] = {
    "id_notificacao": ("NU_NOTIFIC", "NU_NOTIFICACAO"),
    "tipo_notificacao": ("TP_NOT", "TP_NOTIFICACAO"),
    "codigo_agravo": ("ID_AGRAVO", "CO_CID"),
    "data_notificacao": ("DT_NOTIFIC", "DT_NOTIFICACAO"),
    "ano_notificacao": ("NU_ANO", "NOTIFICACAO_ANO", "ANO_NOTIFICACAO"),
    "semana_notificacao": ("SEM_NOT", "DS_SEMANA_NOTIFICACAO"),
    "data_inicio_sintomas": ("DT_SIN_PRI", "DT_DIAGNOSTICO_SINTOMA"),
    "semana_inicio_sintomas": ("SEM_PRI", "DS_SEMANA_SINTOMA"),
    "codigo_bairro": ("ID_BAIRRO", "CO_BAIRRO_RESIDENCIA"),
    "nome_bairro": ("NM_BAIRRO", "NO_BAIRRO_RESIDENCIA"),
    "codigo_distrito": ("ID_DISTRIT", "CO_DISTRITO_RESIDENCIA"),
    "codigo_municipio": ("ID_MUNICIP", "CO_MUNICIPIO_RESIDENCIA"),
    "uf": ("SG_UF", "CO_UF_RESIDENCIA"),
    "classificacao_final": ("CLASSI_FIN", "TP_CLASSIFICACAO_FINAL"),
    "evolucao": ("EVOLUCAO", "TP_EVOLUCAO_CASO"),
    "hospitalizado": ("HOSPITALIZ", "ST_OCORREU_HOSPITALIZACAO"),
}

# Campos tratados como código/string (nunca numérico): preservam zeros à
# esquerda e não sofrem conversão para int/float real.
CAMPOS_CODIGO = (
    "id_notificacao",
    "tipo_notificacao",
    "codigo_agravo",
    "semana_notificacao",
    "semana_inicio_sintomas",
    "codigo_bairro",
    "codigo_distrito",
    "codigo_municipio",
    "uf",
    "classificacao_final",
    "evolucao",
    "hospitalizado",
)

CAMPOS_DATA = ("data_notificacao", "data_inicio_sintomas")

# Campos de negócio + metadados técnicos de lineage (prefixo `_`), na ordem
# em que são gravados no Parquet da Silver.
COLUNAS_SILVER_ARBOVIROSES = (
    "id_notificacao",
    "tipo_arbovirose",
    "tipo_notificacao",
    "codigo_agravo",
    "data_notificacao",
    "ano_notificacao",
    "semana_notificacao",
    "data_inicio_sintomas",
    "semana_inicio_sintomas",
    "codigo_bairro",
    "nome_bairro",
    "codigo_distrito",
    "codigo_municipio",
    "uf",
    "classificacao_final",
    "evolucao",
    "hospitalizado",
    "_source_resource_id",
    "_source_year",
    "_ingestion_run_id",
    "_processed_at",
)

# Dimensões: mapeamento POSICIONAL, não por nome de coluna — os cabeçalhos
# reais têm caracteres especiais (º, ç, ã) com codificação inconsistente, e
# cada arquivo tem só 2 a 4 colunas, então a posição é mais robusta que casar
# o nome exato. Verificado contra os arquivos reais de dimensão da Bronze.
COLUNAS_DIMENSAO_BAIRRO = ("codigo_bairro", "nome_bairro", "nome_municipio")
COLUNAS_DIMENSAO_DISTRITO = (
    "codigo_distrito", "nome_distrito", "codigo_municipio", "nome_municipio",
)
COLUNAS_DIMENSAO_AGRAVO = ("codigo_cid", "nome_agravo")
COLUNAS_DIMENSAO_MUNICIPIO = ("uf_sigla", "codigo_municipio", "nome_municipio")
COLUNAS_DIMENSAO_UF = ("codigo_uf", "sigla_uf", "nome_uf")
