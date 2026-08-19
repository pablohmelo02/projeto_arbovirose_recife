from typing import Any

from src.ingestion.classifier import classificar_recurso


def _recurso(nome: str, formato: str = "CSV") -> dict[str, Any]:
    return {
        "id": "abc123",
        "name": nome,
        "format": formato,
        "url": "https://dados.recife.pe.gov.br/dataset/x/resource/abc123/download/arquivo.csv",
        "datastore_active": True,
    }


def test_classifica_dengue_2025():
    resultado = classificar_recurso(_recurso("Casos de Dengue 2025"))
    assert resultado.tipo == "fato"
    assert resultado.entidade == "dengue"
    assert resultado.ano == 2025


def test_classifica_zika_2024():
    resultado = classificar_recurso(_recurso("Casos confirmados de Zika 2024"))
    assert resultado.tipo == "fato"
    assert resultado.entidade == "zika"
    assert resultado.ano == 2024


def test_classifica_zica_2023_como_zika():
    resultado = classificar_recurso(_recurso("Casos confirmados de Zica 2023"))
    assert resultado.tipo == "fato"
    assert resultado.entidade == "zika"
    assert resultado.ano == 2023


def test_classifica_chikungunya_2025():
    resultado = classificar_recurso(_recurso("Casos confirmados de Chikungunya em 2025"))
    assert resultado.tipo == "fato"
    assert resultado.entidade == "chikungunya"
    assert resultado.ano == 2025


def test_classifica_dimensao_bairro():
    resultado = classificar_recurso(_recurso("Tabela de Bairros"))
    assert resultado.tipo == "dimensao"
    assert resultado.entidade == "bairro"
    assert resultado.ano is None


def test_classifica_dimensao_distrito():
    resultado = classificar_recurso(_recurso("Tabela Distrito"))
    assert resultado.tipo == "dimensao"
    assert resultado.entidade == "distrito"


def test_classifica_dimensao_agravo():
    resultado = classificar_recurso(_recurso("Tabela dos Agravos"))
    assert resultado.tipo == "dimensao"
    assert resultado.entidade == "agravo"


def test_classifica_dimensao_municipio():
    resultado = classificar_recurso(_recurso("Tabela Municípios"))
    assert resultado.tipo == "dimensao"
    assert resultado.entidade == "municipio"


def test_classifica_dimensao_uf():
    resultado = classificar_recurso(_recurso("Tabela UF"))
    assert resultado.tipo == "dimensao"
    assert resultado.entidade == "uf"


def test_ignora_metadados_mesmo_com_palavra_chave_de_dimensao():
    resultado = classificar_recurso(_recurso("Metadados da Tabela UF", formato="JSON"))
    assert resultado is None


def test_ignora_metadados_de_doenca():
    resultado = classificar_recurso(
        _recurso("Metadados dos Casos confirmados de Chikungunya", formato="JSON")
    )
    assert resultado is None


def test_ignora_recurso_sem_correspondencia():
    assert classificar_recurso(_recurso("Boletim Epidemiológico", formato="PDF")) is None


def test_dengue_com_espaco_inicial_no_nome():
    resultado = classificar_recurso(_recurso(" Casos de Dengue 2022"))
    assert resultado.tipo == "fato"
    assert resultado.entidade == "dengue"
    assert resultado.ano == 2022
