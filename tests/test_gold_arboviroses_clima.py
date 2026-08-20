import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from src.gold.arboviroses_clima import (
    agregar_casos,
    calcular_features_climaticas,
    extrair_periodo_epidemiologico,
    juntar_atributos_territorio,
    juntar_bairro_oficial,
    materializar_grao_completo,
    montar_gold_arboviroses_clima,
    remover_duplicatas_exatas,
)
from src.gold.epidemiologia import intervalo_semana_epidemiologica
from src.gold.schema_gold_arboviroses_clima import COLUNAS_GOLD_ARBOVIROSES_CLIMA


def _gdf_bairros_2() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "codigo_bairro": ["1", "2"],
            "nome_bairro": ["BOA VIAGEM", "CASA FORTE"],
            "area_km2": [5.0, 3.0],
            "codigo_rpa": [1, 2],
            "codigo_microrregiao": [1, 1],
            "centroide_lat": [-8.1, -8.05],
            "centroide_lon": [-34.9, -34.92],
            "geometry": [Point(0, 0), Point(1, 1)],
        },
        crs="EPSG:4326",
    )


def _df_arbo_basico() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_notificacao": ["a", "b", "c", "d", "e"],
            "tipo_arbovirose": ["DENGUE", "DENGUE", "ZIKA", "DENGUE", "DENGUE"],
            "semana_notificacao": ["202002", "202002", "202003", "999999", None],
            "nome_bairro": ["Boa Viagem", "boa viagem", "CASA FORTE", "Boa Viagem", "Boa Viagem"],
            "codigo_bairro": ["x", "x", "y", "x", "x"],
        }
    )


def _df_bairro_estacao_2() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_bairro": ["1", "2"],
            "codigo_estacao": ["E1", "E2"],
            "fonte": ["CEMADEN", "CEMADEN"],
            "distancia_km": [0.5, 0.8],
            "metodo_associacao": ["nearest_station", "nearest_station"],
        }
    )


# --------------------------------------------------------------------------
# Dedup / periodo epidemiologico / join bairro oficial
# --------------------------------------------------------------------------


def test_remover_duplicatas_exatas():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"], "_lineage": ["r1", "r2", "r3"]})
    resultado, n = remover_duplicatas_exatas(df)
    assert n == 1
    assert len(resultado) == 2


def test_extrair_periodo_epidemiologico_exclui_semana_invalida_e_conta():
    df = _df_arbo_basico()
    resultado, metricas = extrair_periodo_epidemiologico(df)
    assert metricas["linhas_antes"] == 5
    assert metricas["linhas_sem_semana_epidemiologica_valida"] == 2  # '999999' invalida + None
    assert metricas["linhas_depois"] == 3
    assert set(resultado["ano_epidemiologico"]) == {2020}


def test_juntar_bairro_oficial_normaliza_nome_e_preserva_todos_os_casos_validos():
    df = _df_arbo_basico()
    df, _ = extrair_periodo_epidemiologico(df)
    resultado, metricas = juntar_bairro_oficial(df, _gdf_bairros_2())

    assert metricas["linhas_antes"] == 3
    assert metricas["linhas_depois"] == 3
    # "Boa Viagem" e "boa viagem" devem virar o MESMO nome oficial (BOA VIAGEM)
    assert set(resultado["nome_bairro"]) == {"BOA VIAGEM", "CASA FORTE"}
    assert set(resultado["codigo_bairro"]) == {"1", "2"}


def test_juntar_bairro_oficial_nao_e_many_to_many():
    df = _df_arbo_basico()
    df, _ = extrair_periodo_epidemiologico(df)
    resultado, _ = juntar_bairro_oficial(df, _gdf_bairros_2())
    # 3 linhas validas entram, 3 devem sair (nunca multiplicar)
    assert len(resultado) == 3


def test_juntar_bairro_oficial_nome_fora_dos_oficiais_e_contado_nao_descartado_em_silencio():
    df = pd.DataFrame(
        {
            "id_notificacao": ["a"],
            "tipo_arbovirose": ["DENGUE"],
            "ano_epidemiologico": [2020],
            "semana_epidemiologica": [2],
            "codigo_bairro": ["999"],
            "nome_bairro": ["BAIRRO INEXISTENTE"],
        }
    )
    resultado, metricas = juntar_bairro_oficial(df, _gdf_bairros_2())
    assert resultado.empty
    assert metricas["linhas_com_nome_fora_dos_94_oficiais"] == 1


