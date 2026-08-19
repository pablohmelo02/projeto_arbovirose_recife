"""Transformação Silver do domínio Clima (INMET + APAC).

Produz `silver_estacao_climatica` (dimensão, ambas as fontes) e
`silver_clima_diario` (granularidade estação + dia). Não agrega por semana
nem por bairro — isso pertence à Gold. Nenhum valor ausente vira zero
silenciosamente: precipitação/temperatura/umidade ausentes ficam `None`,
nunca `0`/`fillna(0)`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from src.silver.quality import (
    converter_decimal_brasileiro,
    converter_float,
    limpar_codigo,
    limpar_texto,
)
from src.silver.schema_climate import (
    COLUNA_INMET_PRECIPITACAO,
    COLUNA_INMET_TEMPERATURA,
    COLUNA_INMET_UMIDADE,
    COLUNAS_SILVER_CLIMA_DIARIO,
    COLUNAS_SILVER_ESTACAO_CLIMATICA,
    TEMPERATURA_MAX_PLAUSIVEL_C,
    TEMPERATURA_MIN_PLAUSIVEL_C,
)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parsear_data_fundacao_inmet(valor: Optional[str]) -> Optional[str]:
    """Parseia `DD/MM/AA` (ano de 2 dígitos, regra POSIX: 00-68->20xx, 69-99->19xx)."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%d/%m/%y").date().isoformat()
    except ValueError:
        return None


def _parsear_data_apac(valor: Optional[str]) -> Optional[str]:
    """Parseia `DD-MM-AAAA`, formato do campo 'Data último dado' da APAC."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%d-%m-%Y").date().isoformat()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# silver_estacao_climatica
# --------------------------------------------------------------------------


def transformar_estacoes_inmet(metadados_por_estacao: dict[str, dict[str, str]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Constrói `silver_estacao_climatica` (fonte INMET) a partir dos metadados por estação."""
    processado_em = _agora()
    linhas = []
    for resource_id, metadados in metadados_por_estacao.items():
        linhas.append(
            {
                "codigo_estacao": limpar_codigo(metadados.get("CODIGO (WMO)")),
                "nome_estacao": limpar_texto(metadados.get("ESTACAO")),
                "fonte": "INMET",
                "latitude": converter_decimal_brasileiro(metadados.get("LATITUDE")),
                "longitude": converter_decimal_brasileiro(metadados.get("LONGITUDE")),
                "altitude": converter_decimal_brasileiro(metadados.get("ALTITUDE")),
                "municipio": None,  # não vem no CSV do INMET (ver schema_climate.py)
                "uf": limpar_codigo(metadados.get("UF")),
                "data_inicio": _parsear_data_fundacao_inmet(metadados.get("DATA DE FUNDACAO")),
                "data_fim": None,  # idem
                "_source": resource_id,
                "_processed_at": processado_em,
            }
        )

    return _validar_e_deduplicar_estacoes(pd.DataFrame(linhas))


