"""Testes do dataset consumido pela visualização técnica de validação
(`tools/model_validation_app.py` e `src/plot_evidence_validation.py`).

Não testam aparência de gráfico — testam o CONTRATO: quais chaves/colunas
a visualização exige dos artefatos de backtest, e que o desenho funciona
sobre artefatos sintéticos mínimos sem tocar em `reports/ml/` real.
"""
import json

import pandas as pd

from src.ml.evidence_validation import carregar_artefatos_evidencia
from src import plot_evidence_validation as plots

# Chaves que a página técnica lê do resumo JSON — se alguma sair do
# resultado, a página quebra silenciosamente em produção.
CHAVES_RESUMO_EXIGIDAS = (
    "configuracao",
    "recall_ic",
    "delta_vs_melhor_baseline",
    "por_ano",
    "leave_one_year_out",
    "por_rpa",
    "ipsep",
    "bairros_criticos",
    "grandes_episodios",
    "genuino_vs_recaida",
    "lead_time_k10",
    "estabilidade_top10",
    "carga_operacional",
)


def _resumo_sintetico() -> dict:
    def ic(valor):
        return {"observado": valor, "n": 10, "n_reamostragens": 5, "ic_baixo": valor - 0.05, "ic_alto": valor + 0.05}

    return {
        "id_candidato": "teste",
        "configuracao": {
            "n_episodios_teste": 10,
            "horizonte_semanas": 3,
            "n_treino": 100,
            "janela_lead_time_semanas": 4,
        },
        "recall_ic": [],
        "delta_vs_melhor_baseline": [],
        "por_ano": [],
        "leave_one_year_out": [],
        "por_rpa": [],
        "ipsep": [],
        "bairros_criticos": {"muitos_episodios_baixa_deteccao": [], "poucos_episodios_percentual_extremo": []},
        "grandes_episodios": {
            "n": 3,
            "recall5_grandes": ic(0.2),
            "recall5_todos": ic(0.25),
            "recall10_grandes": ic(0.3),
            "recall10_todos": ic(0.38),
            "lead_time_mediano": 2.0,
        },
        "genuino_vs_recaida": {
            "n_genuinos": 8,
            "n_recaidas": 2,
            **{f"recall{k}_{g}": ic(0.3) for k in (5, 10, 20) for g in ("genuino", "recaida")},
        },
        "lead_time_k10": {
            "n": 4,
            "media": 2.5,
            "p25": 2.0,
            "mediana_ic": ic(2.0),
            "p75": 3.0,
            "minimo": 1.0,
            "maximo": 4.0,
            "pct_>=1_semana": 100.0,
            "pct_>=2_semanas": 75.0,
            "pct_>=3_semanas": 50.0,
        },
        "estabilidade_top10": {"k": 10, "n_pares_consecutivos": 2, "jaccard_medio": 0.3, "jaccard_mediano": 0.25},
        "carga_operacional": [],
    }


