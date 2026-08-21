"""Mapa territorial dos 94 bairros, com métrica alternável."""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import (
    descrever_recorte,
    renderizar_filtros,
    tratar_entrada_invalida,
)
from dashboard.components.graficos_produto import grafico_mapa_metricas
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import numero
from dashboard.utils.data_loader import load_bairro_geojson
from dashboard.utils.validacao import EntradaInvalidaError, validar_escolha
from src.eda.filtros import aplicar_filtros, total_arboviroses
from src.eda.prioridade_observada import JANELA_RECENTE_SEMANAS, prioridade_observada
from src.eda.schema_eda import INCIDENCIA_DISPONIVEL

#: Métricas oferecidas no mapa. Cada uma é uma quantidade observada, uma
#: taxa por população ou uma razão contra o próprio histórico — nenhuma é
#: "risco" ou "score de modelo" (o score experimental vive na página
#: experimental, marcada).
METRICAS = {
    "Casos acumulados no período": {
        "coluna": "casos_acumulados",
        "rotulo": "Casos",
        "ajuda": "Soma dos casos notificados em todo o recorte de anos selecionado.",
    },
    f"Casos nas últimas {JANELA_RECENTE_SEMANAS} semanas": {
        "coluna": "casos_janela_recente",
        "rotulo": "Casos recentes",
        "ajuda": "Casos nas últimas semanas disponíveis dentro do recorte.",
    },
    "Incidência / 100 mil habitantes": {
        "coluna": "incidencia_100k",
        "rotulo": "Incidência /100k",
        "ajuda": (
            "Casos da própria semana de referência divididos pela população do bairro naquele "
            "ano, × 100.000. Ver **Tipo pop.** no detalhe: alguns anos usam população reconstruída, "
            "não Censo."
        ),
    },
    f"Incidência móvel {JANELA_RECENTE_SEMANAS} semanas / 100 mil habitantes": {
        "coluna": "incidencia_4s_100k",
        "rotulo": "Incidência 4 sem. /100k",
        "ajuda": (
            f"Soma dos casos das últimas {JANELA_RECENTE_SEMANAS} semanas dividida pela população do "
            "bairro, × 100.000 — nunca a soma de taxas semanais já calculadas."
        ),
    },
    "Crescimento recente (%)": {
        "coluna": "variacao_pct",
        "rotulo": "Variação %",
        "ajuda": "Variação percentual entre as últimas semanas e as 4 semanas imediatamente anteriores.",
    },
    "Razão contra o histórico do bairro": {
        "coluna": "razao_historico",
        "rotulo": "Razão",
        "ajuda": (
            "Casos recentes divididos pela média da mesma época do ano em anos anteriores. "
            "Acima de 1,00 = acima do padrão histórico daquele bairro."
        ),
    },
    "Densidade populacional": {
        "coluna": "densidade_populacional_hab_km2",
        "rotulo": "Hab./km²",
        "ajuda": "População do bairro no ano de referência dividida pela área do bairro em km².",
    },
}

