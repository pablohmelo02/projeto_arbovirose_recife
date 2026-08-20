import numpy as np
import pandas as pd
import pytest

from src.eda import clima, correlacao, epidemiologia, filtros


def _linha_gold(**overrides) -> dict:
    base = {
        "codigo_bairro": "1",
        "nome_bairro": "BAIRRO A",
        "agravo": "DENGUE",
        "ano_epidemiologico": 2024,
        "semana_epidemiologica": 1,
        "semana_epi_data_inicio": pd.Timestamp("2024-01-07"),
        "semana_epi_data_fim": pd.Timestamp("2024-01-13"),
        "casos": 0,
        "area_km2": 1.0,
        "codigo_rpa": "RPA-1",
        "codigo_microrregiao": "M1",
        "centroide_lat": -8.05,
        "centroide_lon": -34.9,
        "fonte_clima": None,
        "codigo_estacao_clima": None,
        "distancia_estacao_km": None,
        "metodo_associacao_clima": None,
        "precipitacao_total_semana_mm": np.nan,
        "precipitacao_media_diaria_mm": np.nan,
        "precipitacao_maxima_diaria_mm": np.nan,
        "dias_com_chuva": np.nan,
        "dias_com_dado_valido_semana": np.nan,
        "completude_climatica_semana": np.nan,
        "chuva_7d_mm": np.nan,
        "chuva_14d_mm": np.nan,
        "chuva_21d_mm": np.nan,
        "chuva_28d_mm": np.nan,
        "dias_com_dado_valido_7d": np.nan,
        "dias_com_dado_valido_28d": np.nan,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def df_gold_sintetico() -> pd.DataFrame:
    """Gold sintética pequena: 2 bairros x 2 agravos x algumas semanas,
    metade sem clima real (ano 2013) e metade com clima real (ano 2024)."""
    linhas = []
    for ano, tem_clima in [(2013, False), (2024, True)]:
        for semana in (1, 2, 3):
            for bairro, casos_dengue in [("1", 10 + semana), ("2", 5)]:
                for agravo, casos in [("DENGUE", casos_dengue), ("ZIKA", 1), ("CHIKUNGUNYA", 0)]:
                    extra = {}
                    if tem_clima and bairro == "1":
                        extra = {
                            "fonte_clima": "CEMADEN",
                            "codigo_estacao_clima": "100",
                            "precipitacao_total_semana_mm": 10.0 * semana,
                            "chuva_7d_mm": 10.0 * semana,
                            "chuva_14d_mm": 15.0 * semana,
                            "chuva_21d_mm": 20.0 * semana,
                            "chuva_28d_mm": 25.0 * semana,
                            "dias_com_dado_valido_semana": 7,
                            "dias_com_dado_valido_7d": 7,
                            "dias_com_dado_valido_28d": 28,
                        }
                    linhas.append(
                        _linha_gold(
                            codigo_bairro=bairro,
                            nome_bairro=f"BAIRRO {bairro}",
                            agravo=agravo,
                            ano_epidemiologico=ano,
                            semana_epidemiologica=semana,
                            casos=casos,
                            **extra,
                        )
                    )
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------
# filtros
# --------------------------------------------------------------------------


def test_aplicar_filtros_agravo_valido(df_gold_sintetico):
    resultado = filtros.aplicar_filtros(df_gold_sintetico, agravo="ZIKA")
    assert set(resultado["agravo"]) == {"ZIKA"}


def test_aplicar_filtros_agravo_invalido_levanta_erro(df_gold_sintetico):
    with pytest.raises(ValueError):
        filtros.aplicar_filtros(df_gold_sintetico, agravo="MALARIA")


def test_aplicar_filtros_combina_ano_e_bairro(df_gold_sintetico):
    resultado = filtros.aplicar_filtros(df_gold_sintetico, ano_inicio=2024, ano_fim=2024, codigo_bairro="1")
    assert set(resultado["ano_epidemiologico"]) == {2024}
    assert set(resultado["codigo_bairro"]) == {"1"}


def test_total_arboviroses_soma_os_tres_agravos(df_gold_sintetico):
    recorte = df_gold_sintetico[
        (df_gold_sintetico["ano_epidemiologico"] == 2013)
        & (df_gold_sintetico["semana_epidemiologica"] == 1)
        & (df_gold_sintetico["codigo_bairro"] == "1")
    ]
    total = filtros.total_arboviroses(recorte)
    esperado = recorte["casos"].sum()
    assert total["casos"].iloc[0] == esperado
    assert total["agravo"].iloc[0] == "TOTAL_ARBOVIROSES"


def test_linhas_com_clima_real_exclui_dias_validos_nulos_ou_zero(df_gold_sintetico):
    com_clima = filtros.linhas_com_clima_real(df_gold_sintetico)
    assert com_clima["dias_com_dado_valido_semana"].fillna(0).gt(0).all()
    assert set(com_clima["ano_epidemiologico"]) == {2024}
    assert set(com_clima["codigo_bairro"]) == {"1"}


# --------------------------------------------------------------------------
# epidemiologia
# --------------------------------------------------------------------------


def test_resumo_epidemiologico_conta_bairros_com_clima_real(df_gold_sintetico):
    resumo = epidemiologia.resumo_epidemiologico(df_gold_sintetico)
    assert resumo["total_bairros"] == 2
    assert resumo["bairros_com_clima_real"] == 1
    assert resumo["ano_epidemiologico_min"] == 2013
    assert resumo["ano_epidemiologico_max"] == 2024


def test_serie_temporal_semanal_por_agravo_nao_mistura_agravos(df_gold_sintetico):
    serie = epidemiologia.serie_temporal_semanal(df_gold_sintetico, por_agravo=True)
    assert set(serie["agravo"]) == {"DENGUE", "ZIKA", "CHIKUNGUNYA"}
    # dengue semana 1 de 2013: bairro 1 (11 casos) + bairro 2 (5 casos) = 16
    linha = serie[(serie["ano_epidemiologico"] == 2013) & (serie["semana_epidemiologica"] == 1) & (serie["agravo"] == "DENGUE")]
    assert linha["casos"].iloc[0] == 16


def test_comparar_agravos_agrega_por_ano(df_gold_sintetico):
    comparado = epidemiologia.comparar_agravos(df_gold_sintetico)
    assert set(comparado["ano_epidemiologico"]) == {2013, 2024}
    assert set(comparado["agravo"]) == {"DENGUE", "ZIKA", "CHIKUNGUNYA"}


def test_rank_bairros_ordena_por_casos_desc_e_respeita_top_n(df_gold_sintetico):
    apenas_dengue_2024 = filtros.aplicar_filtros(df_gold_sintetico, agravo="DENGUE", ano_inicio=2024, ano_fim=2024)
    ranking = epidemiologia.rank_bairros(apenas_dengue_2024, top_n=1)
    assert len(ranking) == 1
    assert ranking.iloc[0]["codigo_bairro"] == "1"  # bairro 1 tem mais casos de dengue que o 2
    assert ranking.iloc[0]["posicao"] == 1


def test_rank_bairros_metrica_invalida_levanta_erro(df_gold_sintetico):
    with pytest.raises(ValueError):
        epidemiologia.rank_bairros(df_gold_sintetico, metrica="incidencia_por_100k")


# --------------------------------------------------------------------------
# clima
# --------------------------------------------------------------------------


def test_resumo_cobertura_climatica_zero_quando_sem_clima(df_gold_sintetico):
    apenas_2013 = filtros.aplicar_filtros(df_gold_sintetico, ano_inicio=2013, ano_fim=2013)
    resumo = clima.resumo_cobertura_climatica(apenas_2013)
    assert resumo["linhas_com_clima_real"] == 0
    assert resumo["percentual_linhas_com_clima_real"] == 0.0
    assert resumo["bairros_com_clima_real"] == 0


def test_resumo_cobertura_climatica_real_em_2024(df_gold_sintetico):
    apenas_2024 = filtros.aplicar_filtros(df_gold_sintetico, ano_inicio=2024, ano_fim=2024)
    resumo = clima.resumo_cobertura_climatica(apenas_2024)
    assert resumo["linhas_com_clima_real"] > 0
    assert resumo["bairros_com_clima_real"] == 1
    assert resumo["anos_com_clima_real"] == [2024]
    assert resumo["fontes_climaticas"] == ["CEMADEN"]


def test_cobertura_por_ano_nunca_esconde_ano_sem_clima(df_gold_sintetico):
    tabela = clima.cobertura_por_ano(df_gold_sintetico)
    linha_2013 = tabela[tabela["ano_epidemiologico"] == 2013].iloc[0]
    linha_2024 = tabela[tabela["ano_epidemiologico"] == 2024].iloc[0]
    assert linha_2013["percentual_linhas_com_clima_real"] == 0.0
    assert linha_2013["percentual_bairros_com_clima_real"] == 0.0
    assert linha_2024["percentual_bairros_com_clima_real"] > 0.0


def test_cobertura_por_bairro_bairro_sem_clima_fica_em_zero(df_gold_sintetico):
    tabela = clima.cobertura_por_bairro(df_gold_sintetico)
    bairro_2 = tabela[tabela["codigo_bairro"] == "2"].iloc[0]
    assert bairro_2["semanas_com_clima_real"] == 0
    assert bairro_2["percentual_semanas_com_clima_real"] == 0.0


def test_cobertura_ano_semana_grade_completa_sem_pular_semana(df_gold_sintetico):
    grade = clima.cobertura_ano_semana(df_gold_sintetico)
    # 2 anos x 3 semanas = 6 combinacoes, todas presentes mesmo com 0%
    assert len(grade) == 6
    assert (grade["percentual_bairros_com_clima"] >= 0).all()
    linha_2013 = grade[grade["ano_epidemiologico"] == 2013]
    assert (linha_2013["percentual_bairros_com_clima"] == 0.0).all()


def test_serie_precipitacao_so_usa_linhas_com_clima_real(df_gold_sintetico):
    serie = clima.serie_precipitacao(df_gold_sintetico)
    assert set(serie["ano_epidemiologico"]) == {2024}
    assert (serie["bairros_considerados"] == 1).all()


# --------------------------------------------------------------------------
# correlacao
# --------------------------------------------------------------------------


def test_compute_lag_correlations_reporta_n_observacoes(df_gold_sintetico):
    resultado = correlacao.compute_lag_correlations(df_gold_sintetico)
    assert set(resultado["janela_dias"]) == {7, 14, 21, 28}
    for _, linha in resultado.iterrows():
        assert linha["n_observacoes"] >= 0
        assert isinstance(linha["confiavel"], (bool, np.bool_))


def test_compute_lag_correlations_amostra_pequena_marca_nao_confiavel(df_gold_sintetico):
    resultado = correlacao.compute_lag_correlations(df_gold_sintetico)
    # amostra sintetica e pequena (poucas linhas com clima real) -> nao confiavel
    assert not resultado["confiavel"].any()


def test_dados_dispersao_lag_janela_invalida_levanta_erro(df_gold_sintetico):
    with pytest.raises(ValueError):
        correlacao.dados_dispersao_lag(df_gold_sintetico, janela_dias=10)


def test_dados_dispersao_lag_retorna_apenas_linhas_com_leitura_real(df_gold_sintetico):
    dispersao = correlacao.dados_dispersao_lag(df_gold_sintetico, janela_dias=7)
    assert dispersao["precipitacao_mm"].notna().all()
    assert set(dispersao["ano_epidemiologico"]) == {2024}


def test_matriz_correlacao_nao_inclui_identificadores(df_gold_sintetico):
    matriz, n_obs = correlacao.matriz_correlacao(df_gold_sintetico)
    assert "codigo_bairro" not in matriz.columns
    assert "codigo_estacao_clima" not in matriz.columns
    assert "casos" in matriz.columns
    assert n_obs == len(filtros.linhas_com_clima_real(df_gold_sintetico))


def test_matriz_correlacao_vazia_quando_sem_clima_real():
    df_sem_clima = pd.DataFrame([_linha_gold(ano_epidemiologico=2013)])
    matriz, n_obs = correlacao.matriz_correlacao(df_sem_clima)
    assert n_obs == 0


# --------------------------------------------------------------------------
# comportamento com DataFrame vazio (0 linhas, mas colunas corretas) --
# cenário real do dashboard quando um filtro não retorna nada.
# --------------------------------------------------------------------------


@pytest.fixture()
def df_gold_vazio(df_gold_sintetico) -> pd.DataFrame:
    return df_gold_sintetico.iloc[0:0]


def test_funcoes_epidemiologia_nao_quebram_com_dataframe_vazio(df_gold_vazio):
    resumo = epidemiologia.resumo_epidemiologico(df_gold_vazio)
    assert resumo["total_linhas"] == 0
    assert resumo["ano_epidemiologico_min"] is None
    assert epidemiologia.serie_temporal_semanal(df_gold_vazio).empty
    assert epidemiologia.sazonalidade_semanal(df_gold_vazio).empty
    assert epidemiologia.comparar_agravos(df_gold_vazio).empty
    assert epidemiologia.rank_bairros(df_gold_vazio).empty


def test_funcoes_clima_nao_quebram_com_dataframe_vazio(df_gold_vazio):
    resumo = clima.resumo_cobertura_climatica(df_gold_vazio)
    assert resumo["linhas_com_clima_real"] == 0
    assert clima.cobertura_por_ano(df_gold_vazio).empty
    assert clima.cobertura_por_bairro(df_gold_vazio).empty
    assert clima.cobertura_ano_semana(df_gold_vazio).empty
    assert clima.serie_precipitacao(df_gold_vazio).empty


def test_funcoes_correlacao_nao_quebram_com_dataframe_vazio(df_gold_vazio):
    tabela = correlacao.compute_lag_correlations(df_gold_vazio)
    assert (tabela["n_observacoes"] == 0).all()
    assert tabela["correlacao_pearson"].isna().all()
    matriz, n_obs = correlacao.matriz_correlacao(df_gold_vazio)
    assert n_obs == 0
    assert not matriz.empty  # matriz de colunas ainda existe, só sem dado real
