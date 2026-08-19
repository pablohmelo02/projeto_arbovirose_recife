import pytest

from src.utils.inmet_csv import InmetCsvError, ler_estacao_inmet


def _csv_sintetico() -> bytes:
    linhas = [
        "REGIAO:;NE",
        "UF:;PE",
        "ESTACAO:;TESTE",
        "CODIGO (WMO):;A999",
        "LATITUDE:;-8,05",
        "LONGITUDE:;-34,90",
        "ALTITUDE:;10,5",
        "DATA DE FUNDACAO:;01/01/20",
        "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);UMIDADE RELATIVA DO AR, HORARIA (%);",
        "2024/01/01;0000 UTC;0;25,5;86;",
        "2024/01/01;0100 UTC;1,2;25,0;88;",
    ]
    return ("\n".join(linhas)).encode("latin-1")


def test_ler_estacao_inmet_extrai_metadados():
    metadados, _ = ler_estacao_inmet(_csv_sintetico())
    assert metadados["ESTACAO"] == "TESTE"
    assert metadados["CODIGO (WMO)"] == "A999"
    assert metadados["LATITUDE"] == "-8,05"
    assert metadados["UF"] == "PE"


def test_ler_estacao_inmet_extrai_serie_horaria():
    _, df = ler_estacao_inmet(_csv_sintetico())
    assert len(df) == 2
    assert "Data" in df.columns
    assert not any(str(c).startswith("Unnamed") for c in df.columns)
    assert df.iloc[1]["PRECIPITAÇÃO TOTAL, HORÁRIO (mm)"] == "1,2"


def test_ler_estacao_inmet_sem_cabecalho_levanta_erro():
    with pytest.raises(InmetCsvError):
        ler_estacao_inmet(b"REGIAO:;NE\nUF:;PE\n")
