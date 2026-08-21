"""Clima × Dengue — associação observada, nunca causalidade."""
import _bootstrap  # noqa: F401

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import renderizar_filtros, tratar_entrada_invalida
from dashboard.components.graficos import (
    COR_INSTITUCIONAL,
    CORES_AGRAVOS,
    LAYOUT_PADRAO,
    grafico_lag_correlacoes,
)
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero
from dashboard.utils.validacao import EntradaInvalidaError, validar_escolha
from src.eda import clima_grade, correlacao, epidemiologia
from src.eda.filtros import aplicar_filtros, linhas_com_clima_real
from src.eda.schema_eda import AGRAVOS, JANELAS_LAG_DIAS

FONTES = {
    "Reanálise em grade (cobre todo o período)": "grade",
    "Estações físicas (só o período recente)": "estacao",
}

gold, freshness = iniciar_pagina(
    "Clima × Dengue",
    "Relação <b>observada</b> entre chuva e casos notificados. Nada nesta página estabelece "
    "causalidade: chuva e arboviroses variam juntas por muitos motivos (sazonalidade, temperatura, "
    "comportamento humano, capacidade de vigilância). O que se mostra aqui é <b>associação</b>.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

st.warning(
    "**Associação não é causalidade.** Uma correlação positiva entre chuva acumulada e casos não "
    "significa que a chuva cause o aumento de casos, nem permite prever casos a partir de chuva. "
    "As duas séries compartilham a mesma sazonalidade anual, o que sozinho produz correlação.",
    icon="⚠️",
)

try:
    filtros = renderizar_filtros(gold, key_prefix="clima_dengue", permitir_escopo_geografico=False)
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

agravo = filtros["agravo"] or "DENGUE"
if filtros["agravo"] is None:
    st.caption(
        f"Nenhum agravo específico selecionado — usando **{agravo.lower()}**, já que as janelas de "
        "defasagem são específicas por agravo."
    )

df = aplicar_filtros(
    gold, agravo=agravo, ano_inicio=filtros["ano_inicio"], ano_fim=filtros["ano_fim"]
)
if not exigir_dados(not df.empty, "Nenhum registro para o recorte selecionado."):
    st.stop()

tem_grade = clima_grade.gold_tem_clima_grade(df)
opcoes_fonte = [rotulo for rotulo, chave in FONTES.items() if chave != "grade" or tem_grade]
rotulo_fonte = st.radio("Fonte climática", options=opcoes_fonte, horizontal=True, key="clima_dengue_fonte")
rotulo_fonte = validar_escolha(rotulo_fonte, opcoes_fonte, "Fonte climática", permitir_nulo=False)
fonte = FONTES[rotulo_fonte]

# ---------------------------------------------------------------------------
# Amostra
# ---------------------------------------------------------------------------
if fonte == "grade":
    df_analise = clima_grade.linhas_com_grade(df)
    nota_fonte = (
        "Reanálise em grade: cobre todo o período, mas resolve poucas células para os 94 bairros. "
        "Serve para relacionar casos com a variação climática **no tempo**, não entre bairros."
    )
else:
    df_analise = linhas_com_clima_real(df)
    nota_fonte = (
        "Estações físicas: medem chuva num ponto próximo ao bairro, mas cobrem apenas o período "
        "recente — qualquer conclusão vale só para os anos cobertos, e não é generalizável."
    )

resumo = epidemiologia.resumo_epidemiologico(df_analise) if len(df_analise) else None
linha_de_cartoes(
    [
        ("Observações na análise", numero(len(df_analise)), "Bairro × semana com valor climático"),
        (
            "Bairros considerados",
            str(resumo["total_bairros"]) if resumo else "0",
            "Com valor climático no recorte",
        ),
        (
            "Período efetivo",
            f"{resumo['ano_epidemiologico_min']}–{resumo['ano_epidemiologico_max']}" if resumo else "—",
            "Anos realmente presentes na amostra",
        ),
        (
            f"Casos de {agravo.lower()} na amostra",
            numero(resumo["total_casos"]) if resumo else "0",
            "Somente linhas com clima disponível",
        ),
    ]
)
st.caption(nota_fonte)

if not exigir_dados(
    len(df_analise) > 0,
    "Nenhuma observação com valor climático nesta combinação de fonte e recorte.",
):
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Séries sobrepostas
# ---------------------------------------------------------------------------
st.markdown("## Casos e chuva ao longo do tempo")
with secao_protegida("Séries sobrepostas"):
    serie_casos = epidemiologia.serie_temporal_semanal(df_analise, por_agravo=False)
    if fonte == "grade":
        serie_clima = clima_grade.serie_climatica_grade(df_analise).rename(
            columns={"precipitacao_mm": "chuva"}
        )
    else:
        serie_clima = (
            df_analise.drop_duplicates(
                subset=["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]
            )
            .groupby(
                ["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"], observed=True
            )["precipitacao_total_semana_mm"]
            .mean()
            .reset_index()
            .rename(columns={"precipitacao_total_semana_mm": "chuva"})
        )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=serie_clima["semana_epi_data_inicio"], y=serie_clima["chuva"],
            name="Chuva semanal (mm)", marker_color=COR_INSTITUCIONAL, opacity=0.55,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=serie_casos["semana_epi_data_inicio"], y=serie_casos["casos"],
            name=f"Casos de {agravo.lower()}",
            line=dict(color=CORES_AGRAVOS.get(agravo, "#a93226"), width=2),
        ),
        secondary_y=True,
    )
    fig.update_layout(**LAYOUT_PADRAO, title_text="Chuva semanal e casos notificados (exploratório)")
    fig.update_yaxes(title_text="Chuva (mm)", secondary_y=False)
    fig.update_yaxes(title_text="Casos", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Correlação por defasagem
# ---------------------------------------------------------------------------
st.markdown("## Associação por janela de defasagem")
st.markdown(
    "Correlação entre casos de uma semana e a chuva **acumulada até aquela semana**, para janelas "
    "retrospectivas diferentes. Nenhuma janela é apresentada como 'a correta': a tabela mostra "
    "todas, com o número de observações."
)
with secao_protegida("Correlação por defasagem"):
    if fonte == "grade":
        tabela = clima_grade.correlacoes_lag_grade(df)
        if exigir_dados(not tabela.empty, "Sem janelas calculáveis."):
            fig_lag = px.bar(
                tabela, x="janela_semanas", y="correlacao_pearson",
                hover_data=["n_observacoes", "correlacao_spearman"],
                color_discrete_sequence=[COR_INSTITUCIONAL],
                title=f"Correlação (Pearson) casos × chuva acumulada — {agravo.lower()}, reanálise",
            )
            fig_lag.update_layout(
                **LAYOUT_PADRAO,
                xaxis_title="Janela retrospectiva (semanas)", yaxis_title="Correlação de Pearson",
            )
            fig_lag.update_xaxes(type="category")
            st.plotly_chart(fig_lag, use_container_width=True)
            st.dataframe(
                tabela.rename(
                    columns={
                        "janela_semanas": "Janela (semanas)",
                        "janela_dias": "Janela (dias)",
                        "n_observacoes": "Observações",
                        "correlacao_pearson": "Pearson",
                        "correlacao_spearman": "Spearman",
                        "amostra_suficiente": "n ≥ 30",
                    }
                ),
                use_container_width=True, hide_index=True,
            )
    else:
        tabela = correlacao.compute_lag_correlations(df)
        if exigir_dados(not tabela.empty, "Sem janelas calculáveis."):
            st.plotly_chart(grafico_lag_correlacoes(tabela, agravo), use_container_width=True)
            st.dataframe(tabela, use_container_width=True, hide_index=True)

    st.caption(
        "'n ≥ 30' indica apenas tamanho mínimo de amostra — **não** é teste de significância "
        "estatística, e uma correlação com muitas observações continua podendo ser espúria."
    )

st.divider()

# ---------------------------------------------------------------------------
# Dispersão
# ---------------------------------------------------------------------------
st.markdown("## Dispersão")
with secao_protegida("Dispersão chuva × casos"):
    if fonte == "grade":
        janela = st.select_slider(
            "Janela retrospectiva (semanas)",
            options=list(clima_grade.JANELAS_LAG_SEMANAS), value=4, key="clima_dengue_janela_grade",
        )
        dispersao = clima_grade.dispersao_lag_grade(df, janela_semanas=int(janela))
        rotulo_x = f"Chuva acumulada em {int(janela)} semana(s) (mm)"
    else:
        janela = st.select_slider(
            "Janela retrospectiva (dias)",
            options=list(JANELAS_LAG_DIAS), value=28, key="clima_dengue_janela_estacao",
        )
        dispersao = correlacao.dados_dispersao_lag(df, janela_dias=int(janela))
        rotulo_x = f"Chuva acumulada em {int(janela)} dias (mm)"

    if exigir_dados(
        dispersao is not None and not dispersao.empty, "Sem observações para esta janela."
    ):
        fig_disp = px.scatter(
            dispersao, x="precipitacao_mm", y="casos", trendline="ols",
            hover_data=["nome_bairro", "ano_epidemiologico", "semana_epidemiologica"],
            color_discrete_sequence=[CORES_AGRAVOS.get(agravo, "#a93226")],
            opacity=0.35,
            title=f"{rotulo_x} × casos de {agravo.lower()} (n = {numero(len(dispersao))})",
        )
        fig_disp.update_layout(**LAYOUT_PADRAO, xaxis_title=rotulo_x, yaxis_title="Casos na semana")
        st.plotly_chart(fig_disp, use_container_width=True)
        st.caption(
            "A linha é um ajuste linear simples (mínimos quadrados) apenas como referência visual "
            "da direção da associação — não é um modelo preditivo e não deve ser usada para estimar "
            "casos a partir de chuva."
        )

st.divider()
st.markdown("### O clima acrescenta informação ao modelo experimental?")
st.markdown(
    "Foi testado num experimento controlado: o mesmo modelo, as mesmas linhas, os mesmos "
    "hiperparâmetros, mudando apenas a presença das variáveis climáticas em grade. "
    "**Na faixa em que o modelo tem ganho defensável (Top-5), o clima não melhorou o resultado** — "
    "o intervalo de confiança da diferença cruza zero e o sinal não é consistente entre os anos. "
    "Por isso o clima **não** foi incorporado ao modelo do produto. Houve ganho consistente numa "
    "faixa mais larga (Top-10), registrado como candidato a uma versão futura que exigiria "
    "validação própria."
)
st.caption("Experimento completo em `reports/ml/dengue_ranking_clima_experiment.md`.")
