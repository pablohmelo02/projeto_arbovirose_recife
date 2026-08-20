import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.filtros_sidebar import renderizar_filtros
from dashboard.components.graficos import (
    grafico_comparacao_agravos,
    grafico_sazonalidade,
    grafico_serie_temporal,
)
from dashboard.utils.data_loader import load_gold_data
from src.eda import epidemiologia
from src.eda.filtros import aplicar_filtros

st.title("📈 Evolução epidemiológica (2013-2025)")
st.caption(
    "Série completa de arboviroses no Recife — não depende de clima, então cobre todo o período real "
    "disponível (13 anos). Nenhuma conclusão de causalidade é feita nesta página."
)

df_gold = load_gold_data()
filtros_sel = renderizar_filtros(df_gold, key_prefix="epidemiologia")

df_filtrado = aplicar_filtros(
    df_gold,
    agravo=filtros_sel["agravo"],
    ano_inicio=filtros_sel["ano_inicio"],
    ano_fim=filtros_sel["ano_fim"],
    codigo_rpa=filtros_sel["codigo_rpa"],
    codigo_bairro=filtros_sel["codigo_bairro"],
)

st.subheader("Série temporal semanal")
por_agravo = filtros_sel["agravo"] is None
serie = epidemiologia.serie_temporal_semanal(df_filtrado, por_agravo=por_agravo)
titulo_serie = "Casos por semana epidemiológica" + (" (por agravo)" if por_agravo else f" — {filtros_sel['agravo']}")
st.plotly_chart(
    grafico_serie_temporal(serie, titulo_serie, coluna_agravo="agravo" if por_agravo else None),
    use_container_width=True,
)

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.subheader("Sazonalidade")
    st.caption("Padrão observado por semana epidemiológica — não implica causalidade nem previsão.")
    sazonalidade = epidemiologia.sazonalidade_semanal(df_filtrado)
    st.plotly_chart(
        grafico_sazonalidade(sazonalidade, "Casos médios por semana epidemiológica"),
        use_container_width=True,
    )

with col2:
    st.subheader("Comparação entre agravos")
    st.caption("Escalas separadas por agravo — Dengue tem volume muito maior que Zika/Chikungunya.")
    comparado = epidemiologia.comparar_agravos(df_filtrado)
    st.plotly_chart(grafico_comparacao_agravos(comparado), use_container_width=True)
