"""Etapa preditiva: sistema de alerta antecipado de dengue por bairro.

Consome exclusivamente `gold_arboviroses_clima_bairro` (`src/gold/`) — nenhum
join/agregação da Gold é reimplementado aqui, só feature engineering e
modelagem sobre o que a Gold já entrega, igual à camada `src/eda/`.

Ver `reports/ml/dengue_early_warning_baseline.md` para a formalização
completa do problema (target, horizonte, eventos, split, baselines,
métricas) antes de mexer em qualquer módulo.
"""
