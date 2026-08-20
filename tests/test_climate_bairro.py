import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from src.silver.climate_bairro import (
    associar_clima_diario_a_bairro,
    calcular_estacao_representativa_por_bairro,
    calcular_metricas_cobertura,
    calcular_ultima_leitura_por_estacao,
    construir_pontos_representativos_bairro,
    filtrar_estacoes_elegiveis,
    montar_mapeamento_bairro_estacao,
)
from src.silver.schema_climate_bairro import (
    COLUNAS_SILVER_BAIRRO_ESTACAO,
    LIMIAR_DIAS_ESTACAO_ATIVA,
    METODO_ASSOCIACAO,
)

DATA_REFERENCIA = pd.Timestamp("2026-08-19")


def _quadrado(lon: float, lat: float, lado: float = 0.02) -> Polygon:
    return Polygon([(lon, lat), (lon + lado, lat), (lon + lado, lat + lado), (lon, lat + lado)])


def _gdf_bairros_94() -> gpd.GeoDataFrame:
    """94 bairros sintéticos numa grade, cada um um quadrado simples (centroide
    sempre dentro) — usado para os testes de cobertura/determinismo."""
    linhas = []
    lado = 0.02
    colunas = 10
    for i in range(94):
        col = i % colunas
        lin = i // colunas
        lon0 = -35.0 + col * (lado * 1.5)
        lat0 = -8.20 + lin * (lado * 1.5)
        poligono = _quadrado(lon0, lat0, lado)
        centro = poligono.centroid
        linhas.append(
            {
                "codigo_bairro": str(i + 1),
                "nome_bairro": f"BAIRRO {i + 1}",
                "centroide_lon": centro.x,
                "centroide_lat": centro.y,
                "geometry": poligono,
            }
        )
    return gpd.GeoDataFrame(pd.DataFrame(linhas), geometry="geometry", crs="EPSG:4326")


def _bairro_concavo() -> gpd.GeoDataFrame:
    """Um único bairro em forma de 'C' (côncavo) cujo centroide geométrico
    cai fora do polígono — usado para testar o fallback representative_point."""
    poligono = Polygon(
        [
            (-34.90, -8.05),
            (-34.90, -8.00),
            (-34.86, -8.00),
            (-34.86, -8.01),
            (-34.89, -8.01),
            (-34.89, -8.04),
            (-34.86, -8.04),
            (-34.86, -8.05),
        ]
    )
    centro = poligono.centroid
    assert not centro.within(poligono)  # premissa do teste: centroide cai fora
    return gpd.GeoDataFrame(
        {
            "codigo_bairro": ["C1"],
            "nome_bairro": ["BAIRRO C"],
            "centroide_lon": [centro.x],
            "centroide_lat": [centro.y],
        },
        geometry=[poligono],
        crs="EPSG:4326",
    )


def _df_estacoes_apac(n: int = 5, fonte: str = "APAC") -> pd.DataFrame:
    linhas = []
    for i in range(n):
        col = i % 10
        lin = i // 10
        lon = -35.0 + col * (0.02 * 1.5) + 0.005
        lat = -8.20 + lin * (0.02 * 1.5) + 0.005
        linhas.append(
            {
                "codigo_estacao": f"E{i}",
                "nome_estacao": f"Estacao {i}",
                "fonte": fonte,
                "latitude": lat,
                "longitude": lon,
                "altitude": None,
                "municipio": "RECIFE",
                "uf": "PE",
                "data_inicio": None,
                "data_fim": None,
            }
        )
    return pd.DataFrame(linhas)


def _df_clima_diario_ativo(codigos_estacao: list[str], data: pd.Timestamp = DATA_REFERENCIA) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data": [data] * len(codigos_estacao),
            "codigo_estacao": codigos_estacao,
            "fonte": ["APAC"] * len(codigos_estacao),
            "precipitacao_mm": [1.0] * len(codigos_estacao),
        }
    )


# --------------------------------------------------------------------------
# calcular_ultima_leitura_por_estacao
# --------------------------------------------------------------------------


