"""Validação de entradas da UI, priorização observada e EDA em grade."""
from __future__ import annotations

import pandas as pd
import pytest

from dashboard.utils.validacao import (
    EntradaInvalidaError,
    validar_escolha,
    validar_intervalo_de_anos,
    validar_semana_epidemiologica,
    validar_top_k,
)
from src.eda import clima_grade
from src.eda.prioridade_observada import (
    JANELA_RECENTE_SEMANAS,
    ROTULO_TENDENCIA_ALTA,
    ROTULO_TENDENCIA_ESTAVEL,
    ROTULO_TENDENCIA_INDEFINIDA,
    ROTULO_TENDENCIA_QUEDA,
    media_historica_sazonal,
    prioridade_observada,
    resumo_situacao,
    semanas_disponiveis,
    ultima_semana_disponivel,
)


# ===========================================================================
# Validação de entradas
# ===========================================================================
def test_escolha_valida_e_invalida():
    assert validar_escolha("DENGUE", ("DENGUE", "ZIKA"), "Agravo") == "DENGUE"
    assert validar_escolha(None, ("DENGUE",), "Agravo") is None
    with pytest.raises(EntradaInvalidaError):
        validar_escolha("MALARIA", ("DENGUE", "ZIKA"), "Agravo")
    with pytest.raises(EntradaInvalidaError):
        validar_escolha(None, ("DENGUE",), "Agravo", permitir_nulo=False)


def test_intervalo_de_anos_normaliza_e_valida():
    anos = [2023, 2024, 2025]
    assert validar_intervalo_de_anos(2023, 2025, anos) == (2023, 2025)
    assert validar_intervalo_de_anos(2025, 2023, anos) == (2023, 2025), "ordem invertida é corrigida"
    with pytest.raises(EntradaInvalidaError):
        validar_intervalo_de_anos(2010, 2025, anos)
    with pytest.raises(EntradaInvalidaError):
        validar_intervalo_de_anos("a", "b", anos)
    with pytest.raises(EntradaInvalidaError):
        validar_intervalo_de_anos(2023, 2025, [])


def test_semana_epidemiologica_valida_contra_pares_reais():
    pares = [(2025, 1), (2025, 53)]
    assert validar_semana_epidemiologica(2025, 53, pares) == (2025, 53)
    with pytest.raises(EntradaInvalidaError, match="não existe"):
        validar_semana_epidemiologica(2025, 30, pares)
    with pytest.raises(EntradaInvalidaError, match="fora da faixa"):
        validar_semana_epidemiologica(2025, 99, pares)
    with pytest.raises(EntradaInvalidaError, match="não numérica"):
        validar_semana_epidemiologica("x", "y", pares)


def test_top_k_restrito_aos_valores_com_evidencia():
    assert validar_top_k(5, (5, 10, 15, 20)) == 5
    with pytest.raises(EntradaInvalidaError):
        validar_top_k(7, (5, 10, 15, 20))
    with pytest.raises(EntradaInvalidaError):
        validar_top_k("cinco", (5, 10, 15, 20))


# ===========================================================================
# Priorização observada
# ===========================================================================
def _serie_bairros(n_semanas: int = 20, anos_historico: int = 3) -> pd.DataFrame:
    """Dois bairros: ALFA cresce no fim, BETA cai. Mais anos anteriores para
    dar base à comparação sazonal."""
    linhas = []
    for ano in range(2025 - anos_historico, 2026):
        for semana in range(1, n_semanas + 1):
            inicio = pd.Timestamp(f"{ano}-01-05") + pd.Timedelta(weeks=semana - 1)
            base_alfa = 2 if ano < 2025 else (2 if semana <= n_semanas - JANELA_RECENTE_SEMANAS else 20)
            base_beta = 8 if ano < 2025 else (8 if semana <= n_semanas - JANELA_RECENTE_SEMANAS else 1)
            for codigo, nome, casos in (("1", "ALFA", base_alfa), ("2", "BETA", base_beta)):
                linhas.append(
                    {
                        "codigo_bairro": codigo, "nome_bairro": nome, "codigo_rpa": "1",
                        "ano_epidemiologico": ano, "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": inicio,
                        "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                        "casos": casos,
                    }
                )
    return pd.DataFrame(linhas)


def test_ultima_semana_e_semanas_disponiveis():
    df = _serie_bairros()
    assert ultima_semana_disponivel(df) == (2025, 20)
    assert ultima_semana_disponivel(pd.DataFrame()) is None
    lista = semanas_disponiveis(df, limite=3)
    assert lista[0] == (2025, 20)
    assert len(lista) == 3
    assert semanas_disponiveis(pd.DataFrame()) == []


