from datetime import date, timedelta

import pandas as pd
import pytest

from src.gold.epidemiologia import (
    extrair_ano_semana,
    gerar_calendario_epidemiologico,
    intervalo_semana_epidemiologica,
    total_semanas_epidemiologicas,
)


def test_intervalo_semana_1_contem_4_de_janeiro():
    for ano in range(2010, 2027):
        inicio, fim = intervalo_semana_epidemiologica(ano, 1)
        assert inicio <= date(ano, 1, 4) <= fim


def test_semanas_tem_exatamente_7_dias():
    for ano, semana in [(2020, 1), (2020, 26), (2024, 53) if total_semanas_epidemiologicas(2024) == 53 else (2024, 1)]:
        inicio, fim = intervalo_semana_epidemiologica(ano, semana)
        assert (fim - inicio).days == 6


def test_semanas_consecutivas_sao_contiguas_sem_gap_nem_sobreposicao():
    for semana in range(1, 20):
        _, fim1 = intervalo_semana_epidemiologica(2020, semana)
        inicio2, _ = intervalo_semana_epidemiologica(2020, semana + 1)
        assert inicio2 == fim1 + timedelta(days=1)


def test_total_semanas_e_52_ou_53():
    for ano in range(2010, 2027):
        assert total_semanas_epidemiologicas(ano) in (52, 53)


def test_intervalo_semana_1_do_ano_seguinte_comeca_logo_apos_ultima_semana():
    for ano in range(2010, 2026):
        total = total_semanas_epidemiologicas(ano)
        _, fim_ultima = intervalo_semana_epidemiologica(ano, total)
        inicio_prox, _ = intervalo_semana_epidemiologica(ano + 1, 1)
        assert inicio_prox == fim_ultima + timedelta(days=1)


def test_extrair_ano_semana_formato_valido():
    assert extrair_ano_semana("202015") == (2020, 15)


def test_extrair_ano_semana_formato_invalido_retorna_none():
    assert extrair_ano_semana(None) is None
    assert extrair_ano_semana("abc123") is None
    assert extrair_ano_semana("2020") is None  # tamanho errado
    assert extrair_ano_semana("202099") is None  # semana 99 fora de 1-53
    assert extrair_ano_semana("202000") is None  # semana 0 fora de 1-53


def test_gerar_calendario_epidemiologico_cobre_intervalo_completo():
    calendario = gerar_calendario_epidemiologico(2020, 2021)
    assert calendario["ano_epidemiologico"].min() == 2020
    assert calendario["ano_epidemiologico"].max() == 2021
    assert len(calendario) == total_semanas_epidemiologicas(2020) + total_semanas_epidemiologicas(2021)
    assert not calendario.duplicated(subset=["ano_epidemiologico", "semana_epidemiologica"]).any()


@pytest.mark.parametrize("ano,semana,data_str", [
    (2013, 1, "2013-01-03"),
    (2015, 26, "2015-06-30"),
    (2020, 53, "2021-01-01") if total_semanas_epidemiologicas(2020) == 53 else (2020, 1, "2020-01-02"),
    (2024, 1, "2024-01-04"),
])
def test_data_real_conhecida_cai_dentro_da_semana_epidemiologica_esperada(ano, semana, data_str):
    inicio, fim = intervalo_semana_epidemiologica(ano, semana)
    data_alvo = pd.Timestamp(data_str).date()
    assert inicio <= data_alvo <= fim