gold, freshness = iniciar_pagina(
    "Mapa territorial",
    "Distribuição dos casos pelos 94 bairros do Recife, com a métrica alternável. Nenhum dado "
    "individual é exibido: a menor unidade do painel é bairro × semana.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

geojson = load_bairro_geojson()
if geojson is None:
    st.warning(
        "A geometria dos bairros não está disponível nesta publicação, então o mapa não pode ser "
        "desenhado. As demais páginas continuam funcionando; a tabela por bairro abaixo substitui "
        "o mapa nesta sessão.",
        icon="⚠️",
    )

try:
    filtros = renderizar_filtros(gold, key_prefix="mapa", permitir_escopo_geografico=False)
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

st.caption(f"Recorte ativo: **{descrever_recorte(filtros, gold)}**")

df = aplicar_filtros(
    gold, agravo=filtros["agravo"], ano_inicio=filtros["ano_inicio"], ano_fim=filtros["ano_fim"]
)
if not exigir_dados(not df.empty, "Nenhum registro para o recorte selecionado."):
    st.stop()

base = df if filtros["agravo"] else total_arboviroses(df)
if "codigo_rpa" not in base.columns:
    base = base.merge(
        gold[["codigo_bairro", "codigo_rpa"]].drop_duplicates(), on="codigo_bairro", how="left"
    )
if "populacao_bairro_ano" not in base.columns:
    # população/densidade não dependem do agravo -- seguros para repor depois
    # de `total_arboviroses` colapsar as colunas não-chave. Incidência é
    # recalculada dentro de `prioridade_observada`, nunca repassada pronta.
    base = base.merge(
        gold[
            ["codigo_bairro", "ano_epidemiologico", "populacao_bairro_ano",
             "tipo_populacao", "densidade_populacional_hab_km2"]
        ].drop_duplicates(["codigo_bairro", "ano_epidemiologico"]),
        on=["codigo_bairro", "ano_epidemiologico"], how="left",
    )

acumulado = (
    base.groupby(["codigo_bairro", "nome_bairro"], observed=True)["casos"]
    .sum()
    .reset_index(name="casos_acumulados")
)
tabela = prioridade_observada(base).merge(acumulado, on=["codigo_bairro", "nome_bairro"], how="outer")
tabela["casos_acumulados"] = tabela["casos_acumulados"].fillna(0)

rotulo_metrica = st.radio(
    "Métrica exibida",
    options=list(METRICAS),
    horizontal=True,
    key="mapa_metrica",
)
rotulo_metrica = validar_escolha(rotulo_metrica, list(METRICAS), "Métrica", permitir_nulo=False)
config = METRICAS[rotulo_metrica]
st.caption(config["ajuda"])

if INCIDENCIA_DISPONIVEL and config["coluna"] in ("incidencia_100k", "incidencia_4s_100k", "densidade_populacional_hab_km2"):
    tipos_no_recorte = sorted(tabela["tipo_populacao"].dropna().unique().tolist())
    st.caption(
        f"População usada nesta visão: {', '.join(tipos_no_recorte) if tipos_no_recorte else 'indisponível'}. "
        "Anos de Censo (2010, 2022) usam população observada; os demais usam estimativa "
        "intercensitária ou projeção pós-Censo reconstruída por este projeto — ver "
        "`reports/population/population_incidence_integration.md` para o método e a margem de erro."
    )

with secao_protegida("Mapa coroplético"):
    if geojson is not None:
        dados_mapa = tabela.dropna(subset=[config["coluna"]])
        if exigir_dados(
            not dados_mapa.empty,
            "Nenhum bairro tem valor calculável para esta métrica no recorte selecionado.",
        ):
            st.plotly_chart(
                grafico_mapa_metricas(
                    dados_mapa,
                    geojson,
                    coluna_valor=config["coluna"],
                    rotulo_valor=config["rotulo"],
                    titulo=f"{rotulo_metrica} — {descrever_recorte(filtros, gold)}",
                    hover_extra=[
                        "codigo_rpa", "tendencia", "casos_janela_recente",
                        "populacao_bairro_ano", "tipo_populacao", "incidencia_4s_100k",
                    ],
                ),
                use_container_width=True,
            )
            st.caption(
                "Passe o cursor sobre um bairro para ver RPA, tendência e casos recentes. "
                "A escala de cor é sequencial (mais escuro = valor mais alto) e nunca representa "
                "categoria de risco."
            )

st.divider()

st.markdown("## Detalhe por bairro")
exibicao = tabela.sort_values(config["coluna"], ascending=False).copy()
exibicao = exibicao.assign(
    Bairro=exibicao["nome_bairro"].str.title(),
    RPA=exibicao["codigo_rpa"],
    **{
        "Casos no período": exibicao["casos_acumulados"].astype("Int64"),
        f"Casos ({JANELA_RECENTE_SEMANAS} sem.)": exibicao["casos_janela_recente"].astype("Int64"),
        "População usada": exibicao["populacao_bairro_ano"].map(
            lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", ".")
        ),
        "Tipo pop.": exibicao["tipo_populacao"].fillna("—"),
        f"Incidência ({JANELA_RECENTE_SEMANAS} sem.)/100k": exibicao["incidencia_4s_100k"].map(
            lambda v: "—" if pd.isna(v) else f"{v:.1f}"
        ),
        "Densidade (hab./km²)": exibicao["densidade_populacional_hab_km2"].map(
            lambda v: "—" if pd.isna(v) else f"{v:,.0f}".replace(",", ".")
        ),
        "Tendência": exibicao["tendencia"],
        "Razão vs. histórico": exibicao["razao_historico"].map(
            lambda v: "—" if pd.isna(v) else f"{v:.2f}×"
        ),
    },
)[
    ["Bairro", "RPA", "Casos no período", f"Casos ({JANELA_RECENTE_SEMANAS} sem.)",
     "População usada", "Tipo pop.", f"Incidência ({JANELA_RECENTE_SEMANAS} sem.)/100k",
     "Densidade (hab./km²)", "Tendência", "Razão vs. histórico"]
]
st.dataframe(exibicao, use_container_width=True, hide_index=True, height=420)
st.caption(
    f"{numero(len(exibicao))} bairros no recorte. Tabela rolável horizontalmente em telas estreitas."
)
if config["coluna"] in ("incidencia_100k", "incidencia_4s_100k"):
    st.warning(
        "Taxas de curto prazo podem variar fortemente em bairros de menor população: um único caso "
        "a mais ou a menos muda a incidência de forma desproporcional. Os valores não são ocultados "
        "para nenhum bairro.",
        icon="⚠️",
    )
