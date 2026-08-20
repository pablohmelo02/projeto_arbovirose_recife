import numpy as np
import pandas as pd
import pytest

from src.ml.evidence_validation import (
    agregar_recall_por_grupo,
    bootstrap_delta,
    bootstrap_mediana,
    bootstrap_recall,
    calcular_carga_priorizacao,
    carregar_artefatos_evidencia,
    leave_one_group_out,
    serie_jaccard_consecutivo,
)


def test_bootstrap_recall_observado_bate_com_media_simples():
    detectado = np.array([1, 1, 0, 0, 1, 0, 1, 0, 1, 0], dtype=float)
    resultado = bootstrap_recall(detectado, n_reamostragens=500, seed=1)
    assert resultado["observado"] == detectado.mean()
    assert resultado["n"] == 10
    assert resultado["ic_baixo"] <= resultado["observado"] <= resultado["ic_alto"]


def test_bootstrap_recall_e_deterministico_com_mesma_seed():
    detectado = np.array([1, 0, 1, 1, 0, 0, 1, 0, 0, 1], dtype=float)
    r1 = bootstrap_recall(detectado, n_reamostragens=500, seed=42)
    r2 = bootstrap_recall(detectado, n_reamostragens=500, seed=42)
    assert r1 == r2


def test_bootstrap_recall_vazio_nao_quebra():
    resultado = bootstrap_recall(np.array([]), n_reamostragens=100, seed=1)
    assert resultado["n"] == 0
    assert resultado["observado"] is None


def test_bootstrap_recall_todos_positivos_tem_ic_estreito_no_topo():
    detectado = np.ones(50)
    resultado = bootstrap_recall(detectado, n_reamostragens=500, seed=1)
    assert resultado["observado"] == 1.0
    assert resultado["ic_baixo"] == 1.0
    assert resultado["ic_alto"] == 1.0


def test_bootstrap_delta_positivo_quando_a_e_melhor_que_b():
    a = np.array([1, 1, 1, 1, 0, 0, 0, 0, 1, 1], dtype=float)  # 60%
    b = np.array([0, 0, 1, 0, 0, 0, 0, 0, 1, 0], dtype=float)  # 20%
    resultado = bootstrap_delta(a, b, n_reamostragens=1000, seed=7)
    assert resultado["observado"] == pytest_approx(0.4)
    assert resultado["ic_baixo"] < resultado["observado"] < resultado["ic_alto"] or resultado["ic_baixo"] == resultado["observado"]
    # a diferenca real (0.4) deve estar plausivelmente dentro do IC
    assert resultado["ic_baixo"] <= 0.4 <= resultado["ic_alto"]


def test_bootstrap_delta_pareado_usa_mesmos_indices_dos_dois_lados():
    # se a e b forem identicos, delta deve ser exatamente 0 em toda reamostragem
    a = np.array([1, 0, 1, 0, 1, 1, 0, 0, 1, 0], dtype=float)
    resultado = bootstrap_delta(a, a.copy(), n_reamostragens=500, seed=3)
    assert resultado["observado"] == 0.0
    assert resultado["ic_baixo"] == 0.0
    assert resultado["ic_alto"] == 0.0


def test_bootstrap_delta_exige_mesmo_tamanho():
    import pytest

    with pytest.raises(ValueError):
        bootstrap_delta(np.array([1, 0]), np.array([1, 0, 1]))


def test_bootstrap_cluster_agrupa_por_cluster_id():
    # 2 clusters, cada um com resultados bem diferentes -- cluster bootstrap
    # deve produzir uma distribuicao mais dispersa que o bootstrap simples
    detectado = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=float)
    clusters = np.array(["A", "A", "A", "A", "A", "B", "B", "B", "B", "B"])
    resultado_cluster = bootstrap_recall(detectado, cluster_ids=clusters, n_reamostragens=1000, seed=5)
    resultado_simples = bootstrap_recall(detectado, n_reamostragens=1000, seed=5)
    largura_cluster = resultado_cluster["ic_alto"] - resultado_cluster["ic_baixo"]
    largura_simples = resultado_simples["ic_alto"] - resultado_simples["ic_baixo"]
    assert largura_cluster >= largura_simples


