"""Métricas operacionais de alerta: episódios, lead time, falsos alertas —
nível de episódio/bairro/ano, não linha a linha (ver `evaluation.py` para
as métricas de classificação linha a linha).

## Definição de "episódio" (seção 29)

Semanas consecutivas (`indice_semana_global` contíguo, sem furo) com
`estado_alto_risco=1` no MESMO bairro formam **um único episódio** — não
vários surtos independentes. Linhas com `estado_alto_risco` indefinido
(`NaN`, ver `target.py`) quebram a continuidade (nunca são "preenchidas"
como 0 ou 1 para forçar um episódio a continuar) — na prática isso só
afeta os primeiros anos da série (2013-2015), fora do período de teste
(2023-2025, ver `split.py`).

## Definição de "alerta" e distinção previsão x alerta (seção 4/30)

Um alerta é emitido no instante `t` (usando só features de `t` ou antes) e
**se refere** à semana alvo `t+horizonte` (`indice_semana_alvo`,
ver `dataset.py`) — nunca ao próprio `t`. `alerta(t)=1` se a probabilidade
prevista para `t+horizonte` >= limiar de decisão.

## Lead time (seção 30/31) — sem falsificar antecipação

Para um episódio real com início na semana `o` (`indice_semana_global`):

- Procura-se o alerta mais antigo cuja **semana alvo** `w` caia em
  `[o - JANELA_ALERTA_SEMANAS, fim_do_episodio]` — a janela olha até
  `JANELA_ALERTA_SEMANAS` semanas ANTES do início real (não depois),
  permitindo capturar um sinal de probabilidade elevada antes do estado
  binário cruzar o limiar (ver docstring de `target.py`), sem inventar
  antecipação além do que os dados sustentam.
- `lead_time = o - w`:
  - `lead_time >= 1`: alerta **antecipado** (emitido antes do início real).
  - `lead_time == 0`: alerta **simultâneo** (a semana alvo do alerta é
    exatamente a semana de início do episódio — "se o alerta ocorrer em t
    e o evento começa em t, lead time = 0", conforme pedido).
  - `lead_time < 0` (mas `w <= fim`): alerta **tardio** (só disparou depois
    do episódio já ter começado).
  - Nenhum alerta em `[o - JANELA, fim]`: episódio **perdido** (não
    detectado).

`JANELA_ALERTA_SEMANAS = 4`: janela operacional (não escondida em código
sem explicação) — ações de controle vetorial (mutirão de eliminação de
criadouros, aplicação de larvicida) levam tipicamente de 1 a 4 semanas para
gerar efeito populacional mensurável sobre o vetor, por isso um alerta com
mais de 4 semanas de antecedência já não corresponde à mesma decisão
operacional que este sistema pretende informar — período compatível com o
enunciado do próprio desafio (seção 31: "1 a 4 semanas antes").

## Falsos alertas

Um `alerta(t)=1` cuja semana alvo `w` não cai em `[inicio-JANELA, fim]` de
NENHUM episódio real do bairro é um falso alerta — contado por bairro/ano,
nunca descartado silenciosamente.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

JANELA_ALERTA_SEMANAS = 4


def construir_episodios(df_estado: pd.DataFrame) -> pd.DataFrame:
    """`df_estado` precisa ter `codigo_bairro`, `indice_semana_global`,
    `ano_epidemiologico`, `semana_epidemiologica`, `casos`,
    `estado_alto_risco` (linhas com `NaN` são ignoradas, ver docstring do
    módulo). Devolve um episódio por linha."""
    df = (
        df_estado.dropna(subset=["estado_alto_risco"])
        .sort_values(["codigo_bairro", "indice_semana_global"])
        .reset_index(drop=True)
    )
    episodios: list[dict[str, Any]] = []

    for bairro, grupo in df.groupby("codigo_bairro", sort=False):
        grupo = grupo.reset_index(drop=True)
        em_episodio = False
        inicio_pos = None

        def _fechar(fim_pos: int) -> None:
            sub = grupo.iloc[inicio_pos : fim_pos + 1]
            episodios.append(
                {
                    "codigo_bairro": bairro,
                    "inicio_indice": int(sub["indice_semana_global"].iloc[0]),
                    "fim_indice": int(sub["indice_semana_global"].iloc[-1]),
                    "inicio_ano": int(sub["ano_epidemiologico"].iloc[0]),
                    "inicio_semana": int(sub["semana_epidemiologica"].iloc[0]),
                    "duracao_semanas": len(sub),
                    "casos_totais_episodio": float(sub["casos"].sum()),
                    "casos_pico": float(sub["casos"].max()),
                }
            )

        for i in range(len(grupo)):
            estado = grupo.loc[i, "estado_alto_risco"]
            contiguo = i > 0 and grupo.loc[i, "indice_semana_global"] == grupo.loc[i - 1, "indice_semana_global"] + 1
            if estado == 1:
                if not em_episodio:
                    em_episodio = True
                    inicio_pos = i
                elif not contiguo:
                    _fechar(i - 1)
                    inicio_pos = i
            else:
                if em_episodio:
                    _fechar(i - 1)
                    em_episodio = False
        if em_episodio:
            _fechar(len(grupo) - 1)

    colunas_episodio = [
        "codigo_bairro",
        "inicio_indice",
        "fim_indice",
        "inicio_ano",
        "inicio_semana",
        "duracao_semanas",
        "casos_totais_episodio",
        "casos_pico",
    ]
    # `pd.DataFrame([])` (sem episódios, ex.: histórico todo indefinido)
    # devolveria um DataFrame sem NENHUMA coluna -- `columns=` explícito
    # garante que quem chama sempre encontre `codigo_bairro`/`inicio_indice`
    # etc., mesmo com 0 linhas (ver `onset.py`, que faz `groupby` sobre o
    # resultado independente de haver ou não episódios).
    return pd.DataFrame(episodios, columns=colunas_episodio)


def avaliar_antecipacao(
    df_alertas: pd.DataFrame,
    df_episodios: pd.DataFrame,
    janela_alerta: int = JANELA_ALERTA_SEMANAS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`df_alertas` precisa ter `codigo_bairro`, `indice_semana_alvo`,
    `alerta` (0/1). Devolve `(episodios_avaliados, falsos_alertas)`.

    `episodios_avaliados` = `df_episodios` + colunas `detectado`,
    `classificacao` (`antecipado`/`simultaneo`/`tardio`/`perdido`),
    `lead_time_semanas`, `semana_alvo_deteccao`.

    `falsos_alertas` = uma linha por (`codigo_bairro`, `indice_semana_alvo`)
    com `alerta=1` que não cai na janela `[inicio-janela, fim]` de nenhum
    episódio daquele bairro.
    """
    alertas_positivos = df_alertas.loc[df_alertas["alerta"] == 1, ["codigo_bairro", "indice_semana_alvo"]].copy()

    resultados = []
    janelas_cobertas: dict[str, list[tuple[int, int]]] = {}

    for _, ep in df_episodios.iterrows():
        bairro = ep["codigo_bairro"]
        inicio = int(ep["inicio_indice"])
        fim = int(ep["fim_indice"])
        janela_ini = inicio - janela_alerta

        candidatos = alertas_positivos[
            (alertas_positivos["codigo_bairro"] == bairro)
            & (alertas_positivos["indice_semana_alvo"] >= janela_ini)
            & (alertas_positivos["indice_semana_alvo"] <= fim)
        ]

        registro = ep.to_dict()
        janelas_cobertas.setdefault(bairro, []).append((janela_ini, fim))

        if candidatos.empty:
            registro.update(
                {
                    "detectado": False,
                    "classificacao": "perdido",
                    "lead_time_semanas": None,
                    "semana_alvo_deteccao": None,
                }
            )
        else:
            w = int(candidatos["indice_semana_alvo"].min())
            lead = inicio - w
            if lead >= 1:
                classificacao = "antecipado"
            elif lead == 0:
                classificacao = "simultaneo"
            else:
                classificacao = "tardio"
            registro.update(
                {
                    "detectado": True,
                    "classificacao": classificacao,
                    "lead_time_semanas": lead,
                    "semana_alvo_deteccao": w,
                }
            )
        resultados.append(registro)

    episodios_avaliados = pd.DataFrame(resultados)

    # Falsos alertas: alerta positivo cuja semana-alvo não cai na janela de
    # nenhum episódio do próprio bairro.
    def _e_falso(row) -> bool:
        janelas = janelas_cobertas.get(row["codigo_bairro"], [])
        return not any(ini <= row["indice_semana_alvo"] <= fim for ini, fim in janelas)

    if len(alertas_positivos):
        mask_falso = alertas_positivos.apply(_e_falso, axis=1)
        falsos_alertas = alertas_positivos.loc[mask_falso].reset_index(drop=True)
    else:
        falsos_alertas = alertas_positivos.reset_index(drop=True)

    return episodios_avaliados, falsos_alertas


