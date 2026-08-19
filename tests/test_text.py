from src.utils.text import extract_year, normalize_text


def test_normalize_removes_accents_and_lowercases():
    assert normalize_text("Tabela Municípios") == "tabela municipios"
    assert normalize_text("Casos confirmados de Zika 2024") == "casos confirmados de zika 2024"


def test_normalize_strips_surrounding_whitespace():
    assert normalize_text("  Casos de Dengue 2022  ") == "casos de dengue 2022"


def test_normalize_empty_string():
    assert normalize_text("") == ""


def test_extract_year_finds_four_digit_year():
    assert extract_year("casos de dengue em 2016") == 2016
    assert extract_year("casos confirmados de chikungunya em 2025") == 2025


def test_extract_year_returns_none_when_absent():
    assert extract_year("tabela de bairros") is None
