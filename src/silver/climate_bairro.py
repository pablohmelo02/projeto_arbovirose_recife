"""Silver: mapeamento `bairro -> estação climática representativa`.

Implementa a Estratégia A (estação APAC elegível mais próxima), decidida em
`README.md` (seção 26) e detalhada em `src/silver/schema_climate_bairro.py`.

Este módulo reutiliza as abstrações já existentes do domínio clima/território
(`src/silver/climate_spatial.py`, `src/silver/schema_territorio.py`) — não
reimplementa ingestão, CRS ou spatial join.

Duas relações distintas, mantidas em campos separados no mesmo registro:

- `estacao_dentro_do_bairro`: a estação escolhida está fisicamente localizada
  dentro do polígono do bairro que ela representa (localização física).
- o registro inteiro (`codigo_bairro` -> `codigo_estacao`): a estação foi
  *escolhida para representar* o clima daquele bairro (representatividade).
  Uma estação pode representar vários bairros vizinhos mesmo estando
  fisicamente em só um deles (ou em nenhum, se nenhum bairro a contém).

Missing values: nunca imputados aqui. `associar_clima_diario_a_bairro` é um
merge simples — se `precipitacao_mm` está `None` em `silver_clima_diario`,
continua `None` depois do merge.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import geopandas as gpd
import pandas as pd

from src.silver.climate_spatial import (
    CRS_ARMAZENAMENTO,
    CRS_CALCULO_METRICO,
    construir_geodataframe_estacoes,
    estacoes_dentro_do_recife,
)
from src.silver.schema_climate_bairro import (
    COLUNAS_SILVER_BAIRRO_ESTACAO,
    FONTES_ELEGIVEIS,
    LIMIAR_DIAS_ESTACAO_ATIVA,
    METODO_ASSOCIACAO,
    VERSAO_ESTRATEGIA,
)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Elegibilidade de estações
# --------------------------------------------------------------------------


def _vazio_ultima_leitura() -> pd.DataFrame:
    # dtype explícito: um DataFrame vazio "solto" faria `ultima_leitura` virar
    # `object`/`float64` (todo NaN), e a subtração por Timestamp quebraria em
    # `filtrar_estacoes_elegiveis` mesmo sem nenhuma estação candidata.
    return pd.DataFrame(
        {
            "fonte": pd.Series(dtype="object"),
            "codigo_estacao": pd.Series(dtype="object"),
            "ultima_leitura": pd.Series(dtype="datetime64[ns]"),
        }
    )


def calcular_ultima_leitura_por_estacao(df_clima_diario: pd.DataFrame) -> pd.DataFrame:
    """Para cada (fonte, codigo_estacao), a data mais recente com leitura em
    `silver_clima_diario`. Base do critério de atividade — não confundir com
    `silver_estacao_climatica.data_fim`, que é sempre nulo para a APAC (a API
    não informa fim de operação, ver `schema_climate.py`)."""
    if df_clima_diario.empty:
        return _vazio_ultima_leitura()

    valido = df_clima_diario.dropna(subset=["data", "codigo_estacao"])
    if valido.empty:
        return _vazio_ultima_leitura()

    agrupado = (
        valido.groupby(["fonte", "codigo_estacao"])["data"]
        .max()
        .reset_index()
        .rename(columns={"data": "ultima_leitura"})
    )
    return agrupado


def filtrar_estacoes_elegiveis(
    df_estacoes: pd.DataFrame,
    df_clima_diario: pd.DataFrame,
    data_referencia: Optional[pd.Timestamp] = None,
    fontes: tuple[str, ...] = FONTES_ELEGIVEIS,
    limiar_dias: int = LIMIAR_DIAS_ESTACAO_ATIVA,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Filtra `silver_estacao_climatica` para as candidatas elegíveis à
    Estratégia A: fonte em `fontes`, coordenada válida, e evidência de
    atividade recente (última leitura em `silver_clima_diario` dentro de
    `limiar_dias`) — nunca a partir de metadado de cadastro (`tempo_inatividade`
    da APAC/CEMADEN não é usado aqui de propósito, só leitura real).

    `codigo_estacao` não é único entre fontes (só dentro de cada uma) — todo
    cruzamento com `silver_clima_diario` é feito pela chave composta
    (`fonte`, `codigo_estacao`), nunca só por `codigo_estacao`.

    Nenhuma estação é excluída silenciosamente: todo motivo de exclusão é
    contado em `metricas["motivos_exclusao"]`.
    """
    data_referencia = (
        pd.Timestamp(datetime.now(timezone.utc).date())
        if data_referencia is None
        else pd.Timestamp(data_referencia)
    )

    candidatas = df_estacoes[df_estacoes["fonte"].isin(fontes)].reset_index(drop=True).copy()
    total_candidatas = len(candidatas)

    ultima_leitura = calcular_ultima_leitura_por_estacao(df_clima_diario)
    ultima_leitura_fontes = ultima_leitura.loc[
        ultima_leitura["fonte"].isin(fontes), ["fonte", "codigo_estacao", "ultima_leitura"]
    ]
    candidatas = candidatas.merge(ultima_leitura_fontes, on=["fonte", "codigo_estacao"], how="left")

    motivo = pd.Series([None] * len(candidatas), dtype=object)

    sem_coordenada = candidatas["latitude"].isna() | candidatas["longitude"].isna()
    motivo[sem_coordenada & motivo.isna()] = "coordenada ausente"

    lat_invalida = candidatas["latitude"].notna() & (candidatas["latitude"].abs() > 90)
    lon_invalida = candidatas["longitude"].notna() & (candidatas["longitude"].abs() > 180)
    motivo[(lat_invalida | lon_invalida) & motivo.isna()] = (
        "coordenada fora do intervalo geografico valido"
    )

    sem_leitura = candidatas["ultima_leitura"].isna()
    motivo[sem_leitura & motivo.isna()] = "sem leitura em silver_clima_diario"

    dias_desde_ultima_leitura = (data_referencia - candidatas["ultima_leitura"]).dt.days
    obsoleta = candidatas["ultima_leitura"].notna() & (dias_desde_ultima_leitura > limiar_dias)
    motivo[obsoleta & motivo.isna()] = (
        f"ultima leitura ha mais de {limiar_dias} dias (estacao considerada inativa)"
    )

    elegivel = motivo.isna()
    df_elegivel = candidatas.loc[elegivel].reset_index(drop=True)

    motivos_exclusao = {
        str(m): int(c) for m, c in motivo[~elegivel].value_counts().items()
    }
    metricas = {
        "fontes": list(fontes),
        "total_candidatas": total_candidatas,
        "total_elegiveis": len(df_elegivel),
        "total_excluidas": int((~elegivel).sum()),
        "motivos_exclusao": motivos_exclusao,
        "data_referencia": data_referencia.date().isoformat(),
        "limiar_dias_estacao_ativa": limiar_dias,
    }
    return df_elegivel, metricas


