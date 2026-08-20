import numpy as np
import pandas as pd

from src.ml.features import construir_indice_semana_global
from src.ml.onset import construir_target_onset
from src.ml.target import calcular_estado_alto_risco


def _semanal(bairro: str, casos: list[int], ano_inicio: int = 2013) -> pd.DataFrame:
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
            }
        )
        semana += 1
        if semana > 52:
            semana = 1
            ano += 1
    return pd.DataFrame(linhas)


def _preparar(casos, bairro="1"):
    df = _semanal(bairro, casos)
    df_estado = calcular_estado_alto_risco(df)
    return construir_indice_semana_global(df_estado)


def test_onset_marca_so_a_primeira_semana_do_episodio():
    # historico estavel (casos=1) para ter limiar baixo definido, depois
    # 3 semanas consecutivas de risco elevado (21,22,23), seguido de queda.
    casos = [1] * 60 + [50, 60, 55, 1, 1]
    df = _preparar(casos)
    resultado = construir_target_onset(df, horizontes=(1,))

    # localizar indices das semanas de pico (60,61,62 no indice global)
    pico_idx = list(range(60, 63))
    estados = resultado.set_index("indice_semana_global").loc[pico_idx, "estado_alto_risco"]
    assert (estados == 1).all()  # confirma que as 3 semanas sao de fato risco elevado

    # a linha ANTES do inicio (indice 59) deve ter target_onset_h1=1 (onset em 60)
    linha_59 = resultado[resultado["indice_semana_global"] == 59].iloc[0]
    assert linha_59["target_onset_h1"] == 1.0

    # a linha DENTRO do episodio (indice 60, prevendo indice 61) NAO deve
    # contar como onset -- 61 e continuacao, nao um novo inicio
    linha_60 = resultado[resultado["indice_semana_global"] == 60].iloc[0]
    assert linha_60["target_onset_h1"] == 0.0

    linha_61 = resultado[resultado["indice_semana_global"] == 61].iloc[0]
    assert linha_61["target_onset_h1"] == 0.0


def test_onset_nao_marca_semanas_de_continuacao_mesmo_com_horizonte_maior():
    casos = [1] * 60 + [50, 60, 55, 60, 1]
    df = _preparar(casos)
    resultado = construir_target_onset(df, horizontes=(3,))
    # indice 60 = inicio do episodio (onset). indice 59 prevendo ate 62 (h=3)
    # deve capturar o onset em 60.
    linha_59 = resultado[resultado["indice_semana_global"] == 59].iloc[0]
    assert linha_59["target_onset_h3"] == 1.0
    # mas a linha 60 (ja dentro do episodio), prevendo 61-63, nao deve
    # contar continuacao como onset novo
    linha_60 = resultado[resultado["indice_semana_global"] == 60].iloc[0]
    assert linha_60["target_onset_h3"] == 0.0


def test_onset_com_gap_conta_como_novo_episodio():
    # episodio A: indices 60-61 ; volta a baixo em 62-63 ; episodio B comeca em 64
    casos = [1] * 60 + [50, 55, 1, 1, 60, 55, 1]
    df = _preparar(casos)
    resultado = construir_target_onset(df, horizontes=(3,))
    # linha no indice 61 (dentro do episodio A), prevendo 62,63,64 (h=3)
    # deve capturar o onset do episodio B em 64
    linha_61 = resultado[resultado["indice_semana_global"] == 61].iloc[0]
    assert linha_61["target_onset_h3"] == 1.0


def test_target_indefinido_quando_historico_insuficiente():
    casos = [1, 2, 3, 5, 8]  # historico curto demais para definir limiar
    df = _preparar(casos)
    resultado = construir_target_onset(df, horizontes=(1,))
    # com tao pouco historico, os primeiros anos ficam com estado indefinido
    assert resultado["target_onset_h1"].isna().any()


def test_alterar_casos_apenas_no_futuro_nao_muda_onset_de_linhas_anteriores():
    casos_originais = [1] * 60 + [1, 1, 1, 1, 1]
    casos_alterados = casos_originais.copy()
    casos_alterados[-1] = 99999  # altera so a ultima semana
    df_original = _preparar(casos_originais)
    df_alterado = _preparar(casos_alterados)

    onset_original = construir_target_onset(df_original, horizontes=(1, 2, 3))
    onset_alterado = construir_target_onset(df_alterado, horizontes=(1, 2, 3))

    colunas = ["target_onset_h1", "target_onset_h2", "target_onset_h3"]
    # todas as linhas cujo target nao poderia depender da ultima semana
    # alterada precisam ter t+3 estritamente menor que o ultimo indice
    # (a janela do maior horizonte, h=3, nao pode alcancar a semana alterada)
    limite = onset_original["indice_semana_global"].max() - 3 - 1
    original_seguro = onset_original[onset_original["indice_semana_global"] <= limite][colunas].reset_index(drop=True)
    alterado_seguro = onset_alterado[onset_alterado["indice_semana_global"] <= limite][colunas].reset_index(drop=True)
    pd.testing.assert_frame_equal(original_seguro, alterado_seguro)


def test_dois_bairros_nao_se_misturam_no_onset():
    casos_x = [1] * 60 + [50, 55, 1, 1, 1]
    casos_y = [1] * 60 + [1, 1, 1, 1, 1]
    df_x = _preparar(casos_x, bairro="X")
    df_y = _preparar(casos_y, bairro="Y")
    df = pd.concat([df_x, df_y], ignore_index=True)
    df = construir_indice_semana_global(df.drop(columns=["indice_semana_global"]))
    resultado = construir_target_onset(df, horizontes=(1,))

    onset_x_pos59 = resultado[(resultado["codigo_bairro"] == "X") & (resultado["indice_semana_global"] == 59)]
    onset_y_pos59 = resultado[(resultado["codigo_bairro"] == "Y") & (resultado["indice_semana_global"] == 59)]
    assert onset_x_pos59["target_onset_h1"].iloc[0] == 1.0
    assert onset_y_pos59["target_onset_h1"].iloc[0] == 0.0
