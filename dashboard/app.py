"""Recife Alerta — ponto de entrada da aplicação web.

Uso local:

    streamlit run dashboard/app.py

A aplicação consome exclusivamente os artefatos estáticos de
`dashboard/data/`, gerados por `python -m src.update_recife_alerta`. Ela
não acessa o Data Lake, não chama API externa, não treina modelo e não
depende de credencial — é isso que permite publicá-la no Streamlit
Community Cloud sem nenhuma infraestrutura.

## Organização

As páginas estão em dois grupos explícitos na navegação, para que nunca
haja dúvida sobre a natureza do que se está lendo:

- **Situação observada** — o que os registros oficiais mostram.
- **Apoio à decisão** — priorização observada e o módulo experimental
  (modelo), este último sempre marcado como experimental.
"""
import _bootstrap  # noqa: F401  -- garante `src` importável antes de tudo

import streamlit as st

st.set_page_config(
    page_title="Recife Alerta — vigilância de arboviroses",
    page_icon="🦟",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGINAS_SITUACAO = [
    st.Page("pages/1_inicio.py", title="Início", icon=":material/home:", default=True),
    st.Page("pages/2_situacao_epidemiologica.py", title="Situação epidemiológica", icon=":material/monitoring:"),
    st.Page("pages/3_mapa_territorial.py", title="Mapa territorial", icon=":material/map:"),
    st.Page("pages/5_evolucao_historica.py", title="Evolução histórica", icon=":material/timeline:"),
]

PAGINAS_DECISAO = [
    st.Page("pages/4_bairros_prioritarios.py", title="Bairros prioritários", icon=":material/flag:"),
    st.Page("pages/8_priorizacao_experimental.py", title="Priorização experimental", icon=":material/science:"),
]

PAGINAS_CLIMA = [
    st.Page("pages/6_clima.py", title="Clima", icon=":material/rainy:"),
    st.Page("pages/7_clima_dengue.py", title="Clima × Dengue", icon=":material/link:"),
]

PAGINAS_TRANSPARENCIA = [
    st.Page("pages/9_qualidade_limitacoes.py", title="Qualidade e limitações", icon=":material/fact_check:"),
]

navegacao = st.navigation(
    {
        "Situação observada": PAGINAS_SITUACAO,
        "Apoio à decisão": PAGINAS_DECISAO,
        "Contexto climático": PAGINAS_CLIMA,
        "Transparência": PAGINAS_TRANSPARENCIA,
    }
)

with st.sidebar:
    st.markdown("# Recife Alerta")
    st.caption(
        "Inteligência epidemiológica e priorização territorial para apoiar ações preventivas "
        "contra a dengue nos 94 bairros do Recife."
    )
    st.divider()

navegacao.run()

with st.sidebar:
    st.divider()
    st.caption(
        "Dados públicos: Portal de Dados Abertos do Recife (casos notificados e limites "
        "territoriais), CEMADEN (estações pluviométricas) e reanálise climática ERA5/ERA5-Land."
    )
    st.caption(
        "Ferramenta de apoio à decisão. Não representa previsão oficial da Prefeitura do Recife."
    )