def resumo_antecipacao(episodios_avaliados: pd.DataFrame, falsos_alertas: pd.DataFrame) -> dict[str, Any]:
    """KPIs agregados (seção 28): taxa de episódios antecipados, lead time
    médio/mediano/distribuição, contagem de falsos alertas."""
    n_episodios = len(episodios_avaliados)
    if n_episodios == 0:
        return {
            "n_episodios": 0,
            "n_detectados": 0,
            "n_perdidos": 0,
            "taxa_deteccao": None,
            "n_antecipados": 0,
            "n_simultaneos": 0,
            "n_tardios": 0,
            "lead_time_medio_semanas": None,
            "lead_time_mediano_semanas": None,
            "n_falsos_alertas": int(len(falsos_alertas)),
        }

    detectados = episodios_avaliados[episodios_avaliados["detectado"]]
    leads = detectados["lead_time_semanas"].dropna()
    return {
        "n_episodios": n_episodios,
        "n_detectados": int(episodios_avaliados["detectado"].sum()),
        "n_perdidos": int((~episodios_avaliados["detectado"]).sum()),
        "taxa_deteccao": float(episodios_avaliados["detectado"].mean()),
        "n_antecipados": int((episodios_avaliados["classificacao"] == "antecipado").sum()),
        "n_simultaneos": int((episodios_avaliados["classificacao"] == "simultaneo").sum()),
        "n_tardios": int((episodios_avaliados["classificacao"] == "tardio").sum()),
        "lead_time_medio_semanas": float(leads.mean()) if len(leads) else None,
        "lead_time_mediano_semanas": float(leads.median()) if len(leads) else None,
        "n_falsos_alertas": int(len(falsos_alertas)),
    }


