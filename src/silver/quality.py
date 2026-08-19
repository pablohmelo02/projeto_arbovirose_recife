"""Regras de qualidade de dados e utilidades de parsing/normalização da Silver.

Nenhuma função aqui descarta dado silenciosamente: parsing que falha vira
`None` (contabilizado por quem chama), e a decisão de rejeitar uma linha
sempre é tomada em `arboviroses.py`/`dimensoes.py`, nunca aqui.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pandas as pd

# Ordem importa: são tentados nessa sequência. Verificados contra dados reais:
# DD/MM/AAAA é o mais comum; AAAA-MM-DD aparece em alguns anos (ex.: chikungunya
# 2017); AAAA/MM/DD HH:MM:SS aparece em anos antigos (ex.: dengue 2013).
FORMATOS_DATA = ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S")

_PADRAO_FLOAT_INTEIRO = re.compile(r"^-?\d+\.0$")


def limpar_codigo(valor: object) -> Optional[str]:
    """Normaliza um campo tratado como código: string, sem espaços nas bordas,
    sem sufixo `.0` (código exportado como float em alguns anos, ex. "1.0").

    Nunca converte para int/float de verdade, para não perder zeros à
    esquerda em campos como `ID_UNIDADE` ou `codigo_bairro`.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None
    if _PADRAO_FLOAT_INTEIRO.match(texto):
        texto = texto[:-2]
    return texto


def limpar_texto(valor: object) -> Optional[str]:
    """Normaliza um campo de texto livre: colapsa espaços internos/bordas e
    converte para maiúsculas (para permitir join estável, ex. nome_bairro
    contra a dimensão bairro)."""
    limpo = limpar_codigo(valor)
    if limpo is None:
        return None
    texto = " ".join(limpo.split())
    return texto.upper() if texto else None


def normalizar_codigo_agravo(valor: object) -> Optional[str]:
    """Remove pontuação/espaços de um código CID para comparação (ex.: 'A92.0' -> 'A920')."""
    limpo = limpar_codigo(valor)
    if limpo is None:
        return None
    normalizado = re.sub(r"[^A-Za-z0-9]", "", limpo).upper()
    return normalizado or None


def parsear_data(valor: object) -> Optional[pd.Timestamp]:
    """Tenta parsear uma data testando, em ordem, os formatos conhecidos da Bronze.

    Retorna `None` (não levanta exceção) quando nenhum formato bate — quem
    chama é responsável por contabilizar isso como métrica de qualidade.
    """
    texto = limpar_codigo(valor)
    if texto is None:
        return None
    for formato in FORMATOS_DATA:
        try:
            return pd.Timestamp(datetime.strptime(texto, formato))
        except ValueError:
            continue
    return None


def extrair_semana_epidemiologica(valor: object) -> Optional[int]:
    """Extrai o componente de semana (1-53) de um código `AAAASS`.

    Retorna `None` se o valor não tiver o formato esperado ou se a semana
    estiver fora do intervalo plausível — não levanta exceção.
    """
    limpo = limpar_codigo(valor)
    if limpo is None or not limpo.isdigit() or len(limpo) != 6:
        return None
    semana = int(limpo[4:6])
    return semana if 1 <= semana <= 53 else None


def converter_decimal_brasileiro(valor: object) -> Optional[float]:
    """Converte um número no formato decimal brasileiro ("25,5") para float.

    Retorna `None` (não levanta exceção) quando o valor é vazio ou não é um
    número válido — quem chama decide o que fazer com isso. Usar só para
    valores que **de fato** vêm em notação brasileira (ex.: CSV do INMET) —
    para notação padrão (ponto decimal, ex.: coordenadas da API da APAC),
    use `converter_float`.
    """
    limpo = limpar_codigo(valor)
    if limpo is None:
        return None
    try:
        return float(limpo.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def converter_float(valor: object) -> Optional[float]:
    """Converte um número em notação padrão (ponto decimal) para float.

    Retorna `None` em vez de levantar exceção quando o valor é vazio ou
    inválido.
    """
    limpo = limpar_codigo(valor)
    if limpo is None:
        return None
    try:
        return float(limpo)
    except ValueError:
        return None


def ano_plausivel(valor: object, minimo: int = 2000, maximo: int = 2100) -> Optional[int]:
    """Converte para int só se o valor for um ano plausível; senão, `None`."""
    limpo = limpar_codigo(valor)
    if limpo is None or not limpo.isdigit():
        return None
    ano = int(limpo)
    return ano if minimo <= ano <= maximo else None