def test_calcular_ultima_leitura_por_estacao_pega_data_mais_recente():
    df = pd.DataFrame(
        {
            "data": pd.to_datetime(["2026-01-01", "2026-06-15", "2025-01-01"]),
            "codigo_estacao": ["E1", "E1", "E2"],
            "fonte": ["APAC", "APAC", "APAC"],
        }
    )
    resultado = calcular_ultima_leitura_por_estacao(df)
    e1 = resultado[resultado["codigo_estacao"] == "E1"].iloc[0]
    assert e1["ultima_leitura"] == pd.Timestamp("2026-06-15")


def test_calcular_ultima_leitura_por_estacao_vazio():
    resultado = calcular_ultima_leitura_por_estacao(pd.DataFrame(columns=["data", "codigo_estacao", "fonte"]))
    assert resultado.empty


# --------------------------------------------------------------------------
# filtrar_estacoes_elegiveis
# --------------------------------------------------------------------------


def test_filtra_estacao_obsoleta_como_inelegivel():
    df_estacoes = _df_estacoes_apac(2)
    df_diario = pd.DataFrame(
        {
            "data": [DATA_REFERENCIA, pd.Timestamp("2018-01-01")],
            "codigo_estacao": ["E0", "E1"],
            "fonte": ["APAC", "APAC"],
        }
    )
    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    assert list(elegiveis["codigo_estacao"]) == ["E0"]
    assert metricas["total_excluidas"] == 1
    assert any("inativa" in motivo for motivo in metricas["motivos_exclusao"])


def test_estacao_no_limite_do_limiar_e_elegivel():
    df_estacoes = _df_estacoes_apac(1)
    data_no_limite = DATA_REFERENCIA - pd.Timedelta(days=LIMIAR_DIAS_ESTACAO_ATIVA)
    df_diario = _df_clima_diario_ativo(["E0"], data=data_no_limite)

    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert len(elegiveis) == 1
    assert metricas["total_excluidas"] == 0


def test_coordenada_invalida_torna_estacao_inelegivel():
    df_estacoes = _df_estacoes_apac(1)
    df_estacoes.loc[0, "latitude"] = 999.0
    df_diario = _df_clima_diario_ativo(["E0"])

    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert elegiveis.empty
    assert "coordenada fora do intervalo geografico valido" in metricas["motivos_exclusao"]


def test_coordenada_ausente_torna_estacao_inelegivel():
    df_estacoes = _df_estacoes_apac(1)
    df_estacoes.loc[0, "longitude"] = None
    df_diario = _df_clima_diario_ativo(["E0"])

    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert elegiveis.empty
    assert "coordenada ausente" in metricas["motivos_exclusao"]


def test_estacao_sem_nenhuma_leitura_e_inelegivel():
    df_estacoes = _df_estacoes_apac(1)
    df_diario = pd.DataFrame(columns=["data", "codigo_estacao", "fonte"])

    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert elegiveis.empty
    assert "sem leitura em silver_clima_diario" in metricas["motivos_exclusao"]


def test_filtra_apenas_fonte_apac():
    df_estacoes = pd.concat(
        [_df_estacoes_apac(1, fonte="APAC"), _df_estacoes_apac(1, fonte="INMET")], ignore_index=True
    )
    df_diario = _df_clima_diario_ativo(["E0"])

    elegiveis, _ = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert set(elegiveis["fonte"]) == {"APAC"}


# --------------------------------------------------------------------------
# construir_pontos_representativos_bairro
# --------------------------------------------------------------------------


def test_ponto_representativo_usa_centroide_quando_dentro_do_poligono():
    gdf = _gdf_bairros_94().iloc[[0]]
    pontos = construir_pontos_representativos_bairro(gdf)
    assert pontos.iloc[0]["metodo_ponto_representativo_bairro"] == "centroide"
    assert pontos.iloc[0].geometry.within(gdf.iloc[0].geometry)


def test_ponto_representativo_usa_fallback_quando_centroide_cai_fora():
    gdf = _bairro_concavo()
    pontos = construir_pontos_representativos_bairro(gdf)
    assert pontos.iloc[0]["metodo_ponto_representativo_bairro"] == "representative_point_fallback"
    assert pontos.iloc[0].geometry.within(gdf.iloc[0].geometry)


# --------------------------------------------------------------------------
# calcular_estacao_representativa_por_bairro / montar_mapeamento_bairro_estacao
# --------------------------------------------------------------------------


