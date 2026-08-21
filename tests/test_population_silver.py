"""Testes de integração da Silver de população contra os arquivos Bronze
REAIS versionados em `data/bronze/populacao/` (não sintéticos) — protegem
contra uma edição futura desses arquivos quebrar silenciosamente a
cobertura de 94/94 bairros ou a reconciliação municipal. Mesmo princípio de
`src/build_climate_grade.py` tratar `dashboard/data/gold_arboviroses_clima_bairro.parquet`
como um artefato local estável o suficiente para ser lido diretamente."""
import pandas as pd
import pytest

from src.population.reconstruction import carregar_dimensao_bairro, construir_serie_populacao
from src.silver.pipeline_population import (
    ARQUIVO_SILVER_POPULACAO,
    CAMINHO_BRONZE_CENSO2022,
    CAMINHO_BRONZE_CIEVS,
    CAMINHO_BRONZE_MUNICIPAL,
    CAMINHO_GOLD_PUBLICADA,
    executar_transformacao_silver_populacao_local,
)
from src.silver.schema_population import COLUNAS_SILVER_POPULACAO_BAIRRO_ANO, TIPOS_VALOR_POPULACAO

pytestmark = pytest.mark.skipif(
    not CAMINHO_GOLD_PUBLICADA.exists(), reason="Gold publicada ausente neste ambiente"
)


@pytest.fixture(scope="module")
def df_populacao_real() -> pd.DataFrame:
    df_territorio = carregar_dimensao_bairro(CAMINHO_GOLD_PUBLICADA)
    df, _ = construir_serie_populacao(
        CAMINHO_BRONZE_CIEVS, CAMINHO_BRONZE_CENSO2022, CAMINHO_BRONZE_MUNICIPAL, df_territorio
    )
    return df


def test_cobertura_94_bairros_em_todos_os_16_anos(df_populacao_real):
    por_ano = df_populacao_real.groupby("ano")["codigo_bairro"].nunique()
    assert set(df_populacao_real["ano"]) == set(range(2010, 2026))
    assert (por_ano == 94).all()


def test_populacao_sempre_positiva(df_populacao_real):
    assert (df_populacao_real["populacao"] > 0).all()


def test_tipo_valor_sempre_um_dos_valores_do_contrato(df_populacao_real):
    assert set(df_populacao_real["tipo_valor"]).issubset(set(TIPOS_VALOR_POPULACAO))


def test_2010_e_2022_sao_censo_observado(df_populacao_real):
    assert df_populacao_real[df_populacao_real["ano"] == 2010]["tipo_valor"].eq("CENSO_OBSERVADO").all()
    assert df_populacao_real[df_populacao_real["ano"] == 2022]["tipo_valor"].eq("CENSO_OBSERVADO").all()


def test_reconciliacao_municipal_2022_e_exata(df_populacao_real):
    soma_2022 = df_populacao_real[df_populacao_real["ano"] == 2022]["populacao"].sum()
    assert soma_2022 == 1_488_920


def test_reconciliacao_municipal_anos_reconstruidos_fecha_com_diferenca_desprezivel(df_populacao_real):
    for ano in (2018, 2019, 2020, 2021, 2024, 2025):
        subset = df_populacao_real[df_populacao_real["ano"] == ano]
        soma = subset["populacao"].sum()
        referencia = subset["populacao_municipal_referencia"].iloc[0]
        assert abs(soma - referencia) < 10  # diferenca de arredondamento de int, nunca sistemica


def test_chave_codigo_bairro_ano_e_unica(df_populacao_real):
    assert not df_populacao_real.duplicated(subset=["codigo_bairro", "ano"]).any()


def test_pipeline_local_grava_parquet_com_todas_as_colunas_do_contrato():
    manifest = executar_transformacao_silver_populacao_local()
    assert manifest["metricas"]["n_bairros"] == 94
    df = pd.read_parquet(ARQUIVO_SILVER_POPULACAO)
    assert list(df.columns) == list(COLUNAS_SILVER_POPULACAO_BAIRRO_ANO)
    assert df["codigo_bairro"].nunique() == 94
