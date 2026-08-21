"""Evolução histórica — a história epidemiológica do período coberto,
derivada do dataset, nunca narrada de memória.

Todo texto desta página que afirma um fato ("o ano de maior volume foi X")
é calculado a partir da Gold no momento da renderização. Se os dados
mudarem, o texto muda sozinho.
"""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import renderizar_filtros, tratar_entrada_invalida
from dashboard.components.graficos import grafico_sazonalidade
from dashboard.components.graficos_produto import (
    grafico_casos_por_ano,
    grafico_comparacao_sazonal,
    grafico_serie_com_media_movel,
)
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero
from dashboard.utils.validacao import EntradaInvalidaError
from src.eda import epidemiologia
from src.eda.filtros import aplicar_filtros, total_arboviroses

#: Um ano é destacado como "de alta" quando fica pelo menos este tanto acima
#: da mediana anual do período. Critério objetivo e declarado — não uma
#: escolha manual de quais anos "parecem" epidêmicos.
FATOR_ANO_DE_ALTA = 1.5

gold, freshness = iniciar_pagina(
    "Evolução histórica",
    "Como as arboviroses se comportaram no Recife ao longo de todo o período disponível: ciclos, "
    "picos, sazonalidade e diferenças entre regiões. Toda afirmação abaixo é derivada dos dados "
    "carregados.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

try:
    filtros = renderizar_filtros(gold, key_prefix="historico", permitir_escopo_geografico=True)
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

df = aplicar_filtros(
    gold,
    agravo=filtros["agravo"],
    ano_inicio=filtros["ano_inicio"],
    ano_fim=filtros["ano_fim"],
    codigo_rpa=filtros["codigo_rpa"],
    codigo_bairro=filtros["codigo_bairro"],
)
if not exigir_dados(not df.empty, "Nenhum registro para o recorte selecionado."):
    st.stop()

base = df if filtros["agravo"] else total_arboviroses(df)
resumo = epidemiologia.resumo_epidemiologico(df)

# ---------------------------------------------------------------------------
# Fatos derivados
# ---------------------------------------------------------------------------
por_ano = base.groupby("ano_epidemiologico", observed=True)["casos"].sum().reset_index()
ano_maior = int(por_ano.loc[por_ano["casos"].idxmax(), "ano_epidemiologico"])
casos_maior = int(por_ano["casos"].max())
mediana_anual = float(por_ano["casos"].median())
anos_de_alta = sorted(
    int(a) for a, c in zip(por_ano["ano_epidemiologico"], por_ano["casos"])
    if mediana_anual > 0 and c >= FATOR_ANO_DE_ALTA * mediana_anual
)

sazonalidade = epidemiologia.sazonalidade_semanal(base)
semana_pico = int(sazonalidade.loc[sazonalidade["casos_media_por_ano"].idxmax(), "semana_epidemiologica"])

linha_de_cartoes(
    [
        (
            "Período coberto",
            f"{resumo['ano_epidemiologico_min']}–{resumo['ano_epidemiologico_max']}",
            f"{resumo['total_semanas_distintas']} semanas epidemiológicas",
        ),
        ("Casos no período", numero(resumo["total_casos"]), "Contagem absoluta de notificações"),
        (
            "Ano de maior volume",
            str(ano_maior),
            f"{numero(casos_maior)} casos — mediana anual do período: {numero(mediana_anual)}",
        ),
        (
            "Pico sazonal médio",
            f"SE {semana_pico}",
            "Semana epidemiológica com maior média entre os anos observados",
        ),
    ]
)

st.markdown(
    f"**Leitura derivada dos dados:** no recorte selecionado, o ano de maior volume foi "
    f"**{ano_maior}** ({numero(casos_maior)} casos). "
    + (
        f"Anos com volume ao menos {FATOR_ANO_DE_ALTA:.1f}× a mediana anual do período: "
        f"**{', '.join(str(a) for a in anos_de_alta)}**. "
        if anos_de_alta
        else "Nenhum ano do recorte fica ao menos "
        f"{FATOR_ANO_DE_ALTA:.1f}× acima da mediana anual do período. "
    )
    + f"O pico sazonal médio ocorre em torno da semana epidemiológica **{semana_pico}**."
)
st.caption(
    "O critério de 'ano de alta' é objetivo e está no código desta página (fator sobre a mediana "
    "anual do próprio recorte) — nenhum ano é destacado por escolha editorial."
)

st.divider()

# ---------------------------------------------------------------------------
# Série longa + totais anuais
# ---------------------------------------------------------------------------
st.markdown("## Série completa")
with secao_protegida("Série histórica"):
    serie = epidemiologia.serie_temporal_semanal(base, por_agravo=False)
    st.plotly_chart(
        grafico_serie_com_media_movel(
            serie, "Casos por semana epidemiológica em todo o período do recorte"
        ),
        use_container_width=True,
    )

col1, col2 = st.columns(2, gap="large")
with col1:
    st.markdown("### Totais por ano")
    with secao_protegida("Totais por ano"):
        st.plotly_chart(
            grafico_casos_por_ano(por_ano, "Casos por ano epidemiológico"), use_container_width=True
        )
with col2:
    st.markdown("### Sazonalidade média")
    with secao_protegida("Sazonalidade"):
        st.plotly_chart(
            grafico_sazonalidade(sazonalidade, "Casos médios por semana epidemiológica"),
            use_container_width=True,
        )
        st.caption(
            "O número de anos observados por semana aparece no tooltip — semanas 53 existem em "
            "menos anos e por isso têm base menor."
        )

st.divider()

# ---------------------------------------------------------------------------
# Todos os anos sobrepostos
# ---------------------------------------------------------------------------
st.markdown("## Todos os anos sobrepostos")
with secao_protegida("Curvas anuais sobrepostas"):
    por_ano_semana = (
        base.groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)["casos"]
        .sum()
        .reset_index()
    )
    anos = sorted(int(a) for a in por_ano_semana["ano_epidemiologico"].unique())
    destaque = st.selectbox(
        "Ano em destaque", options=list(reversed(anos)),
        index=list(reversed(anos)).index(ano_maior) if ano_maior in anos else 0,
        key="historico_destaque",
    )
    st.plotly_chart(
        grafico_comparacao_sazonal(
            por_ano_semana, destaque, f"Curva semanal de cada ano — {destaque} em destaque"
        ),
        use_container_width=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# Comparação territorial
# ---------------------------------------------------------------------------
st.markdown("## Comparação entre regiões e bairros")
col_rpa, col_bairro = st.columns(2, gap="large")

with col_rpa:
    st.markdown("### Por RPA")
    with secao_protegida("Casos por RPA e ano"):
        com_rpa = base
        if "codigo_rpa" not in com_rpa.columns:
            com_rpa = com_rpa.merge(
                gold[["codigo_bairro", "codigo_rpa"]].drop_duplicates(), on="codigo_bairro", how="left"
            )
        por_rpa_ano = (
            com_rpa.groupby(["ano_epidemiologico", "codigo_rpa"], observed=True)["casos"]
            .sum()
            .reset_index()
        )
        pivot = por_rpa_ano.pivot(
            index="ano_epidemiologico", columns="codigo_rpa", values="casos"
        ).fillna(0).astype(int)
        pivot.columns = [f"RPA {c}" for c in pivot.columns]
        st.dataframe(pivot, use_container_width=True)
        st.caption(
            "As 6 RPAs têm números de bairros e populações diferentes; a comparação é de volume "
            "absoluto de notificações, não de incidência."
        )

with col_bairro:
    st.markdown("### Bairros com maior carga acumulada")
    with secao_protegida("Ranking histórico de bairros"):
        ranking = epidemiologia.rank_bairros(base, metrica="casos", top_n=15)
        st.dataframe(
            pd.DataFrame(
                {
                    "Posição": ranking["posicao"],
                    "Bairro": ranking["nome_bairro"].str.title(),
                    "Casos no período": ranking["casos"].astype(int),
                }
            ),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Contagem absoluta acumulada no recorte. Sem população por bairro, um bairro grande "
            "aparece à frente de um pequeno mesmo com risco individual menor — por isso a página "
            "**Bairros prioritários** oferece também a razão contra o próprio histórico."
        )