def metricas_por_bairro(episodios_avaliados: pd.DataFrame, falsos_alertas: pd.DataFrame) -> pd.DataFrame:
    """Episódios reais/detectados/perdidos, falsos alertas e lead time
    mediano por bairro (seção 32) — identifica onde o sistema funciona
    pior."""
    if episodios_avaliados.empty:
        return pd.DataFrame(
            columns=[
                "codigo_bairro",
                "episodios_reais",
                "episodios_detectados",
                "episodios_perdidos",
                "falsos_alertas",
                "lead_time_mediano_semanas",
            ]
        )
    por_bairro = (
        episodios_avaliados.groupby("codigo_bairro")
        .agg(
            episodios_reais=("detectado", "size"),
            episodios_detectados=("detectado", "sum"),
            lead_time_mediano_semanas=("lead_time_semanas", "median"),
        )
        .reset_index()
    )
    por_bairro["episodios_perdidos"] = por_bairro["episodios_reais"] - por_bairro["episodios_detectados"]
    falsos_por_bairro = (
        falsos_alertas.groupby("codigo_bairro").size().rename("falsos_alertas").reset_index()
        if len(falsos_alertas)
        else pd.DataFrame(columns=["codigo_bairro", "falsos_alertas"])
    )
    resultado = por_bairro.merge(falsos_por_bairro, on="codigo_bairro", how="left")
    resultado["falsos_alertas"] = resultado["falsos_alertas"].fillna(0).astype(int)
    return resultado