def test_montar_mapeamento_cobre_94_bairros_com_uma_estacao_cada():
    gdf_bairros = _gdf_bairros_94()
    df_estacoes = _df_estacoes_apac(20)
    df_diario = _df_clima_diario_ativo(list(df_estacoes["codigo_estacao"]))

    mapeamento, metricas = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    assert len(mapeamento) == 94
    assert mapeamento["codigo_bairro"].nunique() == 94  # uma unica estacao por bairro
    assert (mapeamento["distancia_km"] >= 0).all()
    assert metricas["bairros_associados"] == 94
    assert metricas["percentual_cobertura"] == 100.0


def test_mapeamento_campos_obrigatorios_do_schema():
    gdf_bairros = _gdf_bairros_94().iloc[:5]
    df_estacoes = _df_estacoes_apac(3)
    df_diario = _df_clima_diario_ativo(list(df_estacoes["codigo_estacao"]))

    mapeamento, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert list(mapeamento.columns) == list(COLUNAS_SILVER_BAIRRO_ESTACAO)
    assert (mapeamento["metodo_associacao"] == METODO_ASSOCIACAO).all()
    assert mapeamento["versao_estrategia"].notna().all()
    assert mapeamento["_gerado_em"].notna().all()


def test_estacao_selecionada_e_realmente_a_mais_proxima_entre_elegiveis():
    gdf_bairros = _gdf_bairros_94().iloc[[0]]
    bairro = gdf_bairros.iloc[0]
    ponto_bairro = Point(bairro["centroide_lon"], bairro["centroide_lat"])

    df_estacoes = pd.DataFrame(
        {
            "codigo_estacao": ["PERTO", "LONGE"],
            "nome_estacao": ["Perto", "Longe"],
            "fonte": ["APAC", "APAC"],
            "latitude": [ponto_bairro.y + 0.001, ponto_bairro.y + 5.0],
            "longitude": [ponto_bairro.x + 0.001, ponto_bairro.x + 5.0],
        }
    )
    df_diario = _df_clima_diario_ativo(["PERTO", "LONGE"])

    mapeamento, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert mapeamento.iloc[0]["codigo_estacao"] == "PERTO"


def test_estacao_obsoleta_nao_e_escolhida_mesmo_sendo_mais_proxima():
    gdf_bairros = _gdf_bairros_94().iloc[[0]]
    bairro = gdf_bairros.iloc[0]
    ponto_bairro = Point(bairro["centroide_lon"], bairro["centroide_lat"])

    df_estacoes = pd.DataFrame(
        {
            "codigo_estacao": ["PERTO_MORTA", "LONGE_ATIVA"],
            "nome_estacao": ["Perto Morta", "Longe Ativa"],
            "fonte": ["APAC", "APAC"],
            "latitude": [ponto_bairro.y + 0.001, ponto_bairro.y + 0.5],
            "longitude": [ponto_bairro.x + 0.001, ponto_bairro.x + 0.5],
        }
    )
    df_diario = pd.DataFrame(
        {
            "data": [pd.Timestamp("2018-01-01"), DATA_REFERENCIA],
            "codigo_estacao": ["PERTO_MORTA", "LONGE_ATIVA"],
            "fonte": ["APAC", "APAC"],
        }
    )

    mapeamento, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    assert mapeamento.iloc[0]["codigo_estacao"] == "LONGE_ATIVA"


def test_resultado_deterministico_entre_execucoes():
    gdf_bairros = _gdf_bairros_94()
    df_estacoes = _df_estacoes_apac(15)
    df_diario = _df_clima_diario_ativo(list(df_estacoes["codigo_estacao"]))

    mapeamento1, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)
    mapeamento2, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    pd.testing.assert_frame_equal(
        mapeamento1.drop(columns=["_gerado_em"]), mapeamento2.drop(columns=["_gerado_em"])
    )


