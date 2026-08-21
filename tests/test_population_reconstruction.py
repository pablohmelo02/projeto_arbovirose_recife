import json

import pandas as pd
import pytest

from src.population.reconstruction import (
    carregar_checkpoint_censo2022,
    carregar_checkpoint_cievs,
    carregar_serie_municipal,
    comparar_metodos_pos_censo,
    construir_serie_populacao,
    escolher_metodo_pos_censo,
    identificar_areas_atipicas,
    normalizar_nome_bairro,
    reconstruir_segmento_cagr,
    validar_reconstrucao_sem_checkpoint_intermediario,
)


def _df_territorio_3() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codigo_bairro": ["1", "2", "3"],
            "nome_bairro": ["BOA VIAGEM", "CASA FORTE", "ALTO SANTA TEREZINHA"],
        }
    )


# --------------------------------------------------------------------------
# normalizacao / crosswalk
# --------------------------------------------------------------------------


def test_normalizar_nome_bairro_remove_acento_e_pontuacao():
    assert normalizar_nome_bairro("Água Fria") == "AGUA FRIA"
    assert normalizar_nome_bairro("Pau-Ferro") == "PAU FERRO"
    assert normalizar_nome_bairro("São José") == "SAO JOSE"


def test_normalizar_nome_bairro_aplica_crosswalk_documentado():
    assert normalizar_nome_bairro("Alto Sta Teresinha") == "ALTO SANTA TEREZINHA"
    assert normalizar_nome_bairro("Sítio dos Pintos - São Brás") == "SITIO DOS PINTOS"


# --------------------------------------------------------------------------
# carregamento de checkpoints + relatorio de discrepancias
# --------------------------------------------------------------------------


def test_carregar_checkpoint_cievs_junta_bairros_sem_discrepancia(tmp_path):
    bruto = {
        "bairros": [
            {"nome_bairro_normalizado": "BOA VIAGEM", "populacao_por_ano": {"2010": 100, "2017": 150}},
            {"nome_bairro_normalizado": "CASA FORTE", "populacao_por_ano": {"2010": 200, "2017": 250}},
            {"nome_bairro_normalizado": "ALTO SANTA TEREZINHA", "populacao_por_ano": {"2010": 50, "2017": 60}},
        ]
    }
    caminho = tmp_path / "cievs.json"
    caminho.write_text(json.dumps(bruto), encoding="utf-8")

    df, discrepancias = carregar_checkpoint_cievs(caminho, _df_territorio_3())

    assert len(discrepancias) == 0
    assert set(df["codigo_bairro"]) == {"1", "2", "3"}
    assert df[(df["codigo_bairro"] == "1") & (df["ano"] == 2010)]["populacao"].iloc[0] == 100


def test_carregar_checkpoint_cievs_reporta_discrepancia_sem_descartar_silenciosamente(tmp_path):
    bruto = {
        "bairros": [
            {"nome_bairro_normalizado": "BOA VIAGEM", "populacao_por_ano": {"2010": 100}},
            {"nome_bairro_normalizado": "BAIRRO INEXISTENTE", "populacao_por_ano": {"2010": 999}},
        ]
    }
    caminho = tmp_path / "cievs.json"
    caminho.write_text(json.dumps(bruto), encoding="utf-8")

    _, discrepancias = carregar_checkpoint_cievs(caminho, _df_territorio_3())

    tipos = set(discrepancias["tipo"])
    assert "bairro_territorio_sem_checkpoint" in tipos
    assert "checkpoint_sem_bairro_territorio" in tipos
    assert "BAIRRO INEXISTENTE" in discrepancias["nome"].tolist()


