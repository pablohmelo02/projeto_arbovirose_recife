from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.forecast.projecao_2026 import ANO_PROJECAO, MODELOS_DISPONIVEIS, projetar_agravo


def _gold_sintetica(n_anos: int = 7, semanas_por_ano: int = 52, com_populacao: bool = True) -> pd.DataFrame:
    """~7 anos de histórico sintético (2019-2025), sazonalidade + tendência
    leve + ruído, o suficiente para o ETS ajustar e para as 3 dobras do
    backtest (2022->2023, 2023->2024, 2024->2025) terem dado."""
    rng = np.random.RandomState(7)
    linhas = []
    for i_ano in range(n_anos):
        ano = 2019 + i_ano
        for semana in range(1, semanas_por_ano + 1):
            sazonal = 15 * np.sin(2 * np.pi * semana / 52) + 20
            ruido = rng.normal(0, 1.5)
            casos = max(0.0, sazonal + ruido)
            for bairro, pop in (("1", 100_000.0), ("2", 60_000.0)):
                linha = {
                    "codigo_bairro": bairro,
                    "agravo": "DENGUE",
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "semana_epi_data_inicio": pd.Timestamp(f"{ano}-01-01") + pd.Timedelta(weeks=semana - 1),
                    "casos": int(round(casos / 2)),
                }
                if com_populacao:
                    linha["populacao_bairro_ano"] = pop
                linhas.append(linha)
    return pd.DataFrame(linhas)


@pytest.fixture(scope="module")
def resultado_dengue() -> dict:
    gold = _gold_sintetica()
    return projetar_agravo(gold, "DENGUE")


def test_projetar_agravo_sem_dado_marca_indisponivel():
    gold = pd.DataFrame(columns=["agravo", "casos", "ano_epidemiologico", "semana_epidemiologica"])
    resultado = projetar_agravo(gold, "ZIKA")
    assert resultado["disponivel"] is False


def test_projetar_agravo_devolve_modelo_escolhido_entre_os_disponiveis(resultado_dengue):
    assert resultado_dengue["disponivel"] is True
    assert resultado_dengue["modelo_escolhido"] in MODELOS_DISPONIVEIS


def test_projecao_2026_tem_o_numero_certo_de_semanas_e_ano(resultado_dengue):
    projecao = resultado_dengue["projecao_2026"]
    assert (projecao["ano_epidemiologico"] == ANO_PROJECAO).all()
    assert len(projecao) in (52, 53)
    assert list(projecao["semana_epidemiologica"]) == list(range(1, len(projecao) + 1))


def test_projecao_2026_nunca_tem_casos_negativos(resultado_dengue):
    projecao = resultado_dengue["projecao_2026"]
    assert (projecao["casos"] >= 0).all()
    assert (projecao["banda_80_inferior"] >= 0).all()
    assert (projecao["banda_95_inferior"] >= 0).all()


def test_projecao_2026_banda_95_contem_a_banda_80(resultado_dengue):
    projecao = resultado_dengue["projecao_2026"]
    assert (projecao["banda_95_inferior"] <= projecao["banda_80_inferior"]).all()
    assert (projecao["banda_95_superior"] >= projecao["banda_80_superior"]).all()
    assert (projecao["banda_80_inferior"] <= projecao["casos"]).all()
    assert (projecao["casos"] <= projecao["banda_80_superior"]).all()


def test_pico_projetado_e_consistente_com_a_serie_projetada(resultado_dengue):
    projecao = resultado_dengue["projecao_2026"]
    pico = resultado_dengue["pico_projetado"]
    assert pico["casos_esperados"] == int(projecao["casos"].max())
    assert pico["semana_epidemiologica"] in list(projecao["semana_epidemiologica"])


def test_resumo_backtest_tem_uma_linha_por_modelo(resultado_dengue):
    resumo = resultado_dengue["resumo_backtest"]
    assert set(resumo["modelo"]) == set(MODELOS_DISPONIVEIS)


def test_cobertura_intervalo_presente_e_entre_0_e_1(resultado_dengue):
    cobertura_media = resultado_dengue["cobertura_intervalo_media"]
    assert "cobertura_80_media" in cobertura_media
    assert "cobertura_95_media" in cobertura_media
    for chave, valor in cobertura_media.items():
        if valor is not None:
            assert 0.0 <= valor <= 1.0, f"{chave} fora de [0,1]: {valor}"

    por_dobra = resultado_dengue["cobertura_intervalo_por_dobra"]
    assert not por_dobra.empty
    assert "ano_alvo" in por_dobra.columns


def test_projetar_agravo_sem_populacao_nao_quebra():
    gold = _gold_sintetica(com_populacao=False)
    resultado = projetar_agravo(gold, "DENGUE")
    assert resultado["disponivel"] is True
    assert resultado["serie_historica"]["incidencia_100k"].isna().all()