def test_juntar_bairro_oficial_nome_nulo_e_contado():
    df = pd.DataFrame(
        {
            "id_notificacao": ["a"],
            "tipo_arbovirose": ["DENGUE"],
            "ano_epidemiologico": [2020],
            "semana_epidemiologica": [2],
            "codigo_bairro": [None],
            "nome_bairro": [None],
        }
    )
    resultado, metricas = juntar_bairro_oficial(df, _gdf_bairros_2())
    assert resultado.empty
    assert metricas["linhas_sem_nome_bairro"] == 1


# --------------------------------------------------------------------------
# Agregacao e grao completo
# --------------------------------------------------------------------------


def test_agregar_casos_conta_notificacoes_nao_ids_distintos():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["1", "1"],
            "nome_bairro": ["BOA VIAGEM", "BOA VIAGEM"],
            "tipo_arbovirose": ["DENGUE", "DENGUE"],
            "ano_epidemiologico": [2020, 2020],
            "semana_epidemiologica": [2, 2],
            "id_notificacao": ["100", "100"],  # mesmo id_notificacao, linhas distintas
        }
    )
    resultado = agregar_casos(df)
    assert resultado.iloc[0]["casos"] == 2  # conta linha, nao id distinto


def test_materializar_grao_completo_preserva_total_de_casos():
    df_casos = pd.DataFrame(
        {
            "codigo_bairro": ["1"],
            "nome_bairro": ["BOA VIAGEM"],
            "agravo": ["DENGUE"],
            "ano_epidemiologico": [2020],
            "semana_epidemiologica": [2],
            "casos": [7],
        }
    )
    grao, metricas = materializar_grao_completo(df_casos, _gdf_bairros_2())
    assert metricas["total_casos_preservados"] == 7
    assert metricas["total_casos_no_grao"] == 7
    assert grao["casos"].sum() == 7


def test_materializar_grao_completo_preenche_zero_onde_nao_ha_notificacao():
    df_casos = pd.DataFrame(
        {
            "codigo_bairro": ["1"],
            "nome_bairro": ["BOA VIAGEM"],
            "agravo": ["DENGUE"],
            "ano_epidemiologico": [2020],
            "semana_epidemiologica": [2],
            "casos": [7],
        }
    )
    grao, metricas = materializar_grao_completo(df_casos, _gdf_bairros_2())
    # 2 bairros x 3 agravos x 53 semanas (2020 tem 53 semanas epi)
    assert metricas["total_bairros"] == 2
    assert metricas["total_agravos"] == 3
    linha_sem_caso = grao[(grao["codigo_bairro"] == "2") & (grao["agravo"] == "DENGUE") & (grao["semana_epidemiologica"] == 2)]
    assert linha_sem_caso.iloc[0]["casos"] == 0  # int, nao NaN
    assert not grao.duplicated(subset=["codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica"]).any()


def test_juntar_atributos_territorio_nao_multiplica_linhas():
    grao = pd.DataFrame({"codigo_bairro": ["1", "2", "1"]})
    resultado = juntar_atributos_territorio(grao, _gdf_bairros_2())
    assert len(resultado) == 3
    assert list(resultado["area_km2"]) == [5.0, 3.0, 5.0]


# --------------------------------------------------------------------------
# Features climaticas: missing != 0 e regra de leakage
# --------------------------------------------------------------------------


def _grao_semanal(codigo_bairro: str, ano: int, semana: int) -> pd.DataFrame:
    inicio, fim = intervalo_semana_epidemiologica(ano, semana)
    return pd.DataFrame(
        {
            "codigo_bairro": [codigo_bairro],
            "ano_epidemiologico": [ano],
            "semana_epidemiologica": [semana],
            "semana_epi_data_inicio": [pd.Timestamp(inicio)],
            "semana_epi_data_fim": [pd.Timestamp(fim)],
        }
    )


def test_features_climaticas_semana_sem_dado_fica_none_nao_zero():
    grao = _grao_semanal("1", 2020, 2)  # 2020-01-05 a 2020-01-11
    diario = pd.DataFrame(
        {"data": pd.to_datetime([]), "codigo_estacao": [], "fonte": [], "precipitacao_mm": []}
    )
    resultado, metricas = calcular_features_climaticas(grao, _df_bairro_estacao_2(), diario)
    linha = resultado.iloc[0]
    assert pd.isna(linha["precipitacao_total_semana_mm"])
    assert linha["dias_com_dado_valido_semana"] == 0
    assert metricas["percentual_linhas_com_clima_real"] == 0.0


def test_features_climaticas_zero_real_permanece_zero_nao_none():
    grao = _grao_semanal("1", 2020, 2)
    diario = pd.DataFrame(
        {
            "data": pd.to_datetime(["2020-01-05"]),
            "codigo_estacao": ["E1"],
            "fonte": ["CEMADEN"],
            "precipitacao_mm": [0.0],
        }
    )
    resultado, _ = calcular_features_climaticas(grao, _df_bairro_estacao_2(), diario)
    linha = resultado.iloc[0]
    assert linha["precipitacao_total_semana_mm"] == 0.0  # real zero, nao None
    assert linha["dias_com_dado_valido_semana"] == 1
    assert linha["dias_com_chuva"] == 0


