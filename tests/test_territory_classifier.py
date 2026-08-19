from src.ingestion.territory_classifier import classificar_recurso_territorio


def _recurso(nome: str, formato: str = "GeoJSON") -> dict:
    return {"id": "abc", "name": nome, "format": formato, "url": "http://x/y.geojson"}


def test_classifica_limites_dos_bairros():
    resultado = classificar_recurso_territorio(_recurso("Limites dos Bairros - 2023"))
    assert resultado is not None
    assert resultado.entidade == "bairro"


def test_ignora_limites_por_microrregiao():
    assert classificar_recurso_territorio(_recurso("Limites por Microrregião - 2023")) is None


def test_ignora_limites_por_rpa():
    assert classificar_recurso_territorio(_recurso("Limites por RPA - 2023")) is None


def test_ignora_limites_por_logradouros():
    assert classificar_recurso_territorio(_recurso("Limites por Logradouros - 2023")) is None


def test_ignora_formato_nao_geografico():
    assert classificar_recurso_territorio(_recurso("Limites dos Bairros - 2023", formato="PDF")) is None


def test_tolerante_a_acentos_e_maiusculas():
    resultado = classificar_recurso_territorio(_recurso("limites dos BAIRROS 2023"))
    assert resultado is not None
    assert resultado.entidade == "bairro"
