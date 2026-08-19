import pytest

from src.ingestion.bronze_validation import (
    checar_conteudo,
    detectar_lacunas_anos,
    encontrar_manifest_mais_recente,
)


class _FakeMinioClient:
    def __init__(self, chaves: list[str]) -> None:
        self._chaves = chaves

    def listar_chaves(self, prefixo: str) -> list[str]:
        return [chave for chave in self._chaves if chave.startswith(prefixo)]


def test_checar_conteudo_arquivo_vazio():
    assert checar_conteudo(b"") == [("erro", "arquivo vazio (0 bytes)")]


def test_checar_conteudo_html_por_engano():
    conteudo = b"<!DOCTYPE html><html><body>pagina de erro</body></html>"
    problemas = checar_conteudo(conteudo)
    assert problemas[0][0] == "erro"
    assert "html" in problemas[0][1].lower()


def test_checar_conteudo_csv_valido_com_ponto_e_virgula():
    conteudo = "id;bairro\n1;Boa Viagem\n2;Casa Forte\n".encode("latin-1")
    assert checar_conteudo(conteudo) == []


def test_checar_conteudo_csv_valido_com_virgula():
    conteudo = "id,bairro\n1,Boa Viagem\n".encode("utf-8")
    assert checar_conteudo(conteudo) == []


def test_checar_conteudo_sem_delimitador_gera_aviso():
    conteudo = "apenas-uma-coluna\nvalor1\nvalor2\n".encode("utf-8")
    problemas = checar_conteudo(conteudo)
    assert ("aviso", "nenhum delimitador comum (',' ou ';') encontrado na primeira linha") in problemas


def test_checar_conteudo_uma_linha_so_gera_aviso():
    conteudo = "id;bairro\n".encode("utf-8")
    problemas = checar_conteudo(conteudo)
    assert any("menos de 2 linhas" in mensagem for _, mensagem in problemas)


def test_detectar_lacunas_anos_sem_lacuna():
    manifest = {
        "recursos": [
            {"tipo": "fato", "entidade": "dengue", "status": "SUCCESS", "ano": 2023},
            {"tipo": "fato", "entidade": "dengue", "status": "SUCCESS", "ano": 2024},
            {"tipo": "fato", "entidade": "dengue", "status": "SUCCESS", "ano": 2025},
        ]
    }
    assert detectar_lacunas_anos(manifest) == {}


def test_detectar_lacunas_anos_com_lacuna():
    manifest = {
        "recursos": [
            {"tipo": "fato", "entidade": "zika", "status": "SUCCESS", "ano": 2020},
            {"tipo": "fato", "entidade": "zika", "status": "SUCCESS", "ano": 2022},
        ]
    }
    assert detectar_lacunas_anos(manifest) == {"zika": [2021]}


def test_detectar_lacunas_ignora_dimensoes_e_recursos_com_erro():
    manifest = {
        "recursos": [
            {"tipo": "dimensao", "entidade": "bairro", "status": "SUCCESS", "ano": None},
            {"tipo": "fato", "entidade": "chikungunya", "status": "SUCCESS", "ano": 2020},
            {"tipo": "fato", "entidade": "chikungunya", "status": "ERROR", "ano": 2021},
        ]
    }
    assert detectar_lacunas_anos(manifest) == {}


def test_encontrar_manifest_mais_recente_escolhe_o_mais_novo():
    fake = _FakeMinioClient(
        [
            "bronze/recife/arboviroses/_controle/manifest_20260101T000000Z.json",
            "bronze/recife/arboviroses/_controle/manifest_20260819T150500Z.json",
            "bronze/recife/arboviroses/_controle/manifest_20260301T000000Z.json",
            "bronze/recife/arboviroses/_controle/validacao_20260301T000000Z.json",
        ]
    )
    resultado = encontrar_manifest_mais_recente(fake)
    assert resultado == "bronze/recife/arboviroses/_controle/manifest_20260819T150500Z.json"


def test_encontrar_manifest_mais_recente_sem_manifests():
    fake = _FakeMinioClient([])
    with pytest.raises(ValueError):
        encontrar_manifest_mais_recente(fake)
