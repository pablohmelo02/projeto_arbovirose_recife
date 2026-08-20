import json

import pandas as pd

from src.silver.climate import (
    agregar_diario_cemaden,
    agregar_diario_inmet,
    extrair_observacoes_horarias_cemaden,
    transformar_diario_apac,
    transformar_diario_cemaden,
    transformar_estacoes_apac,
    transformar_estacoes_cemaden,
    transformar_estacoes_inmet,
)
from src.utils.inmet_csv import ler_estacao_inmet


def _metadados_inmet() -> dict[str, str]:
    return {
        "REGIAO": "NE", "UF": "PE", "ESTACAO": "TESTE", "CODIGO (WMO)": "A999",
        "LATITUDE": "-8,05", "LONGITUDE": "-34,90", "ALTITUDE": "10,5",
        "DATA DE FUNDACAO": "01/01/20",
    }


def test_transformar_estacoes_inmet_converte_decimais_e_datas():
    df, metricas = transformar_estacoes_inmet({"res-1": _metadados_inmet()})

    assert metricas["linhas_validas"] == 1
    linha = df.iloc[0]
    assert linha["codigo_estacao"] == "A999"
    assert linha["nome_estacao"] == "TESTE"
    assert linha["fonte"] == "INMET"
    assert linha["latitude"] == -8.05
    assert linha["longitude"] == -34.90
    assert linha["data_inicio"] == "2020-01-01"
    assert linha["municipio"] is None


def test_transformar_estacoes_inmet_rejeita_lat_lon_invalida():
    metadados = dict(_metadados_inmet())
    metadados["LATITUDE"] = "-950,0"  # fora do intervalo valido apos conversao
    df, metricas = transformar_estacoes_inmet({"res-1": metadados})
    assert metricas["linhas_rejeitadas"] == 1


def _csv_com_valores(linhas_dados: list[str]) -> bytes:
    cabecalho = [
        "REGIAO:;NE", "UF:;PE", "ESTACAO:;TESTE", "CODIGO (WMO):;A999",
        "LATITUDE:;-8,05", "LONGITUDE:;-34,90", "ALTITUDE:;10,5", "DATA DE FUNDACAO:;01/01/20",
        "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);UMIDADE RELATIVA DO AR, HORARIA (%);",
    ]
    return ("\n".join(cabecalho + linhas_dados)).encode("latin-1")


def test_agregar_diario_inmet_soma_precipitacao_e_agrega_temperatura():
    conteudo = _csv_com_valores(
        [
            "2024/01/01;0000 UTC;0;20,0;80;",
            "2024/01/01;0100 UTC;1,5;22,0;85;",
            "2024/01/01;0200 UTC;0,5;24,0;90;",
        ]
    )
    _, df_horario = ler_estacao_inmet(conteudo)
    df_valido, df_rejeitado, metricas = agregar_diario_inmet(df_horario, "A999", "res-1", "run-1")

    assert metricas["linhas_validas"] == 1
    linha = df_valido.iloc[0]
    assert linha["precipitacao_mm"] == 2.0  # 0 + 1.5 + 0.5
    assert linha["temperatura_min_c"] == 20.0
    assert linha["temperatura_max_c"] == 24.0
    assert linha["temperatura_media_c"] == 22.0
    assert linha["umidade_min_pct"] == 80.0
    assert linha["umidade_max_pct"] == 90.0


def test_agregar_diario_inmet_dia_totalmente_sem_precipitacao_fica_nulo_nao_zero():
    conteudo = _csv_com_valores(
        [
            "2024/01/01;0000 UTC;;20,0;80;",
            "2024/01/01;0100 UTC;;22,0;85;",
        ]
    )
    _, df_horario = ler_estacao_inmet(conteudo)
    df_valido, _, _ = agregar_diario_inmet(df_horario, "A999", "res-1", "run-1")

    assert pd.isna(df_valido.iloc[0]["precipitacao_mm"])  # nao deve virar 0.0