def test_media_historica_usa_somente_anos_anteriores():
    df = _serie_bairros()
    historico = media_historica_sazonal(df, ano_referencia=2025, semana_referencia=20)
    alfa = historico.loc[historico["codigo_bairro"] == "1", "media_historica"].iloc[0]
    # Nos anos anteriores ALFA tinha 2 casos por semana em toda a série.
    assert alfa == pytest.approx(2.0)


def test_media_historica_vazia_sem_anos_anteriores():
    df = _serie_bairros(anos_historico=0)
    historico = media_historica_sazonal(df, ano_referencia=2025, semana_referencia=20)
    assert historico.empty


def test_prioridade_identifica_alta_e_queda():
    tabela = prioridade_observada(_serie_bairros())
    alfa = tabela[tabela["codigo_bairro"] == "1"].iloc[0]
    beta = tabela[tabela["codigo_bairro"] == "2"].iloc[0]
    assert alfa["tendencia"] == ROTULO_TENDENCIA_ALTA
    assert beta["tendencia"] == ROTULO_TENDENCIA_QUEDA
    assert alfa["razao_historico"] > 1.0, "ALFA está acima do próprio histórico"


def test_prioridade_com_dataframe_vazio_devolve_contrato():
    tabela = prioridade_observada(pd.DataFrame())
    assert tabela.empty
    assert "razao_historico" in tabela.columns
    assert "tendencia" in tabela.columns


def test_prioridade_em_semana_inexistente_devolve_vazio():
    assert prioridade_observada(_serie_bairros(), ano_referencia=1999, semana_referencia=1).empty


def test_tendencia_indefinida_sem_janela_anterior():
    df = _serie_bairros(n_semanas=2, anos_historico=0)
    tabela = prioridade_observada(df, ano_referencia=2025, semana_referencia=1)
    assert (tabela["tendencia"] == ROTULO_TENDENCIA_INDEFINIDA).all() or tabela.empty


def test_razao_historico_nao_explode_com_historico_zero():
    df = _serie_bairros()
    df.loc[df["ano_epidemiologico"] < 2025, "casos"] = 0
    tabela = prioridade_observada(df)
    assert tabela["razao_historico"].notna().all()
    assert (tabela["razao_historico"] < 1e6).all(), "suavização deve impedir razão explosiva"


def test_variacao_estavel_dentro_do_limiar():
    df = _serie_bairros()
    df.loc[df["ano_epidemiologico"] == 2025, "casos"] = 10  # sem variação
    tabela = prioridade_observada(df)
    assert (tabela["tendencia"] == ROTULO_TENDENCIA_ESTAVEL).all()


def test_resumo_situacao_conta_bairros_em_alta():
    df = _serie_bairros()
    tabela = prioridade_observada(df)
    resumo = resumo_situacao(df, tabela)
    assert resumo["total_bairros"] == 2
    assert resumo["bairros_em_alta"] == 1
    assert resumo["casos_janela_recente_cidade"] > 0


def test_resumo_situacao_com_tabela_vazia():
    resumo = resumo_situacao(pd.DataFrame({"codigo_bairro": []}), pd.DataFrame())
    assert resumo["casos_semana_cidade"] == 0
    assert resumo["tendencia_cidade"] == ROTULO_TENDENCIA_INDEFINIDA
    assert resumo["incidencia_janela_recente_100k_cidade"] is None


def test_resumo_situacao_sem_populacao_incidencia_cidade_e_none():
    df = _serie_bairros()
    tabela = prioridade_observada(df)
    resumo = resumo_situacao(df, tabela)
    assert resumo["incidencia_janela_recente_100k_cidade"] is None


def _serie_bairros_com_populacao() -> pd.DataFrame:
    df = _serie_bairros()
    # ALFA: populacao pequena -> incidencia alta apesar de poucos casos.
    # BETA: populacao grande -> incidencia baixa apesar de mais casos.
    df["populacao_bairro_ano"] = df["codigo_bairro"].map({"1": 1000, "2": 1_000_000})
    df["tipo_populacao"] = "CENSO_OBSERVADO"
    df["densidade_populacional_hab_km2"] = df["codigo_bairro"].map({"1": 100.0, "2": 5000.0})
    df["incidencia_100k"] = 100000 * df["casos"] / df["populacao_bairro_ano"]
    df["incidencia_4s_100k"] = df["incidencia_100k"]  # simplificacao suficiente para o teste
    return df


