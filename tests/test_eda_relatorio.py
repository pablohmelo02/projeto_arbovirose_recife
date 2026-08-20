from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.eda.relatorio import gerar_relatorio_eda


def _linha(**overrides) -> dict:
    base = {
        "codigo_bairro": "1", "nome_bairro": "BAIRRO A", "agravo": "DENGUE",
        "ano_epidemiologico": 2024, "semana_epidemiologica": 1,
        "semana_epi_data_inicio": pd.Timestamp("2024-01-07"), "semana_epi_data_fim": pd.Timestamp("2024-01-13"),
        "casos": 0, "area_km2": 1.0, "codigo_rpa": "RPA-1", "codigo_microrregiao": "M1",
        "centroide_lat": -8.05, "centroide_lon": -34.9,
        "fonte_clima": None, "codigo_estacao_clima": None, "distancia_estacao_km": None,
        "metodo_associacao_clima": None,
        "precipitacao_total_semana_mm": np.nan, "precipitacao_media_diaria_mm": np.nan,
        "precipitacao_maxima_diaria_mm": np.nan, "dias_com_chuva": np.nan,
        "dias_com_dado_valido_semana": np.nan, "completude_climatica_semana": np.nan,
        "chuva_7d_mm": np.nan, "chuva_14d_mm": np.nan, "chuva_21d_mm": np.nan, "chuva_28d_mm": np.nan,
        "dias_com_dado_valido_7d": np.nan, "dias_com_dado_valido_28d": np.nan,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def df_gold_sintetico() -> pd.DataFrame:
    linhas = []
    for ano in (2013, 2024):
        for semana in (1, 2, 3):
            for bairro, casos_dengue in [("1", 10 + semana * 3), ("2", 5)]:
                for agravo, casos in [("DENGUE", casos_dengue), ("ZIKA", 1), ("CHIKUNGUNYA", 0)]:
                    extra = {}
                    if ano == 2024 and bairro == "1":
                        extra = {
                            "fonte_clima": "CEMADEN", "codigo_estacao_clima": "100",
                            "precipitacao_total_semana_mm": 5.0 * semana,
                            "chuva_7d_mm": 5.0 * semana, "chuva_14d_mm": 8.0 * semana,
                            "chuva_21d_mm": 10.0 * semana, "chuva_28d_mm": 12.0 * semana,
                            "dias_com_dado_valido_semana": 7, "dias_com_dado_valido_7d": 7,
                            "dias_com_dado_valido_28d": 28,
                        }
                    linhas.append(
                        _linha(
                            codigo_bairro=bairro, nome_bairro=f"BAIRRO {bairro}", agravo=agravo,
                            ano_epidemiologico=ano, semana_epidemiologica=semana, casos=casos, **extra,
                        )
                    )
    return pd.DataFrame(linhas)


def test_gerar_relatorio_eda_grava_arquivos_e_resumo(df_gold_sintetico, tmp_path: Path):
    resultado = gerar_relatorio_eda(df_gold_sintetico, tmp_path)

    assert (tmp_path / "sazonalidade_semanal.csv").exists()
    assert (tmp_path / "comparacao_agravos.csv").exists()
    assert (tmp_path / "ranking_bairros_geral.csv").exists()
    assert (tmp_path / "cobertura_climatica_por_ano.csv").exists()
    assert (tmp_path / "correlacoes_lag_dengue.csv").exists()
    assert (tmp_path / "resumo.json").exists()

    assert "resumo_epidemiologico" in resultado
    assert "resumo_climatico" in resultado
    assert len(resultado["achados"]) > 0


def test_gerar_relatorio_eda_achados_distinguem_observacao_de_hipotese(df_gold_sintetico, tmp_path: Path):
    resultado = gerar_relatorio_eda(df_gold_sintetico, tmp_path)
    tipos = {a["tipo"] for a in resultado["achados"]}
    assert tipos.issubset({"observação", "hipótese", "limitação"})
    # deve haver pelo menos uma limitacao mencionando a janela climatica
    limitacoes = [a for a in resultado["achados"] if a["tipo"] == "limitação"]
    assert any("2024" in a["achado"] for a in limitacoes)


def test_gerar_relatorio_eda_nao_gera_hipotese_para_agravo_sem_amostra_confiavel(df_gold_sintetico, tmp_path: Path):
    resultado = gerar_relatorio_eda(df_gold_sintetico, tmp_path)
    achados_zika = [a for a in resultado["achados"] if "ZIKA" in a["achado"]]
    assert achados_zika  # ZIKA nao tem clima real na amostra sintetica -> so observacao de amostra insuficiente
    assert all(a["tipo"] == "observação" for a in achados_zika)
