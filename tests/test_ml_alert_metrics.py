import pandas as pd

from src.ml.alert_metrics import (
    avaliar_antecipacao,
    construir_episodios,
    duracao_falsos_alertas_consecutivos,
    epidemias_grandes,
    metricas_operacionais_semanais,
    metricas_por_ano,
    metricas_por_bairro,
    resumo_antecipacao,
)


def _estado(bairro: str, indices_estado: list[tuple[int, float]], ano=2020) -> pd.DataFrame:
    linhas = []
    for indice, estado in indices_estado:
        linhas.append(
            {
                "codigo_bairro": bairro,
                "indice_semana_global": indice,
                "ano_epidemiologico": ano,
                "semana_epidemiologica": (indice % 52) + 1,
                "casos": 10 if estado == 1 else 1,
                "estado_alto_risco": estado,
            }
        )
    return pd.DataFrame(linhas)


def test_semanas_consecutivas_formam_um_unico_episodio():
    df = _estado("1", [(0, 0.0), (1, 1.0), (2, 1.0), (3, 1.0), (4, 0.0)])
    episodios = construir_episodios(df)
    assert len(episodios) == 1
    assert episodios.iloc[0]["inicio_indice"] == 1
    assert episodios.iloc[0]["fim_indice"] == 3
    assert episodios.iloc[0]["duracao_semanas"] == 3


def test_episodio_isolado_de_uma_semana():
    df = _estado("1", [(0, 0.0), (1, 1.0), (2, 0.0)])
    episodios = construir_episodios(df)
    assert len(episodios) == 1
    assert episodios.iloc[0]["inicio_indice"] == 1
    assert episodios.iloc[0]["fim_indice"] == 1


def test_dois_episodios_separados_por_semana_de_baixo_risco():
    df = _estado("1", [(0, 1.0), (1, 0.0), (2, 1.0)])
    episodios = construir_episodios(df)
    assert len(episodios) == 2


def test_gap_por_estado_indefinido_quebra_continuidade():
    df = pd.DataFrame(
        [
            {"codigo_bairro": "1", "indice_semana_global": 0, "ano_epidemiologico": 2020, "semana_epidemiologica": 1, "casos": 10, "estado_alto_risco": 1.0},
            {"codigo_bairro": "1", "indice_semana_global": 1, "ano_epidemiologico": 2020, "semana_epidemiologica": 2, "casos": 10, "estado_alto_risco": float("nan")},
            {"codigo_bairro": "1", "indice_semana_global": 2, "ano_epidemiologico": 2020, "semana_epidemiologica": 3, "casos": 10, "estado_alto_risco": 1.0},
        ]
    )
    episodios = construir_episodios(df)
    assert len(episodios) == 2  # a semana indefinida quebra a continuidade


def test_lead_time_antecipado_simultaneo_tardio_e_perdido():
    # Episodio real comeca no indice 10.
    df_ep = pd.DataFrame(
        [{"codigo_bairro": "1", "inicio_indice": 10, "fim_indice": 12, "inicio_ano": 2020, "inicio_semana": 10, "duracao_semanas": 3, "casos_totais_episodio": 30.0, "casos_pico": 15.0}]
    )
    # Alerta com semana-alvo=8 -> lead=2 (antecipado)
    alertas_antecipado = pd.DataFrame({"codigo_bairro": ["1"], "indice_semana_alvo": [8], "alerta": [1]})
    avaliados, falsos = avaliar_antecipacao(alertas_antecipado, df_ep)
    assert avaliados.iloc[0]["classificacao"] == "antecipado"
    assert avaliados.iloc[0]["lead_time_semanas"] == 2

    # Alerta com semana-alvo=10 (a propria semana de inicio) -> simultaneo (lead=0)
    alertas_simultaneo = pd.DataFrame({"codigo_bairro": ["1"], "indice_semana_alvo": [10], "alerta": [1]})
    avaliados, falsos = avaliar_antecipacao(alertas_simultaneo, df_ep)
    assert avaliados.iloc[0]["classificacao"] == "simultaneo"
    assert avaliados.iloc[0]["lead_time_semanas"] == 0

    # Alerta so em indice 11 (dentro do episodio, mas depois do inicio) -> tardio
    alertas_tardio = pd.DataFrame({"codigo_bairro": ["1"], "indice_semana_alvo": [11], "alerta": [1]})
    avaliados, falsos = avaliar_antecipacao(alertas_tardio, df_ep)
    assert avaliados.iloc[0]["classificacao"] == "tardio"
    assert avaliados.iloc[0]["lead_time_semanas"] == -1

    # Sem nenhum alerta na janela -> perdido
    alertas_vazio = pd.DataFrame({"codigo_bairro": pd.Series(dtype=str), "indice_semana_alvo": pd.Series(dtype=int), "alerta": pd.Series(dtype=int)})
    avaliados, falsos = avaliar_antecipacao(alertas_vazio, df_ep)
    assert avaliados.iloc[0]["classificacao"] == "perdido"
    assert not avaliados.iloc[0]["detectado"]