def test_carregar_checkpoint_censo2022_junta_por_nome_normalizado(tmp_path):
    caminho = tmp_path / "censo2022.csv"
    pd.DataFrame(
        {
            "CD_BAIRRO": ["1000000001", "1000000002"],
            "NM_BAIRRO": ["Boa Viagem", "Casa Forte"],
            "nome_bairro_normalizado": ["BOA VIAGEM", "CASA FORTE"],
            "NM_NU": ["RPA 01", "RPA 03"],
            "AREA_KM2": ["1,0", "2,0"],
            "v0001": ["1000", "2000"],
            "v0002": ["1", "1"],
            "v0003": ["1", "1"],
            "v0004": ["0", "0"],
        }
    ).to_csv(caminho, index=False)

    df, discrepancias = carregar_checkpoint_censo2022(caminho, _df_territorio_3())

    assert len(discrepancias) == 1  # ALTO SANTA TEREZINHA nao esta no csv sintetico
    assert df[df["codigo_bairro"] == "1"]["populacao"].iloc[0] == 1000
    assert (df["ano"] == 2022).all()


# --------------------------------------------------------------------------
# serie municipal (2023 interpolado)
# --------------------------------------------------------------------------


def test_carregar_serie_municipal_interpola_2023_geometricamente(tmp_path):
    bruto = {
        "series": {
            "2022": {"valor": 100},
            "2023": {"valor": None},
            "2024": {"valor": 400},
        }
    }
    caminho = tmp_path / "municipal.json"
    caminho.write_text(json.dumps(bruto), encoding="utf-8")

    serie = carregar_serie_municipal(caminho)

    assert serie[2023] == pytest.approx((100 * 400) ** 0.5)


# --------------------------------------------------------------------------
# reconstrucao CAGR + reconciliacao
# --------------------------------------------------------------------------


def test_reconstruir_segmento_cagr_reconcilia_ao_total_oficial():
    pop_inicio = pd.Series({"1": 100.0, "2": 200.0}, name="populacao")
    pop_fim = pd.Series({"1": 121.0, "2": 242.0}, name="populacao")  # crescimento 10%/ano por 2 anos
    serie_municipal = {2011: 400.0}  # oficial diferente da soma preliminar (330), forca reconciliacao

    df, metricas = reconstruir_segmento_cagr(pop_inicio, pop_fim, 2010, 2012, [2011], serie_municipal)

    soma = df["populacao"].sum()
    assert soma == pytest.approx(400.0)
    soma_preliminar = 100.0 * 1.1 + 200.0 * 1.1  # CAGR de 10%/ano, delta=1 ano
    assert metricas["fatores_reconciliacao"][2011] == pytest.approx(400.0 / soma_preliminar, rel=1e-6)
    # proporcao entre bairros preservada apos reconciliacao (1:2 permanece 1:2)
    p1 = df[df["codigo_bairro"] == "1"]["populacao"].iloc[0]
    p2 = df[df["codigo_bairro"] == "2"]["populacao"].iloc[0]
    assert p2 / p1 == pytest.approx(2.0, rel=1e-6)


def test_reconstruir_segmento_cagr_sem_total_oficial_nao_reconcilia():
    pop_inicio = pd.Series({"1": 100.0}, name="populacao")
    pop_fim = pd.Series({"1": 200.0}, name="populacao")
    df, metricas = reconstruir_segmento_cagr(pop_inicio, pop_fim, 2010, 2020, [2015], {2015: None})
    assert metricas["fatores_reconciliacao"][2015] == 1.0


# --------------------------------------------------------------------------
# validacao cruzada (leave-2017-out)
# --------------------------------------------------------------------------


def test_validar_reconstrucao_sem_checkpoint_acerta_crescimento_constante():
    # crescimento exatamente geometrico -> reconstrucao sem 2017 deve acertar 2017 quase exatamente
    pop_2010 = pd.Series({"1": 100.0, "2": 200.0})
    pop_2022 = pd.Series({"1": 100.0 * 1.05**12, "2": 200.0 * 1.05**12})
    pop_2017_real = pd.Series({"1": 100.0 * 1.05**7, "2": 200.0 * 1.05**7})
    serie_municipal = {2017: float(pop_2017_real.sum())}

    _, metricas = validar_reconstrucao_sem_checkpoint_intermediario(
        pop_2010, pop_2022, pop_2017_real, serie_municipal
    )

    assert metricas["mape_pct"] == pytest.approx(0.0, abs=1e-6)
    assert metricas["n_bairros"] == 2