def test_features_climaticas_nunca_usa_dado_posterior_ao_fim_da_semana():
    """Teste de leakage: injeta um dia de chuva DEPOIS do fim da semana-alvo
    e confirma que ele nao influencia nenhuma feature dessa semana."""
    grao = _grao_semanal("1", 2020, 2)  # fim = 2020-01-11
    fim_semana = grao.iloc[0]["semana_epi_data_fim"]

    diario_sem_futuro = pd.DataFrame(
        {
            "data": pd.to_datetime(["2020-01-06", "2020-01-07"]),
            "codigo_estacao": ["E1", "E1"],
            "fonte": ["CEMADEN", "CEMADEN"],
            "precipitacao_mm": [1.0, 2.0],
        }
    )
    diario_com_futuro = pd.concat(
        [
            diario_sem_futuro,
            pd.DataFrame(
                {
                    "data": [fim_semana + pd.Timedelta(days=1), fim_semana + pd.Timedelta(days=10)],
                    "codigo_estacao": ["E1", "E1"],
                    "fonte": ["CEMADEN", "CEMADEN"],
                    "precipitacao_mm": [999.0, 999.0],  # valor absurdo, facil de detectar se vazar
                }
            ),
        ],
        ignore_index=True,
    )

    resultado_sem_futuro, _ = calcular_features_climaticas(grao.copy(), _df_bairro_estacao_2(), diario_sem_futuro)
    resultado_com_futuro, _ = calcular_features_climaticas(grao.copy(), _df_bairro_estacao_2(), diario_com_futuro)

    colunas_climaticas = [c for c in COLUNAS_GOLD_ARBOVIROSES_CLIMA if "chuva" in c or "precipitacao" in c or "dias_com" in c]
    for coluna in colunas_climaticas:
        a = resultado_sem_futuro.iloc[0][coluna]
        b = resultado_com_futuro.iloc[0][coluna]
        if pd.isna(a) and pd.isna(b):
            continue
        assert a == b, f"vazamento de dado futuro detectado na coluna '{coluna}': {a} != {b}"


def test_features_climaticas_bairro_sem_estacao_fica_none_sem_erro():
    grao = _grao_semanal("1", 2020, 2)
    bairro_estacao_vazio = pd.DataFrame(columns=["codigo_bairro", "codigo_estacao", "fonte", "distancia_km", "metodo_associacao"])
    diario = pd.DataFrame({"data": pd.to_datetime([]), "codigo_estacao": [], "fonte": [], "precipitacao_mm": []})
    resultado, metricas = calcular_features_climaticas(grao, bairro_estacao_vazio, diario)
    assert pd.isna(resultado.iloc[0]["precipitacao_total_semana_mm"])
    assert metricas["bairros_sem_estacao_associada"] == 1


# --------------------------------------------------------------------------
# Orquestracao ponta a ponta
# --------------------------------------------------------------------------


def test_montar_gold_chave_unica_e_sem_perda_de_casos():
    df_arbo = _df_arbo_basico()
    df_gold, metricas = montar_gold_arboviroses_clima(
        df_arbo, _gdf_bairros_2(), _df_bairro_estacao_2(),
        pd.DataFrame({"data": pd.to_datetime([]), "codigo_estacao": [], "fonte": [], "precipitacao_mm": []}),
    )
    assert metricas["chave_gold_unica"] is True
    assert list(df_gold.columns) == list(COLUNAS_GOLD_ARBOVIROSES_CLIMA)
    assert df_gold["casos"].sum() == 3  # 2 DENGUE (Boa Viagem, 202002) + 1 ZIKA (Casa Forte, 202003)


def test_montar_gold_reprodutibilidade_mesma_entrada_mesma_saida():
    df_arbo = _df_arbo_basico()
    diario = pd.DataFrame({"data": pd.to_datetime([]), "codigo_estacao": [], "fonte": [], "precipitacao_mm": []})
    df_gold1, _ = montar_gold_arboviroses_clima(df_arbo, _gdf_bairros_2(), _df_bairro_estacao_2(), diario)
    df_gold2, _ = montar_gold_arboviroses_clima(df_arbo, _gdf_bairros_2(), _df_bairro_estacao_2(), diario)
    pd.testing.assert_frame_equal(
        df_gold1.drop(columns=["_processed_at"]), df_gold2.drop(columns=["_processed_at"])
    )