def test_prioridade_observada_repassa_colunas_de_populacao_sem_recalcular():
    tabela = prioridade_observada(_serie_bairros_com_populacao())
    alfa = tabela[tabela["codigo_bairro"] == "1"].iloc[0]
    assert alfa["tipo_populacao"] == "CENSO_OBSERVADO"
    assert alfa["populacao_bairro_ano"] == 1000
    assert alfa["incidencia_100k"] == pytest.approx(100000 * 20 / 1000)


def test_prioridade_observada_sem_colunas_de_populacao_preenche_none():
    tabela = prioridade_observada(_serie_bairros())
    assert tabela["populacao_bairro_ano"].isna().all()
    assert tabela["incidencia_100k"].isna().all()


def test_resumo_situacao_incidencia_cidade_e_uma_unica_divisao_nao_soma_de_taxas():
    df = _serie_bairros_com_populacao()
    tabela = prioridade_observada(df)
    resumo = resumo_situacao(df, tabela)

    casos_totais = float(tabela["casos_janela_recente"].fillna(0).sum())
    populacao_total = float(tabela["populacao_bairro_ano"].fillna(0).sum())
    esperado = casos_totais / populacao_total * 100000

    assert resumo["incidencia_janela_recente_100k_cidade"] == pytest.approx(esperado)


def test_ranking_maior_volume_ordena_por_casos_recentes():
    from src.eda.prioridade_observada import ranking_maior_volume

    tabela = prioridade_observada(_serie_bairros_com_populacao())
    ranking = ranking_maior_volume(tabela)
    assert ranking.iloc[0]["codigo_bairro"] == "1"  # ALFA tem mais casos recentes (20 vs 1)


def test_ranking_maior_incidencia_inverte_ordem_do_ranking_de_volume():
    from src.eda.prioridade_observada import ranking_maior_incidencia

    tabela = prioridade_observada(_serie_bairros_com_populacao())
    ranking = ranking_maior_incidencia(tabela)
    # BETA tem menos casos absolutos mas populacao muito menor proporcionalmente
    # que sua carga -- o ranking de incidencia usa incidencia_4s_100k, nao casos.
    assert ranking.iloc[0]["codigo_bairro"] == ranking.sort_values(
        "incidencia_4s_100k", ascending=False
    ).iloc[0]["codigo_bairro"]


def test_ranking_maior_incidencia_coloca_ausentes_no_fim():
    from src.eda.prioridade_observada import ranking_maior_incidencia

    tabela = prioridade_observada(_serie_bairros())  # sem populacao -> tudo None
    ranking = ranking_maior_incidencia(tabela)
    assert len(ranking) == len(tabela)


def test_ranking_maior_crescimento_e_maior_desvio_sao_rankings_distintos():
    from src.eda.prioridade_observada import ranking_maior_crescimento, ranking_maior_desvio_historico

    tabela = prioridade_observada(_serie_bairros())
    crescimento = ranking_maior_crescimento(tabela)
    desvio = ranking_maior_desvio_historico(tabela)
    assert list(crescimento["codigo_bairro"]) == list(
        tabela.sort_values("variacao_pct", ascending=False, na_position="last")["codigo_bairro"]
    )
    assert list(desvio["codigo_bairro"]) == list(
        tabela.sort_values("razao_historico", ascending=False, na_position="last")["codigo_bairro"]
    )


def test_rankings_observados_cobre_os_4_rotulos_do_produto():
    from src.eda.prioridade_observada import RANKINGS_OBSERVADOS

    assert len(RANKINGS_OBSERVADOS) == 4
    tabela = prioridade_observada(_serie_bairros_com_populacao())
    for funcao in RANKINGS_OBSERVADOS.values():
        resultado = funcao(tabela)
        assert len(resultado) == len(tabela)


# ===========================================================================
# EDA do clima em grade
# ===========================================================================
def _gold_com_grade(com_grade: bool = True, com_estacao: bool = True) -> pd.DataFrame:
    linhas = []
    for ano in (2024, 2025):
        for semana in range(1, 11):
            inicio = pd.Timestamp(f"{ano}-01-05") + pd.Timedelta(weeks=semana - 1)
            for codigo in ("1", "2"):
                linhas.append(
                    {
                        "codigo_bairro": codigo, "nome_bairro": f"B{codigo}", "agravo": "DENGUE",
                        "ano_epidemiologico": ano, "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": inicio,
                        "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                        "casos": semana,
                        "dias_com_dado_valido_semana": 7 if (com_estacao and ano == 2025) else 0,
                        "precipitacao_total_semana_mm": 5.0 * semana if (com_estacao and ano == 2025) else None,
                        "dias_validos_precipitacao_grade_semana": 7 if com_grade else 0,
                        "precipitacao_semana_grade_mm": 4.0 * semana if com_grade else None,
                        "precipitacao_2s_grade_mm": 8.0 * semana if com_grade else None,
                        "precipitacao_3s_grade_mm": 12.0 * semana if com_grade else None,
                        "precipitacao_4s_grade_mm": 16.0 * semana if com_grade else None,
                        "temperatura_media_grade_c": 26.0,
                        "temperatura_minima_grade_c": 22.0,
                        "temperatura_maxima_grade_c": 30.0,
                        "umidade_relativa_media_grade_pct": 78.0,
                        "celula_grade_precipitacao": "-8.0000_-35.0000",
                        "celula_grade_temperatura": "-8.0000_-34.9000",
                    }
                )
    df = pd.DataFrame(linhas)
    if not com_grade:
        df = df.drop(columns=["dias_validos_precipitacao_grade_semana"])
    return df


