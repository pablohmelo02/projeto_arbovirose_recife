import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.filtros_sidebar import renderizar_filtros
from dashboard.components.kpi import alerta_qualidade, renderizar_kpis
from dashboard.utils.data_loader import load_gold_data
from src.eda import epidemiologia
from src.eda.filtros import aplicar_filtros
from src.eda.schema_eda import ANO_INICIO_COBERTURA_CLIMATICA_REAL

st.title("🏠 Visão Geral")
st.caption(
    "Plataforma de vigilância territorial de Dengue, Zika e Chikungunya no Recife — "
    "dados reais SINAN/CKAN (2013-2025), território oficial (94 bairros) e clima real "
    "CEMADEN (2024-2025, após backfill histórico)."
)

df_gold = load_gold_data()
filtros_sel = renderizar_filtros(df_gold, key_prefix="visao_geral")

df_filtrado = aplicar_filtros(
    df_gold,
    agravo=filtros_sel["agravo"],
    ano_inicio=filtros_sel["ano_inicio"],
    ano_fim=filtros_sel["ano_fim"],
    codigo_rpa=filtros_sel["codigo_rpa"],
    codigo_bairro=filtros_sel["codigo_bairro"],
)
# agravo=None mantém as linhas dos 3 agravos -- somar "casos" aqui já dá o
# total de arboviroses corretamente, sem precisar colapsar o DataFrame
# (colapsar destruiria as colunas climáticas usadas nos KPIs abaixo).
resumo = epidemiologia.resumo_epidemiologico(df_filtrado)

st.subheader("Indicadores do recorte selecionado")
renderizar_kpis(
    [
        ("Total de casos", f"{resumo['total_casos']:,}".replace(",", "."), None),
        ("Bairros no recorte", str(resumo["total_bairros"]), None),
        (
            "Período",
            f"{resumo['ano_epidemiologico_min']}–{resumo['ano_epidemiologico_max']}"
            if resumo["ano_epidemiologico_min"] is not None
            else "—",
            None,
        ),
        ("Semanas epidemiológicas", str(resumo["total_semanas_distintas"]), None),
        ("Bairros com ≥1 caso", str(resumo["bairros_com_pelo_menos_1_caso"]), None),
        (
            "Bairros com clima real",
            str(resumo["bairros_com_clima_real"]),
            "Só existe leitura climática real a partir de 2024 (backfill CEMADEN) — ver página Clima.",
        ),
    ]
)

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Escopo epidemiológico + territorial")
    st.markdown(
        "- Cobre **2013–2025** (13 anos), 94 bairros, 3 agravos.\n"
        "- Grão: `bairro × semana epidemiológica × agravo`.\n"
        "- `casos = 0` é dado real (notificação compulsória), não ausência de informação."
    )
with col2:
    st.markdown("#### Escopo climático real (integrado)")
    st.markdown(
        f"- Clima real **só a partir de {ANO_INICIO_COBERTURA_CLIMATICA_REAL}** "
        "(rede CEMADEN, após backfill histórico de 730 dias).\n"
        "- **2013–2023 não têm clima real** — nenhuma fonte investigada resolve esse período.\n"
        "- Ver página **Clima × Arboviroses** para a EDA integrada, restrita a 2024-2025."
    )

if resumo["percentual_linhas_com_clima_real"] == 0.0 and filtros_sel["ano_fim"] < ANO_INICIO_COBERTURA_CLIMATICA_REAL:
    alerta_qualidade(
        f"O recorte selecionado (até {filtros_sel['ano_fim']}) não tem nenhuma linha com clima real — "
        "isso é esperado, não um erro (ver limitação acima)."
    )