def test_localizacao_fisica_separada_da_representatividade():
    """A estação escolhida para representar um bairro vizinho não deve ser
    marcada como fisicamente dentro dele."""
    gdf_bairros = _gdf_bairros_94().iloc[[0, 1]].reset_index(drop=True)
    bairro0 = gdf_bairros.iloc[0]

    # única estação fica fisicamente dentro do bairro 0, mas é a mais
    # próxima para os dois bairros (grade construída para isso)
    df_estacoes = pd.DataFrame(
        {
            "codigo_estacao": ["E0"],
            "nome_estacao": ["Estacao 0"],
            "fonte": ["APAC"],
            "latitude": [bairro0["centroide_lat"]],
            "longitude": [bairro0["centroide_lon"]],
        }
    )
    df_diario = _df_clima_diario_ativo(["E0"])

    mapeamento, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    linha_bairro0 = mapeamento[mapeamento["codigo_bairro"] == gdf_bairros.iloc[0]["codigo_bairro"]].iloc[0]
    linha_bairro1 = mapeamento[mapeamento["codigo_bairro"] == gdf_bairros.iloc[1]["codigo_bairro"]].iloc[0]

    assert bool(linha_bairro0["estacao_dentro_do_bairro"]) is True
    assert bool(linha_bairro1["estacao_dentro_do_bairro"]) is False
    assert linha_bairro0["codigo_estacao"] == linha_bairro1["codigo_estacao"] == "E0"


def test_montar_mapeamento_sem_estacao_elegivel_levanta_erro():
    gdf_bairros = _gdf_bairros_94().iloc[[0]]
    df_estacoes = _df_estacoes_apac(1)
    df_diario = pd.DataFrame(
        {"data": [pd.Timestamp("2018-01-01")], "codigo_estacao": ["E0"], "fonte": ["APAC"]}
    )
    with pytest.raises(ValueError):
        montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)


# --------------------------------------------------------------------------
# calcular_metricas_cobertura
# --------------------------------------------------------------------------


