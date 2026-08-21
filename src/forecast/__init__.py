"""Projeção epidemiológica sazonal 2026 — Recife total × agravo × semana.

**Isolado de `src/ml/` por decisão explícita do usuário**: a pesquisa de
priorização territorial (V1 congelado `dengue_onset_ranking_candidate_v1`
e o experimento V2 de incidência) está encerrada e não deve ser tocada.
Este pacote nunca importa `src.ml` e nunca escreve em nenhum artefato ou
relatório do candidato congelado. Ver `tests/test_forecast_v1_intacto.py`.

Isto também NÃO é priorização territorial: não há ranking, não há bairro,
não há score. É uma série temporal agregada (Recife inteiro) por agravo,
com baselines simples e um único método adicional (ETS/Holt-Winters),
avaliados por backtest antes de qualquer projeção para 2026 (que não tem
caso observado em nenhuma fonte oficial verificada — ver
`reports/forecast/arbovirus_2026_projection.md`).

Convenção do produto (mesma de `src/ml/`, ver CLAUDE.md §11): nenhum app
Streamlit treina ou prevê em tempo real. Este pacote só produz DataFrames
puros; a escrita do artefato consumido pelo dashboard é
`src/generate_forecast_artifacts.py` (entry point separado, roda uma vez,
nunca dentro de uma página).
"""