def test_validar_reconstrucao_detecta_erro_em_trajetoria_irregular():
    # com 2+ bairros, a reconciliacao municipal so ajusta o TOTAL -- o erro
    # individual de uma trajetoria nao-monotonica continua visivel.
    pop_2010 = pd.Series({"1": 100.0, "2": 100.0})
    pop_2022 = pd.Series({"1": 300.0, "2": 300.0})
    # bairro 1: caiu antes de subir (real). bairro 2: cresceu suavemente (CAGR acerta).
    pop_2017_real = pd.Series({"1": 50.0, "2": 173.0})  # 100*(300/100)**(7/12) ~= 173
    serie_municipal = {2017: 223.0}

    _, metricas = validar_reconstrucao_sem_checkpoint_intermediario(
        pop_2010, pop_2022, pop_2017_real, serie_municipal
    )

    assert metricas["mape_pct"] > 50.0
    assert metricas["bairro_maior_erro_percentual"] == "1"


# --------------------------------------------------------------------------
# areas atipicas
# --------------------------------------------------------------------------


def test_identificar_areas_atipicas_marca_pequeno_crescimento_e_reducao():
    pop_2010 = pd.Series({"1": 500.0, "2": 1000.0, "3": 1000.0})
    pop_2022 = pd.Series({"1": 600.0, "2": 1600.0, "3": 800.0})  # 1: pequeno; 2: cresc alto; 3: reducao

    atipicos = identificar_areas_atipicas(pop_2010, pop_2022, limite_pequeno=1000)

    assert set(atipicos["codigo_bairro"]) == {"1", "2", "3"}
    linha_1 = atipicos[atipicos["codigo_bairro"] == "1"].iloc[0]
    assert bool(linha_1["muito_pequeno_2022"]) is True


# --------------------------------------------------------------------------
# comparacao de metodos pos-censo
# --------------------------------------------------------------------------


def test_metodo_a_participacao_fixa_tem_dispersao_minima_e_e_escolhido():
    pop_2010 = pd.Series({"1": 100.0, "2": 300.0})
    pop_2017 = pd.Series({"1": 120.0, "2": 280.0})
    pop_2022 = pd.Series({"1": 150.0, "2": 250.0})
    serie_municipal = {2023: 420.0, 2024: 440.0, 2025: 460.0}

    resultado = comparar_metodos_pos_censo(pop_2010, pop_2017, pop_2022, serie_municipal)
    escolhido = escolher_metodo_pos_censo(resultado["metricas"])

    assert escolhido == "metodo_a_participacao_fixa_2022"
    assert resultado["metricas"]["metodo_a_participacao_fixa_2022"][
        "dispersao_crescimento_entre_bairros"
    ] == pytest.approx(0.0, abs=1e-9)
    # participacao de 2022 preservada em qualquer ano do metodo A
    serie_a = resultado["series"]["A"]
    share_2022 = pop_2022 / pop_2022.sum()
    share_2023 = serie_a[2023] / serie_a[2023].sum()
    pd.testing.assert_series_equal(share_2022, share_2023, check_exact=False, check_names=False)


def test_comparar_metodos_pos_censo_reconcilia_todos_ao_total_oficial():
    pop_2010 = pd.Series({"1": 100.0, "2": 300.0})
    pop_2017 = pd.Series({"1": 120.0, "2": 280.0})
    pop_2022 = pd.Series({"1": 150.0, "2": 250.0})
    serie_municipal = {2023: 420.0, 2024: 440.0, 2025: 460.0}

    resultado = comparar_metodos_pos_censo(pop_2010, pop_2017, pop_2022, serie_municipal)

    for letra in ("A", "B", "C"):
        for ano, total in serie_municipal.items():
            assert resultado["series"][letra][ano].sum() == pytest.approx(total, rel=1e-6)


# --------------------------------------------------------------------------
# orquestracao completa (94 bairros sinteticos = 4, mas cobertura/determinismo testados)
# --------------------------------------------------------------------------


