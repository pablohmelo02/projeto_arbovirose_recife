"""Item 10/13 do pedido: se não existir caso observado de 2026 na fonte
oficial, o forecast não pode tratar dado além do último ano verificado
como se fosse observado sem revisão deliberada do código.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.forecast.dataset import (
    DadoFuturoInesperadoError,
    ULTIMO_ANO_HISTORICO_VALIDADO,
    construir_serie_semanal,
    garantir_sem_observado_futuro,
)


def _linha(ano: int, semana: int = 1, agravo: str = "DENGUE", casos: int = 1) -> dict:
    return {
        "codigo_bairro": "1",
        "agravo": agravo,
        "ano_epidemiologico": ano,
        "semana_epidemiologica": semana,
        "semana_epi_data_inicio": pd.Timestamp(f"{ano}-01-07"),
        "casos": casos,
    }


def test_ultimo_ano_validado_e_2025():
    # se este teste falhar, é porque alguém reverificou a fonte oficial e
    # atualizou a constante -- nesse caso o relatorio de forecast tambem
    # precisa ser atualizado, não só a constante.
    assert ULTIMO_ANO_HISTORICO_VALIDADO == 2025


def test_garantir_sem_observado_futuro_aceita_gold_normal():
    gold = pd.DataFrame([_linha(2024), _linha(2025)])
    garantir_sem_observado_futuro(gold)  # não deve levantar


def test_garantir_sem_observado_futuro_rejeita_ano_2026():
    gold = pd.DataFrame([_linha(2025), _linha(2026)])
    with pytest.raises(DadoFuturoInesperadoError):
        garantir_sem_observado_futuro(gold)


def test_garantir_sem_observado_futuro_aceita_dataframe_vazio():
    garantir_sem_observado_futuro(pd.DataFrame(columns=["ano_epidemiologico"]))


def test_construir_serie_semanal_recusa_gold_com_2026():
    gold = pd.DataFrame([_linha(2025), _linha(2026)])
    with pytest.raises(DadoFuturoInesperadoError):
        construir_serie_semanal(gold, "DENGUE")
