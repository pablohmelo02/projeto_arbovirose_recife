import pytest

from src.utils.csv_bruto import CsvBrutoError, decodificar, detectar_delimitador, ler_csv_bruto


def test_detectar_delimitador_ponto_e_virgula():
    assert detectar_delimitador('"a";"b";"c"') == ";"


def test_detectar_delimitador_virgula():
    assert detectar_delimitador('"a","b","c"') == ","


def test_detectar_delimitador_sem_nenhum_usa_ponto_e_virgula_como_padrao():
    assert detectar_delimitador("coluna_unica") == ";"


def test_decodificar_utf8():
    texto, encoding = decodificar("Município".encode("utf-8"))
    assert texto == "Município"
    assert encoding == "utf-8"


def test_decodificar_latin1_como_fallback():
    texto, encoding = decodificar("Município".encode("latin-1"))
    assert texto == "Município"
    assert encoding == "latin-1"


def test_ler_csv_bruto_com_ponto_e_virgula():
    conteudo = '"id";"bairro"\n"1";"Boa Viagem"\n'.encode("utf-8")
    df = ler_csv_bruto(conteudo)
    assert list(df.columns) == ["id", "bairro"]
    assert df.iloc[0]["bairro"] == "Boa Viagem"


def test_ler_csv_bruto_com_virgula():
    conteudo = '"id","bairro"\n"1","Boa Viagem"\n'.encode("utf-8")
    df = ler_csv_bruto(conteudo)
    assert list(df.columns) == ["id", "bairro"]
    assert df.iloc[0]["bairro"] == "Boa Viagem"


def test_ler_csv_bruto_preserva_zeros_a_esquerda():
    conteudo = '"id_unidade";"nome"\n"0004774";"X"\n'.encode("utf-8")
    df = ler_csv_bruto(conteudo)
    assert df.iloc[0]["id_unidade"] == "0004774"


def test_ler_csv_bruto_vazio_levanta_erro():
    with pytest.raises(CsvBrutoError):
        ler_csv_bruto(b"")
