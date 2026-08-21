"""Transformação Silver da camada climática em grade (reanálise).

Funções puras (DataFrame in / DataFrame out, sem I/O e sem rede) — a
orquestração/I-O vive em `src/silver/pipeline_climate_grade.py` e a
ingestão em `src/ingestion/gridded_climate_ingestion.py`, seguindo o mesmo
desenho já usado para INMET/APAC/CEMADEN.

Regras herdadas sem exceção:

- `precipitacao_mm` ausente é `None`, nunca `0` (CLAUDE.md §5).
- Nenhuma linha é descartada em silêncio: toda rejeição é contada por
  motivo em `metricas["motivos_rejeicao"]`.
- Chave composta `(grade, celula_id, data)` — `celula_id` sozinho não é
  chave (ver `schema_climate_grade.py`).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.silver.schema_climate_grade import (
    CHAVE_SILVER_CLIMA_GRADE_DIARIO,
    COLUNAS_SILVER_BAIRRO_CELULA_GRADE,
    COLUNAS_SILVER_CLIMA_GRADE_DIARIO,
    LIMITES_PLAUSIVEIS,
    MAPA_VARIAVEIS_API,
    METODO_ASSOCIACAO_GRADE,
    RESOLUCAO_GRAUS_POR_GRADE,
    VARIAVEIS_POR_GRADE,
    VERSAO_SCHEMA_CLIMA_GRADE,
)

logger = logging.getLogger(__name__)

RAIO_TERRA_KM = 6371.0088


def identificador_celula(latitude: float, longitude: float) -> str:
    """Identificador estável de célula a partir das coordenadas que o
    provedor devolve (que já são o centro da célula, não o ponto pedido).
    4 casas decimais: suficiente para distinguir células de 0,10 grau sem
    criar identificadores diferentes por ruído de ponto flutuante."""
    return f"{latitude:.4f}_{longitude:.4f}"


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância de grande círculo (Haversine) em km.

    Usada só para reportar quão longe o centroide do bairro está do centro
    da célula que o cobre — é um número de transparência, não entra em
    nenhum cálculo de valor climático. Não usa `EPSG:31985` (como a camada
    de estações) porque aqui não há geometria envolvida, apenas dois pontos.
    """
    lat1_r, lon1_r, lat2_r, lon2_r = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return float(2 * RAIO_TERRA_KM * np.arcsin(np.sqrt(a)))


def _iterar_pontos(payload: Any) -> Iterable[dict]:
    """A API devolve um objeto para 1 ponto e uma lista para N pontos."""
    return payload if isinstance(payload, list) else [payload]


def extrair_series_diarias_grade(conteudo: bytes, grade: str) -> pd.DataFrame:
    """Converte o JSON bruto do provedor numa tabela longa
    `(grade, celula_id, latitude_celula, longitude_celula, data, <variáveis>)`.

    Só as variáveis que `VARIAVEIS_POR_GRADE[grade]` declara são lidas —
    uma variável que o provedor devolva a mais é ignorada (não vira coluna
    surpresa na Silver), e uma que falte levanta `ValueError` (schema drift
    não passa silenciosamente).
    """
    if grade not in VARIAVEIS_POR_GRADE:
        raise ValueError(f"grade desconhecida: {grade!r}")

    payload = json.loads(conteudo.decode("utf-8"))
    variaveis_canonicas = VARIAVEIS_POR_GRADE[grade]
    api_por_canonica = {v: k for k, v in MAPA_VARIAVEIS_API.items()}

    linhas: list[dict] = []
    for item in _iterar_pontos(payload):
        diario = item.get("daily") or {}
        datas = diario.get("time")
        if not datas:
            continue
        lat = float(item["latitude"])
        lon = float(item["longitude"])
        cid = identificador_celula(lat, lon)

        series = {}
        for canonica in variaveis_canonicas:
            nome_api = api_por_canonica[canonica]
            if nome_api not in diario:
                raise ValueError(
                    f"variável {nome_api!r} ausente na resposta da grade {grade!r} "
                    "(schema drift do provedor)"
                )
            series[canonica] = diario[nome_api]

        for i, data_iso in enumerate(datas):
            linha = {
                "grade": grade,
                "celula_id": cid,
                "latitude_celula": lat,
                "longitude_celula": lon,
                "data": data_iso,
            }
            for canonica in variaveis_canonicas:
                valor = series[canonica][i]
                # `None` do provedor permanece `None` -- nunca 0.
                linha[canonica] = None if valor is None else float(valor)
            linhas.append(linha)

    return pd.DataFrame(linhas)


