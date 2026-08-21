import pandas as pd
import pytest

from src.export_powerbi_dataset import (
    COLUNAS_FATO_ASSOCIACAO_CLIMATICA,
    COLUNAS_FATO_BACKTEST,
    COLUNAS_FATO_CLIMA,
    COLUNAS_FATO_EPIDEMIOLOGIA,
    COLUNAS_FATO_PROJECAO_2026,
    montar_dataset_powerbi,
    montar_fact_associacao_climatica,
    montar_fact_projecao_2026,
    montar_semanas_2026_para_dim_tempo,
    validar_star_schema,
)


def _df_gold_2_bairros() -> pd.DataFrame:
    linhas = []
    for codigo, nome, rpa in [("1", "BOA VIAGEM", "1"), ("2", "CASA FORTE", "3")]:
        for semana in (1, 2):
            for agravo in ("DENGUE", "ZIKA", "CHIKUNGUNYA"):
                linhas.append(
                    {
                        "codigo_bairro": codigo, "nome_bairro": nome, "codigo_rpa": rpa,
                        "codigo_microrregiao": "1", "area_km2": 5.0,
                        "centroide_lat": -8.1, "centroide_lon": -34.9,
                        "agravo": agravo, "ano_epidemiologico": 2024, "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=semana - 1),
                        "semana_epi_data_fim": pd.Timestamp("2024-01-07") + pd.Timedelta(weeks=semana - 1),
                        "casos": 1,
                        "populacao_bairro_ano": 100000,
                        "tipo_populacao": "CENSO_OBSERVADO",
                        "densidade_populacional_hab_km2": 20000.0,
                        "incidencia_100k": 1.0, "incidencia_4s_100k": 1.0,
                        "incidencia_8s_100k": 1.0, "incidencia_12s_100k": 1.0, "incidencia_anual_100k": 1.0,
                        "fonte_clima": "CEMADEN", "codigo_estacao_clima": "E1", "distancia_estacao_km": 0.5,
                        "metodo_associacao_clima": "nearest_station",
                        "precipitacao_total_semana_mm": 10.0, "precipitacao_media_diaria_mm": 1.4,
                        "precipitacao_maxima_diaria_mm": 5.0, "dias_com_chuva": 2,
                        "dias_com_dado_valido_semana": 7, "completude_climatica_semana": 1.0,
                        "chuva_7d_mm": 10.0, "chuva_14d_mm": 20.0, "chuva_21d_mm": 30.0, "chuva_28d_mm": 40.0,
                        "dias_com_dado_valido_7d": 7, "dias_com_dado_valido_28d": 28,
                        "fonte_clima_grade": "ERA5", "celula_grade_precipitacao": "c1",
                        "celula_grade_temperatura": "c2", "precipitacao_semana_grade_mm": 8.0,
                        "precipitacao_2s_grade_mm": 15.0, "precipitacao_3s_grade_mm": 22.0,
                        "precipitacao_4s_grade_mm": 29.0, "temperatura_media_grade_c": 27.0,
                        "temperatura_minima_grade_c": 24.0, "temperatura_maxima_grade_c": 31.0,
                        "umidade_relativa_media_grade_pct": 80.0,
                        "dias_validos_precipitacao_grade_semana": 7, "dias_validos_temperatura_grade_semana": 7,
                        "cobertura_grade_semana": 1.0,
                    }
                )
    return pd.DataFrame(linhas)


def _df_backtest_2_bairros() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "codigo_bairro": "1", "ano_epidemiologico": 2024, "semana_epidemiologica": 1,
                "cutoff_epi_year": 2024, "cutoff_epi_week": 1, "ranking": 1, "score_prioridade": 0.9,
                "casos_t": 3, "casos_proximas_3_semanas": 5.0, "estado_alto_risco_t": 1.0,
                "razao_limiar_historico": 1.2, "taxa_crescimento_suavizada": 0.1,
                "onset_real_em_3_semanas": 1, "semanas_ate_onset": 2.0,
                "ranking_baseline_razao_historica": 2, "ranking_baseline_crescimento": 3,
            }
        ]
    )


def _freshness_bruto() -> dict:
    return {
        "gerado_em": "2026-08-21T00:00:00Z",
        "datasets": {
            "epidemiologia": {
                "dataset": "epidemiologia", "fonte": "CKAN", "status": "ATRASADO",
                "atraso_dias": 230, "detalhe": {"bairros": 94},
            }
        },
    }


def test_montar_dataset_powerbi_produz_8_tabelas_sem_forecast():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    assert set(tabelas) == {
        "dim_bairro", "dim_tempo", "dim_agravo",
        "fact_epidemiologia_semanal", "fact_clima_semanal",
        "fact_priorizacao_backtest", "fact_associacao_climatica", "data_freshness",
    }


