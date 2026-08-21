from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.forecast import intervalos
from src.forecast.modelos import SerieCurtaDemaisError, ajustar_ets, ajustar_ets_previsao
from src.forecast.selecao_modelo import escolher_modelo


def _serie_sazonal(n_anos: int = 4, semanas_sazonais: int = 52, amplitude: float = 20.0, ruido_seed: int = 42) -> pd.DataFrame:
    """Série com sazonalidade clara (seno) + leve tendência + ruído
    pequeno -- o suficiente para o ETS conseguir ajustar sem virar teste
    instável (sem assert exato sobre o valor previsto, só sobre a forma)."""
    rng = np.random.RandomState(ruido_seed)
    n = n_anos * semanas_sazonais
    indices = np.arange(n)
    sazonal = amplitude * np.sin(2 * np.pi * indices / semanas_sazonais) + amplitude
    tendencia = indices * 0.05
    ruido = rng.normal(0, 1.0, n)
    casos = np.clip(sazonal + tendencia + ruido, a_min=0, a_max=None)

    linhas = []
    for i in range(n):
        ano = 2020 + i // semanas_sazonais
        semana = (i % semanas_sazonais) + 1
        linhas.append(
            {"ano_epidemiologico": ano, "semana_epidemiologica": semana, "indice_semana": i, "casos": casos[i]}
        )
    return pd.DataFrame(linhas)


def test_ajustar_ets_recusa_serie_curta_demais():
    serie_curta = _serie_sazonal(n_anos=1, semanas_sazonais=52)
    with pytest.raises(SerieCurtaDemaisError):
        ajustar_ets(serie_curta, n_semanas_previsao=10, semanas_sazonais=52)


def test_ajustar_ets_produz_previsao_do_tamanho_pedido_e_nao_negativa():
    serie = _serie_sazonal(n_anos=4, semanas_sazonais=52)
    previsao, modelo = ajustar_ets(serie, n_semanas_previsao=52, semanas_sazonais=52)
    assert len(previsao) == 52
    assert (previsao >= 0).all()
    assert modelo is not None


def test_ajustar_ets_previsao_wrapper_bate_com_ajustar_ets():
    serie = _serie_sazonal(n_anos=4, semanas_sazonais=52)
    semanas_alvo = pd.DataFrame({"ano_epidemiologico": 2024, "semana_epidemiologica": range(1, 11)})
    previsao_wrapper = ajustar_ets_previsao(serie, semanas_alvo)
    assert len(previsao_wrapper) == 10
    assert (previsao_wrapper >= 0).all()


def test_banda_empirica_amplia_com_amostra_de_erro_maior():
    central = np.array([10.0, 10.0, 10.0])
    erros_pequenos = np.array([-1.0, 1.0])
    erros_grandes = np.array([-10.0, 10.0])
    banda_estreita = intervalos.banda_empirica(central, erros_pequenos)
    banda_larga = intervalos.banda_empirica(central, erros_grandes)
    largura_estreita = banda_estreita["banda_95_superior"][0] - banda_estreita["banda_95_inferior"][0]
    largura_larga = banda_larga["banda_95_superior"][0] - banda_larga["banda_95_inferior"][0]
    assert largura_larga > largura_estreita


def test_banda_empirica_sem_amostra_suficiente_colapsa_na_central():
    central = np.array([10.0, 20.0])
    banda = intervalos.banda_empirica(central, np.array([]))
    assert banda["metodo"] == "empirica_sem_amostra_suficiente"
    assert list(banda["banda_80_inferior"]) == list(central)
    assert list(banda["banda_80_superior"]) == list(central)


def test_banda_ets_niveis_95_contem_o_intervalo_80():
    serie = _serie_sazonal(n_anos=4, semanas_sazonais=52)
    _previsao, modelo = ajustar_ets(serie, n_semanas_previsao=10, semanas_sazonais=52)
    banda = intervalos.banda_ets(modelo, n_semanas_previsao=10, n_simulacoes=200)
    assert (banda["banda_95_inferior"] <= banda["banda_80_inferior"]).all()
    assert (banda["banda_95_superior"] >= banda["banda_80_superior"]).all()


def test_escolher_modelo_prefere_menor_mase_mediano():
    bom = pd.DataFrame({"mase": [0.5, 0.6, 0.4], "erro_timing_semanas": [0, 1, 0]})
    ruim = pd.DataFrame({"mase": [1.5, 1.8, 1.2], "erro_timing_semanas": [2, 3, 1]})
    vencedor, resumo = escolher_modelo({"bom": bom, "ruim": ruim})
    assert vencedor == "bom"
    assert set(resumo["modelo"]) == {"bom", "ruim"}


def test_escolher_modelo_desempata_por_erro_de_timing():
    empatado_preciso = pd.DataFrame({"mase": [1.0, 1.0], "erro_timing_semanas": [0, 0]})
    empatado_impreciso = pd.DataFrame({"mase": [1.0, 1.0], "erro_timing_semanas": [3, -3]})
    vencedor, _ = escolher_modelo({"preciso": empatado_preciso, "impreciso": empatado_impreciso})
    assert vencedor == "preciso"


def test_escolher_modelo_ignora_dobras_sem_mase_mas_usa_as_validas():
    parcial = pd.DataFrame({"mase": [None, 0.3], "erro_timing_semanas": [None, 0]})
    vencedor, resumo = escolher_modelo({"parcial": parcial})
    assert vencedor == "parcial"
    assert resumo.iloc[0]["n_dobras_validas"] == 1


def test_escolher_modelo_sem_nenhuma_dobra_valida_levanta_erro():
    vazio = pd.DataFrame({"erro_ajuste": ["falhou"]})
    with pytest.raises(ValueError):
        escolher_modelo({"so_falhas": vazio})
