"""Artefatos de priorização: backtest, corte temporal e portão de projeção.

O comportamento mais importante testado aqui: **nada posterior ao corte
entra numa feature**, e o artefato de "período atual" só existe quando o
portão de atualidade permite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.generate_priority_artifacts import (
    COLUNAS_BACKTEST,
    _distancia_ate_onset,
    _mapear_onsets,
    _score_relativo,
    construir_backtest,
    construir_latest_priority,
)


# ---------------------------------------------------------------------------
# Contexto sintético no formato que `montar_dataset_onset` produz
# ---------------------------------------------------------------------------
def _contexto(n_bairros: int = 6, n_semanas: int = 10) -> pd.DataFrame:
    linhas = []
    for b in range(n_bairros):
        for s in range(n_semanas):
            inicio = pd.Timestamp("2024-01-07") + pd.Timedelta(weeks=s)
            linhas.append(
                {
                    "codigo_bairro": str(b),
                    "nome_bairro": f"BAIRRO {b}",
                    "codigo_rpa": str(1 + b % 3),
                    "ano_epidemiologico": 2024,
                    "semana_epidemiologica": s + 2,
                    "semana_epi_data_inicio": inicio,
                    "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                    "indice_semana_global": s,
                    "indice_semana_alvo": s,
                    "casos": b + s,
                    "casos_t": b + s,
                    "razao_limiar_historico": (b + s) / 3.0,
                    "taxa_crescimento_suavizada": 0.1 * s,
                    "estado_alto_risco_t": 1.0 if s >= n_semanas - 3 else 0.0,
                }
            )
    return pd.DataFrame(linhas).reset_index(drop=True)


def _probabilidades(ctx: pd.DataFrame, semente: int = 7) -> pd.Series:
    gerador = np.random.default_rng(semente)
    return pd.Series(gerador.random(len(ctx)), index=ctx.index, name="probabilidade")


def _alvo(ctx: pd.DataFrame) -> pd.Series:
    return pd.Series((ctx["indice_semana_global"] % 4 == 0).astype(float), index=ctx.index)


# ---------------------------------------------------------------------------
# Score relativo
# ---------------------------------------------------------------------------
def test_score_relativo_vai_de_zero_a_cem_por_semana():
    ctx = _contexto()
    score = _score_relativo(_probabilidades(ctx), ctx["indice_semana_alvo"])
    por_semana = score.groupby(ctx["indice_semana_alvo"])
    assert por_semana.min().eq(0.0).all()
    assert por_semana.max().eq(100.0).all()


def test_score_relativo_com_um_unico_bairro_na_semana():
    ctx = _contexto(n_bairros=1, n_semanas=3)
    score = _score_relativo(_probabilidades(ctx), ctx["indice_semana_alvo"])
    assert score.notna().all(), "não deve dividir por zero quando há 1 bairro na semana"


def test_score_nao_e_probabilidade():
    """O score é posto relativo: a maior probabilidade da semana recebe 100
    independentemente do seu valor absoluto."""
    ctx = _contexto(n_bairros=3, n_semanas=1)
    proba = pd.Series([0.01, 0.02, 0.03], index=ctx.index)
    score = _score_relativo(proba, ctx["indice_semana_alvo"])
    assert score.max() == 100.0
    assert score.min() == 0.0


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def test_backtest_tem_o_contrato_completo():
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    assert list(backtest.columns) == list(COLUNAS_BACKTEST)
    assert len(backtest) == len(ctx)


def test_ranking_e_unico_e_comeca_em_um_por_semana():
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    for _, grupo in backtest.groupby(["ano_epidemiologico", "semana_epidemiologica"]):
        assert grupo["ranking"].min() == 1
        assert grupo["ranking"].is_unique


def test_cutoff_da_linha_e_a_propria_semana_de_decisao():
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    assert (backtest["cutoff_epi_year"] == backtest["ano_epidemiologico"]).all()
    assert (backtest["cutoff_epi_week"] == backtest["semana_epidemiologica"]).all()


def test_desfecho_observado_soma_as_tres_semanas_seguintes():
    ctx = _contexto(n_bairros=1, n_semanas=6)
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    primeira = backtest.sort_values("semana_epidemiologica").iloc[0]
    # casos do bairro 0: 0,1,2,3,4,5 -> soma de t+1..t+3 na primeira semana = 1+2+3
    assert primeira["casos_proximas_3_semanas"] == pytest.approx(6.0)


def test_ultimas_semanas_ficam_sem_desfecho_em_vez_de_zero():
    ctx = _contexto(n_bairros=1, n_semanas=6)
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    ultima = backtest.sort_values("semana_epidemiologica").iloc[-1]
    assert pd.isna(ultima["casos_proximas_3_semanas"]), (
        "sem as 3 semanas seguintes o desfecho é desconhecido, nunca zero"
    )


def test_alvo_indefinido_e_preservado_como_nulo():
    ctx = _contexto(n_bairros=2, n_semanas=5)
    alvo = _alvo(ctx)
    alvo.iloc[0] = np.nan
    backtest = construir_backtest(ctx, _probabilidades(ctx), alvo)
    assert backtest["onset_real_em_3_semanas"].isna().sum() == 1


def test_backtest_nao_usa_o_futuro_para_ordenar_leakage_adversarial():
    """Alterar casos DEPOIS da semana de decisão não pode mudar o ranking
    daquela semana — o ranking vem só da probabilidade calculada em `t`."""
    ctx = _contexto()
    proba = _probabilidades(ctx)
    antes = construir_backtest(ctx, proba, _alvo(ctx))

    ctx_futuro = ctx.copy()
    ultimas = ctx_futuro["indice_semana_global"] >= ctx_futuro["indice_semana_global"].max() - 1
    ctx_futuro.loc[ultimas, "casos"] = 99999
    depois = construir_backtest(ctx_futuro, proba, _alvo(ctx))

    semanas_iniciais = antes["semana_epidemiologica"] <= antes["semana_epidemiologica"].max() - 4
    pd.testing.assert_series_equal(
        antes.loc[semanas_iniciais, "ranking"].reset_index(drop=True),
        depois.loc[semanas_iniciais, "ranking"].reset_index(drop=True),
        check_names=False,
    )


def test_rankings_de_baseline_tambem_sao_produzidos():
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    assert backtest["ranking_baseline_razao_historica"].min() == 1
    assert backtest["ranking_baseline_crescimento"].min() == 1


# ---------------------------------------------------------------------------
# Onsets
# ---------------------------------------------------------------------------
def test_mapear_onsets_pega_apenas_a_transicao_zero_para_um():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["1"] * 6,
            "indice_semana_global": [0, 1, 2, 3, 4, 5],
            "estado_alto_risco_t": [0.0, 0.0, 1.0, 1.0, 0.0, 1.0],
        }
    )
    assert _mapear_onsets(df) == {"1": {2, 5}}


def test_dois_bairros_nao_se_misturam():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1", "2", "2"],
            "indice_semana_global": [0, 1, 0, 1],
            "estado_alto_risco_t": [0.0, 1.0, 0.0, 0.0],
        }
    )
    mapa = _mapear_onsets(df)
    assert mapa["1"] == {1}
    assert mapa["2"] == set()


def test_distancia_ate_onset_so_olha_a_janela_de_tres_semanas():
    mapa = {"1": {5}}
    assert _distancia_ate_onset(mapa, "1", 2) == 3.0
    assert _distancia_ate_onset(mapa, "1", 4) == 1.0
    assert np.isnan(_distancia_ate_onset(mapa, "1", 0)), "4 semanas à frente está fora da janela"
    assert np.isnan(_distancia_ate_onset(mapa, "2", 2)), "bairro sem onset"


# ---------------------------------------------------------------------------
# latest_priority
# ---------------------------------------------------------------------------
def test_latest_priority_usa_a_ultima_semana_e_o_contrato_esperado():
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    metadados = {"model_version": "dengue_onset_ranking_candidate_v1"}
    latest = construir_latest_priority(backtest, metadados, "2026-08-21T00:00:00+00:00")

    esperadas = [
        "reference_year", "reference_week", "forecast_horizon", "bairro", "codigo_bairro",
        "rpa", "score_prioridade", "ranking", "model_version", "generated_at", "data_cutoff",
    ]
    assert list(latest.columns) == esperadas
    assert latest["reference_week"].nunique() == 1
    assert latest["reference_week"].iloc[0] == backtest["semana_epidemiologica"].max()
    assert latest["ranking"].tolist() == sorted(latest["ranking"].tolist())


def test_latest_priority_nao_expoe_probabilidade():
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    latest = construir_latest_priority(backtest, {"model_version": "v"}, "2026-08-21T00:00:00+00:00")
    proibidas = {"probabilidade", "probability", "proba", "chance"}
    assert not (set(latest.columns) & proibidas), (
        "a probabilidade bruta não deve ser publicada — só posição e score relativo"
    )


def test_latest_priority_nao_expoe_desfecho_futuro():
    """A priorização do período atual não pode carregar o que aconteceu
    depois — isso só existe no backtest."""
    ctx = _contexto()
    backtest = construir_backtest(ctx, _probabilidades(ctx), _alvo(ctx))
    latest = construir_latest_priority(backtest, {"model_version": "v"}, "2026-08-21T00:00:00+00:00")
    assert "onset_real_em_3_semanas" not in latest.columns
    assert "casos_proximas_3_semanas" not in latest.columns