def test_dim_bairro_tem_uma_linha_por_bairro():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    assert len(tabelas["dim_bairro"]) == 2
    assert not tabelas["dim_bairro"]["codigo_bairro"].duplicated().any()


def test_dim_tempo_tem_id_semana_epi_correto():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    dim_tempo = tabelas["dim_tempo"]
    assert set(dim_tempo["id_semana_epi"]) == {202401, 202402}
    assert len(dim_tempo) == 2


def test_fact_clima_semanal_nao_duplica_por_agravo():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    # 2 bairros x 2 semanas = 4 linhas, mesmo com 3 agravos na Gold de entrada
    assert len(tabelas["fact_clima_semanal"]) == 4
    assert set(tabelas["fact_clima_semanal"].columns) == set(COLUNAS_FATO_CLIMA)


def test_fact_epidemiologia_semanal_preserva_grao_completo():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    # 2 bairros x 2 semanas x 3 agravos = 12 linhas
    assert len(tabelas["fact_epidemiologia_semanal"]) == 12
    assert set(tabelas["fact_epidemiologia_semanal"].columns) == set(COLUNAS_FATO_EPIDEMIOLOGIA)


def test_fact_priorizacao_backtest_tem_id_semana_epi():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    fato = tabelas["fact_priorizacao_backtest"]
    assert fato["id_semana_epi"].iloc[0] == 202401
    assert set(fato.columns) == set(COLUNAS_FATO_BACKTEST)
    assert "score_prioridade" in fato.columns
    assert "probabilidade" not in fato.columns


def test_data_freshness_achata_datasets_sem_o_bloco_detalhe():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    freshness = tabelas["data_freshness"]
    assert len(freshness) == 1
    assert "detalhe" not in freshness.columns
    assert freshness["status"].iloc[0] == "ATRASADO"


def test_validar_star_schema_aprova_dataset_valido():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    metricas = validar_star_schema(tabelas, n_bairros_esperado=2)
    assert metricas["integridade_referencial"] == "ok"
    assert metricas["n_agravos"] == 3


