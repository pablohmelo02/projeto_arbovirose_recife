import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.filtros_sidebar import renderizar_filtros
from dashboard.components.graficos import grafico_ranking_bairros
from dashboard.utils.data_loader import load_gold_data
from src.eda import epidemiologia
from src.eda.filtros import aplicar_filtros, total_arboviroses

st.title("🏘️ Ranking de bairros")
st.caption("Ranking por total de casos no recorte selecionado (agravo/anos/RPA) — sem incidência (sem dado de população).")

df_gold = load_gold_data()
filtros_sel = renderizar_filtros(df_gold, key_prefix="bairros", permitir_escopo_geografico=False)

df_filtrado = aplicar_filtros(
    df_gold, agravo=filtros_sel["agravo"], ano_inicio=filtros_sel["ano_inicio"], ano_fim=filtros_sel["ano_fim"],
)
if filtros_sel["agravo"] is None:
    df_para_ranking = total_arboviroses(df_filtrado)
else:
    df_para_ranking = df_filtrado

top_n_label = st.radio("Mostrar", options=["Top 10", "Top 20", "Todos os bairros"], horizontal=True, key="bairros_top_n")
top_n = {"Top 10": 10, "Top 20": 20, "Todos os bairros": None}[top_n_label]

ranking = epidemiologia.rank_bairros(df_para_ranking, metrica="casos", top_n=top_n)

titulo = f"Bairros por casos — {filtros_sel['agravo'] or 'total de arboviroses'}, {filtros_sel['ano_inicio']}-{filtros_sel['ano_fim']}"
st.plotly_chart(grafico_ranking_bairros(ranking, "casos", titulo), use_container_width=True)

with st.expander("Tabela completa"):
    st.dataframe(ranking, use_container_width=True)
