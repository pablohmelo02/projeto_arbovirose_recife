from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.forecast import backtest as bt


def _serie(anos: range, semanas_por_ano: int = 10) -> pd.DataFrame:
    linhas = []
    indice = 0
    for ano in anos:
        for semana in range(1, semanas_por_ano + 1):
            linhas.append(
                {
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "indice_semana": indice,
                    "casos": float(semana),  # mesma forma todo ano -> seasonal naive perfeito
                }
            )
            indice += 1
    return pd.DataFrame(linhas)


def test_mae_rmse_valores_conhecidos():
    observado = np.array([10.0, 20.0, 30.0])
    previsto = np.array([12.0, 18.0, 33.0])
    assert bt.mae(observado, previsto) == pytest.approx((2 + 2 + 3) / 3)
    assert bt.rmse(observado, previsto) == pytest.approx(np.sqrt((4 + 4 + 9) / 3))


def test_mase_relativo_ao_naive_zero_mae_naive_devolve_none():
    assert bt.mase([1.0], [2.0], mae_naive_sazonal=0.0) is None
    assert bt.mase([1.0, 1.0], [3.0, 3.0], mae_naive_sazonal=2.0) == pytest.approx(1.0)


def test_erro_de_pico_identifica_semana_e_magnitude():
    observado = pd.Series([1.0, 5.0, 2.0])
    previsto = np.array([1.0, 2.0, 6.0])
    semanas = pd.Series([1, 2, 3])
    resultado = bt.erro_de_pico(observado, previsto, semanas)
    assert resultado["semana_pico_observada"] == 2
    assert resultado["semana_pico_prevista"] == 3
    assert resultado["erro_timing_semanas"] == 1  # previu 1 semana depois do pico real
    assert resultado["erro_magnitude_pico"] == pytest.approx(6.0 - 5.0)


def test_cobertura_intervalo_conta_fracao_dentro_da_banda():
    observado = np.array([1.0, 5.0, 10.0])
    inferior = np.array([0.0, 0.0, 0.0])
    superior = np.array([2.0, 6.0, 8.0])  # o terceiro valor fica fora
    assert bt.cobertura_intervalo(observado, inferior, superior) == pytest.approx(2 / 3)


def _serie_com_tendencia(anos: range, semanas_por_ano: int = 10) -> pd.DataFrame:
    """Casos = semana + tendência por ano -- o seasonal naive (repete o
    último ano) erra sistematicamente por causa da tendência, o que
    permite testar MASE < 1 com um modelo que a capture."""
    linhas = []
    indice = 0
    for ano in anos:
        deslocamento = (ano - min(anos)) * 2
        for semana in range(1, semanas_por_ano + 1):
            linhas.append(
                {
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "indice_semana": indice,
                    "casos": float(semana + deslocamento),
                }
            )
            indice += 1
    return pd.DataFrame(linhas)


def test_backtest_walk_forward_modelo_perfeito_da_erro_zero_e_mase_menor_que_naive():
    serie = _serie_com_tendencia(range(2020, 2026), semanas_por_ano=10)

    def modelo_perfeito(serie_treino, semanas_alvo):
        deslocamento = (semanas_alvo["ano_epidemiologico"] - int(serie_treino["ano_epidemiologico"].min())) * 2
        return (semanas_alvo["semana_epidemiologica"] + deslocamento).to_numpy(dtype=float)

    tabela = bt.backtest_walk_forward(serie, modelo_perfeito)
    assert len(tabela) == len(bt.ANOS_TESTE)
    assert (tabela["mae"] == 0).all()
    # o seasonal naive erra pela tendência (deslocamento de 2 por ano) --
    # com erro zero do lado do modelo, MASE = 0 / erro_naive = 0.
    assert (tabela["mase"] == 0).all()


def test_mase_e_none_quando_o_proprio_naive_ja_acerta_tudo():
    serie = _serie(range(2020, 2026), semanas_por_ano=10)  # sem tendencia -> naive e perfeito

    def modelo_qualquer(serie_treino, semanas_alvo):
        return semanas_alvo["semana_epidemiologica"].to_numpy(dtype=float)

    tabela = bt.backtest_walk_forward(serie, modelo_qualquer)
    assert tabela["mase"].isna().all()


