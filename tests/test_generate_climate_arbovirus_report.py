"""`gerar_relatorio` nunca deve levantar exceção e deve conter as seções
esperadas -- os números em si já são exercitados por
`tests/test_associacao_climatica.py`."""
from __future__ import annotations

import pandas as pd

from src.generate_climate_arbovirus_report import gerar_relatorio


def _gold_sintetica() -> pd.DataFrame:
    linhas = []
    for ano in (2024, 2025):
        for semana in range(1, 6):
            inicio = pd.Timestamp(f"{ano}-01-07") + pd.Timedelta(weeks=semana - 1)
            for agravo, casos in (("DENGUE", 10 + semana), ("ZIKA", 2), ("CHIKUNGUNYA", 1)):
                linhas.append(
                    {
                        "codigo_bairro": "1",
                        "nome_bairro": "BAIRRO A",
                        "agravo": agravo,
                        "ano_epidemiologico": ano,
                        "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": inicio,
                        "casos": casos,
                        "populacao_bairro_ano": 100_000.0,
                        "dias_validos_precipitacao_grade_semana": 7,
                        "precipitacao_semana_grade_mm": 5.0 * semana,
                        "temperatura_media_grade_c": 27.0,
                        "temperatura_minima_grade_c": 23.0,
                        "temperatura_maxima_grade_c": 31.0,
                        "umidade_relativa_media_grade_pct": 80.0,
                    }
                )
    return pd.DataFrame(linhas)


def test_gerar_relatorio_nao_levanta_erro_e_tem_as_secoes_esperadas():
    conteudo = gerar_relatorio(_gold_sintetica())
    assert "## Dengue" in conteudo
    assert "## Zika" in conteudo
    assert "## Chikungunya" in conteudo
    assert "## Limitações" in conteudo
    assert "causalidade" in conteudo.lower()


def test_gerar_relatorio_com_gold_vazia_nao_levanta_erro():
    vazio = pd.DataFrame(columns=["agravo", "casos", "ano_epidemiologico", "semana_epidemiologica"])
    conteudo = gerar_relatorio(vazio)
    assert "## Dengue" in conteudo
