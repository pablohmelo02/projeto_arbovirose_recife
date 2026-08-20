import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.filtros_sidebar import renderizar_filtros
from dashboard.components.graficos import grafico_mapa_coropletico
from dashboard.components.kpi import alerta_qualidade
from dashboard.utils.data_loader import load_bairro_geojson, load_gold_data
from src.eda.filtros import aplicar_filtros
from src.eda.schema_eda import INCIDENCIA_DISPONIVEL

st.title("🗺️ Mapa epidemiológico")
st.caption("Geometria oficial dos 94 bairros do Recife (silver_bairro_geo) — nenhuma simplificação inventada.")

df_gold = load_gold_data()
geojson = load_bairro_geojson()

filtros_sel = renderizar_filtros(df_gold, key_prefix="mapa", permitir_escopo_geografico=False)

df_filtrado = aplicar_filtros(
    df_gold, agravo=filtros_sel["agravo"], ano_inicio=filtros_sel["ano_inicio"], ano_fim=filtros_sel["ano_fim"],
)

if not INCIDENCIA_DISPONIVEL:
    st.caption(
        "ℹ️ 'Incidência por 100 mil' não está disponível — nenhuma fonte do projeto tem população por bairro "
        "(ver `src/gold/schema_gold_arboviroses_clima.py`). O mapa mostra apenas contagem absoluta de casos."
    )

metrica = st.radio("Métrica", options=["Casos"], horizontal=True, key="mapa_metrica")

agregado = (
    df_filtrado.groupby(["codigo_bairro", "nome_bairro"], observed=True)
    .agg(casos=("casos", "sum"), area_km2=("area_km2", "first"), codigo_rpa=("codigo_rpa", "first"))
    .reset_index()
)

st.plotly_chart(
    grafico_mapa_coropletico(
        agregado, geojson, coluna_valor="casos",
        titulo=f"Casos ({filtros_sel['agravo'] or 'todos os agravos'}, "
        f"{filtros_sel['ano_inicio']}-{filtros_sel['ano_fim']})",
        hover_extra=["area_km2", "codigo_rpa"],
    ),
    use_container_width=True,
)

if agregado["casos"].sum() == 0:
    alerta_qualidade("Nenhum caso no recorte selecionado — o mapa fica uniformemente vazio (não é um erro).")

with st.expander("Detalhe por bairro (tabela)"):
    st.dataframe(
        agregado.sort_values("casos", ascending=False).reset_index(drop=True),
        use_container_width=True,
    )