def test_backtest_walk_forward_treino_nunca_ve_o_ano_alvo():
    """Um modelo "vidente" que olhasse o futuro teria erro zero mesmo
    quando os dados de treino não bastam para prever nada -- construímos
    um modelo que só sabe reproduzir o formato exato de `serie` completa
    (incluindo o ano alvo) e verificamos que ele SÓ recebe `serie_treino`
    truncada, nunca a série completa."""
    serie = _serie(range(2020, 2026), semanas_por_ano=10)
    anos_vistos_no_treino = []

    def modelo_espiao(serie_treino, semanas_alvo):
        anos_vistos_no_treino.append(sorted(serie_treino["ano_epidemiologico"].unique().tolist()))
        return np.zeros(len(semanas_alvo))

    bt.backtest_walk_forward(serie, modelo_espiao)
    for ano_treino_max, anos_vistos in zip(bt.ANOS_TESTE, anos_vistos_no_treino):
        assert max(anos_vistos) == ano_treino_max
        assert ano_treino_max + 1 not in anos_vistos


def test_cobertura_leave_one_fold_out_banda_larga_cobre_mais_que_banda_estreita():
    """Dobras com erro pequeno nas OUTRAS dobras (banda estreita) devem
    cobrir uma dobra com erro grande pior do que dobras com erro grande nas
    outras (banda larga) -- verifica que a banda de cada dobra vem das
    OUTRAS, não da própria (senão a cobertura seria artificialmente alta
    em todos os casos)."""
    tabela = pd.DataFrame(
        [
            {"ano_alvo": 2023, "erros_pontuais": [0.0, 0.1, -0.1] * 20},
            {"ano_alvo": 2024, "erros_pontuais": [0.0, 0.1, -0.1] * 20},
            {"ano_alvo": 2025, "erros_pontuais": [50.0, -50.0, 40.0] * 20},
        ]
    )
    cobertura = bt.cobertura_leave_one_fold_out(tabela)
    assert len(cobertura) == 3
    # a dobra 2025 (erro grande) e avaliada com banda das dobras 2023/2024
    # (erro pequeno) -> cobertura baixa, porque a banda das outras nao
    # capta a magnitude do erro desta dobra.
    cobertura_2025 = cobertura[cobertura["ano_alvo"] == 2025].iloc[0]
    assert cobertura_2025["cobertura_95"] < 0.5


def test_cobertura_leave_one_fold_out_sem_amostra_suficiente_devolve_none():
    tabela = pd.DataFrame([{"ano_alvo": 2023, "erros_pontuais": [1.0, 2.0]}])
    cobertura = bt.cobertura_leave_one_fold_out(tabela)
    assert cobertura.iloc[0]["cobertura_80"] is None


def test_cobertura_leave_one_fold_out_ignora_dobras_com_erro_de_ajuste():
    tabela = pd.DataFrame(
        [
            {"ano_alvo": 2023, "erro_ajuste": "falhou"},
            {"ano_alvo": 2024, "erros_pontuais": [0.0, 0.1, -0.1] * 20},
            {"ano_alvo": 2025, "erros_pontuais": [0.0, 0.1, -0.1] * 20},
        ]
    )
    cobertura = bt.cobertura_leave_one_fold_out(tabela)
    assert len(cobertura) == 2
    assert set(cobertura["ano_alvo"]) == {2024, 2025}


def test_backtest_walk_forward_modelo_que_falha_nao_quebra_as_outras_dobras():
    serie = _serie(range(2020, 2026), semanas_por_ano=10)

    def modelo_instavel(serie_treino, semanas_alvo):
        if int(serie_treino["ano_epidemiologico"].max()) == bt.ANOS_TESTE[0]:
            raise RuntimeError("falha proposital")
        return semanas_alvo["semana_epidemiologica"].to_numpy(dtype=float)

    tabela = bt.backtest_walk_forward(serie, modelo_instavel)
    assert len(tabela) == len(bt.ANOS_TESTE)
    assert tabela.iloc[0]["erro_ajuste"] == "falha proposital"
    assert pd.isna(tabela.iloc[0]["mase"])
    # dobras 2 e 3 nao falham e o modelo acerta perfeitamente (mae=0);
    # o seasonal naive tambem acerta tudo nesta fixture (sem tendencia),
    # entao mae_naive=0 -> mase fica None/NaN por definicao (0/0), nunca 0.
    assert tabela.iloc[1]["mae"] == pytest.approx(0.0)
    assert pd.isna(tabela.iloc[1]["mase"])