def test_agregar_diario_inmet_rejeita_precipitacao_negativa():
    conteudo = _csv_com_valores(["2024/01/01;0000 UTC;-5;20,0;80;"])
    _, df_horario = ler_estacao_inmet(conteudo)
    df_valido, df_rejeitado, metricas = agregar_diario_inmet(df_horario, "A999", "res-1", "run-1")

    assert metricas["linhas_rejeitadas"] == 1
    assert "negativa" in df_rejeitado.iloc[0]["_motivo_rejeicao"]


def test_agregar_diario_inmet_temperatura_implausivel_gera_aviso_nao_rejeicao():
    conteudo = _csv_com_valores(["2024/01/01;0000 UTC;0;55,0;80;"])  # 55C fora do plausivel
    _, df_horario = ler_estacao_inmet(conteudo)
    df_valido, df_rejeitado, metricas = agregar_diario_inmet(df_horario, "A999", "res-1", "run-1")

    assert metricas["linhas_validas"] == 1  # nao rejeitada
    assert metricas["avisos_temperatura_implausivel"] >= 1


def _snapshot_apac_json(municipio: str = "RECIFE", data_ultimo: str = "15-01-2024", precip: str = "0.62") -> bytes:
    ponto = {
        "ponto": {"id": "10", "nome": "Estacao Teste", "latitude": "-8.0", "longitude": "-34.9"},
        "3": {"titulo": "Município", "valor": municipio},
        "dados_monitorados": {
            "dados": [
                {"titulo": "Data último dado", "valor": data_ultimo},
                {"titulo": "24 Horas", "valor": precip},
            ]
        },
    }
    return json.dumps({"pontos": {"0": ponto}}).encode("utf-8")


def test_transformar_estacoes_apac():
    df, metricas = transformar_estacoes_apac(_snapshot_apac_json(), "res-apac")
    assert metricas["linhas_validas"] == 1
    linha = df.iloc[0]
    assert linha["codigo_estacao"] == "10"
    assert linha["fonte"] == "APAC"
    assert linha["latitude"] == -8.0
    assert linha["municipio"] == "RECIFE"
    assert linha["altitude"] is None


def test_transformar_diario_apac_usa_data_do_ultimo_dado():
    df_valido, _, metricas = transformar_diario_apac(_snapshot_apac_json(data_ultimo="15-01-2024"), "res-apac", "run-1")
    assert metricas["linhas_validas"] == 1
    linha = df_valido.iloc[0]
    assert str(linha["data"].date()) == "2024-01-15"
    assert linha["precipitacao_mm"] == 0.62
    assert linha["temperatura_media_c"] is None


def test_transformar_diario_apac_rejeita_sem_data():
    df_valido, df_rejeitado, metricas = transformar_diario_apac(
        _snapshot_apac_json(data_ultimo=""), "res-apac", "run-1"
    )
    assert metricas["linhas_rejeitadas"] == 1
    assert "data" in df_rejeitado.iloc[0]["_motivo_rejeicao"]


# --------------------------------------------------------------------------
# CEMADEN — silver_estacao_climatica
# --------------------------------------------------------------------------