def _escrever_artefatos_sinteticos(pasta) -> None:
    with open(pasta / "resultado_evidence_validation_completo.json", "w", encoding="utf-8") as f:
        json.dump(_resumo_sintetico(), f)

    pd.DataFrame(
        {
            "k": [5, 5, 10, 10],
            "metodo": ["modelo", "razao_historica_local", "modelo", "razao_historica_local"],
            "observado": [0.25, 0.20, 0.38, 0.35],
            "ic_baixo": [0.22, 0.17, 0.35, 0.32],
            "ic_alto": [0.28, 0.23, 0.41, 0.38],
        }
    ).to_csv(pasta / "evidence_recall_ic.csv", index=False)

    pd.DataFrame(
        {
            "k": [5, 10],
            "melhor_baseline": ["razao_historica_local", "razao_historica_local"],
            "observado": [0.05, 0.02],
            "ic_baixo": [0.02, -0.01],
            "ic_alto": [0.09, 0.06],
        }
    ).to_csv(pasta / "evidence_delta_vs_baseline.csv", index=False)

    pd.DataFrame(
        {
            "inicio_ano": [2023, 2024],
            "n_episodios": [10, 20],
            "recall5_modelo": [0.3, 0.25],
            "recall10_modelo": [0.4, 0.37],
            "recall5_melhor_baseline": [0.29, 0.20],
            "recall10_melhor_baseline": [0.47, 0.38],
        }
    ).to_csv(pasta / "evidence_por_ano.csv", index=False)

    pd.DataFrame(
        {
            "codigo_rpa": ["5", "6"],
            "n_episodios": [197, 74],
            "recall5_modelo": [0.41, 0.14],
            "recall10_modelo": [0.59, 0.22],
            "recall20_modelo": [0.74, 0.33],
        }
    ).to_csv(pasta / "evidence_por_rpa.csv", index=False)

    pd.DataFrame(
        {
            "codigo_bairro": ["213", "884", "999"],
            "nome_bairro": ["IPSEP", "COHAB", "BAIRRO RARO"],
            "n_episodios": [6, 5, 1],
            "recall10_modelo": [0.0, 0.2, 1.0],
            "recall20_modelo": [0.16, 0.2, 1.0],
        }
    ).to_csv(pasta / "evidence_por_bairro.csv", index=False)

    pd.DataFrame(
        {
            "codigo_bairro": ["213", "884", "999"],
            "detectado_modelo_k10": [1, 1, 0],
            "lead_modelo": [1.0, 3.0, None],
        }
    ).to_csv(pasta / "evidence_master_episodios.csv", index=False)

    pd.DataFrame(
        {"indice_semana_alvo": [1, 2, 3], "jaccard": [0.2, 0.4, 0.3], "n_bairros_mantidos": [2, 4, 3], "k": [10, 10, 10]}
    ).to_csv(pasta / "evidence_estabilidade_top10_semanal.csv", index=False)


def test_resumo_real_tem_todas_as_chaves_que_a_pagina_tecnica_le():
    artefatos = carregar_artefatos_evidencia(plots.PASTA_RELATORIO)
    resumo = artefatos["resumo"]
    assert resumo is not None, "artefatos de validação ausentes em reports/ml/"
    faltando = [c for c in CHAVES_RESUMO_EXIGIDAS if c not in resumo]
    assert faltando == [], f"chaves ausentes no resumo: {faltando}"


def test_artefatos_reais_reportam_n_de_episodios_em_toda_agregacao():
    """Nenhum percentual anual/territorial pode ser publicado sem o N que o
    sustenta (seção 9 do pedido desta etapa)."""
    artefatos = carregar_artefatos_evidencia(plots.PASTA_RELATORIO)
    for chave in ("por_ano", "por_rpa", "por_bairro", "leave_one_year_out"):
        tabela = artefatos[chave]
        assert tabela is not None, f"{chave} ausente"
        assert "n_episodios" in tabela.columns, f"{chave} sem n_episodios"


def test_carga_operacional_real_tem_priorizacoes_sem_episodio_futuro():
    artefatos = carregar_artefatos_evidencia(plots.PASTA_RELATORIO)
    carga = artefatos["carga_operacional"]
    assert carga is not None
    for coluna in ("episodios_antecipados", "episodios_perdidos", "priorizacoes_total", "priorizacoes_sem_episodio_futuro"):
        assert coluna in carga.columns, f"coluna {coluna} ausente na carga operacional"


def test_figuras_geram_a_partir_de_artefatos_sinteticos(tmp_path, monkeypatch):
    _escrever_artefatos_sinteticos(tmp_path)
    monkeypatch.setattr(plots, "PASTA_RELATORIO", tmp_path)
    assert plots.main() == 0
    geradas = sorted(p.name for p in tmp_path.glob("*.png"))
    assert len(geradas) == 9, geradas


def test_plot_sem_artefatos_falha_sem_quebrar(tmp_path, monkeypatch):
    monkeypatch.setattr(plots, "PASTA_RELATORIO", tmp_path)
    assert plots.main() == 1
    assert list(tmp_path.glob("*.png")) == []
