"""Gera o relatório reproduzível de EDA (`reports/eda/`).

Usa exatamente as mesmas funções de `src/eda/` que o dashboard usa — o
relatório e o dashboard nunca calculam a mesma métrica de duas formas
diferentes (ver CLAUDE.md, seção de EDA)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.eda import clima, correlacao, epidemiologia
from src.eda.filtros import aplicar_filtros
from src.eda.schema_eda import AGRAVOS, ANO_INICIO_COBERTURA_CLIMATICA_REAL


def gerar_achados(
    df_gold: pd.DataFrame,
    sazonalidade: pd.DataFrame,
    comparacao_agravos: pd.DataFrame,
    ranking_geral: pd.DataFrame,
    correlacoes_por_agravo: dict[str, pd.DataFrame],
) -> list[dict[str, str]]:
    """Achados objetivos (observação, não hipótese) — cada um rastreável a
    um cálculo específico, nunca a uma impressão subjetiva."""
    achados = []

    ano_pico = comparacao_agravos.groupby("ano_epidemiologico")["casos"].sum().idxmax()
    achados.append(
        {
            "tipo": "observação",
            "achado": f"O ano epidemiológico com mais casos de arboviroses no total é {int(ano_pico)}.",
        }
    )

    semana_pico = sazonalidade.sort_values("casos_media_por_ano", ascending=False).iloc[0]
    achados.append(
        {
            "tipo": "observação",
            "achado": (
                f"A semana epidemiológica com maior média de casos é a semana "
                f"{int(semana_pico['semana_epidemiologica'])} "
                f"({semana_pico['casos_media_por_ano']:.1f} casos/ano em média, "
                f"{int(semana_pico['anos_observados'])} anos observados)."
            ),
        }
    )

    top3_bairros = ranking_geral.head(3)["nome_bairro"].tolist()
    achados.append(
        {
            "tipo": "observação",
            "achado": f"Os 3 bairros com mais casos totais (2013-2025, todos os agravos) são: {', '.join(top3_bairros)}.",
        }
    )

    for agravo, tabela in correlacoes_por_agravo.items():
        confiaveis = tabela[tabela["confiavel"]]
        if confiaveis.empty:
            achados.append(
                {
                    "tipo": "observação",
                    "achado": f"Para {agravo}, nenhuma janela de lag teve amostra considerada confiável (n < 30).",
                }
            )
            continue
        melhor = confiaveis.sort_values("correlacao_pearson", ascending=False, key=abs).iloc[0]
        achados.append(
            {
                "tipo": "hipótese",
                "achado": (
                    f"Para {agravo}, a janela de lag com maior correlação exploratória (Pearson) "
                    f"observada é {int(melhor['janela_dias'])} dias "
                    f"(r={melhor['correlacao_pearson']}, n={int(melhor['n_observacoes'])}) — "
                    "observação exploratória sobre janela climática curta (2024-2025), NÃO uma "
                    "conclusão causal nem generalizável a 2013-2023."
                ),
            }
        )

    achados.append(
        {
            "tipo": "limitação",
            "achado": (
                f"Cobertura climática real começa em {ANO_INICIO_COBERTURA_CLIMATICA_REAL} — "
                "qualquer achado envolvendo clima é restrito a 2024-2025, nunca aos 13 anos completos."
            ),
        }
    )
    return achados


def gerar_relatorio_eda(df_gold: pd.DataFrame, pasta_saida: Path) -> dict[str, Any]:
    pasta_saida.mkdir(parents=True, exist_ok=True)

    resumo_geral = epidemiologia.resumo_epidemiologico(df_gold)
    sazonalidade = epidemiologia.sazonalidade_semanal(df_gold)
    comparacao_agravos = epidemiologia.comparar_agravos(df_gold)
    ranking_geral = epidemiologia.rank_bairros(df_gold, top_n=None)

    cobertura_ano = clima.cobertura_por_ano(df_gold)
    resumo_clima = clima.resumo_cobertura_climatica(df_gold)

    correlacoes_por_agravo: dict[str, pd.DataFrame] = {}
    for agravo in AGRAVOS:
        recorte = aplicar_filtros(df_gold, agravo=agravo)
        correlacoes_por_agravo[agravo] = correlacao.compute_lag_correlations(recorte)

    achados = gerar_achados(df_gold, sazonalidade, comparacao_agravos, ranking_geral, correlacoes_por_agravo)

    sazonalidade.to_csv(pasta_saida / "sazonalidade_semanal.csv", index=False, encoding="utf-8")
    comparacao_agravos.to_csv(pasta_saida / "comparacao_agravos.csv", index=False, encoding="utf-8")
    ranking_geral.to_csv(pasta_saida / "ranking_bairros_geral.csv", index=False, encoding="utf-8")
    cobertura_ano.to_csv(pasta_saida / "cobertura_climatica_por_ano.csv", index=False, encoding="utf-8")
    for agravo, tabela in correlacoes_por_agravo.items():
        tabela.to_csv(pasta_saida / f"correlacoes_lag_{agravo.lower()}.csv", index=False, encoding="utf-8")

    resultado = {
        "resumo_epidemiologico": resumo_geral,
        "resumo_climatico": resumo_clima,
        "achados": achados,
    }
    (pasta_saida / "resumo.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return resultado
