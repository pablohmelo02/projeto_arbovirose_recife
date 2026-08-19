import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.silver.climate_spatial import (
    calcular_cobertura_bairros,
    calcular_estacao_mais_proxima_por_bairro,
    construir_geodataframe_estacoes,
    estacoes_dentro_do_recife,
)


def _quadrado(lon: float, lat: float, lado: float = 0.02) -> Polygon:
    return Polygon([(lon, lat), (lon + lado, lat), (lon + lado, lat + lado), (lon, lat + lado)])


def _gdf_bairros() -> gpd.GeoDataFrame:
    # bairro A tem uma estação dentro; bairro B não tem nenhuma
    return gpd.GeoDataFrame(
        {
            "codigo_bairro": ["1", "2"],
            "nome_bairro": ["BAIRRO A", "BAIRRO B"],
            "centroide_lon": [-34.90 + 0.01, -34.80 + 0.01],
            "centroide_lat": [-8.05 + 0.01, -8.10 + 0.01],
        },
        geometry=[_quadrado(-34.90, -8.05), _quadrado(-34.80, -8.10)],
        crs="EPSG:4326",
    )


def _df_estacoes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_estacao": ["E1", "E2", "E3"],
            "fonte": ["APAC", "APAC", "INMET"],
            "latitude": [-8.05 + 0.005, -7.50, None],
            "longitude": [-34.90 + 0.005, -35.00, None],
        }
    )


def test_construir_geodataframe_estacoes_ignora_sem_coordenada():
    gdf = construir_geodataframe_estacoes(_df_estacoes())
    assert len(gdf) == 2  # E3 (sem lat/lon) foi excluída
    assert gdf.crs.to_string() == "EPSG:4326"


def test_estacoes_dentro_do_recife_identifica_bairro_correto():
    gdf_estacoes = construir_geodataframe_estacoes(_df_estacoes())
    resultado = estacoes_dentro_do_recife(gdf_estacoes, _gdf_bairros())

    dentro = resultado[resultado["codigo_bairro"].notna()]
    assert len(dentro) == 1
    assert dentro.iloc[0]["codigo_bairro"] == "1"

    fora = resultado[resultado["codigo_bairro"].isna()]
    assert len(fora) == 1  # E2, que fica bem longe dos dois bairros


def test_calcular_cobertura_bairros():
    gdf_estacoes = construir_geodataframe_estacoes(_df_estacoes())
    resultado = estacoes_dentro_do_recife(gdf_estacoes, _gdf_bairros())
    cobertura = calcular_cobertura_bairros(resultado, _gdf_bairros())

    assert cobertura["quantidade_bairros_com_estacao"] == 1
    assert cobertura["quantidade_bairros_sem_estacao"] == 1
    assert cobertura["bairros_com_estacao"] == ["1"]
    assert cobertura["bairros_sem_estacao"] == ["2"]


def test_calcular_estacao_mais_proxima_por_bairro_usa_crs_metrico():
    gdf_estacoes = construir_geodataframe_estacoes(_df_estacoes())
    distancias = calcular_estacao_mais_proxima_por_bairro(_gdf_bairros(), gdf_estacoes)

    assert len(distancias) == 2
    assert (distancias["distancia_km"] >= 0).all()
    # bairro 1 tem a estação E1 bem perto (dentro do próprio bairro)
    linha_bairro_1 = distancias[distancias["codigo_bairro"] == "1"].iloc[0]
    assert linha_bairro_1["distancia_km"] < 2


def test_calcular_estacao_mais_proxima_sem_estacoes_retorna_vazio():
    gdf_vazio = construir_geodataframe_estacoes(pd.DataFrame({"codigo_estacao": [], "fonte": [], "latitude": [], "longitude": []}))
    distancias = calcular_estacao_mais_proxima_por_bairro(_gdf_bairros(), gdf_vazio)
    assert distancias.empty