# --------------------------------------------------------------------------
# Ponto representativo do bairro
# --------------------------------------------------------------------------


def construir_pontos_representativos_bairro(gdf_bairros: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Ponto usado para medir distância bairro -> estação.

    Regra: usa o `centroide_lat`/`centroide_lon` já calculado por
    `silver/territorio.py` (não recalcula, para não ter duas fontes de
    verdade) **desde que o centroide caia dentro do próprio polígono**.
    Polígonos complexos/côncavos podem ter centroide geométrico fora dos
    seus limites (achado conhecido de geometria) — nesses casos, usa
    `representative_point()` (sempre garantidamente dentro do polígono,
    calculado em CRS métrico) só para o(s) bairro(s) afetado(s), e marca o
    método usado em `metodo_ponto_representativo_bairro` para transparência
    no relatório.
    """
    gdf = gdf_bairros.reset_index(drop=True)

    centroides = gpd.GeoSeries(
        gpd.points_from_xy(gdf["centroide_lon"], gdf["centroide_lat"]), crs=CRS_ARMAZENAMENTO
    )
    centroide_dentro = centroides.within(gdf.geometry.reset_index(drop=True)).to_numpy()

    geometria_metrica = gdf.geometry.to_crs(CRS_CALCULO_METRICO)
    rep_point_metrico = geometria_metrica.representative_point()
    rep_point_wgs84 = gpd.GeoSeries(rep_point_metrico.to_numpy(), crs=CRS_CALCULO_METRICO).to_crs(
        CRS_ARMAZENAMENTO
    )

    geometria_final = [
        centroide if dentro else representativo
        for centroide, representativo, dentro in zip(
            centroides.to_numpy(), rep_point_wgs84.to_numpy(), centroide_dentro
        )
    ]
    metodo = ["centroide" if dentro else "representative_point_fallback" for dentro in centroide_dentro]

    return gpd.GeoDataFrame(
        {
            "codigo_bairro": gdf["codigo_bairro"].to_numpy(),
            "nome_bairro": gdf["nome_bairro"].to_numpy(),
            "metodo_ponto_representativo_bairro": metodo,
        },
        geometry=geometria_final,
        crs=CRS_ARMAZENAMENTO,
    )


# --------------------------------------------------------------------------
# Estação representativa por bairro (Estratégia A)
# --------------------------------------------------------------------------


def calcular_estacao_representativa_por_bairro(
    gdf_bairros: gpd.GeoDataFrame,
    df_estacoes_elegiveis: pd.DataFrame,
) -> pd.DataFrame:
    """Para cada bairro, a estação elegível mais próxima do seu ponto
    representativo — distância medida em CRS métrico (SIRGAS2000/UTM 25S,
    o mesmo já usado em `climate_spatial.py`/`territorio.py`), nunca em graus.
    """
    if df_estacoes_elegiveis.empty:
        raise ValueError(
            "Nenhuma estacao elegivel disponivel para montar o mapeamento bairro-estacao. "
            "Verifique filtrar_estacoes_elegiveis() e o LIMIAR_DIAS_ESTACAO_ATIVA."
        )

    pontos_bairro = construir_pontos_representativos_bairro(gdf_bairros)
    gdf_estacoes = construir_geodataframe_estacoes(df_estacoes_elegiveis)

    join_fisico = estacoes_dentro_do_recife(gdf_estacoes, gdf_bairros)
    # chave composta (fonte, codigo_estacao): codigo_estacao nao e unico entre
    # fontes (ex.: APAC e CEMADEN podem compartilhar o mesmo codigo textual
    # para estacoes fisicamente diferentes) -- indexar so por codigo_estacao
    # colidiria silenciosamente entre fontes.
    bairro_fisico_por_estacao = (
        join_fisico.dropna(subset=["codigo_bairro"])
        .drop_duplicates(subset=["fonte", "codigo_estacao"])
        .set_index(["fonte", "codigo_estacao"])["codigo_bairro"]
    )

    pontos_metrico = pontos_bairro.to_crs(CRS_CALCULO_METRICO).reset_index(drop=True)
    estacoes_metrico = gdf_estacoes.to_crs(CRS_CALCULO_METRICO).reset_index(drop=True)

    linhas = []
    for _, bairro in pontos_metrico.iterrows():
        distancias = estacoes_metrico.geometry.distance(bairro.geometry)
        idx_min = distancias.idxmin()
        estacao = estacoes_metrico.loc[idx_min]
        distancia_km = round(float(distancias.loc[idx_min]) / 1000, 3)
        bairro_fisico_estacao = bairro_fisico_por_estacao.get(
            (estacao["fonte"], estacao["codigo_estacao"])
        )

        linhas.append(
            {
                "codigo_bairro": bairro["codigo_bairro"],
                "nome_bairro": bairro["nome_bairro"],
                "codigo_estacao": estacao["codigo_estacao"],
                "nome_estacao": estacao.get("nome_estacao"),
                "fonte": estacao["fonte"],
                "latitude_estacao": estacao["latitude"],
                "longitude_estacao": estacao["longitude"],
                "distancia_km": distancia_km,
                "estacao_dentro_do_bairro": bool(bairro_fisico_estacao == bairro["codigo_bairro"]),
                "metodo_ponto_representativo_bairro": bairro["metodo_ponto_representativo_bairro"],
            }
        )

    return pd.DataFrame(linhas)


def montar_mapeamento_bairro_estacao(
    gdf_bairros: gpd.GeoDataFrame,
    df_estacoes: pd.DataFrame,
    df_clima_diario: pd.DataFrame,
    data_referencia: Optional[pd.Timestamp] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Orquestra a Estratégia A ponta a ponta: elegibilidade -> estação mais
    próxima por bairro -> contrato canônico + métricas reais de cobertura."""
    processado_em = _agora()

    df_elegiveis, metricas_elegibilidade = filtrar_estacoes_elegiveis(
        df_estacoes, df_clima_diario, data_referencia=data_referencia
    )

    df_mapeamento = calcular_estacao_representativa_por_bairro(gdf_bairros, df_elegiveis)
    df_mapeamento["metodo_associacao"] = METODO_ASSOCIACAO
    df_mapeamento["versao_estrategia"] = VERSAO_ESTRATEGIA
    df_mapeamento["_gerado_em"] = processado_em
    df_mapeamento = df_mapeamento[list(COLUNAS_SILVER_BAIRRO_ESTACAO)]

    metricas = {
        "elegibilidade": metricas_elegibilidade,
        **calcular_metricas_cobertura(df_mapeamento, total_bairros=len(gdf_bairros)),
    }
    return df_mapeamento, metricas


def calcular_metricas_cobertura(df_mapeamento: pd.DataFrame, total_bairros: int) -> dict[str, Any]:
    """Métricas reais de cobertura/distância da Estratégia A — nunca inventadas,
    sempre calculadas a partir do `df_mapeamento` produzido pelo pipeline."""
    if df_mapeamento.empty:
        return {
            "total_bairros": total_bairros,
            "bairros_associados": 0,
            "percentual_cobertura": 0.0,
            "estacoes_distintas_utilizadas": 0,
        }

    distancias = df_mapeamento["distancia_km"]
    return {
        "total_bairros": total_bairros,
        "bairros_associados": len(df_mapeamento),
        "percentual_cobertura": round(100 * len(df_mapeamento) / total_bairros, 2)
        if total_bairros
        else 0.0,
        "estacoes_distintas_utilizadas": int(df_mapeamento["codigo_estacao"].nunique()),
        "distancia_km_media": round(float(distancias.mean()), 3),
        "distancia_km_mediana": round(float(distancias.median()), 3),
        "distancia_km_p90": round(float(distancias.quantile(0.90)), 3),
        "distancia_km_p95": round(float(distancias.quantile(0.95)), 3),
        "distancia_km_maxima": round(float(distancias.max()), 3),
        "distancia_km_minima": round(float(distancias.min()), 3),
        "bairros_com_estacao_propria": int(df_mapeamento["estacao_dentro_do_bairro"].sum()),
        "bairros_com_estacao_de_outro_bairro": int((~df_mapeamento["estacao_dentro_do_bairro"]).sum()),
        "top10_bairros_mais_distantes": (
            df_mapeamento.sort_values("distancia_km", ascending=False)
            [["codigo_bairro", "nome_bairro", "codigo_estacao", "distancia_km"]]
            .head(10)
            .to_dict(orient="records")
        ),
        "estacoes_mais_utilizadas": (
            df_mapeamento["codigo_estacao"].value_counts().head(10).to_dict()
        ),
    }


# --------------------------------------------------------------------------
# Integração conceitual com silver_clima_diario (não persiste tabela nova)
# --------------------------------------------------------------------------


def associar_clima_diario_a_bairro(
    df_mapeamento: pd.DataFrame, df_clima_diario: pd.DataFrame
) -> pd.DataFrame:
    """Junta o mapeamento bairro->estação com `silver_clima_diario` pela
    chave (`codigo_estacao`, `fonte`) — um merge simples, sem imputação.
    `precipitacao_mm` ausente continua `None` depois do merge (nunca vira
    `0`). Não persiste uma tabela nova: é uma view de conveniência para
    validação/uso futuro pela Gold, mantendo o mapeamento e o clima diário
    como fontes de verdade separadas e desacopladas (sem duplicar metadados
    de estação em cada linha climática)."""
    chave = df_mapeamento[["codigo_bairro", "nome_bairro", "codigo_estacao", "fonte"]]
    return chave.merge(df_clima_diario, on=["codigo_estacao", "fonte"], how="left")