def test_bootstrap_mediana_lead_time():
    leads = np.array([1, 2, 2, 3, 3, 3, 4, 4, 5], dtype=float)
    resultado = bootstrap_mediana(leads, n_reamostragens=500, seed=9)
    assert resultado["observado"] == 3.0
    assert resultado["ic_baixo"] <= 3.0 <= resultado["ic_alto"]


def pytest_approx(valor):
    import pytest

    return pytest.approx(valor)


def _master_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "inicio_ano": [2023, 2023, 2024, 2024, 2024, 2025],
            "codigo_rpa": ["1", "1", "2", "2", "1", "2"],
            "detectado_modelo_k5": [1, 0, 1, 1, 0, 1],
            "detectado_baseline_k5": [0, 0, 1, 0, 0, 1],
        }
    )


def test_agregar_recall_por_grupo_calcula_media_e_n_por_ano():
    master = _master_sintetico()
    resultado = agregar_recall_por_grupo(master, "inicio_ano", ["detectado_modelo_k5", "detectado_baseline_k5"])
    linha_2023 = resultado[resultado["inicio_ano"] == 2023].iloc[0]
    assert linha_2023["n_episodios"] == 2
    assert linha_2023["detectado_modelo_k5"] == 0.5
    linha_2024 = resultado[resultado["inicio_ano"] == 2024].iloc[0]
    assert linha_2024["n_episodios"] == 3
    assert linha_2024["detectado_modelo_k5"] == pytest_approx(2 / 3)


def test_agregar_recall_por_grupo_funciona_por_rpa():
    master = _master_sintetico()
    resultado = agregar_recall_por_grupo(master, "codigo_rpa", ["detectado_modelo_k5"])
    rpa1 = resultado[resultado["codigo_rpa"] == "1"].iloc[0]
    assert rpa1["n_episodios"] == 3
    assert rpa1["detectado_modelo_k5"] == pytest_approx(1 / 3)


def test_leave_one_group_out_exclui_um_ano_por_vez_sem_retreinar():
    master = _master_sintetico()
    resultado = leave_one_group_out(master, "inicio_ano", "detectado_modelo_k5", "detectado_baseline_k5")
    assert set(resultado["inicio_ano_excluido"]) == {2023, 2024, 2025}
    linha_sem_2023 = resultado[resultado["inicio_ano_excluido"] == 2023].iloc[0]
    # excluindo 2023 (2 episodios), sobram os 4 de 2024/2025
    assert linha_sem_2023["n_episodios"] == 4
    esperado = master.loc[master["inicio_ano"] != 2023, "detectado_modelo_k5"].mean()
    assert linha_sem_2023["recall_modelo"] == esperado


def test_carregar_artefatos_evidencia_sem_arquivos_nao_quebra(tmp_path):
    resultado = carregar_artefatos_evidencia(tmp_path)
    assert resultado["resumo"] is None
    assert resultado["por_ano"] is None
    assert resultado["master_episodios"] is None


def test_carregar_artefatos_evidencia_le_csvs_existentes(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    df.to_csv(tmp_path / "evidence_por_ano.csv", index=False)
    resultado = carregar_artefatos_evidencia(tmp_path)
    assert resultado["por_ano"] is not None
    pd.testing.assert_frame_equal(resultado["por_ano"], df)
    assert resultado["por_rpa"] is None


def _ranking_com_onset() -> pd.DataFrame:
    # 2 semanas x 4 bairros; posicao 1 = maior risco naquela semana
    return pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "D", "A", "B", "C", "D"],
            "indice_semana_alvo": [1, 1, 1, 1, 2, 2, 2, 2],
            "posicao": [1, 2, 3, 4, 4, 3, 2, 1],
            "onset_futuro": [1, 0, 0, 0, 0, 0, 1, 1],
        }
    )