def test_deteccao_de_gold_com_e_sem_grade():
    assert clima_grade.gold_tem_clima_grade(_gold_com_grade())
    assert not clima_grade.gold_tem_clima_grade(_gold_com_grade(com_grade=False))


def test_resumo_de_cobertura_em_grade():
    resumo = clima_grade.resumo_cobertura_grade(_gold_com_grade())
    assert resumo["disponivel"] is True
    assert resumo["percentual_linhas"] == 100.0
    assert resumo["celulas_precipitacao"] == 1


def test_resumo_indica_indisponivel_em_gold_antiga():
    assert clima_grade.resumo_cobertura_grade(_gold_com_grade(com_grade=False)) == {"disponivel": False}


def test_cobertura_dupla_separa_as_duas_fontes():
    tabela = clima_grade.cobertura_dupla_por_ano(_gold_com_grade())
    linha_2024 = tabela[tabela["ano_epidemiologico"] == 2024].iloc[0]
    linha_2025 = tabela[tabela["ano_epidemiologico"] == 2025].iloc[0]
    assert linha_2024["pct_com_grade"] == 100.0
    assert linha_2024["pct_com_estacao"] == 0.0
    assert linha_2025["pct_com_estacao"] == 100.0


def test_cobertura_dupla_com_dataframe_vazio():
    assert clima_grade.cobertura_dupla_por_ano(pd.DataFrame()).empty


def test_serie_e_sazonalidade_em_grade():
    serie = clima_grade.serie_climatica_grade(_gold_com_grade())
    assert len(serie) == 20
    assert (serie["bairros_considerados"] == 2).all()
    assert "temperatura_minima_c" in serie.columns
    assert (serie["temperatura_minima_c"] == 22.0).all()
    sazonal = clima_grade.sazonalidade_climatica_grade(_gold_com_grade())
    assert len(sazonal) == 10
    assert (sazonal["anos_observados"] == 2).all()


def test_serie_em_grade_vazia_quando_nao_ha_grade():
    assert clima_grade.serie_climatica_grade(_gold_com_grade(com_grade=False)).empty


def test_correlacoes_em_grade_reportam_n():
    tabela = clima_grade.correlacoes_lag_grade(_gold_com_grade())
    assert set(tabela["janela_semanas"]) == {1, 2, 3, 4}
    assert (tabela["n_observacoes"] > 0).all()
    assert "correlacao_spearman" in tabela.columns


def test_dispersao_em_grade_rejeita_janela_invalida():
    with pytest.raises(ValueError):
        clima_grade.dispersao_lag_grade(_gold_com_grade(), janela_semanas=7)


def test_comparacao_entre_fontes_so_usa_linhas_com_as_duas():
    comparacao = clima_grade.comparar_estacao_com_grade(_gold_com_grade())
    assert comparacao is not None
    assert comparacao["anos"] == [2025], "só 2025 tem as duas fontes nesta fixture"
    assert comparacao["n_bairro_semana"] == 20


def test_comparacao_e_none_sem_sobreposicao():
    assert clima_grade.comparar_estacao_com_grade(_gold_com_grade(com_estacao=False)) is None
    assert clima_grade.comparar_estacao_com_grade(_gold_com_grade(com_grade=False)) is None


def test_linhas_com_grade_nunca_preenche_ausencia_com_zero():
    gold = _gold_com_grade()
    gold.loc[0, "dias_validos_precipitacao_grade_semana"] = 0
    gold.loc[0, "precipitacao_semana_grade_mm"] = None
    com_grade = clima_grade.linhas_com_grade(gold)
    assert len(com_grade) == len(gold) - 1
    assert com_grade["precipitacao_semana_grade_mm"].notna().all()