def _cadastro_cemaden_json(estacoes: list[dict]) -> bytes:
    features = [
        {
            "type": "Feature",
            "properties": e,
            "geometry": {"type": "Point", "coordinates": [e.get("longitude"), e.get("latitude")]},
        }
        for e in estacoes
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


def _status_cemaden_json(registros: list[dict]) -> bytes:
    return json.dumps(registros).encode("utf-8")


def test_transformar_estacoes_cemaden_junta_cadastro_e_status_por_nome():
    cadastro = _cadastro_cemaden_json(
        [
            {
                "codestacao": "261160620A", "nome": "Porto", "latitude": -8.054,
                "longitude": -34.873, "cidade": "RECIFE", "uf": "PE",
                "tipo": "Pluviométrica", "tempo_inatividade": 0,
            }
        ]
    )
    status = _status_cemaden_json(
        [
            {
                "idestacao": 6846, "uf": "PE", "cidade": "RECIFE", "nomeestacao": "Porto",
                "tipoestacao": 1, "datahoraUltimovalor": "20/08/26 00:50",
            }
        ]
    )
    df, metricas = transformar_estacoes_cemaden(cadastro, status, "res-cemaden")

    assert metricas["linhas_validas"] == 1
    linha = df.iloc[0]
    assert linha["codigo_estacao"] == "6846"
    assert linha["fonte"] == "CEMADEN"
    assert linha["latitude"] == -8.054
    assert linha["longitude"] == -34.873
    assert linha["municipio"] == "RECIFE"
    assert linha["altitude"] is None
    assert metricas["estacoes_cadastro_sem_status_pluviometrico_correspondente"] == 0


def test_transformar_estacoes_cemaden_ignora_tipoestacao_diferente_de_pluviometrica():
    cadastro = _cadastro_cemaden_json(
        [{"codestacao": "X", "nome": "Estacao X", "latitude": -8.0, "longitude": -34.9, "cidade": "RECIFE", "uf": "PE"}]
    )
    status = _status_cemaden_json(
        [{"idestacao": 999, "uf": "PE", "cidade": "RECIFE", "nomeestacao": "Estacao X", "tipoestacao": 5}]
    )
    df, metricas = transformar_estacoes_cemaden(cadastro, status, "res-cemaden")

    assert df.empty
    assert metricas["estacoes_cadastro_sem_status_pluviometrico_correspondente"] == 1


def test_transformar_estacoes_cemaden_nome_sem_correspondencia_nao_e_incluido():
    cadastro = _cadastro_cemaden_json(
        [{"codestacao": "A", "nome": "Estacao Sem Status", "latitude": -8.0, "longitude": -34.9, "cidade": "RECIFE", "uf": "PE"}]
    )
    status = _status_cemaden_json([])
    df, metricas = transformar_estacoes_cemaden(cadastro, status, "res-cemaden")

    assert df.empty
    assert metricas["estacoes_cadastro_sem_status_pluviometrico_correspondente"] == 1


def test_transformar_estacoes_cemaden_rejeita_coordenada_invalida():
    cadastro = _cadastro_cemaden_json(
        [{"codestacao": "A", "nome": "Estacao Ruim", "latitude": 999.0, "longitude": -34.9, "cidade": "RECIFE", "uf": "PE"}]
    )
    status = _status_cemaden_json(
        [{"idestacao": 1, "uf": "PE", "cidade": "RECIFE", "nomeestacao": "Estacao Ruim", "tipoestacao": 1}]
    )
    df, metricas = transformar_estacoes_cemaden(cadastro, status, "res-cemaden")

    assert metricas["linhas_rejeitadas"] == 1


# --------------------------------------------------------------------------
# CEMADEN — extrair_observacoes_horarias_cemaden
# --------------------------------------------------------------------------


def _serie_horaria_cemaden(datas: list[str], horarios: list[str], acumulados: list[list]) -> bytes:
    return json.dumps({"datas": datas, "horarios": horarios, "acumulados": acumulados}).encode("utf-8")


def test_extrair_observacoes_horarias_cemaden_estrutura_real_com_virada_de_dia():
    # estrutura real observada na investigacao: o mesmo rotulo de hora
    # aparece nas duas linhas, mas so uma delas tem valor nao-nulo naquela
    # posicao -- timestamp = data da linha + rotulo da coluna.
    conteudo = _serie_horaria_cemaden(
        datas=["19/08/2026", "20/08/2026"],
        horarios=["23h", "0h", "1h"],
        acumulados=[[0.4, None, None], [None, 0.0, 0.6]],
    )
    df, metricas = extrair_observacoes_horarias_cemaden(conteudo, "6846")

    assert len(df) == 3
    assert metricas["linhas_sem_data_hora"] == 0
    linha_23h = df[df["hora"] == 23].iloc[0]
    assert str(linha_23h["data"]) == "2026-08-19"
    assert linha_23h["precipitacao"] == 0.4
    linha_1h = df[df["hora"] == 1].iloc[0]
    assert str(linha_1h["data"]) == "2026-08-20"
    assert linha_1h["precipitacao"] == 0.6


def test_extrair_observacoes_horarias_cemaden_resposta_vazia():
    conteudo = json.dumps({}).encode("utf-8")
    df, metricas = extrair_observacoes_horarias_cemaden(conteudo, "6846")

    assert df.empty
    assert metricas["linhas_lidas"] == 0


def test_extrair_observacoes_horarias_cemaden_arrays_incompativeis_nao_quebra():
    conteudo = _serie_horaria_cemaden(
        datas=["19/08/2026"], horarios=["1h", "2h", "3h"], acumulados=[[0.5]]
    )
    df, _ = extrair_observacoes_horarias_cemaden(conteudo, "6846")

    assert len(df) == 1
    assert df.iloc[0]["hora"] == 1


def test_extrair_observacoes_horarias_cemaden_rotulo_hora_invalido_e_ignorado():
    conteudo = _serie_horaria_cemaden(datas=["19/08/2026"], horarios=["Xh"], acumulados=[[1.0]])
    df, metricas = extrair_observacoes_horarias_cemaden(conteudo, "6846")

    assert df.empty
    assert metricas["linhas_sem_data_hora"] == 1


def test_extrair_observacoes_horarias_cemaden_preserva_valor_negativo_para_validacao_posterior():
    conteudo = _serie_horaria_cemaden(datas=["19/08/2026"], horarios=["1h"], acumulados=[[-5.0]])
    df, _ = extrair_observacoes_horarias_cemaden(conteudo, "6846")

    assert df.iloc[0]["precipitacao"] == -5.0


# --------------------------------------------------------------------------
# CEMADEN — agregar_diario_cemaden / transformar_diario_cemaden
# --------------------------------------------------------------------------


def test_agregar_diario_cemaden_soma_horas_validas():
    df_horarias = pd.DataFrame(
        {
            "codigo_estacao": ["6846"] * 3,
            "data": [pd.Timestamp("2026-08-19").date()] * 3,
            "hora": [0, 1, 2],
            "precipitacao": [1.0, 0.0, 0.5],
        }
    )
    df_valido, _, metricas = agregar_diario_cemaden(df_horarias, "res-1", "run-1")

    assert metricas["linhas_validas"] == 1
    linha = df_valido.iloc[0]
    assert linha["precipitacao_mm"] == 1.5
    assert linha["horas_validas_dia"] == 3
    assert linha["fonte"] == "CEMADEN"
    assert linha["temperatura_media_c"] is None


def test_agregar_diario_cemaden_sem_nenhuma_leitura_real_fica_vazio():
    """Caso 'Dois Unidos': estacao existe em silver_estacao_climatica mas a
    serie horaria nao tem nenhuma leitura real utilizavel -- nao deve gerar
    linha diaria nenhuma (e portanto nunca vira elegivel na Estrategia A)."""
    df_horarias = pd.DataFrame(columns=["codigo_estacao", "data", "hora", "precipitacao"])
    df_valido, _, metricas = agregar_diario_cemaden(df_horarias, "res-1", "run-1")

    assert df_valido.empty
    assert metricas["linhas_validas"] == 0


def test_agregar_diario_cemaden_rejeita_precipitacao_negativa():
    df_horarias = pd.DataFrame(
        {
            "codigo_estacao": ["6846"],
            "data": [pd.Timestamp("2026-08-19").date()],
            "hora": [10],
            "precipitacao": [-2.0],
        }
    )
    df_valido, df_rejeitado, metricas = agregar_diario_cemaden(df_horarias, "res-1", "run-1")

    assert metricas["linhas_rejeitadas"] == 1
    assert "negativa" in df_rejeitado.iloc[0]["_motivo_rejeicao"]


def test_transformar_diario_cemaden_conveniencia_ponta_a_ponta():
    conteudo = _serie_horaria_cemaden(
        datas=["19/08/2026"], horarios=["10h", "11h"], acumulados=[[0.6, 0.79]]
    )
    df_valido, _, metricas = transformar_diario_cemaden(conteudo, "6846", "res-1", "run-1")

    assert metricas["linhas_validas"] == 1
    linha = df_valido.iloc[0]
    assert round(linha["precipitacao_mm"], 2) == 1.39
    assert linha["horas_validas_dia"] == 2
    assert linha["codigo_estacao"] == "6846"
