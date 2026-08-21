"""Metadados de atualidade e o portão da priorização do período atual.

O ponto central testado aqui: **nada é considerado atual por omissão**, e a
projeção do período atual só é liberada quando os dados realmente cobrem um
período recente.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.freshness import (
    LIMIAR_SEMANAS_PROJECAO_ATUAL,
    MOTIVO_DADO_DESATUALIZADO,
    STATUS_ATRASADO,
    STATUS_ATUAL,
    STATUS_DESCONHECIDO,
    avaliar_projecao_atual,
    calcular_status,
    formatar_semana_epi,
    freshness_clima_estacao,
    freshness_clima_grade,
    freshness_epidemiologia,
    freshness_modelo,
    montar_artefato_freshness,
)


def _gold(ano_max: int = 2025, semana_max: int = 53, com_grade: bool = True) -> pd.DataFrame:
    semanas = [(2024, 1), (2024, 26), (ano_max, semana_max)]
    linhas = []
    for ano, semana in semanas:
        inicio = pd.Timestamp(f"{ano}-01-07") + pd.Timedelta(weeks=semana - 1)
        linhas.append(
            {
                "codigo_bairro": "1",
                "nome_bairro": "ALFA",
                "agravo": "DENGUE",
                "ano_epidemiologico": ano,
                "semana_epidemiologica": semana,
                "semana_epi_data_inicio": inicio,
                "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                "casos": 1,
                "dias_com_dado_valido_semana": 7 if ano >= 2024 else 0,
                "dias_validos_precipitacao_grade_semana": 7 if com_grade else None,
                "celula_grade_precipitacao": "-8.0000_-35.0000" if com_grade else None,
                "celula_grade_temperatura": "-8.0000_-34.9000" if com_grade else None,
            }
        )
    df = pd.DataFrame(linhas)
    if not com_grade:
        df = df.drop(columns=["dias_validos_precipitacao_grade_semana"])
    return df


# ---------------------------------------------------------------------------
# calcular_status
# ---------------------------------------------------------------------------
def test_status_atual_dentro_do_limiar():
    atraso, status, limiar = calcular_status("2026-08-01", "epidemiologia", referencia=date(2026, 8, 21))
    assert atraso == 20
    assert status == STATUS_ATUAL
    assert limiar == 120


def test_status_atrasado_acima_do_limiar():
    _, status, _ = calcular_status("2025-01-01", "epidemiologia", referencia=date(2026, 8, 21))
    assert status == STATUS_ATRASADO


@pytest.mark.parametrize("valor", [None, "", "data-invalida", "2026-13-45"])
def test_status_desconhecido_nunca_vira_atual(valor):
    atraso, status, _ = calcular_status(valor, "epidemiologia", referencia=date(2026, 8, 21))
    assert atraso is None
    assert status == STATUS_DESCONHECIDO, "ausência de informação nunca deve ser lida como 'atual'"


def test_formatar_semana_epi():
    assert formatar_semana_epi(2025, 3) == "2025-03"
    assert formatar_semana_epi(2025, None) is None
    assert formatar_semana_epi(None, 3) is None


# ---------------------------------------------------------------------------
# Por conjunto de dados
# ---------------------------------------------------------------------------
def test_freshness_epidemiologia_usa_a_ultima_semana_com_dado():
    fresh = freshness_epidemiologia(_gold(), referencia=date(2026, 8, 21))
    assert fresh.semana_epi_maxima == "2025-53"
    assert fresh.status == STATUS_ATRASADO
    assert fresh.detalhe["bairros"] == 1
    assert "último período publicado pela fonte oficial" in fresh.observacao


def test_freshness_epidemiologia_com_gold_vazia_nao_quebra():
    fresh = freshness_epidemiologia(pd.DataFrame(), referencia=date(2026, 8, 21))
    assert fresh.status == STATUS_DESCONHECIDO
    assert fresh.semana_epi_maxima is None


def test_freshness_clima_grade_declara_que_nao_e_estacao():
    fresh = freshness_clima_grade(_gold(), referencia=date(2026, 8, 21))
    assert "não é leitura de estação meteorológica" in fresh.observacao
    assert fresh.detalhe["celulas_precipitacao"] == 1


def test_freshness_clima_grade_ausente_em_gold_antiga():
    fresh = freshness_clima_grade(_gold(com_grade=False), referencia=date(2026, 8, 21))
    assert fresh.status == STATUS_DESCONHECIDO
    assert "versão < 1.1" in fresh.observacao


def test_freshness_clima_estacao_conta_apenas_leitura_real():
    fresh = freshness_clima_estacao(_gold(), referencia=date(2026, 8, 21))
    assert fresh.detalhe["linhas_com_leitura_real"] == 3


def test_freshness_modelo_sem_artefato():
    fresh = freshness_modelo(None)
    assert fresh.status == STATUS_DESCONHECIDO
    assert "nenhum artefato" in fresh.observacao


def test_freshness_modelo_com_metadados():
    fresh = freshness_modelo(
        {
            "model_version": "v1", "created_at": "2026-08-21T00:00:00+00:00",
            "data_cutoff": "2019-12-28", "cutoff_epi_week_formatada": "2019-52",
            "trained_until": 2019, "horizon": 3, "target_definition": "onset",
            "feature_schema_version": "38-abc",
        }
    )
    assert fresh.status == STATUS_ATUAL
    assert fresh.detalhe["horizon"] == 3


# ---------------------------------------------------------------------------
# Portão da projeção atual — o teste mais importante deste arquivo
# ---------------------------------------------------------------------------
def test_projecao_bloqueada_quando_dado_esta_velho():
    fresh = freshness_epidemiologia(_gold(), referencia=date(2026, 8, 21))
    portao = avaliar_projecao_atual(fresh, referencia=date(2026, 8, 21))
    assert portao["current_projection_available"] is False
    assert portao["reason"] == MOTIVO_DADO_DESATUALIZADO
    assert portao["semanas_de_atraso"] > LIMIAR_SEMANAS_PROJECAO_ATUAL
    assert "acima do limite" in portao["detalhe"]


def test_projecao_liberada_quando_dado_esta_recente():
    gold = _gold()
    gold.loc[gold.index[-1], "semana_epi_data_fim"] = pd.Timestamp("2026-08-15")
    fresh = freshness_epidemiologia(gold, referencia=date(2026, 8, 21))
    portao = avaliar_projecao_atual(fresh, referencia=date(2026, 8, 21))
    assert portao["current_projection_available"] is True
    assert portao["reason"] is None


def test_projecao_bloqueada_quando_atualidade_e_indeterminada():
    fresh = freshness_epidemiologia(pd.DataFrame())
    portao = avaliar_projecao_atual(fresh)
    assert portao["current_projection_available"] is False
    assert portao["reason"] == MOTIVO_DADO_DESATUALIZADO


def test_limite_e_exatamente_inclusivo():
    """Atraso igual ao limite ainda libera; um dia além do limite bloqueia."""
    gold = _gold()
    limite_dias = LIMIAR_SEMANAS_PROJECAO_ATUAL * 7
    gold.loc[gold.index[-1], "semana_epi_data_fim"] = pd.Timestamp("2026-08-21") - pd.Timedelta(days=limite_dias)
    fresh = freshness_epidemiologia(gold, referencia=date(2026, 8, 21))
    assert avaliar_projecao_atual(fresh, referencia=date(2026, 8, 21))["current_projection_available"]

    gold.loc[gold.index[-1], "semana_epi_data_fim"] = pd.Timestamp("2026-08-21") - pd.Timedelta(days=limite_dias + 7)
    fresh = freshness_epidemiologia(gold, referencia=date(2026, 8, 21))
    assert not avaliar_projecao_atual(fresh, referencia=date(2026, 8, 21))["current_projection_available"]


def test_artefato_final_tem_resumo_por_dataset():
    gold = _gold()
    artefato = montar_artefato_freshness(
        [
            freshness_epidemiologia(gold, referencia=date(2026, 8, 21)),
            freshness_clima_grade(gold, referencia=date(2026, 8, 21)),
        ],
        projecao=avaliar_projecao_atual(
            freshness_epidemiologia(gold, referencia=date(2026, 8, 21)), referencia=date(2026, 8, 21)
        ),
    )
    assert set(artefato["datasets"]) == {"epidemiologia", "clima_grade"}
    assert artefato["resumo_status"]["epidemiologia"] == STATUS_ATRASADO
    assert artefato["projecao_atual"]["current_projection_available"] is False
