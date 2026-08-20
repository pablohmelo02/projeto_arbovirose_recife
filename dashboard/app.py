"""Ponto de entrada do dashboard Streamlit.

Uso local:

    streamlit run dashboard/app.py

O dataset consumido é o exportado por `python -m src.export_dashboard_dataset`
(ver `dashboard/utils/data_loader.py`) — a aplicação nunca lê o Data
Lake/MinIO diretamente, o que permite publicá-la no Streamlit Community
Cloud sem nenhuma infraestrutura adicional.
"""
import _bootstrap  # noqa: F401  -- garante `src` importável antes de qualquer outra coisa

import streamlit as st

st.set_page_config(
    page_title="Vigilância de Arboviroses — Recife",
    page_icon="🦟",
    layout="wide",
)

pagina_visao_geral = st.Page("pages/1_visao_geral.py", title="Visão Geral", icon="🏠", default=True)
pagina_epidemiologia = st.Page("pages/2_epidemiologia.py", title="Epidemiologia (2013-2025)", icon="📈")
pagina_mapa = st.Page("pages/3_mapa.py", title="Mapa Epidemiológico", icon="🗺️")
pagina_bairros = st.Page("pages/4_bairros.py", title="Ranking de Bairros", icon="🏘️")
pagina_clima = st.Page("pages/5_clima.py", title="Clima (CEMADEN)", icon="🌧️")
pagina_clima_arboviroses = st.Page("pages/6_clima_arboviroses.py", title="Clima × Arboviroses (2024-2025)", icon="🔗")
pagina_qualidade = st.Page("pages/7_qualidade_dados.py", title="Qualidade dos Dados", icon="✅")

navegacao = st.navigation(
    [
        pagina_visao_geral,
        pagina_epidemiologia,
        pagina_mapa,
        pagina_bairros,
        pagina_clima,
        pagina_clima_arboviroses,
        pagina_qualidade,
    ]
)

with st.sidebar:
    st.title("🦟 Arboviroses Recife")
    st.caption(
        "Vigilância territorial de Dengue, Zika e Chikungunya — "
        "dados públicos SINAN/CKAN + território + clima (CEMADEN)."
    )

navegacao.run()
