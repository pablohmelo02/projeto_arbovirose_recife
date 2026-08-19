"""Análise espacial de cobertura: `silver_estacao_climatica` × `silver_bairro_geo`.

Responde: quais estações caem dentro do Recife, quais bairros têm estação,
quais não têm, e qual a distância do centroide de cada bairro até a estação
mais próxima. **Não atribui clima de estação a bairro** — isso é uma decisão
de modelagem para uma etapa futura (Gold), não implementada aqui.
"""
from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd

CRS_ARMAZENAMENTO = "EPSG:4326"
CRS_CALCULO_METRICO = "EPSG:31985"  # SIRGAS 2000 / UTM zone 25S — mesmo usado em territorio.py


def construir_geodataframe_estacoes(df_estacoes: pd.DataFrame) -> gpd.GeoDataFrame:
    """Converte `silver_estacao_climatica` (tabular) num GeoDataFrame de pontos.

    Estações sem coordenada válida são excluídas da análise espacial (não
    têm como participar de um join geométrico) — quantas foram excluídas é
    reportado por quem chama, não escondido.
    """
    df = df_estacoes.dropna(subset=["latitude", "longitude"]).copy()
    geometria = gpd.points_from_xy(df["longitude"], df["latitude"])
    return gpd.GeoDataFrame(df, geometry=geometria, crs=CRS_ARMAZENAMENTO)


def estacoes_dentro_do_recife(
    gdf_estacoes: gpd.GeoDataFrame, gdf_bairros: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Para cada estação, acha o bairro que a contém (nulo se estiver fora do Recife)."""
    return gpd.sjoin(
        gdf_estacoes,
        gdf_bairros[["codigo_bairro", "nome_bairro", "geometry"]],
        how="left",
        predicate="within",
        lsuffix="estacao",
        rsuffix="bairro",
    )


def calcular_cobertura_bairros(
    join_resultado: gpd.GeoDataFrame, gdf_bairros: gpd.GeoDataFrame
) -> dict[str, Any]:
    """Quantos bairros têm ao menos 1 estação dentro deles, e quais não têm."""
    bairros_com_estacao = set(join_resultado["codigo_bairro"].dropna())
    todos_bairros = set(gdf_bairros["codigo_bairro"])
    sem_estacao = todos_bairros - bairros_com_estacao

    return {
        "total_bairros": len(todos_bairros),
        "bairros_com_estacao": sorted(bairros_com_estacao),
        "bairros_sem_estacao": sorted(sem_estacao),
        "quantidade_bairros_com_estacao": len(bairros_com_estacao),
        "quantidade_bairros_sem_estacao": len(sem_estacao),
    }


def calcular_estacao_mais_proxima_por_bairro(
    gdf_bairros: gpd.GeoDataFrame, gdf_estacoes: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Para cada bairro, a distância (km) do seu centroide até a estação mais próxima.

    Usa `centroide_lat`/`centroide_lon` já calculados por `silver/territorio.py`
    (não recalcula centroide aqui, para não ter duas fontes de verdade) e
    mede a distância em CRS métrico (SIRGAS2000/UTM 25S) — nunca em graus.
    """
    if gdf_estacoes.empty:
        return pd.DataFrame(
            columns=["codigo_bairro", "nome_bairro", "estacao_mais_proxima", "fonte_estacao", "distancia_km"]
        )

    centroides = gpd.GeoDataFrame(
        gdf_bairros[["codigo_bairro", "nome_bairro"]],
        geometry=gpd.points_from_xy(gdf_bairros["centroide_lon"], gdf_bairros["centroide_lat"]),
        crs=CRS_ARMAZENAMENTO,
    ).to_crs(CRS_CALCULO_METRICO)

    estacoes_metrico = gdf_estacoes.to_crs(CRS_CALCULO_METRICO).reset_index(drop=True)

    linhas = []
    for _, centroide in centroides.iterrows():
        distancias = estacoes_metrico.geometry.distance(centroide.geometry)
        idx_min = distancias.idxmin()
        estacao = estacoes_metrico.loc[idx_min]
        linhas.append(
            {
                "codigo_bairro": centroide["codigo_bairro"],
                "nome_bairro": centroide["nome_bairro"],
                "estacao_mais_proxima": estacao["codigo_estacao"],
                "fonte_estacao": estacao["fonte"],
                "distancia_km": round(distancias.loc[idx_min] / 1000, 3),
            }
        )

    return pd.DataFrame(linhas)