def test_falso_alerta_fora_da_janela_de_qualquer_episodio():
    df_ep = pd.DataFrame(
        [{"codigo_bairro": "1", "inicio_indice": 10, "fim_indice": 12, "inicio_ano": 2020, "inicio_semana": 10, "duracao_semanas": 3, "casos_totais_episodio": 30.0, "casos_pico": 15.0}]
    )
    alertas = pd.DataFrame({"codigo_bairro": ["1", "1"], "indice_semana_alvo": [8, 30], "alerta": [1, 1]})
    avaliados, falsos = avaliar_antecipacao(alertas, df_ep)
    assert len(falsos) == 1
    assert falsos.iloc[0]["indice_semana_alvo"] == 30


def test_resumo_antecipacao_agrega_corretamente():
    df_ep = pd.DataFrame(
        [
            {"codigo_bairro": "1", "inicio_indice": 10, "fim_indice": 10, "inicio_ano": 2020, "inicio_semana": 10, "duracao_semanas": 1, "casos_totais_episodio": 10.0, "casos_pico": 10.0, "detectado": True, "classificacao": "antecipado", "lead_time_semanas": 2, "semana_alvo_deteccao": 8},
            {"codigo_bairro": "2", "inicio_indice": 20, "fim_indice": 20, "inicio_ano": 2021, "inicio_semana": 5, "duracao_semanas": 1, "casos_totais_episodio": 5.0, "casos_pico": 5.0, "detectado": False, "classificacao": "perdido", "lead_time_semanas": None, "semana_alvo_deteccao": None},
        ]
    )
    falsos = pd.DataFrame({"codigo_bairro": ["1"], "indice_semana_alvo": [50]})
    resumo = resumo_antecipacao(df_ep, falsos)
    assert resumo["n_episodios"] == 2
    assert resumo["n_detectados"] == 1
    assert resumo["taxa_deteccao"] == 0.5
    assert resumo["n_falsos_alertas"] == 1

    por_bairro = metricas_por_bairro(df_ep, falsos)
    assert set(por_bairro["codigo_bairro"]) == {"1", "2"}

    por_ano = metricas_por_ano(df_ep)
    assert set(por_ano["inicio_ano"]) == {2020, 2021}

    grandes = epidemias_grandes(df_ep, top_pct=0.5)
    assert len(grandes) == 1
    assert grandes.iloc[0]["codigo_bairro"] == "1"


def test_metricas_operacionais_semanais_reporta_media_e_mediana():
    df_alertas = pd.DataFrame(
        {
            "codigo_bairro": ["1", "2", "3", "1"],
            "indice_semana_alvo": [10, 10, 10, 11],
            "alerta": [1, 1, 0, 1],
        }
    )
    falsos = pd.DataFrame({"codigo_bairro": ["1", "2"], "indice_semana_alvo": [10, 10]})
    resultado = metricas_operacionais_semanais(df_alertas, falsos)
    assert resultado["bairros_alertados_por_semana_max"] == 2  # semana 10 teve 2 alertas
    assert resultado["n_semanas_com_pelo_menos_1_falso_alerta"] == 1


def test_duracao_falsos_alertas_consecutivos_agrupa_sequencias():
    falsos = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1", "1", "1", "2"],
            "indice_semana_alvo": [10, 11, 12, 20, 5],
        }
    )
    resultado = duracao_falsos_alertas_consecutivos(falsos)
    # bairro 1: sequencia 10-11-12 (comprimento 3) + sequencia isolada 20 (comprimento 1)
    # bairro 2: sequencia isolada 5 (comprimento 1)
    assert resultado["n_sequencias"] == 3
    assert resultado["duracao_maxima_semanas"] == 3


def test_duracao_falsos_alertas_consecutivos_vazio():
    falsos_vazio = pd.DataFrame({"codigo_bairro": pd.Series(dtype=str), "indice_semana_alvo": pd.Series(dtype=int)})
    resultado = duracao_falsos_alertas_consecutivos(falsos_vazio)
    assert resultado["n_sequencias"] == 0
    assert resultado["duracao_media_semanas"] is None
