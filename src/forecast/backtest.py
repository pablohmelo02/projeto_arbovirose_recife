"""Backtest walk-forward (item 14 do pedido): nunca escolhe modelo olhando
2026, que não tem caso observado em nenhuma fonte oficial verificada.

Três dobras (ou o que estiver disponível dentro delas, ver `ANOS_TESTE`):
treina até 2022 → prevê 2023; até 2023 → prevê 2024; até 2024 → prevê 2025.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from src.forecast.baselines import naive_sazonal

#: Cada valor é o último ano epidemiológico DENTRO do treino; o ano alvo
#: previsto é sempre o ano seguinte.
ANOS_TESTE = (2022, 2023, 2024)

#: `(serie_treino, semanas_alvo) -> previsao`. `semanas_alvo` é um
#: DataFrame com `ano_epidemiologico`/`semana_epidemiologica` (nunca só a
#: contagem de semanas) porque os baselines precisam saber a QUAL semana
#: epidemiológica cada previsão corresponde (`naive_sazonal`,
#: `media_historica_semana`) — não é só "as próximas N semanas".
ModeloForecast = Callable[[pd.DataFrame, pd.DataFrame], np.ndarray]


def mae(observado: np.ndarray, previsto: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(observado, dtype=float) - np.asarray(previsto, dtype=float))))


def rmse(observado: np.ndarray, previsto: np.ndarray) -> float:
    erro = np.asarray(observado, dtype=float) - np.asarray(previsto, dtype=float)
    return float(np.sqrt(np.mean(erro**2)))


def mase(observado: np.ndarray, previsto: np.ndarray, mae_naive_sazonal: float) -> float | None:
    """MASE relativo ao seasonal naive (o baseline obrigatório mais
    apropriado para uma série sazonal semanal — não a variação ingênua
    t-1, que não captura sazonalidade)."""
    if mae_naive_sazonal == 0:
        return None
    return mae(observado, previsto) / mae_naive_sazonal


def erro_de_pico(observado: pd.Series, previsto: np.ndarray, semanas: pd.Series) -> dict:
    observado_np = observado.to_numpy(dtype=float)
    idx_obs = int(np.argmax(observado_np))
    idx_prev = int(np.argmax(np.asarray(previsto, dtype=float)))
    semanas_np = semanas.to_numpy()
    return {
        "semana_pico_observada": int(semanas_np[idx_obs]),
        "semana_pico_prevista": int(semanas_np[idx_prev]),
        "erro_timing_semanas": idx_prev - idx_obs,
        "valor_pico_observado": float(observado_np[idx_obs]),
        "valor_pico_previsto": float(np.asarray(previsto)[idx_prev]),
        "erro_magnitude_pico": float(np.asarray(previsto)[idx_prev] - observado_np[idx_obs]),
    }


def cobertura_intervalo(observado: np.ndarray, inferior: np.ndarray, superior: np.ndarray) -> float:
    observado_np = np.asarray(observado, dtype=float)
    dentro = (observado_np >= np.asarray(inferior, dtype=float)) & (observado_np <= np.asarray(superior, dtype=float))
    return float(np.mean(dentro))


def cobertura_leave_one_fold_out(
    tabela_backtest: pd.DataFrame, niveis: tuple[float, ...] = (0.80, 0.95)
) -> pd.DataFrame:
    """Cobertura das bandas 80%/95% por dobra do backtest (item 14 e 17 do
    pedido: toda projeção precisa mostrar incerteza, e essa incerteza
    precisa ser avaliada, não só declarada).

    A banda usada para avaliar a dobra `i` vem dos erros pontuais das
    OUTRAS dobras (leave-one-fold-out) — nunca dos erros da própria dobra,
    o que validaria a banda com a mesma informação que a define (cobertura
    artificialmente alta, viés otimista). Requer a coluna `erros_pontuais`
    de `backtest_walk_forward`; dobras sem essa coluna (ex.: erro de
    ajuste) são ignoradas."""
    validas = tabela_backtest[tabela_backtest.get("erros_pontuais").notna()] if "erros_pontuais" in tabela_backtest.columns else tabela_backtest.iloc[0:0]
    linhas = []
    for idx, linha in validas.iterrows():
        erros_propria = np.asarray(linha["erros_pontuais"], dtype=float)
        erros_outras_listas = [
            np.asarray(outra["erros_pontuais"], dtype=float)
            for outro_idx, outra in validas.iterrows()
            if outro_idx != idx
        ]
        resultado: dict = {"ano_alvo": linha["ano_alvo"]}
        erros_outras = np.concatenate(erros_outras_listas) if erros_outras_listas else np.array([])
        for nivel in niveis:
            pct = int(round(nivel * 100))
            if erros_outras.size < 2 or erros_propria.size == 0:
                resultado[f"cobertura_{pct}"] = None
                continue
            alpha = 1 - nivel
            inferior = np.quantile(erros_outras, alpha / 2)
            superior = np.quantile(erros_outras, 1 - alpha / 2)
            dentro = (erros_propria >= inferior) & (erros_propria <= superior)
            resultado[f"cobertura_{pct}"] = float(np.mean(dentro))
        linhas.append(resultado)
    return pd.DataFrame(linhas)


def backtest_walk_forward(
    serie: pd.DataFrame, ajustar_modelo: ModeloForecast, anos_teste: tuple[int, ...] = ANOS_TESTE
) -> pd.DataFrame:
    """`ajustar_modelo(serie_treino, n_semanas) -> array` prevê as próximas
    `n_semanas` a partir do fim de `serie_treino`. Cada dobra usa só dado
    `<= ano_treino_max` para treinar — nunca olha o ano alvo antes de
    prever."""
    linhas = []
    for ano_treino_max in anos_teste:
        ano_alvo = ano_treino_max + 1
        treino = serie[serie["ano_epidemiologico"] <= ano_treino_max]
        alvo = serie[serie["ano_epidemiologico"] == ano_alvo].sort_values("semana_epidemiologica")
        if alvo.empty or treino.empty:
            continue

        alvo = alvo.reset_index(drop=True)
        try:
            previsto = np.asarray(ajustar_modelo(treino, alvo[["ano_epidemiologico", "semana_epidemiologica"]]), dtype=float)
        except Exception as exc:  # noqa: BLE001 - dobra fica registrada como indisponível, não quebra o backtest inteiro
            linhas.append({"ano_alvo": ano_alvo, "erro_ajuste": str(exc)})
            continue

        observado = alvo["casos"].to_numpy(dtype=float)
        naive_prev = naive_sazonal(treino, alvo).to_numpy(dtype=float)
        mae_naive = mae(observado, naive_prev)

        pico = erro_de_pico(alvo["casos"], previsto, alvo["semana_epidemiologica"])
        linhas.append(
            {
                "ano_alvo": ano_alvo,
                "n_semanas": len(alvo),
                "mae": mae(observado, previsto),
                "rmse": rmse(observado, previsto),
                "mase": mase(observado, previsto, mae_naive),
                **pico,
                # erro ponto-a-ponto (observado - previsto) desta dobra --
                # usado por `intervalos.banda_empirica` como amostra da
                # distribuição de erro; guardado como lista para não perder
                # informação frente ao MAE/RMSE já agregados na linha.
                "erros_pontuais": (observado - previsto).tolist(),
            }
        )
    return pd.DataFrame(linhas)
