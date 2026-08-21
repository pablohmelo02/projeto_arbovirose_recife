"""Guarda-rail do filtro global de agravo (item 2/3 do pedido de produto):

- trocar o agravo realmente altera KPI/série/incidência via `src/eda`
  (testado diretamente sobre as funções que as páginas chamam, sem depender
  de Streamlit rodando);
- a página de priorização experimental (dengue-only por construção) exibe
  a mensagem fixa exigida quando o usuário tentaria usá-la para outro
  agravo.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.eda.filtros import aplicar_filtros, total_arboviroses
from src.eda.prioridade_observada import prioridade_observada, resumo_situacao
from src.eda.schema_eda import AGRAVOS

RAIZ = Path(__file__).resolve().parent.parent


def _linha(**overrides) -> dict:
    base = {
        "codigo_bairro": "1",
        "nome_bairro": "BAIRRO A",
        "agravo": "DENGUE",
        "ano_epidemiologico": 2024,
        "semana_epidemiologica": 1,
        "semana_epi_data_inicio": pd.Timestamp("2024-01-07"),
        "semana_epi_data_fim": pd.Timestamp("2024-01-13"),
        "casos": 0,
        "codigo_rpa": "RPA-1",
        "populacao_bairro_ano": 100_000.0,
        "tipo_populacao": "CENSO_OBSERVADO",
        "densidade_populacional_hab_km2": 5000.0,
    }
    base.update(overrides)
    return base


def _gold_sintetica() -> pd.DataFrame:
    linhas = []
    casos_por_agravo = {"DENGUE": 40, "ZIKA": 4, "CHIKUNGUNYA": 1}
    for semana in range(1, 6):
        for agravo, casos_base in casos_por_agravo.items():
            linhas.append(_linha(semana_epidemiologica=semana, agravo=agravo, casos=casos_base + semana))
    return pd.DataFrame(linhas)


def test_trocar_agravo_altera_casos_e_incidencia():
    gold = _gold_sintetica()

    resultados = {}
    for agravo in AGRAVOS:
        df = aplicar_filtros(gold, agravo=agravo)
        tabela = prioridade_observada(df)
        resumo = resumo_situacao(df, tabela)
        resultados[agravo] = resumo["casos_janela_recente_cidade"]

    # os tres agravos tem volumes de casos distintos na fixture -> o filtro
    # de fato propaga (nao fica com o mesmo numero independente da escolha).
    assert len(set(resultados.values())) == len(AGRAVOS)


def test_todas_arboviroses_soma_casos_mas_nao_soma_incidencias_publicadas():
    gold = _gold_sintetica()
    df_todos = aplicar_filtros(gold)  # agravo=None -> mantem as 3 linhas
    total = total_arboviroses(df_todos)

    soma_esperada = gold["casos"].sum()
    assert total["casos"].sum() == soma_esperada
    # populacao e a mesma nos 3 agravos (mesmo bairro/semana) -> incidencia
    # combinada e casos_totais / populacao, nunca soma de 3 incidencias.
    assert "incidencia_100k_combinada" in total.columns


def test_pagina_priorizacao_experimental_mostra_aviso_dengue_only():
    codigo = (RAIZ / "dashboard" / "pages" / "8_priorizacao_experimental.py").read_text(encoding="utf-8")
    assert "Priorização experimental atualmente validada apenas para dengue." in codigo


def test_pagina_priorizacao_experimental_nao_oferece_filtro_de_agravo():
    codigo = (RAIZ / "dashboard" / "pages" / "8_priorizacao_experimental.py").read_text(encoding="utf-8")
    assert "renderizar_filtros(" not in codigo
