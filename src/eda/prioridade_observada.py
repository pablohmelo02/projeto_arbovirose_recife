"""Priorização **observada** — o que os dados já mostram, sem modelo.

Esta camada responde às perguntas operacionais que não dependem de
predição alguma:

- onde há maior concentração de casos observados?
- quais bairros estão **acelerando**?
- quais estão acima do próprio histórico para esta época do ano?

Tudo aqui é descritivo e verificável a partir da Gold. Nenhuma função
devolve "risco", "probabilidade" ou categoria colorida: devolve contagens,
variações percentuais e razões contra o próprio histórico do bairro, com o
número de observações que sustenta cada uma. A priorização preditiva
(experimental, com modelo) vive em `src/ml/` e é exibida em página separada
e claramente marcada.

## Por que "razão contra o próprio histórico" e não incidência

Nenhuma fonte do projeto tem população por bairro
(`INCIDENCIA_DISPONIVEL = False`, ver `schema_eda.py`), então incidência por
100 mil habitantes **não existe** e não é aproximada. O normalizador
disponível é o próprio histórico do bairro na mesma época do ano — o mesmo
princípio do "canal endêmico" usado na vigilância brasileira. Isso permite
comparar um bairro grande com um pequeno sem inventar denominador.

## Sem leakage acidental na comparação histórica

A média histórica de uma semana usa **somente anos estritamente
anteriores** ao ano da semana de referência. Assim o número mostrado é o
mesmo que estaria disponível no momento em que aquela semana aconteceu — e
não fica inflado pelo próprio ano que se quer avaliar.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

#: Janela usada para "casos recentes" e para a comparação de crescimento.
#: 4 semanas ≈ um mês epidemiológico: curto o bastante para refletir
#: mudança recente, longo o bastante para não oscilar com uma única semana.
JANELA_RECENTE_SEMANAS = 4

#: Largura da janela sazonal na comparação com o histórico (± semanas),
#: igual à usada pela definição de risco do módulo de ML — para que as duas
#: leituras do "mesmo período do ano" sejam consistentes entre as páginas.
LARGURA_JANELA_SAZONAL = 2

#: Suavização de Laplace: evita divisão por zero em bairro sem histórico e
#: impede que "1 caso onde a média histórica é 0" apareça como razão
#: infinita.
EPS_RAZAO = 1.0

ROTULO_TENDENCIA_ALTA = "em alta"
ROTULO_TENDENCIA_ESTAVEL = "estável"
ROTULO_TENDENCIA_QUEDA = "em queda"
ROTULO_TENDENCIA_INDEFINIDA = "sem base de comparação"

#: Variação percentual mínima (em módulo) para chamar de alta/queda em vez
#: de estável. 20 % evita rotular ruído de contagem pequena como tendência.
LIMIAR_VARIACAO_TENDENCIA_PCT = 20.0


def ultima_semana_disponivel(df_gold: pd.DataFrame) -> Optional[tuple[int, int]]:
    """`(ano_epidemiologico, semana_epidemiologica)` mais recente presente."""
    if df_gold.empty:
        return None
    ultima = (
        df_gold[["ano_epidemiologico", "semana_epidemiologica"]]
        .drop_duplicates()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
        .iloc[-1]
    )
    return int(ultima["ano_epidemiologico"]), int(ultima["semana_epidemiologica"])


def _ordenar_semanas(df: pd.DataFrame) -> pd.DataFrame:
    calendario = (
        df[["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"]]
        .drop_duplicates()
        .sort_values("semana_epi_data_inicio")
        .reset_index(drop=True)
    )
    calendario["ordem_semana"] = range(len(calendario))
    return df.merge(
        calendario[["ano_epidemiologico", "semana_epidemiologica", "ordem_semana"]],
        on=["ano_epidemiologico", "semana_epidemiologica"],
        how="left",
    )


def _rotular_tendencia(variacao_pct: Optional[float]) -> str:
    if variacao_pct is None or pd.isna(variacao_pct):
        return ROTULO_TENDENCIA_INDEFINIDA
    if variacao_pct >= LIMIAR_VARIACAO_TENDENCIA_PCT:
        return ROTULO_TENDENCIA_ALTA
    if variacao_pct <= -LIMIAR_VARIACAO_TENDENCIA_PCT:
        return ROTULO_TENDENCIA_QUEDA
    return ROTULO_TENDENCIA_ESTAVEL


def media_historica_sazonal(
    df_agravo: pd.DataFrame,
    ano_referencia: int,
    semana_referencia: int,
    largura: int = LARGURA_JANELA_SAZONAL,
) -> pd.DataFrame:
    """Média de casos por bairro na janela sazonal
    `semana_referencia ± largura`, considerando **apenas anos anteriores** a
    `ano_referencia`. Devolve `codigo_bairro`, `media_historica`,
    `n_observacoes_historicas`."""
    semana_min = max(1, semana_referencia - largura)
    semana_max = min(53, semana_referencia + largura)
    historico = df_agravo[
        (df_agravo["ano_epidemiologico"] < ano_referencia)
        & (df_agravo["semana_epidemiologica"].between(semana_min, semana_max))
    ]
    if historico.empty:
        return pd.DataFrame(columns=["codigo_bairro", "media_historica", "n_observacoes_historicas"])
    return (
        historico.groupby("codigo_bairro", observed=True)["casos"]
        .agg(media_historica="mean", n_observacoes_historicas="size")
        .reset_index()
    )


def prioridade_observada(
    df_agravo: pd.DataFrame,
    ano_referencia: Optional[int] = None,
    semana_referencia: Optional[int] = None,
    janela_recente: int = JANELA_RECENTE_SEMANAS,
) -> pd.DataFrame:
    """Tabela de priorização observada por bairro, na semana de referência.

    `df_agravo` deve conter **um único agravo** (recorte de
    `src/eda/filtros.py`) e o grão completo `bairro × semana`.

    Colunas devolvidas:

    | coluna | significado |
    |---|---|
    | `casos_semana` | casos na semana de referência |
    | `casos_janela_recente` | soma das últimas `janela_recente` semanas (inclui a de referência) |
    | `casos_janela_anterior` | soma das `janela_recente` semanas imediatamente antes |
    | `variacao_pct` | variação percentual entre as duas janelas |
    | `tendencia` | rótulo textual derivado de `variacao_pct` |
    | `media_historica` | média da mesma época do ano, só anos anteriores |
    | `razao_historico` | `casos_janela_recente / (media_historica * janela + 1)` |
    | `n_observacoes_historicas` | tamanho da amostra histórica usada |
    """
    colunas = [
        "codigo_bairro", "nome_bairro", "codigo_rpa", "casos_semana", "casos_janela_recente",
        "casos_janela_anterior", "variacao_pct", "tendencia", "media_historica",
        "razao_historico", "n_observacoes_historicas",
    ]
    if df_agravo.empty:
        return pd.DataFrame(columns=colunas)

    if ano_referencia is None or semana_referencia is None:
        ultima = ultima_semana_disponivel(df_agravo)
        if ultima is None:
            return pd.DataFrame(columns=colunas)
        ano_referencia, semana_referencia = ultima

    df = _ordenar_semanas(df_agravo)
    alvo = df[
        (df["ano_epidemiologico"] == ano_referencia)
        & (df["semana_epidemiologica"] == semana_referencia)
    ]
    if alvo.empty:
        return pd.DataFrame(columns=colunas)
    ordem_alvo = int(alvo["ordem_semana"].iloc[0])

    recente = df[df["ordem_semana"].between(ordem_alvo - janela_recente + 1, ordem_alvo)]
    anterior = df[df["ordem_semana"].between(ordem_alvo - 2 * janela_recente + 1, ordem_alvo - janela_recente)]

    base = (
        alvo.groupby(["codigo_bairro", "nome_bairro", "codigo_rpa"], observed=True)["casos"]
        .sum()
        .reset_index(name="casos_semana")
    )
    base = base.merge(
        recente.groupby("codigo_bairro", observed=True)["casos"].sum().reset_index(name="casos_janela_recente"),
        on="codigo_bairro", how="left",
    )
    base = base.merge(
        anterior.groupby("codigo_bairro", observed=True)["casos"].sum().reset_index(name="casos_janela_anterior"),
        on="codigo_bairro", how="left",
    )
    base = base.merge(
        media_historica_sazonal(df_agravo, ano_referencia, semana_referencia),
        on="codigo_bairro", how="left",
    )

    tem_anterior = base["casos_janela_anterior"].notna()
    base["variacao_pct"] = pd.Series(
        [
            None if not ok else round(
                100.0 * (recente_v - anterior_v) / anterior_v, 1
            ) if anterior_v > 0 else (None if recente_v == 0 else float("inf"))
            for ok, recente_v, anterior_v in zip(
                tem_anterior,
                base["casos_janela_recente"].fillna(0),
                base["casos_janela_anterior"].fillna(0),
            )
        ]
    )
    base["tendencia"] = base["variacao_pct"].map(_rotular_tendencia)
    base["razao_historico"] = (
        base["casos_janela_recente"].fillna(0)
        / (base["media_historica"].fillna(0) * janela_recente + EPS_RAZAO)
    ).round(2)

    return base[colunas].sort_values(
        ["casos_janela_recente", "razao_historico"], ascending=False
    ).reset_index(drop=True)


def resumo_situacao(df_agravo: pd.DataFrame, tabela_prioridade: pd.DataFrame) -> dict[str, Any]:
    """KPIs da semana de referência para a página inicial — sempre com o
    número de bairros que sustenta cada afirmação."""
    if tabela_prioridade.empty:
        return {
            "casos_semana_cidade": 0,
            "casos_janela_recente_cidade": 0,
            "variacao_pct_cidade": None,
            "tendencia_cidade": ROTULO_TENDENCIA_INDEFINIDA,
            "bairros_com_caso_na_semana": 0,
            "bairros_em_alta": 0,
            "bairros_acima_do_historico": 0,
            "total_bairros": int(df_agravo["codigo_bairro"].nunique()) if len(df_agravo) else 0,
        }

    recente = float(tabela_prioridade["casos_janela_recente"].fillna(0).sum())
    anterior = float(tabela_prioridade["casos_janela_anterior"].fillna(0).sum())
    variacao = round(100.0 * (recente - anterior) / anterior, 1) if anterior > 0 else None
    return {
        "casos_semana_cidade": int(tabela_prioridade["casos_semana"].fillna(0).sum()),
        "casos_janela_recente_cidade": int(recente),
        "casos_janela_anterior_cidade": int(anterior),
        "variacao_pct_cidade": variacao,
        "tendencia_cidade": _rotular_tendencia(variacao),
        "bairros_com_caso_na_semana": int((tabela_prioridade["casos_semana"].fillna(0) > 0).sum()),
        "bairros_em_alta": int((tabela_prioridade["tendencia"] == ROTULO_TENDENCIA_ALTA).sum()),
        "bairros_acima_do_historico": int((tabela_prioridade["razao_historico"] > 1.0).sum()),
        "total_bairros": int(len(tabela_prioridade)),
    }


def semanas_disponiveis(df_gold: pd.DataFrame, limite: Optional[int] = None) -> list[tuple[int, int]]:
    """Lista `(ano, semana)` disponível, mais recente primeiro — usada para
    popular seletores da UI a partir do dado real (nunca de um range fixo)."""
    if df_gold.empty:
        return []
    pares = (
        df_gold[["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"]]
        .drop_duplicates()
        .sort_values("semana_epi_data_inicio", ascending=False)
    )
    lista = [(int(a), int(s)) for a, s in zip(pares["ano_epidemiologico"], pares["semana_epidemiologica"])]
    return lista[:limite] if limite else lista
