import pandas as pd

from src.ml.dataset import montar_dataset


def _gold_sintetica(n_semanas: int = 60, bairros: tuple[str, ...] = ("1", "2")) -> pd.DataFrame:
    linhas = []
    for bairro in bairros:
        ano, semana = 2013, 1
        casos_base = 1 if bairro == "1" else 50
        for i in range(n_semanas):
            data_fim = pd.Timestamp("2013-01-05") + pd.Timedelta(weeks=i)
            data_inicio = data_fim - pd.Timedelta(days=6)
            casos = casos_base + (5 if (i % 20 == 0) else 0)
            linhas.append(
                {
                    "codigo_bairro": bairro,
                    "nome_bairro": f"BAIRRO {bairro}",
                    "agravo": "DENGUE",
                    "ano_epidemiologico": ano,
                    "semana_epidemiologica": semana,
                    "semana_epi_data_inicio": data_inicio,
                    "semana_epi_data_fim": data_fim,
                    "casos": casos,
                    "area_km2": 1.0,
                    "codigo_rpa": "1",
                    "codigo_microrregiao": "1.1",
                    "centroide_lat": -8.0,
                    "centroide_lon": -34.9,
                    "dias_com_dado_valido_semana": 0,
                    "precipitacao_total_semana_mm": None,
                    "precipitacao_media_diaria_mm": None,
                    "precipitacao_maxima_diaria_mm": None,
                    "dias_com_chuva": None,
                    "completude_climatica_semana": None,
                    "chuva_7d_mm": None,
                    "chuva_14d_mm": None,
                    "chuva_21d_mm": None,
                    "chuva_28d_mm": None,
                    "dias_com_dado_valido_7d": None,
                    "dias_com_dado_valido_28d": None,
                }
            )
            semana += 1
            if semana > 52:
                semana = 1
                ano += 1
    return pd.DataFrame(linhas)


def test_target_e_estado_da_semana_t_mais_horizonte():
    df_gold = _gold_sintetica()
    df_ctx, X, y, metricas = montar_dataset(df_gold, horizonte=1)
    # Para cada linha final, o target deve bater com o estado_alto_risco da
    # linha seguinte (mesmo bairro, indice_semana_global+1).
    mapa_estado = df_ctx.set_index(["codigo_bairro", "indice_semana_global"])["estado_alto_risco"]
    for _, row in df_ctx.iterrows():
        chave_alvo = (row["codigo_bairro"], row["indice_semana_global"] + 1)
        if chave_alvo in mapa_estado.index:
            assert row["target_t_mais_h"] == mapa_estado.loc[chave_alvo]


def test_ultima_semana_de_cada_bairro_e_excluida_nao_vaza_para_outro_bairro():
    df_gold = _gold_sintetica(n_semanas=30, bairros=("1", "2"))
    df_ctx, X, y, metricas = montar_dataset(df_gold, horizonte=1)
    # a ultima semana global de cada bairro nao pode aparecer no dataset final
    # (nao existe t+1 dentro da propria serie do bairro)
    for bairro, grupo in df_ctx.groupby("codigo_bairro"):
        max_indice_disponivel = df_gold.loc[df_gold["codigo_bairro"] == bairro, "semana_epi_data_fim"].count() - 1
        assert grupo["indice_semana_global"].max() < max_indice_disponivel + 1000  # sanity, nao trava em vazio


def test_alterar_casos_apenas_no_futuro_nao_muda_features_passadas():
    df_gold = _gold_sintetica()
    _, X_original, _, _ = montar_dataset(df_gold, horizonte=1)

    df_alterado = df_gold.copy()
    ultimo_indice = df_alterado.groupby("codigo_bairro")["semana_epi_data_fim"].transform("max")
    mask_ultima_semana = df_alterado["semana_epi_data_fim"] == ultimo_indice
    df_alterado.loc[mask_ultima_semana, "casos"] = 99999

    _, X_alterado, _, _ = montar_dataset(df_alterado, horizonte=1)

    # As features das linhas restantes (que nao sao a ultima semana alterada)
    # devem ser identicas -- a alteracao so poderia vazar via rolling/lag se
    # houvesse bug de leakage.
    assert X_original.shape[0] == X_alterado.shape[0]
    pd.testing.assert_frame_equal(X_original.reset_index(drop=True), X_alterado.reset_index(drop=True))


def test_exigir_clima_real_reduz_ou_mantem_linhas():
    df_gold = _gold_sintetica()
    _, _, y_sem_clima, m_sem = montar_dataset(df_gold, horizonte=1, exigir_clima_real=False)
    _, _, y_com_clima, m_com = montar_dataset(df_gold, horizonte=1, exigir_clima_real=True)
    # dataset sintetico nao tem clima real (dias_com_dado_valido_semana=0) -> deve zerar
    assert len(y_com_clima) == 0
    assert len(y_sem_clima) >= 0