def _bronze_sintetico(tmp_path):
    cievs = {
        "bairros": [
            {
                "nome_bairro_normalizado": nome,
                "populacao_por_ano": {
                    str(ano): pop * (1.02 ** (ano - 2010)) for ano in range(2010, 2018)
                },
            }
            for nome, pop in [("BOA VIAGEM", 1000), ("CASA FORTE", 2000), ("ALTO SANTA TEREZINHA", 500)]
        ]
    }
    caminho_cievs = tmp_path / "cievs.json"
    caminho_cievs.write_text(json.dumps(cievs), encoding="utf-8")

    censo2022_rows = []
    for nome, pop in [("BOA VIAGEM", 1300), ("CASA FORTE", 2300), ("ALTO SANTA TEREZINHA", 600)]:
        censo2022_rows.append(
            {
                "CD_BAIRRO": "x",
                "NM_BAIRRO": nome,
                "nome_bairro_normalizado": nome,
                "NM_NU": "RPA 01",
                "AREA_KM2": "1,0",
                "v0001": pop,
                "v0002": 1,
                "v0003": 1,
                "v0004": 0,
            }
        )
    caminho_censo2022 = tmp_path / "censo2022.csv"
    pd.DataFrame(censo2022_rows).to_csv(caminho_censo2022, index=False)

    municipal = {
        "series": {
            str(ano): {"valor": 3800 + 40 * (ano - 2010)}
            for ano in list(range(2010, 2023)) + [2024, 2025]
        }
    }
    municipal["series"]["2023"] = {"valor": None}
    caminho_municipal = tmp_path / "municipal.json"
    caminho_municipal.write_text(json.dumps(municipal), encoding="utf-8")

    return caminho_cievs, caminho_censo2022, caminho_municipal


def test_construir_serie_populacao_cobre_todos_os_bairros_e_anos_2010_2025(tmp_path):
    caminho_cievs, caminho_censo2022, caminho_municipal = _bronze_sintetico(tmp_path)
    df_final, metricas = construir_serie_populacao(
        caminho_cievs, caminho_censo2022, caminho_municipal, _df_territorio_3()
    )

    assert set(df_final["ano"]) == set(range(2010, 2026))
    assert df_final.groupby("ano")["codigo_bairro"].nunique().eq(3).all()
    assert (df_final["populacao"] > 0).all()
    assert metricas["discrepancias_join_cievs"] == []
    assert metricas["discrepancias_join_censo2022"] == []


def test_construir_serie_populacao_e_deterministico(tmp_path):
    caminho_cievs, caminho_censo2022, caminho_municipal = _bronze_sintetico(tmp_path)
    df1, _ = construir_serie_populacao(caminho_cievs, caminho_censo2022, caminho_municipal, _df_territorio_3())
    df2, _ = construir_serie_populacao(caminho_cievs, caminho_censo2022, caminho_municipal, _df_territorio_3())

    colunas_sem_timestamp = [c for c in df1.columns if c != "_processed_at"]
    pd.testing.assert_frame_equal(
        df1[colunas_sem_timestamp].reset_index(drop=True),
        df2[colunas_sem_timestamp].reset_index(drop=True),
    )


def test_construir_serie_populacao_marca_tipo_valor_correto_por_ano(tmp_path):
    caminho_cievs, caminho_censo2022, caminho_municipal = _bronze_sintetico(tmp_path)
    df_final, _ = construir_serie_populacao(
        caminho_cievs, caminho_censo2022, caminho_municipal, _df_territorio_3()
    )

    por_ano = df_final.groupby("ano")["tipo_valor"].first()
    assert por_ano[2010] == "CENSO_OBSERVADO"
    assert por_ano[2022] == "CENSO_OBSERVADO"
    assert por_ano[2015] == "ESTIMATIVA_INTERCENSITARIA"
    assert por_ano[2019] == "ESTIMATIVA_INTERCENSITARIA"
    assert por_ano[2024] == "PROJECAO_POS_CENSO"
