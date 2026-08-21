"""Constantes compartilhadas da camada de EDA (`src/eda/`) e do dashboard.

Esta camada **consome** `gold_arboviroses_clima_bairro` — não reimplementa
nenhum join/agregação que já existe em `src/gold/` (ver docstring de
`src/eda/filtros.py`). Todas as funções aqui são puras (recebem DataFrame,
devolvem DataFrame/dict), sem I/O e sem dependência do Streamlit, para
poderem ser testadas isoladamente e reutilizadas tanto pelo dashboard quanto
por `reports/eda/` (ver `src/eda/relatorio.py`).
"""
from __future__ import annotations

AGRAVOS = ("DENGUE", "ZIKA", "CHIKUNGUNYA")

JANELAS_LAG_DIAS = (7, 14, 21, 28)

# Ano a partir do qual existe cobertura climática real (CEMADEN pós-backfill,
# ver reports/climate_source_analysis/cemaden_historical_backfill_analysis.md).
# Usado só para destacar a janela na UI/relatório -- a filtragem real de
# "linha com clima utilizável" sempre usa `dias_com_dado_valido_semana > 0`,
# nunca este ano como proxy (uma linha de 2024 sem estação/leitura real
# continua sem clima mesmo estando "dentro" do ano).
ANO_INICIO_COBERTURA_CLIMATICA_REAL = 2024

# Colunas climáticas numéricas elegíveis para correlação exploratória — nunca
# inclui codigo_bairro/codigo_estacao_clima/codigo_rpa (identificadores, não
# variáveis numéricas de conteúdo, ver `src/eda/correlacao.py`).
COLUNAS_CLIMA_NUMERICAS = (
    "precipitacao_total_semana_mm",
    "precipitacao_media_diaria_mm",
    "precipitacao_maxima_diaria_mm",
    "chuva_7d_mm",
    "chuva_14d_mm",
    "chuva_21d_mm",
    "chuva_28d_mm",
)

COLUNA_CASOS = "casos"

# A partir da Gold 1.2 (ver `src/gold/populacao.py`), existe uma série de
# população por bairro/ano reconstruída (94/94 bairros, 2010-2025 — Censos
# 2010/2022 observados, checkpoint institucional 2011-2017, reconstrução
# própria 2018-2021, projeção pós-censo 2023-2025 — ver
# `reports/population/population_incidence_integration.md`), então
# `incidencia_100k` e as janelas móveis existem de verdade na Gold. Nunca
# tratar os anos reconstruídos/projetados (`tipo_populacao != CENSO_OBSERVADO`)
# como equivalentes a um censo -- a UI deve expor `tipo_populacao` sempre que
# mostrar incidência.
INCIDENCIA_DISPONIVEL = True