def test_validar_star_schema_rejeita_bairro_fora_da_dimensao():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    tabelas["fact_epidemiologia_semanal"].loc[0, "codigo_bairro"] = "999"
    with pytest.raises(ValueError, match="fora de dim_bairro"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_validar_star_schema_rejeita_chave_duplicada():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    duplicada = pd.concat([tabelas["fact_epidemiologia_semanal"]] * 2, ignore_index=True)
    tabelas["fact_epidemiologia_semanal"] = duplicada
    with pytest.raises(ValueError, match="duplicada"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_validar_star_schema_rejeita_casos_negativo():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    tabelas["fact_epidemiologia_semanal"].loc[0, "casos"] = -1
    with pytest.raises(ValueError, match="casos negativo"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_validar_star_schema_rejeita_populacao_zero_ou_negativa():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    tabelas["fact_epidemiologia_semanal"].loc[0, "populacao_bairro_ano"] = 0
    with pytest.raises(ValueError, match="populacao_bairro_ano"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_montar_dataset_powerbi_e_deterministico():
    t1 = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    t2 = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    for nome in t1:
        pd.testing.assert_frame_equal(t1[nome], t2[nome])


# ---------------------------------------------------------------------------
# fact_associacao_climatica (item 28 do pedido de produto)
# ---------------------------------------------------------------------------
def test_montar_fact_associacao_climatica_tem_as_colunas_esperadas():
    fato = montar_fact_associacao_climatica(_df_gold_2_bairros())
    assert set(fato.columns) == set(COLUNAS_FATO_ASSOCIACAO_CLIMATICA)
    assert set(fato["agravo"]) <= {"DENGUE", "ZIKA", "CHIKUNGUNYA"}
    assert set(fato["ajustada_por_sazonalidade"]) <= {True, False}
    assert fato["lag_semanas"].between(0, 12).all()


def test_montar_fact_associacao_climatica_sem_grade_devolve_vazio():
    df = _df_gold_2_bairros().drop(columns=["fonte_clima_grade", "precipitacao_semana_grade_mm"])
    fato = montar_fact_associacao_climatica(df)
    assert list(fato.columns) == list(COLUNAS_FATO_ASSOCIACAO_CLIMATICA)


def test_fact_associacao_climatica_nao_tem_coluna_de_probabilidade_ou_risco():
    fato = montar_fact_associacao_climatica(_df_gold_2_bairros())
    assert not ({"probabilidade", "risco", "cor_risco", "categoria_risco"} & set(fato.columns))


# ---------------------------------------------------------------------------
# fact_projecao_2026 (item 28 do pedido de produto)
# ---------------------------------------------------------------------------
def _df_forecast_2026() -> pd.DataFrame:
    linhas = []
    for agravo in ("DENGUE", "ZIKA", "CHIKUNGUNYA"):
        for semana, is_observado, ano in ((1, True, 2025), (2, True, 2025), (1, False, 2026), (2, False, 2026)):
            linhas.append(
                {
                    "agravo": agravo, "ano_epidemiologico": ano, "semana_epidemiologica": semana,
                    "semana_epi_data_inicio": pd.Timestamp(f"{ano}-01-01") + pd.Timedelta(weeks=semana - 1),
                    "is_observado": is_observado,
                    "casos": 10,
                    "banda_80_inferior": None if is_observado else 5,
                    "banda_80_superior": None if is_observado else 15,
                    "banda_95_inferior": None if is_observado else 2,
                    "banda_95_superior": None if is_observado else 20,
                }
            )
    return pd.DataFrame(linhas)


def test_montar_fact_projecao_2026_tem_id_semana_epi_e_colunas_esperadas():
    fato = montar_fact_projecao_2026(_df_forecast_2026())
    assert set(fato.columns) == set(COLUNAS_FATO_PROJECAO_2026)
    assert set(fato["id_semana_epi"]) == {202501, 202502, 202601, 202602}
    assert fato["is_observado"].sum() == 6  # 3 agravos x 2 semanas observadas


def test_montar_semanas_2026_para_dim_tempo_deriva_data_fim():
    extra = montar_semanas_2026_para_dim_tempo(_df_forecast_2026())
    linha = extra[(extra["ano_epidemiologico"] == 2026) & (extra["semana_epidemiologica"] == 1)].iloc[0]
    assert linha["semana_epi_data_fim"] == linha["semana_epi_data_inicio"] + pd.Timedelta(days=6)
    assert set(extra["ano_epidemiologico"]) == {2025, 2026}


def test_montar_dataset_powerbi_com_forecast_produz_9_tabelas_e_dim_tempo_inclui_2026():
    tabelas = montar_dataset_powerbi(
        _df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto(), df_forecast=_df_forecast_2026()
    )
    assert "fact_projecao_2026" in tabelas
    assert 202601 in set(tabelas["dim_tempo"]["id_semana_epi"])
    assert not tabelas["dim_tempo"]["id_semana_epi"].duplicated().any()


def test_montar_dataset_powerbi_sem_forecast_nao_inclui_fact_projecao_2026():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    assert "fact_projecao_2026" not in tabelas


def test_validar_star_schema_aceita_dataset_com_projecao_2026():
    tabelas = montar_dataset_powerbi(
        _df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto(), df_forecast=_df_forecast_2026()
    )
    metricas = validar_star_schema(tabelas, n_bairros_esperado=2)
    assert metricas["integridade_referencial"] == "ok"
    assert "linhas_fact_projecao_2026" in metricas
    assert "linhas_fact_associacao_climatica" in metricas


def test_validar_star_schema_rejeita_fact_projecao_2026_com_casos_negativo():
    tabelas = montar_dataset_powerbi(
        _df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto(), df_forecast=_df_forecast_2026()
    )
    tabelas["fact_projecao_2026"].loc[0, "casos"] = -1
    with pytest.raises(ValueError, match="fact_projecao_2026"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_validar_star_schema_rejeita_fact_projecao_2026_com_chave_duplicada():
    tabelas = montar_dataset_powerbi(
        _df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto(), df_forecast=_df_forecast_2026()
    )
    duplicada = pd.concat([tabelas["fact_projecao_2026"]] * 2, ignore_index=True)
    tabelas["fact_projecao_2026"] = duplicada
    with pytest.raises(ValueError, match="fact_projecao_2026"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_validar_star_schema_rejeita_lag_fora_da_faixa_0_a_12():
    tabelas = montar_dataset_powerbi(_df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto())
    if tabelas["fact_associacao_climatica"].empty:
        pytest.skip("fixture não gerou linhas de associação climática")
    tabelas["fact_associacao_climatica"].loc[tabelas["fact_associacao_climatica"].index[0], "lag_semanas"] = 99
    with pytest.raises(ValueError, match="lag_semanas"):
        validar_star_schema(tabelas, n_bairros_esperado=2)


def test_validar_star_schema_rejeita_probabilidade_em_fact_projecao_2026():
    tabelas = montar_dataset_powerbi(
        _df_gold_2_bairros(), _df_backtest_2_bairros(), _freshness_bruto(), df_forecast=_df_forecast_2026()
    )
    tabelas["fact_projecao_2026"]["probabilidade"] = 0.5
    with pytest.raises(ValueError, match="probabilidade/risco"):
        validar_star_schema(tabelas, n_bairros_esperado=2)
