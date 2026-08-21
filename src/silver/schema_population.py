"""Contrato de dados da camada `silver_populacao_bairro_ano`.

Resolve a lacuna documentada em `schema_gold_arboviroses_clima.py` ("nenhuma
fonte do projeto tem população por bairro"): a partir desta camada, existe
uma série anual de população por bairro (94/94), 2010-2025, construída com
os checkpoints oficiais/institucionais realmente disponíveis — nunca
inventada, nunca tratada como observada quando é estimada.

## Checkpoints reais usados (ver `data/bronze/populacao/` para a proveniência completa)

| ano  | fonte                                   | tipo               |
|------|------------------------------------------|--------------------|
| 2010 | IBGE Censo 2010 (via CIEVS/Sesau Recife) | CENSO_OBSERVADO    |
| 2011-2016 | CIEVS/Sesau Recife (partilha proporcional fixa do Censo 2010 aplicada às projeções municipais do IBGE) | ESTIMATIVA_INTERCENSITARIA |
| 2017 | CIEVS/Sesau Recife (idem)                | ESTIMATIVA_INTERCENSITARIA |
| 2018-2021 | reconstrução própria (CAGR por bairro entre os checkpoints 2017 e 2022, reconciliada à série municipal oficial do IBGE) | ESTIMATIVA_INTERCENSITARIA |
| 2022 | IBGE Censo 2022 (produto "Agregados por Bairro") | CENSO_OBSERVADO |
| 2023 | projeção pós-Censo (município interpolado entre 2022 e 2024; participação por bairro = Censo 2022) | PROJECAO_POS_CENSO |
| 2024-2025 | projeção pós-Censo (ver `src/population/reconstruction.py::projetar_pos_censo` para o método escolhido entre as alternativas comparadas) | PROJECAO_POS_CENSO |

Não existe checkpoint oficial por bairro entre 2017 e 2022 nem depois de
2022 — os anos `ESTIMATIVA_INTERCENSITARIA` (2018-2021) e
`PROJECAO_POS_CENSO` (2023-2025) são reconstrução deste projeto, não dado
publicado por bairro. A reconciliação ao total municipal oficial do IBGE
(SIDRA, tabelas 202/6579/9514) é aplicada em todos os anos reconstruídos —
nunca nos anos observados/checkpoint, que já batem com o total oficial por
construção da própria fonte.

## Chave de junção com o território: nome normalizado, não código

Nenhuma das fontes de população publica o `codigo_bairro` interno usado por
`silver_bairro_geo` (ver `schema_territorio.py`) — nem o CIEVS nem o IBGE
Censo 2022 (que usa `CD_BAIRRO`, um código de 10 dígitos, espaço de códigos
diferente). O join é feito por nome normalizado (maiúsculo, sem acento, sem
pontuação — mesmo princípio de `limpar_texto`, estendido com remoção de
acento porque as fontes de população vêm com acentuação e `silver_bairro_geo`
não). Duas correções pontuais e documentadas (não fuzzy matching) resolvem
94/94 em ambas as fontes: ver `src/population/reconstruction.py::CROSSWALK_NOMES`.

## `populacao_municipal_referencia` e `fator_reconciliacao`

Todo ano carrega o total municipal oficial usado como referência daquele
ano (mesmo nos anos observados, onde o fator é 1.0 por construção). Isso
permite auditar, para qualquer ano, se a soma dos 94 bairros bate com a
fonte municipal independente — nunca forçado a bater artificialmente sem
essa coluna tornar o ajuste visível.
"""
from __future__ import annotations

TIPO_CENSO_OBSERVADO = "CENSO_OBSERVADO"
TIPO_ESTIMATIVA_OFICIAL = "ESTIMATIVA_OFICIAL"
TIPO_ESTIMATIVA_INTERCENSITARIA = "ESTIMATIVA_INTERCENSITARIA"
TIPO_PROJECAO_POS_CENSO = "PROJECAO_POS_CENSO"

TIPOS_VALOR_POPULACAO = (
    TIPO_CENSO_OBSERVADO,
    TIPO_ESTIMATIVA_OFICIAL,
    TIPO_ESTIMATIVA_INTERCENSITARIA,
    TIPO_PROJECAO_POS_CENSO,
)

VERSAO_SCHEMA_POPULACAO = "1.0"

ANO_MINIMO = 2010
ANO_MAXIMO = 2025

COLUNAS_SILVER_POPULACAO_BAIRRO_ANO = (
    "codigo_bairro",
    "nome_bairro",
    "ano",
    "populacao",
    "tipo_valor",
    "fonte_base",
    "metodo",
    "checkpoint_anterior",
    "checkpoint_posterior",
    "populacao_municipal_referencia",
    "fator_reconciliacao",
    "versao_schema_populacao",
    "_processed_at",
)

CHAVE_SILVER_POPULACAO_BAIRRO_ANO = ("codigo_bairro", "ano")