def test_carga_priorizacao_conta_priorizacoes_sem_episodio_futuro():
    tabela = calcular_carga_priorizacao(_ranking_com_onset(), k_valores=(2,))
    linha = tabela.iloc[0]
    # Top-2: semana 1 -> A(1), B(0); semana 2 -> D(1), C(1)
    assert linha["priorizacoes_total"] == 4
    assert linha["n_semanas_avaliadas"] == 2
    assert linha["priorizacoes_com_episodio_futuro"] == 3
    assert linha["priorizacoes_sem_episodio_futuro"] == 1
    assert linha["pct_priorizacoes_sem_episodio_futuro"] == 25.0
    assert linha["bairros_priorizados_por_semana_medio"] == 2.0


def test_carga_priorizacao_cresce_com_k_e_nunca_excede_o_total():
    tabela = calcular_carga_priorizacao(_ranking_com_onset(), k_valores=(1, 2, 4)).set_index("k")
    assert tabela.loc[1, "priorizacoes_total"] == 2
    assert tabela.loc[4, "priorizacoes_total"] == 8
    assert tabela["priorizacoes_total"].is_monotonic_increasing
    soma = tabela["priorizacoes_com_episodio_futuro"] + tabela["priorizacoes_sem_episodio_futuro"]
    assert (soma == tabela["priorizacoes_total"]).all()


def test_carga_priorizacao_nao_forca_alvo_indefinido_para_zero():
    df = _ranking_com_onset()
    df.loc[0, "onset_futuro"] = np.nan
    tabela = calcular_carga_priorizacao(df, k_valores=(2,))
    linha = tabela.iloc[0]
    assert linha["priorizacoes_alvo_indefinido"] == 1
    # o indefinido sai do numerador E do denominador (nunca conta como "sem episodio")
    assert linha["priorizacoes_com_episodio_futuro"] + linha["priorizacoes_sem_episodio_futuro"] == 3
    assert linha["priorizacoes_sem_episodio_futuro"] == 1


def test_serie_jaccard_top_k_identico_e_totalmente_diferente():
    identico = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "A", "B"],
            "indice_semana_alvo": [1, 1, 2, 2],
            "posicao": [1, 2, 1, 2],
        }
    )
    serie = serie_jaccard_consecutivo(identico, k=2)
    assert len(serie) == 1
    assert serie.iloc[0]["jaccard"] == 1.0

    trocado = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "D"],
            "indice_semana_alvo": [1, 1, 2, 2],
            "posicao": [1, 2, 1, 2],
        }
    )
    serie2 = serie_jaccard_consecutivo(trocado, k=2)
    assert serie2.iloc[0]["jaccard"] == 0.0
    assert serie2.iloc[0]["n_bairros_mantidos"] == 0


def test_serie_jaccard_ignora_semanas_nao_consecutivas():
    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "A", "B", "A", "C"],
            "indice_semana_alvo": [1, 1, 2, 2, 7, 7],
            "posicao": [1, 2, 1, 2, 1, 2],
        }
    )
    serie = serie_jaccard_consecutivo(df, k=2)
    # so o par (1,2) e consecutivo; a lacuna 2->7 nunca e tratada como consecutiva
    assert list(serie["indice_semana_alvo"]) == [1]


def test_serie_jaccard_media_bate_com_estabilidade_ranking():
    from src.ml.ranking import estabilidade_ranking

    df = pd.DataFrame(
        {
            "codigo_bairro": ["A", "B", "C", "A", "C", "D", "B", "C", "D"],
            "indice_semana_alvo": [1, 1, 1, 2, 2, 2, 3, 3, 3],
            "posicao": [1, 2, 3, 1, 2, 3, 1, 2, 3],
        }
    )
    serie = serie_jaccard_consecutivo(df, k=2)
    resumo = estabilidade_ranking(df, k=2)
    assert resumo["n_pares_consecutivos"] == len(serie)
    assert resumo["jaccard_medio"] == pytest.approx(serie["jaccard"].mean())
