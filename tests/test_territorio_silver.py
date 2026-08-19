import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from src.silver.territorio import transformar_bairro_geo


def _quadrado_perto_do_recife(lon: float = -34.9, lat: float = -8.05, lado: float = 0.01) -> Polygon:
    return Polygon(
        [
            (lon, lat),
            (lon + lado, lat),
            (lon + lado, lat + lado),
            (lon, lat + lado),
        ]
    )


def _poligono_invalido() -> Polygon:
    return Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])


def _gdf_bruto(**overrides) -> gpd.GeoDataFrame:
    dados = {
        "CBAIRRCODI": [1, 2],
        "EBAIRRNOME": ["BAIRRO A", "BAIRRO B"],
        "EBAIRRNOMEOF": ["Bairro A", "Bairro B"],
        "CRPAAACODI": [1, 2],
        "CMICROCODI": [1, 1],
    }
    dados.update(overrides)
    geometrias = dados.pop(
        "geometry", [_quadrado_perto_do_recife(-34.9), _quadrado_perto_do_recife(-34.8)]
    )
    return gpd.GeoDataFrame(dados, geometry=geometrias, crs="EPSG:4326")


def test_transformar_bairro_geo_caso_valido():
    gdf_valido, gdf_rejeitado, metricas = transformar_bairro_geo(_gdf_bruto(), "res-1", "run-1")

    assert metricas["linhas_lidas"] == 2
    assert metricas["linhas_validas"] == 2
    assert metricas["linhas_rejeitadas"] == 0
    assert gdf_rejeitado.empty

    assert gdf_valido.crs.to_string() == "EPSG:4326"
    assert list(gdf_valido["codigo_bairro"]) == ["1", "2"]
    assert list(gdf_valido["nome_bairro"]) == ["BAIRRO A", "BAIRRO B"]
    assert list(gdf_valido["nome_bairro_oficial"]) == ["Bairro A", "Bairro B"]

    # área de um quadrado de ~0.01 grau perto do Recife deve dar uma fração
    # pequena e positiva de km² (não zero, não um valor absurdo)
    assert (gdf_valido["area_km2"] > 0).all()
    assert (gdf_valido["area_km2"] < 5).all()

    # o centroide de um quadrado deve cair dentro dos limites do próprio quadrado
    linha = gdf_valido.iloc[0]
    assert -34.9 <= linha["centroide_lon"] <= -34.89
    assert -8.05 <= linha["centroide_lat"] <= -8.04


def test_transformar_bairro_geo_crs_ausente_assume_4326():
    gdf = _gdf_bruto()
    gdf_sem_crs = gpd.GeoDataFrame(gdf.drop(columns="geometry"), geometry=gdf.geometry.to_numpy())
    assert gdf_sem_crs.crs is None

    _, _, metricas = transformar_bairro_geo(gdf_sem_crs, "res-1", "run-1")
    assert metricas["crs_original_detectado"] == "EPSG:4326"


def test_transformar_bairro_geo_rejeita_geometria_invalida():
    gdf = _gdf_bruto(geometry=[_quadrado_perto_do_recife(-34.9), _poligono_invalido()])
    gdf_valido, gdf_rejeitado, metricas = transformar_bairro_geo(gdf, "res-1", "run-1")

    assert metricas["linhas_validas"] == 1
    assert metricas["linhas_rejeitadas"] == 1
    assert metricas["geometrias_invalidas_encontradas"] == 1
    assert metricas["geometrias_corrigidas_automaticamente"] == 0
    assert "invalida" in gdf_rejeitado.iloc[0]["_motivo_rejeicao"]


def test_transformar_bairro_geo_rejeita_geometria_nula():
    gdf = _gdf_bruto()
    gdf.loc[1, "geometry"] = None

    _, gdf_rejeitado, metricas = transformar_bairro_geo(gdf, "res-1", "run-1")

    assert metricas["linhas_rejeitadas"] == 1
    assert gdf_rejeitado.iloc[0]["_motivo_rejeicao"] == "geometry nula"


def test_transformar_bairro_geo_rejeita_codigo_ausente():
    gdf = _gdf_bruto(CBAIRRCODI=[1, None])
    _, gdf_rejeitado, metricas = transformar_bairro_geo(gdf, "res-1", "run-1")

    assert metricas["linhas_rejeitadas"] == 1
    assert gdf_rejeitado.iloc[0]["_motivo_rejeicao"] == "codigo_bairro ausente"


def test_transformar_bairro_geo_rejeita_codigo_duplicado():
    gdf = _gdf_bruto(CBAIRRCODI=[1, 1])
    gdf_valido, gdf_rejeitado, metricas = transformar_bairro_geo(gdf, "res-1", "run-1")

    assert metricas["linhas_validas"] == 1
    assert metricas["linhas_rejeitadas"] == 1
    assert gdf_rejeitado.iloc[0]["_motivo_rejeicao"] == "codigo_bairro duplicado"


def test_transformar_bairro_geo_rejeita_nome_vazio():
    gdf = _gdf_bruto(EBAIRRNOME=["BAIRRO A", "   "])
    _, gdf_rejeitado, metricas = transformar_bairro_geo(gdf, "res-1", "run-1")

    assert metricas["linhas_rejeitadas"] == 1
    assert gdf_rejeitado.iloc[0]["_motivo_rejeicao"] == "nome_bairro vazio"


def test_transformar_bairro_geo_preserva_lineage():
    gdf_valido, _, _ = transformar_bairro_geo(_gdf_bruto(), "res-xyz", "run-abc")
    assert (gdf_valido["_source_resource_id"] == "res-xyz").all()
    assert (gdf_valido["_ingestion_run_id"] == "run-abc").all()
    assert gdf_valido["_processed_at"].notna().all()
