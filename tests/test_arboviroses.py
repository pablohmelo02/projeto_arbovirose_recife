import pandas as pd

from src.silver.arboviroses import transformar_fato
from src.silver.schema import COLUNAS_SILVER_ARBOVIROSES


def _df_era_nova() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "NU_NOTIFIC": ["1", "2", "3"],
            "TP_NOT": ["2", "2", "2"],
            "ID_AGRAVO": ["A90", "A90", "A90"],
            "DT_NOTIFIC": ["04/03/2025", "05/03/2025", ""],
            "NU_ANO": ["2025", "2025", "2025"],
            "SEM_NOT": ["202510", "202510", "202599"],
            "DT_SIN_PRI": ["02/03/2025", "", ""],
            "SEM_PRI": ["202510", "", ""],
            "ID_BAIRRO": ["24", "24", "24"],
            "NM_BAIRRO": [" pina ", "PINA", "Pina"],
            "ID_DISTRIT": ["122", "122", "122"],
            "ID_MUNICIP": ["261160", "261160", "261160"],
            "SG_UF": ["26", "26", "26"],
            "CLASSI_FIN": ["10.0", "10.0", "10.0"],
            "EVOLUCAO": ["1", "1", "1"],
            "HOSPITALIZ": ["2", "2", "2"],
        }
    )


def _df_era_antiga() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nu_notificacao": ["10", "11"],
            "tp_notificacao": ["2", "2"],
            "co_cid": ["A90", "A90"],
            "dt_notificacao": ["2013/01/04 00:00:00", "2013/01/05 00:00:00"],
            "notificacao_ano": ["2013", "2013"],
            "ds_semana_notificacao": ["201301", "201302"],
            "no_bairro_residencia": ["BOA VIAGEM", "BOA VIAGEM"],
            "co_bairro_residencia": ["58", "58"],
        }
    )


def test_transformar_fato_era_nova_mapeia_aliases_corretamente():
    df_valido, df_rejeitado, metricas = transformar_fato(
        _df_era_nova(), "DENGUE", "resource-1", 2025, "run-1"
    )

    assert list(df_valido.columns) == list(COLUNAS_SILVER_ARBOVIROSES)
    assert metricas["linhas_lidas"] == 3
    assert metricas["linhas_validas"] == 3
    assert metricas["linhas_rejeitadas"] == 0
    assert not metricas["arquivo_rejeitado_integralmente"]

    assert df_valido["nome_bairro"].tolist() == ["PINA", "PINA", "PINA"]
    assert df_valido["classificacao_final"].tolist() == ["10", "10", "10"]
    assert df_valido.loc[0, "data_notificacao"] == pd.Timestamp("2025-03-04")
    assert pd.isna(df_valido.loc[2, "data_notificacao"])
    assert metricas["semanas_epidemiologicas_invalidas"] == 1  # "202599"


def test_transformar_fato_era_antiga_mapeia_aliases_corretamente():
    df_valido, _, metricas = transformar_fato(
        _df_era_antiga(), "DENGUE", "resource-2", 2013, "run-1"
    )

    assert metricas["linhas_validas"] == 2
    assert df_valido["nome_bairro"].tolist() == ["BOA VIAGEM", "BOA VIAGEM"]
    assert df_valido.loc[0, "data_notificacao"] == pd.Timestamp("2013-01-04")
    assert df_valido["_source_year"].tolist() == [2013, 2013]
    assert df_valido["_ingestion_run_id"].tolist() == ["run-1", "run-1"]


def test_transformar_fato_rejeita_arquivo_inteiro_quando_codigo_agravo_sistematicamente_errado():
    # Reproduz o caso real do recurso "Zika 2021": 100% das linhas com
    # codigo_agravo de Chikungunya (A92.0) em um recurso classificado como Zika.
    df_contaminado = _df_era_nova().copy()
    df_contaminado["ID_AGRAVO"] = "A92.0"

    df_valido, df_rejeitado, metricas = transformar_fato(
        df_contaminado, "ZIKA", "resource-zika-2021", 2021, "run-1"
    )

    assert metricas["arquivo_rejeitado_integralmente"] is True
    assert metricas["linhas_validas"] == 0
    assert metricas["linhas_rejeitadas"] == 3
    assert df_valido.empty
    assert (df_rejeitado["_motivo_rejeicao"].str.contains("rejeitado integralmente")).all()


def test_transformar_fato_rejeita_linha_sem_id_notificacao():
    df = _df_era_nova().copy()
    df.loc[0, "NU_NOTIFIC"] = ""

    df_valido, df_rejeitado, metricas = transformar_fato(df, "DENGUE", "resource-3", 2025, "run-1")

    assert metricas["linhas_validas"] == 2
    assert metricas["linhas_rejeitadas"] == 1
    assert df_rejeitado.iloc[0]["_motivo_rejeicao"] == "id_notificacao ausente"


def test_transformar_fato_coluna_ausente_vira_nula_sem_quebrar():
    df = _df_era_nova().drop(columns=["HOSPITALIZ"])
    df_valido, _, metricas = transformar_fato(df, "DENGUE", "resource-4", 2025, "run-1")

    assert metricas["linhas_validas"] == 3
    assert df_valido["hospitalizado"].isna().all()
