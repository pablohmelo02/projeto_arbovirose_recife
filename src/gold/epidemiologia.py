"""Calendário de semana epidemiológica (convenção brasileira/SVS, igual à
usada pelo SINAN — a mesma que já vem no campo `semana_notificacao` da
Silver de arboviroses).

**Não recalculamos a semana epidemiológica dos casos** — `semana_notificacao`
(formato `AAAASS`, ver `src/silver/schema.py`) já vem do próprio SINAN e é
usada como está. O que este módulo resolve é o problema inverso, necessário
para o join com clima: dado um (ano, semana) epidemiológico, qual o
intervalo de datas de calendário correspondente (domingo a sábado), para
poder agregar `silver_clima_diario` (que só tem data de calendário) no
mesmo grão.

Regra implementada (convenção CDC/OMS/SVS — semanas de domingo a sábado; a
semana 1 do ano é a que contém o dia 4 de janeiro): validada empiricamente
contra 5.000 pares reais (`data_notificacao`, `semana_notificacao`) da
Silver de arboviroses antes de ser usada aqui — 5000/5000 bateram. Não é
`date.isocalendar()` (que é ISO: semanas de segunda a domingo, semana 1
contém a primeira quinta-feira) — usar isocalendar() teria desalinhado
sistematicamente com o campo já existente.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd


def inicio_semana_epidemiologica_1(ano: int) -> date:
    """Domingo de início da semana epidemiológica 1 do `ano` (a semana que
    contém 4 de janeiro)."""
    jan4 = date(ano, 1, 4)
    dias_desde_domingo = jan4.isoweekday() % 7  # isoweekday: Seg=1..Dom=7 -> Dom=0
    return jan4 - timedelta(days=dias_desde_domingo)


def intervalo_semana_epidemiologica(ano: int, semana: int) -> tuple[date, date]:
    """Intervalo (domingo, sábado) de uma semana epidemiológica `ano`-`semana`."""
    inicio = inicio_semana_epidemiologica_1(ano) + timedelta(weeks=semana - 1)
    fim = inicio + timedelta(days=6)
    return inicio, fim


def total_semanas_epidemiologicas(ano: int) -> int:
    """52 ou 53 — quantas semanas epidemiológicas o `ano` tem, derivado da
    distância real entre o início da semana 1 deste ano e do próximo."""
    inicio_este_ano = inicio_semana_epidemiologica_1(ano)
    inicio_proximo_ano = inicio_semana_epidemiologica_1(ano + 1)
    return (inicio_proximo_ano - inicio_este_ano).days // 7


def extrair_ano_semana(semana_notificacao: Optional[str]) -> Optional[tuple[int, int]]:
    """Extrai (ano, semana) de um valor `semana_notificacao` no formato
    `AAAASS` (6 dígitos). Retorna `None` se o formato não bater — nunca
    levanta exceção; quem chama decide o que fazer (ver
    `arboviroses_clima.py`, que conta isso como exclusão documentada)."""
    if not isinstance(semana_notificacao, str) or len(semana_notificacao) != 6 or not semana_notificacao.isdigit():
        return None
    ano = int(semana_notificacao[:4])
    semana = int(semana_notificacao[4:6])
    if not (1 <= semana <= 53):
        return None
    return ano, semana


def gerar_calendario_epidemiologico(ano_inicio: int, ano_fim: int) -> pd.DataFrame:
    """Todas as combinações reais (ano_epidemiologico, semana_epidemiologica,
    data_inicio, data_fim) entre `ano_inicio` e `ano_fim` (inclusive) — usado
    para materializar o grão completo da Gold (ver seção 16 do pedido: uma
    semana sem nenhum caso notificado deve aparecer como `casos=0`, não
    ficar ausente)."""
    linhas = []
    for ano in range(ano_inicio, ano_fim + 1):
        for semana in range(1, total_semanas_epidemiologicas(ano) + 1):
            inicio, fim = intervalo_semana_epidemiologica(ano, semana)
            linhas.append(
                {
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "semana_epi_data_inicio": pd.Timestamp(inicio),
                    "semana_epi_data_fim": pd.Timestamp(fim),
                }
            )
    return pd.DataFrame(linhas)
