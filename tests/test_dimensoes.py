import pandas as pd
import pytest

from src.silver.dimensoes import transformar_dimensao


def test_transformar_dimensao_bairro_normaliza_e_dedupe():
    df_bruto = pd.DataFrame(
        {
            "Nº Localidade": ["132", "132", "779"],
            "Nome Localidade": [" aflitos ", "AFLITOS", "Afogados"],
            "Nome Município": ["RECIFE", "RECIFE", "RECIFE"],
        }
    )

    df, metricas = transformar_dimensao(df_bruto, "bairro")

    assert list(df.columns) == ["codigo_bairro", "nome_bairro", "nome_municipio"]
    assert metricas["linhas_lidas"] == 3
    assert metricas["linhas_validas"] == 2
    assert metricas["rejeitados_duplicados"] == 1
    assert df["nome_bairro"].tolist() == ["AFLITOS", "AFOGADOS"]


def test_transformar_dimensao_rejeita_linha_sem_chave_natural():
    df_bruto = pd.DataFrame(
        {
            "Nº Localidade": ["132", ""],
            "Nome Localidade": ["AFLITOS", "SEM CODIGO"],
            "Nome Município": ["RECIFE", "RECIFE"],
        }
    )

    df, metricas = transformar_dimensao(df_bruto, "bairro")

    assert metricas["rejeitados_sem_chave_natural"] == 1
    assert len(df) == 1


def test_transformar_dimensao_municipio_usa_indice_de_chave_correto():
    df_bruto = pd.DataFrame(
        {
            "UF": ["PE", "PE"],
            "Código": ["260005", "260010"],
            "Município": ["ABREU E LIMA", "AFOGADOS DA INGAZEIRA"],
        }
    )

    df, metricas = transformar_dimensao(df_bruto, "municipio")

    assert list(df.columns) == ["uf_sigla", "codigo_municipio", "nome_municipio"]
    assert metricas["linhas_validas"] == 2
    assert df["uf_sigla"].tolist() == ["PE", "PE"]


def test_transformar_dimensao_entidade_desconhecida_levanta_erro():
    with pytest.raises(ValueError):
        transformar_dimensao(pd.DataFrame({"a": [1]}), "inexistente")


def test_transformar_dimensao_colunas_insuficientes_levanta_erro():
    with pytest.raises(ValueError):
        transformar_dimensao(pd.DataFrame({"a": [1]}), "distrito")