def transformar_estacoes_apac(conteudo_json: bytes, resource_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Constrói `silver_estacao_climatica` (fonte APAC) a partir de um instantâneo PCD."""
    processado_em = _agora()
    dados = json.loads(conteudo_json.decode("utf-8", errors="replace"))
    pontos = dict(dados.get("pontos", {}))
    pontos.pop("metadados", None)

    linhas = []
    for ponto in pontos.values():
        info = ponto.get("ponto", {})
        municipio = ponto.get("3", {}).get("valor")
        linhas.append(
            {
                "codigo_estacao": limpar_codigo(info.get("id")),
                "nome_estacao": limpar_texto(info.get("nome")),
                "fonte": "APAC",
                "latitude": converter_float(info.get("latitude")),
                "longitude": converter_float(info.get("longitude")),
                "altitude": None,  # não vem na API da APAC
                "municipio": limpar_texto(municipio),
                "uf": "PE",
                "data_inicio": None,  # não vem na API da APAC
                "data_fim": None,
                "_source": resource_id,
                "_processed_at": processado_em,
            }
        )

    return _validar_e_deduplicar_estacoes(pd.DataFrame(linhas))


def _validar_e_deduplicar_estacoes(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    linhas_lidas = len(df)
    if linhas_lidas == 0:
        return df.reindex(columns=list(COLUNAS_SILVER_ESTACAO_CLIMATICA)), {
            "linhas_lidas": 0, "linhas_validas": 0, "linhas_rejeitadas": 0, "motivos_rejeicao": {},
        }

    motivo_linha = pd.Series([None] * len(df), dtype=object)

    sem_codigo = df["codigo_estacao"].isna()
    motivo_linha[sem_codigo & motivo_linha.isna()] = "codigo_estacao ausente"

    lat_invalida = df["latitude"].notna() & (df["latitude"].abs() > 90)
    lon_invalida = df["longitude"].notna() & (df["longitude"].abs() > 180)
    motivo_linha[(lat_invalida | lon_invalida) & motivo_linha.isna()] = "latitude/longitude fora do intervalo valido"

    duplicado = df.duplicated(subset=["fonte", "codigo_estacao"]) & df["codigo_estacao"].notna()
    motivo_linha[duplicado & motivo_linha.isna()] = "codigo_estacao duplicado (mesma fonte)"

    rejeitar = motivo_linha.notna()
    df_valido = df.loc[~rejeitar, list(COLUNAS_SILVER_ESTACAO_CLIMATICA)].reset_index(drop=True)

    motivos = {
        motivo: int(c) for motivo, c in motivo_linha[rejeitar].value_counts().items()
    }

    metricas = {
        "linhas_lidas": linhas_lidas,
        "linhas_validas": len(df_valido),
        "linhas_rejeitadas": int(rejeitar.sum()),
        "motivos_rejeicao": motivos,
    }
    return df_valido, metricas


# --------------------------------------------------------------------------
# silver_clima_diario
# --------------------------------------------------------------------------


def agregar_diario_inmet(
    df_horario: pd.DataFrame, codigo_estacao: str, resource_id: str, ingestion_run_id: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Agrega a série horária do INMET em `silver_clima_diario` (1 linha = estação + dia).

    Regra de agregação, documentada e explícita (nunca aplicada às cegas):
    - `precipitacao_mm` = soma das leituras horárias válidas do dia. Se
      NENHUMA hora do dia tiver leitura, o resultado é `None` (não `0`) —
      "sem dado" e "choveu zero" são coisas diferentes.
    - `temperatura_min/max/media_c` = mínimo/máximo/média das leituras
      horárias de bulbo seco do dia (não usamos os campos auxiliares
      "MÁXIMA/MÍNIMA NA HORA ANTERIOR" do INMET, que têm semântica de
      janela deslizante, não de dia calendário).
    - `umidade_min/max/media_pct` = idem, a partir da umidade relativa horária.
    """
    processado_em = _agora()
    linhas_lidas = len(df_horario)

    datas = pd.to_datetime(df_horario["Data"], format="%Y/%m/%d", errors="coerce")
    precip = df_horario[COLUNA_INMET_PRECIPITACAO].map(converter_decimal_brasileiro)
    temp = df_horario[COLUNA_INMET_TEMPERATURA].map(converter_decimal_brasileiro)
    umid = df_horario[COLUNA_INMET_UMIDADE].map(converter_decimal_brasileiro)

    base = pd.DataFrame({"data": datas, "precipitacao": precip, "temperatura": temp, "umidade": umid})
    sem_data = base["data"].isna()
    base = base.loc[~sem_data].copy()
    base["data"] = base["data"].dt.date

    agregado = (
        base.groupby("data")
        .agg(
            precipitacao_mm=("precipitacao", lambda s: s.sum(min_count=1)),
            temperatura_min_c=("temperatura", "min"),
            temperatura_max_c=("temperatura", "max"),
            temperatura_media_c=("temperatura", "mean"),
            umidade_min_pct=("umidade", "min"),
            umidade_max_pct=("umidade", "max"),
            umidade_media_pct=("umidade", "mean"),
        )
        .reset_index()
    )
    agregado["data"] = pd.to_datetime(agregado["data"])
    agregado["codigo_estacao"] = codigo_estacao
    agregado["fonte"] = "INMET"
    agregado["_source_resource"] = resource_id
    agregado["_ingestion_run_id"] = ingestion_run_id
    agregado["_processed_at"] = processado_em

    return _validar_clima_diario(agregado, linhas_lidas_hora=linhas_lidas, linhas_sem_data_hora=int(sem_data.sum()))


def transformar_diario_apac(
    conteudo_json: bytes, resource_id: str, ingestion_run_id: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Constrói `silver_clima_diario` (fonte APAC) a partir de um instantâneo PCD.

    Grão: 1 linha por estação, na data do último dado reportado por ela (não
    necessariamente "hoje" — estações offline podem reportar uma data antiga;
    isso é um achado de qualidade, não um erro do pipeline, ver
    `reports/climate_profile/quality_findings.csv`). `temperatura_*` e
    `umidade_*` ficam sempre nulos: a rede PCD da APAC é só de pluviômetros.
    """
    processado_em = _agora()
    dados = json.loads(conteudo_json.decode("utf-8", errors="replace"))
    pontos = dict(dados.get("pontos", {}))
    pontos.pop("metadados", None)

    linhas = []
    for ponto in pontos.values():
        info = ponto.get("ponto", {})
        campos = {
            item.get("titulo"): item.get("valor")
            for item in ponto.get("dados_monitorados", {}).get("dados", [])
        }
        linhas.append(
            {
                "data": _parsear_data_apac(campos.get("Data último dado")),
                "codigo_estacao": limpar_codigo(info.get("id")),
                "fonte": "APAC",
                "precipitacao_mm": converter_float(campos.get("24 Horas")),
                "temperatura_min_c": None,
                "temperatura_max_c": None,
                "temperatura_media_c": None,
                "umidade_min_pct": None,
                "umidade_max_pct": None,
                "umidade_media_pct": None,
                "_source_resource": resource_id,
                "_ingestion_run_id": ingestion_run_id,
                "_processed_at": processado_em,
            }
        )

    df = pd.DataFrame(linhas)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
    return _validar_clima_diario(df, linhas_lidas_hora=None, linhas_sem_data_hora=None)


def _validar_clima_diario(
    df: pd.DataFrame,
    linhas_lidas_hora: Optional[int],
    linhas_sem_data_hora: Optional[int],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    linhas_lidas = len(df)
    if linhas_lidas == 0:
        vazio = df.reindex(columns=list(COLUNAS_SILVER_CLIMA_DIARIO))
        return vazio, vazio.copy(), {
            "linhas_lidas": 0, "linhas_validas": 0, "linhas_rejeitadas": 0, "motivos_rejeicao": {},
        }

    motivo_linha = pd.Series([None] * len(df), dtype=object)

    sem_data = df["data"].isna()
    motivo_linha[sem_data & motivo_linha.isna()] = "data ausente ou nao parseavel"

    sem_codigo = df["codigo_estacao"].isna()
    motivo_linha[sem_codigo & motivo_linha.isna()] = "codigo_estacao ausente"

    precip_negativa = df["precipitacao_mm"].notna() & (df["precipitacao_mm"] < 0)
    motivo_linha[precip_negativa & motivo_linha.isna()] = "precipitacao_mm negativa"

    for coluna in ("umidade_min_pct", "umidade_max_pct", "umidade_media_pct"):
        invalida = df[coluna].notna() & ((df[coluna] < 0) | (df[coluna] > 100))
        motivo_linha[invalida & motivo_linha.isna()] = f"{coluna} fora de 0-100"

    # temperatura implausível é AVISO, não rejeição (ver docstring do schema)
    avisos_temperatura = 0
    for coluna in ("temperatura_min_c", "temperatura_max_c", "temperatura_media_c"):
        implausivel = df[coluna].notna() & (
            (df[coluna] < TEMPERATURA_MIN_PLAUSIVEL_C) | (df[coluna] > TEMPERATURA_MAX_PLAUSIVEL_C)
        )
        avisos_temperatura += int(implausivel.sum())

    rejeitar = motivo_linha.notna()
    df_valido = df.loc[~rejeitar, list(COLUNAS_SILVER_CLIMA_DIARIO)].reset_index(drop=True)
    df_rejeitado = df.loc[rejeitar].copy()
    df_rejeitado["_motivo_rejeicao"] = motivo_linha[rejeitar]

    motivos = {motivo: int(c) for motivo, c in motivo_linha[rejeitar].value_counts().items()}

    metricas: dict[str, Any] = {
        "linhas_lidas": linhas_lidas,
        "linhas_validas": len(df_valido),
        "linhas_rejeitadas": int(rejeitar.sum()),
        "motivos_rejeicao": motivos,
        "avisos_temperatura_implausivel": avisos_temperatura,
    }
    if linhas_lidas_hora is not None:
        metricas["linhas_lidas_hora_origem"] = linhas_lidas_hora
        metricas["linhas_sem_data_hora_origem"] = linhas_sem_data_hora

    return df_valido, df_rejeitado, metricas
