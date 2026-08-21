# Projeção epidemiológica sazonal 2026 (casos, por agravo)

Gerado por `python -m src.generate_forecast_report` a partir de
`dashboard/data/_forecast_2026_metadata.json` (produzido por
`python -m src.generate_forecast_artifacts`, que por sua vez usa
`src/forecast/`). Todos os números abaixo são reais.

> **Projeção estatística baseada nos dados históricos disponíveis até 2025. Não representa casos observados em 2026 nem previsão oficial da Prefeitura do Recife.**

## Fonte de casos 2026 — verificação ao vivo (2026-08-21)

O Portal de Dados Abertos do Recife (`dados.recife.pe.gov.br`, dataset "Casos de Dengue, Zika e
Chikungunya") foi consultado ao vivo nesta sessão: 58 recursos, todos rotulados até 2025; o
metadado do dataset foi tocado em 2026-05-20, mas nenhum recurso 2026 existe. **Não há caso
observado de 2026 nesta fonte.** Existe um boletim estadual (SES-PE, Boletim Epidemiológico de
Arboviroses) com números de 2026 para Pernambuco inteiro, mas é uma fonte diferente — estadual,
sem granularidade de bairro — e integrá-la ao pipeline está fora do escopo desta etapa.

## População municipal 2026 — verificação ao vivo (2026-08-21)

As estimativas municipais mais recentes do IBGE têm data de referência 01/07/2025; nenhuma
estimativa oficial municipal de 2026 foi encontrada. Por isso a projeção é sempre em número de
casos — nunca em incidência por 100 mil habitantes para 2026 (`reports/population/` também para em
2025, e estender essa metodologia exigiria um total municipal 2026 que igualmente não existe).

## Metodologia

- **Granularidade**: Recife total × agravo × semana. Nenhuma projeção por bairro/RPA é publicada
  (instabilidade alta demais numa série semanal por bairro para ser defensável).
- **Baselines obrigatórios**: seasonal naive (repete a mesma semana do último ano), média
  histórica da mesma semana epidemiológica, tendência linear + sazonalidade média.
- **Método adicional**: ETS/Holt-Winters (`statsmodels`), único, sem SARIMA/deep learning/AutoML.
- **Seleção do modelo**: mediana do MASE (erro relativo ao seasonal naive) nas 3 dobras do backtest
  walk-forward (treina ≤2022→prevê 2023; ≤2023→2024; ≤2024→2025), desempate pelo menor erro de
  timing do pico absoluto mediano — nunca escolhido olhando 2026.
- **Intervalos**: 80% e 95%, via quantis empíricos dos erros do próprio backtest (ou simulação
  nativa do ETS quando é o modelo escolhido) — nunca uma única linha.

## DENGUE

**Modelo escolhido**: `media_historica_semana` (banda de incerteza: empirica), entre 3
baselines obrigatórios e 1 método adicional (ETS/Holt-Winters), escolhido pela mediana do MASE nas 3
dobras do backtest walk-forward — nunca olhando 2026.

### Comparação de modelos no backtest

| Modelo | Dobras válidas | MASE mediano | Erro de timing absoluto mediano (semanas) |
|---|---|---|---|
| seasonal_naive | 3 | 1.000 | 19.0 |
| media_historica_semana | 3 | 0.613 | 2.0 |
| tendencia_sazonal | 3 | 1.037 | 2.0 |
| ets_holt_winters | 3 | 1.124 | 3.0 |

### Desempenho do modelo escolhido, por dobra

| Ano-alvo | MAE | RMSE | MASE | Pico observado (SE) | Pico previsto (SE) | Erro de timing (semanas) | Erro de magnitude do pico |
|---|---|---|---|---|---|---|---|
| 2023 | 98.7 | 112.8 | 3.431 | 13 | 11 | -2 | +94.3 |
| 2024 | 82.9 | 139.8 | 0.613 | 11 | 11 | +0 | -475.8 |
| 2025 | 85.8 | 103.4 | 0.599 | 33 | 11 | -22 | -64.2 |

> **Achado honesto**: no backtest de 2025, o modelo escolhido errou o timing do pico por 22 semanas (previu SE 11, real foi SE 33) — um ano com padrão sazonal atípico frente à média histórica usada pelo modelo.

### Cobertura das bandas de previsão (leave-one-fold-out)

A banda de cada dobra do backtest usa os erros das OUTRAS dobras (nunca os
da própria, o que inflaria a cobertura artificialmente):
| Ano-alvo | Cobertura 80% | Cobertura 95% |
|---|---|---|
| 2023 | 54% | 58% |
| 2024 | 81% | 85% |
| 2025 | 70% | 98% |

Cobertura média — 80%: 68% ·
95%: 80%.
Com só 3 dobras, a cobertura média é uma leitura aproximada, não uma
estimativa estatisticamente precisa da taxa de cobertura real.

### Projeção 2026

- **Semana de maior valor esperado**: SE 11/2026 (início em
  2026-03-15 00:00:00).
- **Casos esperados no pico**: 280.
- **Média sazonal histórica das mesmas semanas**: 162.3 casos/semana.
- **Pico projetado vs. média histórica**: 1.7×.
- **Incidência 2026**: não calculada — não há estimativa municipal oficial do IBGE para a população de 2026 (verificado ao vivo — ver reports/forecast/arbovirus_2026_projection.md); a projeção é sempre em número de casos.

A série semanal completa (observado 2013-2025 + projeção 2026 com bandas
80%/95%) está em `dashboard/data/_forecast_2026.parquet`, coluna `is_observado` distingue as duas
partes.

## ZIKA

**Modelo escolhido**: `seasonal_naive` (banda de incerteza: empirica), entre 3
baselines obrigatórios e 1 método adicional (ETS/Holt-Winters), escolhido pela mediana do MASE nas 3
dobras do backtest walk-forward — nunca olhando 2026.

### Comparação de modelos no backtest

| Modelo | Dobras válidas | MASE mediano | Erro de timing absoluto mediano (semanas) |
|---|---|---|---|
| seasonal_naive | 3 | 1.000 | 17.0 |
| media_historica_semana | 3 | 1.205 | 4.0 |
| tendencia_sazonal | 3 | 1.303 | 4.0 |
| ets_holt_winters | 3 | 1.349 | 5.0 |

### Desempenho do modelo escolhido, por dobra

| Ano-alvo | MAE | RMSE | MASE | Pico observado (SE) | Pico previsto (SE) | Erro de timing (semanas) | Erro de magnitude do pico |
|---|---|---|---|---|---|---|---|
| 2023 | 3.4 | 4.5 | 1.000 | 12 | 29 | +17 | -10.0 |
| 2024 | 6.2 | 8.4 | 1.000 | 11 | 12 | +1 | -4.0 |
| 2025 | 12.2 | 15.3 | 1.000 | 33 | 11 | -22 | -13.0 |

> **Achado honesto**: no backtest de 2023, o modelo escolhido errou o timing do pico por 17 semanas (previu SE 29, real foi SE 12) — um ano com padrão sazonal atípico frente à média histórica usada pelo modelo.

> **Achado honesto**: no backtest de 2025, o modelo escolhido errou o timing do pico por 22 semanas (previu SE 11, real foi SE 33) — um ano com padrão sazonal atípico frente à média histórica usada pelo modelo.

### Cobertura das bandas de previsão (leave-one-fold-out)

A banda de cada dobra do backtest usa os erros das OUTRAS dobras (nunca os
da própria, o que inflaria a cobertura artificialmente):
| Ano-alvo | Cobertura 80% | Cobertura 95% |
|---|---|---|
| 2023 | 92% | 100% |
| 2024 | 94% | 100% |
| 2025 | 38% | 64% |

Cobertura média — 80%: 75% ·
95%: 88%.
Com só 3 dobras, a cobertura média é uma leitura aproximada, não uma
estimativa estatisticamente precisa da taxa de cobertura real.

### Projeção 2026

- **Semana de maior valor esperado**: SE 33/2026 (início em
  2026-08-16 00:00:00).
- **Casos esperados no pico**: 40.
- **Média sazonal histórica das mesmas semanas**: 10.6 casos/semana.
- **Pico projetado vs. média histórica**: 3.8×.
- **Incidência 2026**: não calculada — não há estimativa municipal oficial do IBGE para a população de 2026 (verificado ao vivo — ver reports/forecast/arbovirus_2026_projection.md); a projeção é sempre em número de casos.

A série semanal completa (observado 2013-2025 + projeção 2026 com bandas
80%/95%) está em `dashboard/data/_forecast_2026.parquet`, coluna `is_observado` distingue as duas
partes.

## CHIKUNGUNYA

**Modelo escolhido**: `seasonal_naive` (banda de incerteza: empirica), entre 3
baselines obrigatórios e 1 método adicional (ETS/Holt-Winters), escolhido pela mediana do MASE nas 3
dobras do backtest walk-forward — nunca olhando 2026.

### Comparação de modelos no backtest

| Modelo | Dobras válidas | MASE mediano | Erro de timing absoluto mediano (semanas) |
|---|---|---|---|
| seasonal_naive | 3 | 1.000 | 19.0 |
| media_historica_semana | 3 | 1.903 | 13.0 |
| tendencia_sazonal | 3 | 3.508 | 13.0 |
| ets_holt_winters | 3 | 1.008 | 12.0 |

### Desempenho do modelo escolhido, por dobra

| Ano-alvo | MAE | RMSE | MASE | Pico observado (SE) | Pico previsto (SE) | Erro de timing (semanas) | Erro de magnitude do pico |
|---|---|---|---|---|---|---|---|
| 2023 | 19.6 | 26.9 | 1.000 | 13 | 32 | +19 | +29.0 |
| 2024 | 24.1 | 40.2 | 1.000 | 9 | 13 | +4 | -89.0 |
| 2025 | 30.3 | 44.8 | 1.000 | 39 | 9 | -30 | +102.0 |

> **Achado honesto**: no backtest de 2023, o modelo escolhido errou o timing do pico por 19 semanas (previu SE 32, real foi SE 13) — um ano com padrão sazonal atípico frente à média histórica usada pelo modelo.

> **Achado honesto**: no backtest de 2025, o modelo escolhido errou o timing do pico por 30 semanas (previu SE 9, real foi SE 39) — um ano com padrão sazonal atípico frente à média histórica usada pelo modelo.

### Cobertura das bandas de previsão (leave-one-fold-out)

A banda de cada dobra do backtest usa os erros das OUTRAS dobras (nunca os
da própria, o que inflaria a cobertura artificialmente):
| Ano-alvo | Cobertura 80% | Cobertura 95% |
|---|---|---|
| 2023 | 79% | 100% |
| 2024 | 77% | 85% |
| 2025 | 72% | 83% |

Cobertura média — 80%: 76% ·
95%: 89%.
Com só 3 dobras, a cobertura média é uma leitura aproximada, não uma
estimativa estatisticamente precisa da taxa de cobertura real.

### Projeção 2026

- **Semana de maior valor esperado**: SE 39/2026 (início em
  2026-09-27 00:00:00).
- **Casos esperados no pico**: 69.
- **Média sazonal histórica das mesmas semanas**: 58.5 casos/semana.
- **Pico projetado vs. média histórica**: 1.2×.
- **Incidência 2026**: não calculada — não há estimativa municipal oficial do IBGE para a população de 2026 (verificado ao vivo — ver reports/forecast/arbovirus_2026_projection.md); a projeção é sempre em número de casos.

A série semanal completa (observado 2013-2025 + projeção 2026 com bandas
80%/95%) está em `dashboard/data/_forecast_2026.parquet`, coluna `is_observado` distingue as duas
partes.


## Limitações gerais

- Nenhuma das três séries (dengue, zika, chikungunya) tem caso observado em 2026 — toda a seção
  "Projeção 2026" é, por definição, extrapolação estatística do padrão 2013-2025.
- O backtest mostra que o erro de timing do pico pode ser grande num ano atípico (ver achados
  honestos por agravo acima) — a banda de 95% existe para comunicar essa incerteza, a projeção
  central não deve ser lida como data exata.
- Projeção completamente separada da Priorização Territorial Experimental (V1/V2): nenhuma usa a
  outra como insumo, nenhuma foi ajustada para concordar com a outra.