def test_calcular_metricas_cobertura_campos_esperados():
    gdf_bairros = _gdf_bairros_94()
    df_estacoes = _df_estacoes_apac(20)
    df_diario = _df_clima_diario_ativo(list(df_estacoes["codigo_estacao"]))
    mapeamento, _ = montar_mapeamento_bairro_estacao(gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    metricas = calcular_metricas_cobertura(mapeamento, total_bairros=94)
    for chave in (
        "distancia_km_media", "distancia_km_mediana", "distancia_km_p90", "distancia_km_p95",
        "distancia_km_maxima", "distancia_km_minima", "bairros_com_estacao_propria",
        "bairros_com_estacao_de_outro_bairro", "top10_bairros_mais_distantes", "estacoes_mais_utilizadas",
    ):
        assert chave in metricas


# --------------------------------------------------------------------------
# associar_clima_diario_a_bairro — missing values
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# multiplas fontes elegiveis (APAC + CEMADEN)
# --------------------------------------------------------------------------


def test_filtra_fontes_apac_e_cemaden_por_padrao_exclui_inmet():
    df_estacoes = pd.concat(
        [
            _df_estacoes_apac(1, fonte="APAC"),
            _df_estacoes_apac(1, fonte="CEMADEN"),
            _df_estacoes_apac(1, fonte="INMET"),
        ],
        ignore_index=True,
    )
    df_diario = pd.concat(
        [
            _df_clima_diario_ativo(["E0"], data=DATA_REFERENCIA),
            pd.DataFrame({"data": [DATA_REFERENCIA], "codigo_estacao": ["E0"], "fonte": ["CEMADEN"]}),
        ],
        ignore_index=True,
    )

    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    assert set(elegiveis["fonte"]) == {"APAC", "CEMADEN"}
    assert metricas["fontes"] == ["APAC", "CEMADEN"]


def test_codigo_estacao_colidindo_entre_fontes_nao_contamina_elegibilidade():
    """APAC e CEMADEN compartilhando o mesmo codigo_estacao textual ('100')
    -- uma ativa, outra obsoleta. A chave real e (fonte, codigo_estacao),
    nunca so codigo_estacao."""
    df_estacoes = pd.DataFrame(
        {
            "codigo_estacao": ["100", "100"],
            "nome_estacao": ["Estacao Ativa", "Estacao Obsoleta"],
            "fonte": ["APAC", "CEMADEN"],
            "latitude": [-8.0, -8.0],
            "longitude": [-34.9, -34.9],
        }
    )
    df_diario = pd.DataFrame(
        {
            "data": [DATA_REFERENCIA, pd.Timestamp("2018-01-01")],
            "codigo_estacao": ["100", "100"],
            "fonte": ["APAC", "CEMADEN"],
        }
    )

    elegiveis, metricas = filtrar_estacoes_elegiveis(df_estacoes, df_diario, data_referencia=DATA_REFERENCIA)

    assert list(elegiveis["fonte"]) == ["APAC"]
    assert metricas["total_excluidas"] == 1


def test_join_fisico_nao_colide_entre_fontes_com_mesmo_codigo_estacao():
    """calcular_estacao_representativa_por_bairro tambem usa (fonte,
    codigo_estacao) como chave -- uma estacao CEMADEN fisicamente dentro do
    bairro nao deve "vazar" estacao_dentro_do_bairro=True para uma estacao
    APAC de codigo_estacao igual mas fisicamente fora."""
    gdf_bairros = _gdf_bairros_94().iloc[[0]]
    bairro = gdf_bairros.iloc[0]

    df_estacoes = pd.DataFrame(
        {
            "codigo_estacao": ["100", "100"],
            "nome_estacao": ["Dentro (CEMADEN)", "Fora (APAC)"],
            "fonte": ["CEMADEN", "APAC"],
            # CEMADEN fisicamente dentro do bairro; APAC helipado bem longe
            "latitude": [bairro["centroide_lat"], bairro["centroide_lat"] + 5.0],
            "longitude": [bairro["centroide_lon"], bairro["centroide_lon"] + 5.0],
        }
    )

    resultado = calcular_estacao_representativa_por_bairro(gdf_bairros, df_estacoes)

    linha = resultado.iloc[0]
    assert linha["fonte"] == "CEMADEN"
    assert bool(linha["estacao_dentro_do_bairro"]) is True


def test_estrategia_a_prefere_estacao_ativa_mesmo_com_outra_fonte_mais_perto_porem_inativa():
    """Simula o cenario real do projeto: a estacao APAC mais proxima esta
    congelada (inativa), e uma estacao CEMADEN um pouco mais distante, mas
    realmente ativa, deve ser escolhida no lugar -- sem nenhuma prioridade
    hardcoded, so o filtro de atividade real."""
    gdf_bairros = _gdf_bairros_94().iloc[[0]]
    bairro = gdf_bairros.iloc[0]
    ponto_bairro = Point(bairro["centroide_lon"], bairro["centroide_lat"])

    df_estacoes = pd.DataFrame(
        {
            "codigo_estacao": ["APAC_PERTO", "CEMADEN_LONGE"],
            "nome_estacao": ["APAC Perto (congelada)", "CEMADEN Longe (ativa)"],
            "fonte": ["APAC", "CEMADEN"],
            "latitude": [ponto_bairro.y + 0.001, ponto_bairro.y + 0.05],
            "longitude": [ponto_bairro.x + 0.001, ponto_bairro.x + 0.05],
        }
    )
    df_diario = pd.DataFrame(
        {
            "data": [pd.Timestamp("2024-04-09"), DATA_REFERENCIA],
            "codigo_estacao": ["APAC_PERTO", "CEMADEN_LONGE"],
            "fonte": ["APAC", "CEMADEN"],
        }
    )

    mapeamento, _ = montar_mapeamento_bairro_estacao(
        gdf_bairros, df_estacoes, df_diario, data_referencia=DATA_REFERENCIA
    )

    assert mapeamento.iloc[0]["fonte"] == "CEMADEN"
    assert mapeamento.iloc[0]["codigo_estacao"] == "CEMADEN_LONGE"


def test_associar_clima_diario_preserva_none_e_zero():
    mapeamento = pd.DataFrame(
        {"codigo_bairro": ["1"], "nome_bairro": ["BAIRRO 1"], "codigo_estacao": ["E0"], "fonte": ["APAC"]}
    )
    diario = pd.DataFrame(
        {
            "data": [DATA_REFERENCIA, DATA_REFERENCIA + pd.Timedelta(days=1)],
            "codigo_estacao": ["E0", "E0"],
            "fonte": ["APAC", "APAC"],
            "precipitacao_mm": [None, 0.0],
        }
    )

    resultado = associar_clima_diario_a_bairro(mapeamento, diario)
    assert resultado.loc[resultado["precipitacao_mm"].isna(), "codigo_bairro"].tolist() == ["1"]
    assert (resultado.loc[resultado["precipitacao_mm"] == 0.0, "codigo_bairro"] == "1").all()
    assert resultado["precipitacao_mm"].isna().sum() == 1
    assert (resultado["precipitacao_mm"] == 0.0).sum() == 1
