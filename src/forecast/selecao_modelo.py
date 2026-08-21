"""Escolhe o modelo vencedor por agravo a partir do backtest — nunca
olhando 2026 (item 14 do pedido).

Critério: mediana do MASE nas dobras válidas do backtest (menor é melhor,
já que é um erro relativo ao seasonal naive); desempate pelo erro de
timing do pico absoluto mediano."""
from __future__ import annotations

import pandas as pd


def escolher_modelo(resultados_por_modelo: dict[str, pd.DataFrame]) -> tuple[str, pd.DataFrame]:
    """`resultados_por_modelo`: nome do modelo -> saída de
    `backtest.backtest_walk_forward`. Devolve `(nome_vencedor, resumo)`.

    Uma dobra com `erro_ajuste` (o modelo não conseguiu nem ajustar,
    ex.: série curta demais para o ETS) não entra no cálculo da mediana,
    mas o modelo continua elegível se tiver ao menos uma dobra válida.
    """
    linhas = []
    for nome, tabela in resultados_por_modelo.items():
        validas = tabela[tabela.get("mase").notna()] if "mase" in tabela.columns else tabela.iloc[0:0]
        linhas.append(
            {
                "modelo": nome,
                "n_dobras_validas": int(len(validas)),
                "mase_mediano": float(validas["mase"].median()) if len(validas) else None,
                "erro_timing_absoluto_mediano": (
                    float(validas["erro_timing_semanas"].abs().median()) if len(validas) else None
                ),
            }
        )
    resumo = pd.DataFrame(linhas)
    elegiveis = resumo[resumo["mase_mediano"].notna()]
    if elegiveis.empty:
        raise ValueError(
            "nenhum modelo produziu dobra válida no backtest — não há vencedor a escolher"
        )
    vencedor = elegiveis.sort_values(
        ["mase_mediano", "erro_timing_absoluto_mediano"], na_position="last"
    ).iloc[0]["modelo"]
    return str(vencedor), resumo
