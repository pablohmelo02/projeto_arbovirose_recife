import numpy as np
import pandas as pd

from src.ml.features import construir_indice_semana_global
from src.ml.onset_incidencia import construir_episodios_incidencia, construir_target_onset_incidencia
from src.ml.target_incidencia import calcular_estado_alto_risco_incidencia


def _semanal(bairro: str, casos: list[int], populacao: int = 10000, ano_inicio: int = 2013) -> pd.DataFrame:
    linhas = []
    ano, semana = ano_inicio, 1
    for i, c in enumerate(casos):
        data_fim = pd.Timestamp("2013-01-05") + pd.Timedelta(weeks=i)
        data_inicio = data_fim - pd.Timedelta(days=6)
        linhas.append(
            {
                "codigo_bairro": bairro,
                "nome_bairro": f"BAIRRO {bairro}",
                "ano_epidemiologico": ano,
                "semana_epidemiologica": semana,
                "semana_epi_data_inicio": data_inicio,
                "semana_epi_data_fim": data_fim,
                "casos": c,
                "populacao_bairro_ano": populacao,
                "incidencia_100k": 100000 * c / populacao,
            }
        )
        semana += 1
        if semana > 52:
            semana = 1
            ano += 1
    return pd.DataFrame(linhas)


def _preparar(casos, bairro="1", populacao=10000):
    df = _semanal(bairro, casos, populacao=populacao)
    df_estado = calcular_estado_alto_risco_incidencia(df, coluna_valor="incidencia_100k")
    return construir_indice_semana_global(df_estado)


def test_onset_incidencia_marca_so_a_primeira_semana_do_episodio():
    # historico estavel (baixa incidencia) seguido de 3 semanas consecutivas de alta
    casos = [1] * 52 * 3 + [50, 50, 50] + [1] * 10
    df = _preparar(casos)
    resultado = construir_target_onset_incidencia(df, horizontes=(3,))
    idx_pico = len(casos) - 13  # primeira das 3 semanas de pico (52*3)
    # a segunda e terceira semanas do episodio (continuacao) nao sao onset
    episodios = construir_episodios_incidencia(df)
    inicios = set(episodios["inicio_indice"])
    assert idx_pico in inicios
    assert (idx_pico + 1) not in inicios
    assert (idx_pico + 2) not in inicios


def test_episodios_incidencia_preserva_casos_absolutos_reais():
    casos = [1] * 60 + [80, 80]
    df = _preparar(casos, populacao=10000)
    episodios = construir_episodios_incidencia(df)
    assert len(episodios) >= 1
    maior = episodios.sort_values("casos_pico", ascending=False).iloc[0]
    assert maior["casos_pico"] == 80.0


def test_target_onset_incidencia_leakage_futuro_nao_afeta_passado():
    casos = [1] * 100
    df = _preparar(casos)
    resultado_original = construir_target_onset_incidencia(df, horizontes=(3,))
    valores_originais = resultado_original.loc[:50, "target_onset_incidencia_h3"].copy()

    df_alterado = df.copy()
    df_alterado.loc[80:, "incidencia_100k"] = 99999.0
    df_alterado.loc[80:, "estado_alto_risco_incidencia"] = 1.0
    resultado_alterado = construir_target_onset_incidencia(df_alterado, horizontes=(3,))
    valores_alterados = resultado_alterado.loc[:50, "target_onset_incidencia_h3"]

    pd.testing.assert_series_equal(valores_originais, valores_alterados, check_names=False)


def test_bairro_ja_ativo_nao_gera_novo_onset_por_continuacao():
    casos = [1] * 52 + [40] * 5  # 5 semanas consecutivas de risco elevado
    df = _preparar(casos)
    episodios = construir_episodios_incidencia(df)
    # um unico episodio de 5 semanas, nao 5 episodios/onsets separados
    assert len(episodios) == 1
    assert episodios.iloc[0]["duracao_semanas"] == 5
