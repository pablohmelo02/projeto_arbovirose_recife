"""Transformação Silver do domínio Território (`silver_bairro_geo`).

Lê um GeoDataFrame bruto (a feature collection de bairros) e produz
`(silver_valido, rejeitados, metricas)` segundo o contrato canônico de
`schema_territorio.py`. Não agrega e não faz join com arboviroses — os
domínios ficam independentes nesta etapa; a integração é responsabilidade da
Gold (fora do escopo atual).

Geometria inválida NUNCA é corrigida automaticamente (sem `make_valid()`):
é rejeitada e reportada em `_rejected`, para não mascarar um problema da
fonte. Se essa estratégia mudar no futuro, a decisão e a contagem de
correções devem ficar explícitas nas métricas (`geometrias_corrigidas_automaticamente`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import geopandas as gpd
import pandas as pd

from src.silver.quality import limpar_codigo, limpar_texto
from src.silver.schema_territorio import (
    COLUNAS_SILVER_BAIRRO_GEO,
    CRS_ARMAZENAMENTO,
    CRS_CALCULO_METRICO,
    CRS_ORIGINAL,
)


def transformar_bairro_geo(
    gdf_bruto: gpd.GeoDataFrame,
    resource_id: str,
    ingestion_run_id: str,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, Any]]:
    """Transforma o GeoDataFrame bruto de bairros em `(silver_valido, rejeitados, metricas)`."""
    processado_em = datetime.now(timezone.utc).isoformat()
    linhas_lidas = len(gdf_bruto)

    if gdf_bruto.crs is None:
        crs_detectado = CRS_ORIGINAL
        gdf = gdf_bruto.set_crs(CRS_ORIGINAL)
    else:
        crs_detectado = str(gdf_bruto.crs)
        gdf = gdf_bruto.to_crs(CRS_ORIGINAL)

    df = pd.DataFrame(
        {
            "codigo_bairro": gdf["CBAIRRCODI"].map(limpar_codigo),
            "nome_bairro": gdf["EBAIRRNOME"].map(limpar_texto),
            "nome_bairro_oficial": gdf["EBAIRRNOMEOF"].map(limpar_codigo),
            "codigo_rpa": gdf["CRPAAACODI"].map(limpar_codigo),
            "codigo_microrregiao": gdf["CMICROCODI"].map(limpar_codigo),
        }
    )
    gdf_trabalho = gpd.GeoDataFrame(df, geometry=gdf.geometry.values, crs=CRS_ORIGINAL)

    # Área e centroide NUNCA são calculados direto em graus (EPSG:4326) —
    # reprojeta para um CRS métrico (SIRGAS2000/UTM 25S) antes de calcular.
    geometria_metrica = gdf_trabalho.geometry.to_crs(CRS_CALCULO_METRICO)
    gdf_trabalho["area_km2"] = geometria_metrica.area / 1_000_000

    centroide_metrico = geometria_metrica.centroid
    centroide_wgs84 = gpd.GeoSeries(centroide_metrico, crs=CRS_CALCULO_METRICO).to_crs(
        CRS_ARMAZENAMENTO
    )
    gdf_trabalho["centroide_lon"] = centroide_wgs84.x.to_numpy()
    gdf_trabalho["centroide_lat"] = centroide_wgs84.y.to_numpy()
    gdf_trabalho["crs"] = CRS_ARMAZENAMENTO

    gdf_trabalho["_source_resource_id"] = resource_id
    gdf_trabalho["_ingestion_run_id"] = ingestion_run_id
    gdf_trabalho["_processed_at"] = processado_em

    # --- Data Quality espacial: toda rejeição é explícita, nada é corrigido silenciosamente ---
    motivo_linha = pd.Series([None] * len(gdf_trabalho), dtype=object)

    geometria_nula = gdf_trabalho.geometry.isna()
    motivo_linha[geometria_nula & motivo_linha.isna()] = "geometry nula"

    geometria_invalida = ~geometria_nula & ~gdf_trabalho.geometry.is_valid
    motivo_linha[geometria_invalida & motivo_linha.isna()] = (
        "geometry invalida (nao corrigida automaticamente, ver decisao no docstring)"
    )

    sem_codigo = gdf_trabalho["codigo_bairro"].isna()
    motivo_linha[sem_codigo & motivo_linha.isna()] = "codigo_bairro ausente"

    duplicado = gdf_trabalho["codigo_bairro"].duplicated() & gdf_trabalho["codigo_bairro"].notna()
    motivo_linha[duplicado & motivo_linha.isna()] = "codigo_bairro duplicado"

    sem_nome = gdf_trabalho["nome_bairro"].isna()
    motivo_linha[sem_nome & motivo_linha.isna()] = "nome_bairro vazio"

    area_invalida = gdf_trabalho["area_km2"].isna() | (gdf_trabalho["area_km2"] <= 0)
    motivo_linha[area_invalida & motivo_linha.isna()] = "area_km2 invalida (<= 0)"

    latitude_invalida = gdf_trabalho["centroide_lat"].abs() > 90
    longitude_invalida = gdf_trabalho["centroide_lon"].abs() > 180
    motivo_linha[(latitude_invalida | longitude_invalida) & motivo_linha.isna()] = (
        "centroide fora do intervalo geografico valido"
    )

    rejeitar = motivo_linha.notna()

    colunas_negocio = [c for c in COLUNAS_SILVER_BAIRRO_GEO if c != "geometry"]
    gdf_valido = gpd.GeoDataFrame(
        gdf_trabalho.loc[~rejeitar, colunas_negocio].reset_index(drop=True),
        geometry=gdf_trabalho.loc[~rejeitar, "geometry"].reset_index(drop=True),
        crs=CRS_ARMAZENAMENTO,
    )
    gdf_rejeitado = gdf_trabalho.loc[rejeitar].copy()
    gdf_rejeitado["_motivo_rejeicao"] = motivo_linha[rejeitar]

    motivos_rejeicao = {
        motivo: int(contagem)
        for motivo, contagem in motivo_linha[rejeitar].value_counts().items()
    }

    metricas = {
        "linhas_lidas": linhas_lidas,
        "linhas_validas": len(gdf_valido),
        "linhas_rejeitadas": int(rejeitar.sum()),
        "motivos_rejeicao": motivos_rejeicao,
        "crs_original_detectado": crs_detectado,
        "crs_calculo": CRS_CALCULO_METRICO,
        "crs_armazenamento": CRS_ARMAZENAMENTO,
        "geometrias_invalidas_encontradas": int(geometria_invalida.sum()),
        "geometrias_corrigidas_automaticamente": 0,
    }

    return gdf_valido, gdf_rejeitado, metricas
