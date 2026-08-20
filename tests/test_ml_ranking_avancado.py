import pandas as pd

from src.ml.ranking import (
    estabilidade_ranking,
    persistencia_consecutiva_antes_de_onset,
    precision_em_k,
)


def test_precision_em_k_mede_fracao_correta_do_topk():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "D"],
            "indice_semana_alvo": [1, 1, 1, 1],
            "posicao": [1, 2, 3, 4],
            "estado_real": [1, 1, 0, 0],
        }
    )
    resultado = precision_em_k(df, k_valores=(2, 4))
    p2 = resultado[resultado["k"] == 2].iloc[0]
    p4 = resultado[resultado["k"] == 4].iloc[0]
    assert p2["precision_media"] == 1.0  # top2 = A,B, ambos positivos
    assert p4["precision_media"] == 0.5  # top4 = todos, 2 de 4 positivos


def test_estabilidade_ranking_jaccard_1_quando_topk_identico():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "A", "B"],
            "indice_semana_alvo": [1, 1, 2, 2],
            "posicao": [1, 2, 1, 2],
        }
    )
    resultado = estabilidade_ranking(df, k=2)
    assert resultado["jaccard_medio"] == 1.0
    assert resultado["n_pares_consecutivos"] == 1


def test_estabilidade_ranking_jaccard_0_quando_topk_totalmente_diferente():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "D"],
            "indice_semana_alvo": [1, 1, 2, 2],
            "posicao": [1, 2, 1, 2],
        }
    )
    resultado = estabilidade_ranking(df, k=2)
    assert resultado["jaccard_medio"] == 0.0


def test_persistencia_consecutiva_conta_semanas_seguidas_no_topk():
    ranking = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1", "1", "1"],
            "indice_semana_alvo": [7, 8, 9, 10],
            "posicao": [3, 2, 50, 1],  # semana 9 sai do top-10 (posicao 50)
        }
    )
    episodios = pd.DataFrame([{"codigo_bairro": "1", "inicio_indice": 10, "inicio_ano": 2024}])
    resultado = persistencia_consecutiva_antes_de_onset(ranking, episodios, k=10, janela=4)
    # onset=10; olhando p/ tras: semana 9 (fora do topk) -> para imediatamente
    assert resultado.iloc[0]["semanas_consecutivas_topk_antes"] == 0


def test_persistencia_consecutiva_conta_ate_a_primeira_quebra():
    ranking = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1", "1"],
            "indice_semana_alvo": [7, 8, 9],
            "posicao": [5, 3, 2],
        }
    )
    episodios = pd.DataFrame([{"codigo_bairro": "1", "inicio_indice": 10, "inicio_ano": 2024}])
    resultado = persistencia_consecutiva_antes_de_onset(ranking, episodios, k=10, janela=4)
    # semanas 9,8,7 todas <=10 -> 3 consecutivas (janela permite ate 4 semanas: 6,7,8,9)
    assert resultado.iloc[0]["semanas_consecutivas_topk_antes"] == 3
