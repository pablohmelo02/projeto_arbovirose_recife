"""Situação epidemiológica: casos por semana, comparação com o período
anterior e comparação sazonal, com filtros combináveis."""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import (
    descrever_recorte,
    renderizar_filtros,
    tratar_entrada_invalida,
)
from dashboard.components.graficos import grafico_comparacao_agravos
from dashboard.components.graficos_produto import (
    grafico_casos_por_ano,
    grafico_comparacao_sazonal,
    grafico_serie_com_media_movel,
)
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero, variacao_com_sinal
from dashboard.utils.validacao import EntradaInvalidaError
from src.eda import epidemiologia
from src.eda.filtros import aplicar_filtros, total_arboviroses
from src.eda.prioridade_observada import (
    JANELA_RECENTE_SEMANAS,
    prioridade_observada,
    resumo_situacao,
    ultima_semana_disponivel,
)

gold, freshness = iniciar_pagina(
    "Situação epidemiológica",
    "Casos notificados por semana epidemiológica, comparação com o período anterior e com a mesma "
    "época de anos anteriores. Dengue é o agravo padrão; zika e chikungunya seguem disponíveis "
    "como comparação.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

try:
    filtros = renderizar_filtros(gold, key_prefix="situacao")
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

st.caption(f"Recorte ativo: **{descrever_recorte(filtros, gold)}**")

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

# ---------------------------------------------------------------------------
# Indicadores do recorte
# ---------------------------------------------------------------------------
resumo = epidemiologia.resumo_epidemiologico(df)
df_para_prioridade = df if filtros["agravo"] else total_arboviroses(df)
if "codigo_rpa" not in df_para_prioridade.columns:
    df_para_prioridade = df_para_prioridade.merge(
        gold[["codigo_bairro", "codigo_rpa"]].drop_duplicates(), on="codigo_bairro", how="left"
    )
tabela_prioridade = prioridade_observada(df_para_prioridade)
situacao = resumo_situacao(df_para_prioridade, tabela_prioridade)
ultima = ultima_semana_disponivel(df)

linha_de_cartoes(
    [
        ("Casos no recorte", numero(resumo["total_casos"]), f"{resumo['total_semanas_distintas']} semanas"),
        (
            f"Casos nas últimas {JANELA_RECENTE_SEMANAS} semanas",
            numero(situacao["casos_janela_recente_cidade"]),
            f"Encerradas em SE {ultima[1]} / {ultima[0]}" if ultima else "—",
        ),
        (
            "Incidência (100 mil hab.) no período recente",
            numero(situacao["incidencia_janela_recente_100k_cidade"], decimais=1),
            f"Últimas {JANELA_RECENTE_SEMANAS} semanas — 'sem base' se a população do ano não estiver disponível",
        ),
        (
            "Variação sobre o período anterior",
            variacao_com_sinal(situacao["variacao_pct_cidade"]),
            f"Comparação com as {JANELA_RECENTE_SEMANAS} semanas imediatamente anteriores",
        ),
        (
            "Bairros com pelo menos 1 caso",
            f"{resumo['bairros_com_pelo_menos_1_caso']} de {resumo['total_bairros']}",
            "No recorte completo selecionado",
        ),
    ]
)
st.caption(
    "**Incidência** = casos da janela dividido pela população total da cidade no ano de referência, "
    "vezes 100.000 — uma única divisão sobre os totais, nunca a soma das incidências por bairro. "
    "Onde é preciso comparar bairros de tamanhos diferentes ver também a razão contra o próprio "
    "histórico do bairro (**Bairros prioritários**)."
)

st.divider()

# ---------------------------------------------------------------------------
# Série semanal
# ---------------------------------------------------------------------------
st.markdown("## Casos por semana epidemiológica")
with secao_protegida("Série semanal"):
    if filtros["agravo"]:
        serie = epidemiologia.serie_temporal_semanal(df, por_agravo=False)
        st.plotly_chart(
            grafico_serie_com_media_movel(serie, f"Casos de {filtros['agravo'].lower()} por semana"),
            use_container_width=True,
        )
    else:
        from dashboard.components.graficos import grafico_serie_temporal

        serie = epidemiologia.serie_temporal_semanal(df, por_agravo=True)
        st.plotly_chart(
            grafico_serie_temporal(serie, "Casos por semana epidemiológica, por agravo"),
            use_container_width=True,
        )

st.divider()

# ---------------------------------------------------------------------------
# Comparação sazonal
# ---------------------------------------------------------------------------
st.markdown("## Comparação sazonal entre anos")
st.markdown(
    "Cada linha é um ano epidemiológico; o ano em destaque aparece em vermelho. Responde "
    "diretamente: *nesta época do ano, estamos acima ou abaixo dos anos anteriores?*"
)
with secao_protegida("Comparação sazonal"):
    base_sazonal = df if filtros["agravo"] else total_arboviroses(df)
    por_ano_semana = (
        base_sazonal.groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)["casos"]
        .sum()
        .reset_index()
    )
    anos = sorted(int(a) for a in por_ano_semana["ano_epidemiologico"].unique())
    if exigir_dados(len(anos) > 0, "Sem anos disponíveis no recorte."):
        ano_destaque = st.selectbox(
            "Ano em destaque", options=list(reversed(anos)), index=0, key="situacao_ano_destaque"
        )
        st.plotly_chart(
            grafico_comparacao_sazonal(
                por_ano_semana, ano_destaque,
                f"Casos por semana epidemiológica — {ano_destaque} em destaque",
            ),
            use_container_width=True,
        )

st.divider()

# ---------------------------------------------------------------------------
# Totais por ano e comparação entre agravos
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("### Total por ano")
    with secao_protegida("Total por ano"):
        por_ano = (
            (df if filtros["agravo"] else total_arboviroses(df))
            .groupby("ano_epidemiologico", observed=True)["casos"]
            .sum()
            .reset_index()
        )
        st.plotly_chart(
            grafico_casos_por_ano(por_ano, "Casos notificados por ano epidemiológico"),
            use_container_width=True,
        )

with col2:
    st.markdown("### Dengue, zika e chikungunya")
    st.caption(
        "Escalas separadas por agravo: dengue tem volume muito maior, e forçar os três na mesma "
        "escala tornaria zika e chikungunya ilegíveis."
    )
    with secao_protegida("Comparação entre agravos"):
        df_todos = aplicar_filtros(
            gold,
            ano_inicio=filtros["ano_inicio"],
            ano_fim=filtros["ano_fim"],
            codigo_rpa=filtros["codigo_rpa"],
            codigo_bairro=filtros["codigo_bairro"],
        )
        st.plotly_chart(
            grafico_comparacao_agravos(epidemiologia.comparar_agravos(df_todos)),
            use_container_width=True,
        )

st.caption(
    "Fonte: Portal de Dados Abertos do Recife (CKAN), casos notificados ao SINAN. Notificação é "
    "compulsória, portanto ausência de notificação numa semana é lida como zero caso — não como "
    "dado faltante. Subnotificação permanece um risco conhecido e não é corrigida por este painel."
)