def normalizar_clima_grade_diario(df_bruto: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Valida domínio/tipos, remove duplicatas de chave e devolve a Silver
    diária no contrato de `COLUNAS_SILVER_CLIMA_GRADE_DIARIO`.

    Deduplicação: janelas de execuções sucessivas se sobrepõem no tempo
    (igual ao CEMADEN); em conflito a linha **mais recentemente ingerida**
    vence — por isso a ordem de entrada é preservada e `keep="last"`.
    """
    motivos: dict[str, int] = {}
    linhas_antes = len(df_bruto)

    if df_bruto.empty:
        vazio = pd.DataFrame(columns=list(COLUNAS_SILVER_CLIMA_GRADE_DIARIO))
        return vazio, {
            "linhas_antes": 0,
            "linhas_validas": 0,
            "duplicatas_removidas": 0,
            "motivos_rejeicao": {},
            "celulas_distintas": 0,
            "data_minima": None,
            "data_maxima": None,
        }

    df = df_bruto.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date

    sem_data = df["data"].isna()
    if sem_data.any():
        motivos["data invalida ou ausente"] = int(sem_data.sum())
        df = df[~sem_data]

    for coluna, (minimo, maximo) in LIMITES_PLAUSIVEIS.items():
        if coluna not in df.columns:
            df[coluna] = None
            continue
        valores = pd.to_numeric(df[coluna], errors="coerce")
        fora = valores.notna() & ((valores < minimo) | (valores > maximo))
        if fora.any():
            motivos[f"{coluna} fora do intervalo plausivel [{minimo}, {maximo}]"] = int(fora.sum())
            # Valor implausível é anulado (a linha continua, as outras
            # variáveis dela seguem válidas) -- e o motivo fica contado.
            valores = valores.mask(fora)
        df[coluna] = valores

    duplicadas = df.duplicated(subset=list(CHAVE_SILVER_CLIMA_GRADE_DIARIO), keep="last")
    n_duplicadas = int(duplicadas.sum())
    if n_duplicadas:
        df = df[~duplicadas]

    df["versao_schema_clima_grade"] = VERSAO_SCHEMA_CLIMA_GRADE
    df["_processed_at"] = datetime.now(timezone.utc).isoformat()

    df = df[list(COLUNAS_SILVER_CLIMA_GRADE_DIARIO)].sort_values(
        ["grade", "celula_id", "data"]
    ).reset_index(drop=True)

    metricas = {
        "linhas_antes": linhas_antes,
        "linhas_validas": len(df),
        "duplicatas_removidas": n_duplicadas,
        "motivos_rejeicao": motivos,
        "celulas_distintas": int(df.groupby(["grade", "celula_id"]).ngroups),
        "data_minima": str(df["data"].min()) if len(df) else None,
        "data_maxima": str(df["data"].max()) if len(df) else None,
    }
    return df, metricas


def montar_mapeamento_bairro_celula(
    df_centroides: pd.DataFrame,
    df_grade_diario: pd.DataFrame,
    mapa_bairro_celula: dict[tuple[str, str], str],
) -> pd.DataFrame:
    """Materializa `silver_bairro_celula_grade`.

    `df_centroides`: `codigo_bairro`, `nome_bairro`, `centroide_lat`,
    `centroide_lon` (vem de `silver_bairro_geo`, já calculado em CRS
    métrico — não recalculado aqui).
    `mapa_bairro_celula`: `(codigo_bairro, grade) -> celula_id`, produzido
    pela ingestão (é o provedor que decide qual célula cobre o ponto, não
    este projeto — por isso o mapa vem de fora, medido, e não de uma
    aritmética de arredondamento local).
    """
    coordenadas_celula = (
        df_grade_diario[["grade", "celula_id", "latitude_celula", "longitude_celula"]]
        .drop_duplicates()
        .set_index(["grade", "celula_id"])
    )

    linhas = []
    agora = datetime.now(timezone.utc).isoformat()
    for _, bairro in df_centroides.iterrows():
        for (codigo, grade), celula_id in mapa_bairro_celula.items():
            if codigo != bairro["codigo_bairro"]:
                continue
            chave = (grade, celula_id)
            if chave not in coordenadas_celula.index:
                continue
            coord = coordenadas_celula.loc[chave]
            lat_celula = float(coord["latitude_celula"])
            lon_celula = float(coord["longitude_celula"])
            linhas.append(
                {
                    "codigo_bairro": codigo,
                    "nome_bairro": bairro["nome_bairro"],
                    "grade": grade,
                    "celula_id": celula_id,
                    "latitude_celula": lat_celula,
                    "longitude_celula": lon_celula,
                    "resolucao_graus": RESOLUCAO_GRAUS_POR_GRADE[grade],
                    "distancia_centroide_celula_km": round(
                        distancia_km(
                            float(bairro["centroide_lat"]),
                            float(bairro["centroide_lon"]),
                            lat_celula,
                            lon_celula,
                        ),
                        3,
                    ),
                    "metodo_associacao": METODO_ASSOCIACAO_GRADE,
                    "versao_schema_clima_grade": VERSAO_SCHEMA_CLIMA_GRADE,
                    "_processed_at": agora,
                }
            )

    df = pd.DataFrame(linhas, columns=list(COLUNAS_SILVER_BAIRRO_CELULA_GRADE))
    return df.sort_values(["grade", "codigo_bairro"]).reset_index(drop=True)
