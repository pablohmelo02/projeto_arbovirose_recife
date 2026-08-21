"""Orquestra o forecast completo por agravo (itens 10-17 do pedido):
backtest dos 4 métodos, seleção do vencedor sem olhar 2026, projeção final
semanal com bandas 80%/95%, pico esperado, comparação sazonal.

Nunca é chamado dentro de uma página Streamlit — convenção do produto
(mesma de `src/ml/`, ver `src/forecast/__init__.py`). O entry point que
grava o artefato consumido pelo dashboard é
`src/generate_forecast_artifacts.py`.

Não gera incidência 2026: a população municipal 2026 não tem estimativa
oficial do IBGE publicada (verificado ao vivo nesta sessão — ver
`reports/forecast/arbovirus_2026_projection.md`), então a projeção é
sempre em número de casos. `reports/population/` para em 2025; estender a
metodologia de projeção populacional para 2026 exigiria um total
municipal 2026 que também não existe — por isso não é feito aqui.
"""
from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import pandas as pd

from src.forecast import backtest as bt
from src.forecast.baselines import media_historica_semana, naive_sazonal, tendencia_sazonal
from src.forecast.dataset import construir_serie_semanal
from src.forecast.intervalos import banda_empirica, banda_ets
from src.forecast.modelos import SerieCurtaDemaisError, ajustar_ets, ajustar_ets_previsao
from src.forecast.selecao_modelo import escolher_modelo
from src.gold.epidemiologia import intervalo_semana_epidemiologica, total_semanas_epidemiologicas

ANO_PROJECAO = 2026

#: Nome do modelo -> função `(serie_treino, semanas_alvo) -> previsao`,
#: todas com a mesma assinatura `ModeloForecast` (ver `backtest.py`).
MODELOS_DISPONIVEIS = {
    "seasonal_naive": naive_sazonal,
    "media_historica_semana": media_historica_semana,
    "tendencia_sazonal": tendencia_sazonal,
    "ets_holt_winters": ajustar_ets_previsao,
}


def rodar_backtest_todos_modelos(serie: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Backtest walk-forward dos 4 métodos sobre a mesma série — a mesma
    tabela é reaproveitada para escolher o vencedor E para a banda empírica
    do vencedor (nenhum backtest é recalculado duas vezes)."""
    return {nome: bt.backtest_walk_forward(serie, fn) for nome, fn in MODELOS_DISPONIVEIS.items()}


def _erros_empiricos(tabela_backtest: pd.DataFrame) -> np.ndarray:
    """Achata os erros ponto-a-ponto de todas as dobras válidas de uma
    tabela de backtest em uma única amostra para `intervalos.banda_empirica`."""
    if "erros_pontuais" not in tabela_backtest.columns:
        return np.array([])
    listas = tabela_backtest["erros_pontuais"].dropna().tolist()
    return np.asarray(list(itertools.chain.from_iterable(listas)), dtype=float)


def projetar_agravo(df_gold: pd.DataFrame, agravo: str) -> dict[str, Any]:
    """Resultado completo do forecast 2026 para um agravo."""
    serie = construir_serie_semanal(df_gold, agravo)
    if serie.empty:
        return {"agravo": agravo, "disponivel": False, "motivo": "sem histórico na Gold para este agravo"}

    resultados_backtest = rodar_backtest_todos_modelos(serie)
    modelo_vencedor, resumo_backtest = escolher_modelo(resultados_backtest)

    n_semanas_2026 = total_semanas_epidemiologicas(ANO_PROJECAO)
    semanas_alvo_2026 = pd.DataFrame(
        {"ano_epidemiologico": ANO_PROJECAO, "semana_epidemiologica": range(1, n_semanas_2026 + 1)}
    )
    datas_inicio_2026 = [
        pd.Timestamp(intervalo_semana_epidemiologica(ANO_PROJECAO, int(s))[0])
        for s in semanas_alvo_2026["semana_epidemiologica"]
    ]

    erros_empiricos_vencedor = _erros_empiricos(resultados_backtest[modelo_vencedor])

    if modelo_vencedor == "ets_holt_winters":
        try:
            _previsao_ets, modelo_ajustado = ajustar_ets(serie, n_semanas_2026)
            bandas = banda_ets(modelo_ajustado, n_semanas_2026)
        except SerieCurtaDemaisError:
            # Não deveria acontecer se o ETS venceu o backtest (precisaria
            # de série ainda mais curta), mas a série completa é sempre
            # maior ou igual à de qualquer dobra de treino -- guarda
            # defensiva, cai na mesma banda empírica dos baselines.
            previsao_central = MODELOS_DISPONIVEIS[modelo_vencedor](serie, semanas_alvo_2026)
            bandas = banda_empirica(previsao_central, erros_empiricos_vencedor)
    else:
        previsao_central = MODELOS_DISPONIVEIS[modelo_vencedor](serie, semanas_alvo_2026)
        bandas = banda_empirica(np.asarray(previsao_central, dtype=float), erros_empiricos_vencedor)

    projecao = pd.DataFrame(
        {
            "ano_epidemiologico": ANO_PROJECAO,
            "semana_epidemiologica": semanas_alvo_2026["semana_epidemiologica"].to_numpy(),
            "semana_epi_data_inicio": datas_inicio_2026,
            "casos": np.round(np.asarray(bandas["central"])).astype(int),
            "banda_80_inferior": np.round(np.clip(bandas["banda_80_inferior"], a_min=0, a_max=None)).astype(int),
            "banda_80_superior": np.round(bandas["banda_80_superior"]).astype(int),
            "banda_95_inferior": np.round(np.clip(bandas["banda_95_inferior"], a_min=0, a_max=None)).astype(int),
            "banda_95_superior": np.round(bandas["banda_95_superior"]).astype(int),
        }
    )

    idx_pico = int(projecao["casos"].idxmax())
    pico_projetado = {
        "semana_epidemiologica": int(projecao.loc[idx_pico, "semana_epidemiologica"]),
        "casos_esperados": int(projecao.loc[idx_pico, "casos"]),
        "data_inicio": str(projecao.loc[idx_pico, "semana_epi_data_inicio"]),
    }

    media_sazonal_historica = serie.groupby("semana_epidemiologica")["casos"].mean()
    media_semanal_historica_comparavel = float(
        media_sazonal_historica.reindex(projecao["semana_epidemiologica"]).mean()
    )

    cobertura_por_dobra = bt.cobertura_leave_one_fold_out(resultados_backtest[modelo_vencedor])
    cobertura_media = {
        f"cobertura_{pct}_media": (
            float(cobertura_por_dobra[f"cobertura_{pct}"].dropna().mean())
            if f"cobertura_{pct}" in cobertura_por_dobra.columns and cobertura_por_dobra[f"cobertura_{pct}"].notna().any()
            else None
        )
        for pct in (80, 95)
    }

    return {
        "agravo": agravo,
        "disponivel": True,
        "ultimo_ano_historico": int(serie["ano_epidemiologico"].max()),
        "modelo_escolhido": modelo_vencedor,
        "metodo_banda": bandas.get("metodo", "empirica"),
        "resumo_backtest": resumo_backtest,
        "backtest_por_modelo": resultados_backtest,
        "cobertura_intervalo_por_dobra": cobertura_por_dobra,
        "cobertura_intervalo_media": cobertura_media,
        "serie_historica": serie,
        "projecao_2026": projecao,
        "pico_projetado": pico_projetado,
        "media_semanal_historica_comparavel": media_semanal_historica_comparavel,
    }