def metricas_por_ano(episodios_avaliados: pd.DataFrame) -> pd.DataFrame:
    """Desempenho por ano de início do episódio (seção 33) — mostra se o
    sistema só funciona em certos ciclos epidêmicos."""
    if episodios_avaliados.empty:
        return pd.DataFrame(columns=["inicio_ano", "episodios_reais", "episodios_detectados", "taxa_deteccao"])
    por_ano = (
        episodios_avaliados.groupby("inicio_ano")
        .agg(episodios_reais=("detectado", "size"), episodios_detectados=("detectado", "sum"))
        .reset_index()
    )
    por_ano["taxa_deteccao"] = por_ano["episodios_detectados"] / por_ano["episodios_reais"]
    return por_ano


def metricas_operacionais_semanais(df_alertas: pd.DataFrame, falsos_alertas: pd.DataFrame) -> dict[str, Any]:
    """Capacidade operacional (seção 23): não basta reportar o TOTAL de
    falsos alertas — uma Prefeitura tolera alguns falsos positivos
    espalhados, mas não pode receber dezenas de bairros em alerta toda
    semana. `df_alertas` precisa ter `codigo_bairro`, `indice_semana_alvo`,
    `alerta` (0/1) — todas as linhas avaliadas (não só as com alerta=1)."""
    alertados_por_semana = df_alertas.loc[df_alertas["alerta"] == 1].groupby("indice_semana_alvo").size()
    falsos_por_semana = falsos_alertas.groupby("indice_semana_alvo").size() if len(falsos_alertas) else pd.Series(dtype=int)
    return {
        "bairros_alertados_por_semana_media": float(alertados_por_semana.mean()) if len(alertados_por_semana) else 0.0,
        "bairros_alertados_por_semana_mediana": float(alertados_por_semana.median()) if len(alertados_por_semana) else 0.0,
        "bairros_alertados_por_semana_max": int(alertados_por_semana.max()) if len(alertados_por_semana) else 0,
        "falsos_alertas_por_semana_media": float(falsos_por_semana.mean()) if len(falsos_por_semana) else 0.0,
        "falsos_alertas_por_semana_mediana": float(falsos_por_semana.median()) if len(falsos_por_semana) else 0.0,
        "n_semanas_com_pelo_menos_1_falso_alerta": int((falsos_por_semana > 0).sum()) if len(falsos_por_semana) else 0,
    }


def duracao_falsos_alertas_consecutivos(falsos_alertas: pd.DataFrame) -> dict[str, Any]:
    """Agrupa falsos alertas consecutivos (mesmo bairro, semanas-alvo
    contíguas) em sequências e mede a duração média — um falso alerta
    isolado de 1 semana é operacionalmente muito diferente de uma
    sequência de 6 semanas erradas seguidas no mesmo bairro."""
    if falsos_alertas.empty:
        return {"n_sequencias": 0, "duracao_media_semanas": None, "duracao_maxima_semanas": None}
    duracoes = []
    for _, grupo in falsos_alertas.sort_values("indice_semana_alvo").groupby("codigo_bairro"):
        semanas = grupo["indice_semana_alvo"].tolist()
        comprimento = 1
        anterior = semanas[0]
        for s in semanas[1:]:
            if s == anterior + 1:
                comprimento += 1
            else:
                duracoes.append(comprimento)
                comprimento = 1
            anterior = s
        duracoes.append(comprimento)
    return {
        "n_sequencias": len(duracoes),
        "duracao_media_semanas": float(np.mean(duracoes)),
        "duracao_maxima_semanas": int(max(duracoes)),
    }


def epidemias_grandes(episodios_avaliados: pd.DataFrame, top_pct: float = 0.10) -> pd.DataFrame:
    """Recorte dos `top_pct` episódios por `casos_totais_episodio` (seção
    34) — desempenho do sistema justamente nos eventos mais relevantes."""
    if episodios_avaliados.empty:
        return episodios_avaliados
    n_top = max(1, int(np.ceil(len(episodios_avaliados) * top_pct)))
    return episodios_avaliados.sort_values("casos_totais_episodio", ascending=False).head(n_top)
