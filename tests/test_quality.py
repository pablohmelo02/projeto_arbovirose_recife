import pandas as pd

from src.silver.quality import (
    ano_plausivel,
    extrair_semana_epidemiologica,
    limpar_codigo,
    limpar_texto,
    normalizar_codigo_agravo,
    parsear_data,
)


def test_limpar_codigo_remove_espacos():
    assert limpar_codigo("  0004774  ") == "0004774"


def test_limpar_codigo_remove_sufixo_float():
    assert limpar_codigo("1.0") == "1"
    assert limpar_codigo("-2.0") == "-2"


def test_limpar_codigo_preserva_zeros_a_esquerda():
    assert limpar_codigo("0004774") == "0004774"


def test_limpar_codigo_vazio_ou_none_vira_none():
    assert limpar_codigo(None) is None
    assert limpar_codigo("") is None
    assert limpar_codigo("   ") is None
    assert limpar_codigo(float("nan")) is None


def test_limpar_texto_colapsa_espacos_e_maiuscula():
    assert limpar_texto("  boa   viagem ") == "BOA VIAGEM"


def test_normalizar_codigo_agravo_remove_pontuacao():
    assert normalizar_codigo_agravo("A92.0") == "A920"
    assert normalizar_codigo_agravo("A928") == "A928"
    assert normalizar_codigo_agravo(None) is None


def test_parsear_data_formato_dd_mm_aaaa():
    assert parsear_data("04/03/2025") == pd.Timestamp("2025-03-04")


def test_parsear_data_formato_iso():
    assert parsear_data("2017-01-09") == pd.Timestamp("2017-01-09")


def test_parsear_data_formato_datetime_com_hora():
    assert parsear_data("2013/01/04 00:00:00") == pd.Timestamp("2013-01-04")


def test_parsear_data_invalida_retorna_none():
    assert parsear_data("nao e uma data") is None
    assert parsear_data(None) is None


def test_extrair_semana_epidemiologica_valida():
    assert extrair_semana_epidemiologica("202514") == 14
    assert extrair_semana_epidemiologica("201301") == 1


def test_extrair_semana_epidemiologica_fora_do_intervalo():
    assert extrair_semana_epidemiologica("202599") is None


def test_extrair_semana_epidemiologica_formato_invalido():
    assert extrair_semana_epidemiologica("abc") is None
    assert extrair_semana_epidemiologica("2025") is None
    assert extrair_semana_epidemiologica(None) is None


def test_ano_plausivel():
    assert ano_plausivel("2025") == 2025
    assert ano_plausivel("1800") is None
    assert ano_plausivel("abc") is None
    assert ano_plausivel(None) is None
