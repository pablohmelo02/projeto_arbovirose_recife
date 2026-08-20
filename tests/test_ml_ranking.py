import pandas as pd
import pytest

from src.ml.ranking import (
    construir_ranking_semanal,
    posicao_antes_de_episodios,
    recall_em_k,
    resumo_posicao_antes_de_episodios,
)


def test_construir_ranking_semanal_ordena_por_probabilidade_dentro_da_semana():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "A", "B"],
            "indice_semana_alvo": [10, 10, 10, 11, 11],
            "probabilidade": [0.9, 0.5, 0.7, 0.2, 0.8],
        }
    )
    resultado = construir_ranking_semanal(df)
    semana_10 = resultado[resultado["indice_semana_alvo"] == 10].set_index("codigo_bairro")
    assert semana_10.loc["A", "posicao"] == 1
    assert semana_10.loc["C", "posicao"] == 2
    assert semana_10.loc["B", "posicao"] == 3
    semana_11 = resultado[resultado["indice_semana_alvo"] == 11].set_index("codigo_bairro")
    assert semana_11.loc["B", "posicao"] == 1
    assert semana_11.loc["A", "posicao"] == 2


def test_recall_em_k_captura_positivos_no_topo():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "D"],
            "indice_semana_alvo": [1, 1, 1, 1],
            "posicao": [1, 2, 3, 4],
            "estado_real": [1, 0, 1, 0],
        }
    )
    resultado = recall_em_k(df, k_valores=(1, 2, 3))
    r1 = resultado[resultado["k"] == 1].iloc[0]
    r2 = resultado[resultado["k"] == 2].iloc[0]
    r3 = resultado[resultado["k"] == 3].iloc[0]
    assert r1["recall_micro"] == 0.5  # so A (posicao 1) capturado, dos 2 positivos
    assert r2["recall_micro"] == 0.5  # C (posicao 3) ainda fora do top2
    assert r3["recall_micro"] == 1.0  # top3 pega A e C


def test_posicao_antes_de_episodios_encontra_melhor_posicao_na_janela():
    ranking = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1", "1", "1", "1"],
            "indice_semana_alvo": [6, 7, 8, 9, 10],
            "posicao": [50, 20, 3, 40, 1],
        }
    )
    episodios = pd.DataFrame([{"codigo_bairro": "1", "inicio_indice": 10, "inicio_ano": 2024}])
    resultado = posicao_antes_de_episodios(ranking, episodios, janela=4)
    linha = resultado.iloc[0]
    # janela = semanas 6..9 (antes de 10) -- melhor posicao = 3 (semana 8)
    assert linha["melhor_posicao_antes_do_inicio"] == 3
    assert linha["semanas_antecedencia_melhor_posicao"] == 2  # 10 - 8
    assert linha["posicao_na_semana_de_inicio"] == 1


def test_posicao_antes_de_episodios_nao_olha_para_o_futuro_do_episodio():
    # ranking so tem dado NA semana de inicio e depois -- nao deve contar como "antes"
    ranking = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1"],
            "indice_semana_alvo": [10, 11],
            "posicao": [1, 1],
        }
    )
    episodios = pd.DataFrame([{"codigo_bairro": "1", "inicio_indice": 10, "inicio_ano": 2024}])
    resultado = posicao_antes_de_episodios(ranking, episodios, janela=4)
    assert resultado.iloc[0]["melhor_posicao_antes_do_inicio"] is None or pd.isna(
        resultado.iloc[0]["melhor_posicao_antes_do_inicio"]
    )


def test_resumo_posicao_antes_de_episodios_calcula_percentuais_top_k():
    posicoes = pd.DataFrame(
        {
            "melhor_posicao_antes_do_inicio": [1, 8, 25, None],
            "semanas_antecedencia_melhor_posicao": [2, 1, 3, None],
        }
    )
    resumo = resumo_posicao_antes_de_episodios(posicoes, k_valores=(5, 10, 20))
    assert resumo["n_episodios"] == 4
    assert resumo["n_com_ranking_disponivel_antes"] == 3
    assert resumo["pct_top_5_antes"] == pytest.approx(1 / 3 * 100)
    assert resumo["pct_top_10_antes"] == pytest.approx(2 / 3 * 100)
    assert resumo["pct_top_20_antes"] == pytest.approx(2 / 3 * 100)
