"""Transformação Silver das tabelas fato de arboviroses (Dengue/Zika/Chikungunya).

Lê um DataFrame bruto de uma única Bronze fato (uma doença, um ano) e produz
`(silver_valido, rejeitados, metricas)` segundo o contrato canônico de
`schema.py`. Não agrega nada: a granularidade continua sendo o registro de
notificação, um passo mais próximo do dado bruto do que a Gold.

Nenhuma linha é descartada silenciosamente — toda rejeição carrega um motivo
explícito em `_motivo_rejeicao`, e as métricas retornadas dizem exatamente
quantas linhas foram lidas/válidas/rejeitadas e por quê.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.silver.quality import (
    extrair_semana_epidemiologica,
    limpar_codigo,
    limpar_texto,
    normalizar_codigo_agravo,
    parsear_data,
)
from src.silver.schema import (
    ALIASES_FATO,
    CAMPOS_CODIGO,
    CAMPOS_DATA,
    CODIGO_AGRAVO_ESPERADO,
    COLUNAS_SILVER_ARBOVIROSES,
    TIPOS_ARBOVIROSE,
)

# Se a fração de linhas com codigo_agravo divergente do esperado ultrapassar
# este limiar, tratamos como um problema sistêmico do ARQUIVO (a fonte
# publicou o recurso errado sob aquele nome — foi o que aconteceu com "Zika
# 2021", que é 100% Chikungunya) e rejeitamos o recurso inteiro, em vez de
# rejeitar linha a linha.
LIMIAR_REJEICAO_ARQUIVO = 0.9


def _mapear_aliases(df: pd.DataFrame) -> dict[str, str]:
    """Para cada campo canônico, acha a coluna real do df correspondente (se houver)."""
    colunas_normalizadas = {coluna.strip().upper(): coluna for coluna in df.columns}
    encontrado: dict[str, str] = {}
    for campo, aliases in ALIASES_FATO.items():
        for alias in aliases:
            if alias in colunas_normalizadas:
                encontrado[campo] = colunas_normalizadas[alias]
                break
    return encontrado


def transformar_fato(
    df_bruto: pd.DataFrame,
    tipo_arbovirose: str,
    resource_id: str,
    ano_fonte: int,
    ingestion_run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Transforma um DataFrame bruto de fato em `(silver_valido, rejeitados, metricas)`."""
    mapeamento = _mapear_aliases(df_bruto)
    processado_em = datetime.now(timezone.utc).isoformat()
    linhas_lidas = len(df_bruto)

    dados: dict[str, pd.Series] = {}
    for campo in ALIASES_FATO:
        coluna_origem = mapeamento.get(campo)
        dados[campo] = (
            df_bruto[coluna_origem].reset_index(drop=True)
            if coluna_origem
            else pd.Series([None] * linhas_lidas, dtype=object)
        )

    df = pd.DataFrame(dados)
    df["tipo_arbovirose"] = tipo_arbovirose
    df["_source_resource_id"] = resource_id
    df["_source_year"] = ano_fonte
    df["_ingestion_run_id"] = ingestion_run_id
    df["_processed_at"] = processado_em

    for campo in CAMPOS_CODIGO:
        df[campo] = df[campo].map(limpar_codigo)
    df["nome_bairro"] = df["nome_bairro"].map(limpar_texto)

    for campo in CAMPOS_DATA:
        df[campo] = df[campo].map(parsear_data)

    df["ano_notificacao"] = pd.array(
        [limpar_codigo(v) for v in df["ano_notificacao"]], dtype="string"
    )
    df["ano_notificacao"] = pd.to_numeric(df["ano_notificacao"], errors="coerce").astype("Int64")

    codigo_normalizado = df["codigo_agravo"].map(normalizar_codigo_agravo)
    codigos_esperados = CODIGO_AGRAVO_ESPERADO[tipo_arbovirose]
    presentes = codigo_normalizado.notna()
    divergentes = presentes & ~codigo_normalizado.isin(codigos_esperados)

    taxa_divergencia = float(divergentes.sum() / presentes.sum()) if presentes.sum() else 0.0
    arquivo_rejeitado_integralmente = taxa_divergencia >= LIMIAR_REJEICAO_ARQUIVO

    if arquivo_rejeitado_integralmente:
        motivo = (
            f"arquivo rejeitado integralmente: {int(divergentes.sum())}/{int(presentes.sum())} "
            f"linhas com codigo_agravo fora de {codigos_esperados} (esperado para {tipo_arbovirose}) "
            "— a fonte provavelmente publicou o recurso errado sob este nome"
        )
        df_rejeitado = df.copy()
        df_rejeitado["_motivo_rejeicao"] = motivo
        metricas = {
            "linhas_lidas": linhas_lidas,
            "linhas_validas": 0,
            "linhas_rejeitadas": linhas_lidas,
            "arquivo_rejeitado_integralmente": True,
            "taxa_divergencia_codigo_agravo": round(taxa_divergencia, 4),
            "motivos_rejeicao": {motivo: linhas_lidas},
            "semanas_epidemiologicas_invalidas": 0,
            "datas_nulas_por_campo": {},
        }
        df_valido_vazio = df.iloc[0:0][list(COLUNAS_SILVER_ARBOVIROSES)]
        return df_valido_vazio, df_rejeitado, metricas

    motivo_linha = pd.Series([None] * len(df), dtype=object)

    sem_id = df["id_notificacao"].isna()
    motivo_linha[sem_id & motivo_linha.isna()] = "id_notificacao ausente"

    tipo_invalido = ~df["tipo_arbovirose"].isin(TIPOS_ARBOVIROSE)
    motivo_linha[tipo_invalido & motivo_linha.isna()] = "tipo_arbovirose invalido"

    motivo_linha[divergentes & motivo_linha.isna()] = (
        f"codigo_agravo inconsistente com tipo_arbovirose (esperado {codigos_esperados})"
    )

    rejeitar = motivo_linha.notna()

    df_valido = df.loc[~rejeitar, list(COLUNAS_SILVER_ARBOVIROSES)].reset_index(drop=True)
    df_rejeitado = df.loc[rejeitar].copy()
    df_rejeitado["_motivo_rejeicao"] = motivo_linha[rejeitar]

    motivos_rejeicao = {
        motivo: int(contagem)
        for motivo, contagem in motivo_linha[rejeitar].value_counts().items()
    }

    semanas_com_valor = df["semana_notificacao"].notna()
    semanas_invalidas = (
        semanas_com_valor
        & df["semana_notificacao"].map(extrair_semana_epidemiologica).isna()
    )

    metricas = {
        "linhas_lidas": linhas_lidas,
        "linhas_validas": len(df_valido),
        "linhas_rejeitadas": int(rejeitar.sum()),
        "arquivo_rejeitado_integralmente": False,
        "taxa_divergencia_codigo_agravo": round(taxa_divergencia, 4),
        "motivos_rejeicao": motivos_rejeicao,
        "semanas_epidemiologicas_invalidas": int(semanas_invalidas.sum()),
        "datas_nulas_por_campo": {
            campo: int(df[campo].isna().sum()) for campo in CAMPOS_DATA
        },
    }

    return df_valido, df_rejeitado, metricas
