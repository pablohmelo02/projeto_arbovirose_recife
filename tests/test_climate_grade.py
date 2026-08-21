"""Testes da camada climática em grade (reanálise): cliente, Silver, Gold.

Nenhum teste depende de internet — todas as respostas HTTP são simuladas
com `responses`, e as séries em grade são construídas em memória.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import responses

from src.clients.gridded_climate_client import (
    URL_ARCHIVE,
    GriddedClimateClientError,
    OpenMeteoArchiveClient,
)
from src.gold.clima_grade import (
    COLUNAS_GOLD_CLIMA_GRADE,
    JANELAS_SEMANAS_ACUMULADO,
    calcular_features_clima_grade,
)
from src.silver.climate_grade import (
    distancia_km,
    extrair_series_diarias_grade,
    identificador_celula,
    montar_mapeamento_bairro_celula,
    normalizar_clima_grade_diario,
)
from src.silver.schema_climate_grade import GRADE_PRECIPITACAO, GRADE_TEMPERATURA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _payload_precipitacao(lat=-8.0, lon=-35.0, datas=("2024-01-07", "2024-01-08"), valores=(1.0, 2.0)):
    return {
        "latitude": lat,
        "longitude": lon,
        "daily": {"time": list(datas), "precipitation_sum": list(valores)},
    }


def _payload_temperatura(lat=-8.0, lon=-34.9, datas=("2024-01-07",), n=1):
    return {
        "latitude": lat,
        "longitude": lon,
        "daily": {
            "time": list(datas),
            "temperature_2m_mean": [26.0] * n,
            "temperature_2m_min": [22.0] * n,
            "temperature_2m_max": [30.0] * n,
            "relative_humidity_2m_mean": [78.0] * n,
        },
    }


def _serie_grade_diaria(datas, precipitacao, celula="-8.0000_-35.0000"):
    return pd.DataFrame(
        {
            "grade": GRADE_PRECIPITACAO,
            "celula_id": celula,
            "latitude_celula": -8.0,
            "longitude_celula": -35.0,
            "data": pd.to_datetime(list(datas)).date,
            "precipitacao_mm": list(precipitacao),
            "temperatura_media_c": None,
            "temperatura_minima_c": None,
            "temperatura_maxima_c": None,
            "umidade_relativa_media_pct": None,
        }
    )


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
@responses.activate
def test_cliente_devolve_bytes_para_resposta_valida():
    responses.add(responses.GET, URL_ARCHIVE, json=[_payload_precipitacao()], status=200)
    cliente = OpenMeteoArchiveClient(tentativas=1)
    conteudo = cliente.baixar_series_diarias(
        [(-8.05, -34.9)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
    )
    assert json.loads(conteudo)[0]["daily"]["precipitation_sum"] == [1.0, 2.0]


@responses.activate
def test_cliente_retenta_e_depois_falha_com_erro_500():
    responses.add(responses.GET, URL_ARCHIVE, status=500)
    responses.add(responses.GET, URL_ARCHIVE, status=500)
    cliente = OpenMeteoArchiveClient(tentativas=2, espera_inicial=0.0)
    with pytest.raises(GriddedClimateClientError, match="após 2 tentativa"):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
        )
    assert len(responses.calls) == 2


@responses.activate
def test_cliente_recupera_na_segunda_tentativa():
    responses.add(responses.GET, URL_ARCHIVE, status=503)
    responses.add(responses.GET, URL_ARCHIVE, json=[_payload_precipitacao()], status=200)
    cliente = OpenMeteoArchiveClient(tentativas=3, espera_inicial=0.0)
    conteudo = cliente.baixar_series_diarias(
        [(-8.05, -34.9)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
    )
    assert conteudo
    assert len(responses.calls) == 2


@responses.activate
def test_cliente_rejeita_resposta_vazia():
    responses.add(responses.GET, URL_ARCHIVE, body=b"", status=200)
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(GriddedClimateClientError):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
        )


@responses.activate
def test_cliente_rejeita_json_invalido():
    responses.add(responses.GET, URL_ARCHIVE, body=b"nao eh json", status=200)
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(GriddedClimateClientError, match="JSON"):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
        )


@responses.activate
def test_cliente_detecta_schema_drift_variavel_ausente():
    payload = _payload_precipitacao()
    del payload["daily"]["precipitation_sum"]
    responses.add(responses.GET, URL_ARCHIVE, json=[payload], status=200)
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(GriddedClimateClientError, match="ausente"):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
        )


@responses.activate
def test_cliente_detecta_numero_de_pontos_diferente_do_pedido():
    responses.add(responses.GET, URL_ARCHIVE, json=[_payload_precipitacao()], status=200)
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(GriddedClimateClientError, match="schema inesperado"):
        cliente.baixar_series_diarias(
            [(-8.05, -34.9), (-8.1, -35.0)], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5"
        )


def test_cliente_rejeita_lista_de_pontos_vazia():
    cliente = OpenMeteoArchiveClient(tentativas=1)
    with pytest.raises(ValueError):
        cliente.baixar_series_diarias([], "2024-01-07", "2024-01-08", ("precipitation_sum",), "era5")


# ---------------------------------------------------------------------------
# Silver
# ---------------------------------------------------------------------------
def test_extrair_series_preserva_none_da_fonte():
    payload = _payload_precipitacao(valores=(1.0, None))
    df = extrair_series_diarias_grade(json.dumps([payload]).encode("utf-8"), GRADE_PRECIPITACAO)
    # pandas materializa o `None` de uma coluna float como `NaN` — o que
    # importa é que continua AUSENTE, nunca virou 0.
    assert df["precipitacao_mm"].iloc[0] == 1.0
    assert pd.isna(df["precipitacao_mm"].iloc[1])


def test_extrair_series_levanta_em_schema_drift():
    payload = _payload_precipitacao()
    del payload["daily"]["precipitation_sum"]
    with pytest.raises(ValueError, match="schema drift"):
        extrair_series_diarias_grade(json.dumps([payload]).encode("utf-8"), GRADE_PRECIPITACAO)


def test_normalizar_nunca_transforma_ausencia_em_zero():
    bruto = _serie_grade_diaria(["2024-01-07", "2024-01-08"], [np.nan, 5.0])
    df, metricas = normalizar_clima_grade_diario(bruto)
    assert df["precipitacao_mm"].isna().sum() == 1
    assert metricas["linhas_validas"] == 2


def test_normalizar_deduplica_por_chave_composta_mantendo_o_mais_recente():
    bruto = pd.concat(
        [
            _serie_grade_diaria(["2024-01-07"], [1.0]),
            _serie_grade_diaria(["2024-01-07"], [9.0]),
        ],
        ignore_index=True,
    )
    df, metricas = normalizar_clima_grade_diario(bruto)
    assert metricas["duplicatas_removidas"] == 1
    assert df["precipitacao_mm"].tolist() == [9.0]


def test_normalizar_mesma_celula_em_grades_diferentes_nao_e_duplicata():
    a = _serie_grade_diaria(["2024-01-07"], [1.0])
    b = a.copy()
    b["grade"] = GRADE_TEMPERATURA
    df, metricas = normalizar_clima_grade_diario(pd.concat([a, b], ignore_index=True))
    assert metricas["duplicatas_removidas"] == 0
    assert len(df) == 2


def test_normalizar_anula_valor_implausivel_e_conta_o_motivo():
    bruto = _serie_grade_diaria(["2024-01-07", "2024-01-08"], [10.0, 9999.0])
    df, metricas = normalizar_clima_grade_diario(bruto)
    assert df["precipitacao_mm"].isna().sum() == 1
    assert any("fora do intervalo plausivel" in m for m in metricas["motivos_rejeicao"])


def test_normalizar_dataframe_vazio_devolve_contrato_completo():
    df, metricas = normalizar_clima_grade_diario(pd.DataFrame())
    assert list(df.columns)  # nunca um DataFrame sem colunas
    assert metricas["linhas_validas"] == 0


def test_identificador_celula_e_estavel_contra_ruido_de_ponto_flutuante():
    assert identificador_celula(-8.0, -35.0) == identificador_celula(-8.000000001, -34.999999998)


def test_distancia_km_entre_pontos_conhecidos():
    # ~1 grau de latitude no equador ≈ 111 km
    assert 110.0 < distancia_km(0.0, 0.0, 1.0, 0.0) < 112.0
    assert distancia_km(-8.0, -35.0, -8.0, -35.0) == pytest.approx(0.0)


def test_mapeamento_bairro_celula_calcula_distancia_e_resolucao():
    centroides = pd.DataFrame(
        [{"codigo_bairro": "1", "nome_bairro": "A", "centroide_lat": -8.05, "centroide_lon": -34.9}]
    )
    diario = _serie_grade_diaria(["2024-01-07"], [1.0])
    mapa = {("1", GRADE_PRECIPITACAO): "-8.0000_-35.0000"}
    df = montar_mapeamento_bairro_celula(centroides, diario, mapa)
    assert len(df) == 1
    assert df.loc[0, "resolucao_graus"] == 0.25
    assert df.loc[0, "distancia_centroide_celula_km"] > 0
    assert df.loc[0, "metodo_associacao"] == "celula_que_contem_o_centroide"


# ---------------------------------------------------------------------------
# Gold — features em grade
# ---------------------------------------------------------------------------
def _grao_semanal(n_semanas=6, codigo_bairro="1"):
    inicios = pd.date_range("2024-01-07", periods=n_semanas, freq="7D")
    return pd.DataFrame(
        {
            "codigo_bairro": codigo_bairro,
            "ano_epidemiologico": 2024,
            "semana_epidemiologica": range(2, 2 + n_semanas),
            "semana_epi_data_inicio": inicios,
            "semana_epi_data_fim": inicios + pd.Timedelta(days=6),
        }
    )


def _diario_para_grao(grao, valor_por_dia=1.0):
    inicio = grao["semana_epi_data_inicio"].min() - pd.Timedelta(days=7 * max(JANELAS_SEMANAS_ACUMULADO))
    fim = grao["semana_epi_data_fim"].max()
    datas = pd.date_range(inicio, fim, freq="D")
    precip = _serie_grade_diaria(datas, [valor_por_dia] * len(datas))
    temp = precip.copy()
    temp["grade"] = GRADE_TEMPERATURA
    temp["celula_id"] = "-8.0000_-34.9000"
    temp["precipitacao_mm"] = None
    temp["temperatura_media_c"] = 26.0
    temp["temperatura_minima_c"] = 22.0
    temp["temperatura_maxima_c"] = 30.0
    temp["umidade_relativa_media_pct"] = 78.0
    return pd.concat([precip, temp], ignore_index=True)


def _bairro_celula(codigo_bairro="1"):
    return pd.DataFrame(
        [
            {"codigo_bairro": codigo_bairro, "grade": GRADE_PRECIPITACAO, "celula_id": "-8.0000_-35.0000"},
            {"codigo_bairro": codigo_bairro, "grade": GRADE_TEMPERATURA, "celula_id": "-8.0000_-34.9000"},
        ]
    )


def test_features_grade_produzem_todas_as_colunas_do_contrato():
    grao = _grao_semanal()
    df, metricas = calcular_features_clima_grade(grao, _bairro_celula(), _diario_para_grao(grao))
    for coluna in COLUNAS_GOLD_CLIMA_GRADE:
        assert coluna in df.columns, coluna
    assert metricas["linhas_com_precipitacao_grade"] == len(grao)


def test_precipitacao_semanal_e_soma_de_7_dias_e_acumulados_sao_multiplos():
    grao = _grao_semanal()
    df, _ = calcular_features_clima_grade(grao, _bairro_celula(), _diario_para_grao(grao, valor_por_dia=2.0))
    assert df["precipitacao_semana_grade_mm"].iloc[-1] == pytest.approx(14.0)
    assert df["precipitacao_2s_grade_mm"].iloc[-1] == pytest.approx(28.0)
    assert df["precipitacao_4s_grade_mm"].iloc[-1] == pytest.approx(56.0)


def test_temperatura_minima_semanal_e_a_menor_minima_nao_a_media():
    grao = _grao_semanal(n_semanas=2)
    diario = _diario_para_grao(grao)
    ultima_data = pd.Timestamp(grao["semana_epi_data_fim"].iloc[-1]).date()
    mask = (diario["grade"] == GRADE_TEMPERATURA) & (diario["data"] == ultima_data)
    diario.loc[mask, "temperatura_minima_c"] = 15.0
    diario.loc[mask, "temperatura_maxima_c"] = 40.0
    df, _ = calcular_features_clima_grade(grao, _bairro_celula(), diario)
    assert df["temperatura_minima_grade_c"].iloc[-1] == pytest.approx(15.0)
    assert df["temperatura_maxima_grade_c"].iloc[-1] == pytest.approx(40.0)


def test_features_grade_nao_usam_chuva_futura_leakage_adversarial():
    """Injeta chuva ENORME depois do fim da última semana avaliada: nenhuma
    feature de nenhuma semana anterior pode mudar."""
    grao = _grao_semanal()
    diario = _diario_para_grao(grao)
    antes, _ = calcular_features_clima_grade(grao, _bairro_celula(), diario)

    futuro = _serie_grade_diaria(
        pd.date_range(pd.Timestamp(grao["semana_epi_data_fim"].max()) + pd.Timedelta(days=1), periods=30, freq="D"),
        [999.0] * 30,
    )
    depois, _ = calcular_features_clima_grade(
        grao, _bairro_celula(), pd.concat([diario, futuro], ignore_index=True)
    )
    for coluna in COLUNAS_GOLD_CLIMA_GRADE:
        if antes[coluna].dtype.kind in "fi":
            pd.testing.assert_series_equal(antes[coluna], depois[coluna], check_names=False)


def test_semana_sem_nenhum_dia_valido_fica_none_e_contador_zero():
    grao = _grao_semanal(n_semanas=3)
    # Só a primeira semana tem dado; as outras não têm nenhum dia na série.
    datas = pd.date_range(grao["semana_epi_data_inicio"].iloc[0], grao["semana_epi_data_fim"].iloc[0], freq="D")
    diario = _serie_grade_diaria(datas, [1.0] * len(datas))
    df, _ = calcular_features_clima_grade(grao, _bairro_celula(), diario)
    assert pd.isna(df["precipitacao_semana_grade_mm"].iloc[-1])
    assert df["dias_validos_precipitacao_grade_semana"].iloc[-1] == 0


def test_bairro_sem_celula_associada_fica_sem_features_de_grade():
    grao = _grao_semanal()
    df, metricas = calcular_features_clima_grade(
        grao, _bairro_celula(codigo_bairro="999"), _diario_para_grao(grao)
    )
    assert df["precipitacao_semana_grade_mm"].isna().all()
    assert df["fonte_clima_grade"].isna().all() or (df["fonte_clima_grade"] == "None").all()
    assert metricas["linhas_com_precipitacao_grade"] == 0


def test_features_grade_com_silver_vazia_nao_quebra():
    grao = _grao_semanal()
    df, metricas = calcular_features_clima_grade(grao, _bairro_celula(), pd.DataFrame())
    assert len(df) == len(grao)
    assert metricas["percentual_linhas_com_clima_grade"] == 0.0


def test_enriquecimento_da_gold_preserva_linhas_casos_e_e_idempotente():
    from src.enrich_gold_clima_grade import enriquecer_gold_com_grade

    grao = _grao_semanal(n_semanas=4)
    gold = pd.concat(
        [grao.assign(agravo=a, casos=range(len(grao))) for a in ("DENGUE", "ZIKA", "CHIKUNGUNYA")],
        ignore_index=True,
    )
    gold["nome_bairro"] = "A"
    diario = _diario_para_grao(grao)

    primeira, m1 = enriquecer_gold_com_grade(gold, diario, _bairro_celula())
    assert len(primeira) == len(gold)
    assert int(primeira["casos"].sum()) == int(gold["casos"].sum())
    assert m1["cardinalidade_preservada"] is True

    segunda, _ = enriquecer_gold_com_grade(primeira, diario, _bairro_celula())
    assert len(segunda) == len(primeira)
    for coluna in COLUNAS_GOLD_CLIMA_GRADE:
        pd.testing.assert_series_equal(primeira[coluna], segunda[coluna], check_names=False)


def test_enriquecimento_atribui_o_mesmo_clima_aos_tres_agravos():
    from src.enrich_gold_clima_grade import enriquecer_gold_com_grade

    grao = _grao_semanal(n_semanas=3)
    gold = pd.concat(
        [grao.assign(agravo=a, casos=1) for a in ("DENGUE", "ZIKA", "CHIKUNGUNYA")], ignore_index=True
    )
    gold["nome_bairro"] = "A"
    enriquecida, _ = enriquecer_gold_com_grade(gold, _diario_para_grao(grao), _bairro_celula())
    por_semana = enriquecida.groupby(["codigo_bairro", "semana_epidemiologica"])[
        "precipitacao_semana_grade_mm"
    ].nunique()
    assert (por_semana == 1).all()
