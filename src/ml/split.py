"""Split temporal (nunca aleatório) — treino/validação/teste prospectivos e
walk-forward (expanding window), respeitando cronologia.

O corte é sempre pelo **ano epidemiológico da linha `t`** (o instante de
decisão, coluna `ano_epidemiologico` de `df_contexto`, ver `dataset.py`) —
não pelo ano do target (`t+horizonte`), que já está implicitamente à frente.
Cortar por `t` garante que nenhuma linha de treino tenha sido decidida
"depois" de uma linha de teste no tempo real.

## Cortes escolhidos (dataset real de dengue, 2013-2025)

`ANO_TREINO_FIM=2019`, `ANO_VALIDACAO_FIM=2022`, teste = 2023-2025. Não é
um corte arbitrário de conveniência: o histórico de 3 anos mínimo exigido
pelo target (`target.N_MIN_HISTORICO_SAZONAL`/`N_MIN_HISTORICO_GERAL`, ver
`target.py`) só passa a produzir `estado_alto_risco` definido de forma
consistente a partir de ~2016 — treino 2013-2019 dá margem real de anos
utilizáveis (2016-2019) incluindo o platô pós-epidemia de 2015-2016;
validação (2020-2022) cobre um período de baixa incidência relativa (ver
`reports/eda/README.md`, casos por ano); teste (2023-2025) cobre a retomada
de alta de dengue em 2024-2025 — o cenário mais relevante operacionalmente
para avaliar antecipação (ver `reports/gold_analysis/README.md`).
"""
from __future__ import annotations

from typing import Iterator

import pandas as pd

ANO_TREINO_FIM = 2019
ANO_VALIDACAO_FIM = 2022

ANOS_WALK_FORWARD_TESTE = tuple(range(2019, 2026))  # 2019..2025


def split_temporal(
    df_contexto: pd.DataFrame,
) -> tuple[pd.Index, pd.Index, pd.Index]:
    """Devolve `(idx_treino, idx_validacao, idx_teste)` — índices posicionais
    de `df_contexto` (mesmo índice de `X`/`y`, ver `dataset.py`)."""
    ano = df_contexto["ano_epidemiologico"]
    idx_treino = df_contexto.index[ano <= ANO_TREINO_FIM]
    idx_validacao = df_contexto.index[(ano > ANO_TREINO_FIM) & (ano <= ANO_VALIDACAO_FIM)]
    idx_teste = df_contexto.index[ano > ANO_VALIDACAO_FIM]
    return idx_treino, idx_validacao, idx_teste


def walk_forward_splits(
    df_contexto: pd.DataFrame,
    anos_teste: tuple[int, ...] = ANOS_WALK_FORWARD_TESTE,
) -> Iterator[tuple[int, pd.Index, pd.Index]]:
    """Gera `(ano_teste, idx_treino, idx_teste)` em janela expansiva: treino
    = todas as linhas com `ano_epidemiologico < ano_teste`, teste = linhas
    daquele ano exato. Pula anos sem nenhuma linha de teste (ex.: fora do
    intervalo real do dataset)."""
    ano = df_contexto["ano_epidemiologico"]
    for ano_teste in anos_teste:
        idx_teste = df_contexto.index[ano == ano_teste]
        if len(idx_teste) == 0:
            continue
        idx_treino = df_contexto.index[ano < ano_teste]
        if len(idx_treino) == 0:
            continue
        yield ano_teste, idx_treino, idx_teste
