import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.filtros_sidebar import renderizar_filtros
from dashboard.components.graficos import (
    grafico_cobertura_por_ano,
    grafico_heatmap_cobertura,
    grafico_precipitacao,
)
from dashboard.components.kpi import alerta_qualidade, renderizar_kpis
from dashboard.utils.data_loader import load_gold_data
from src.eda import clima
from src.eda.filtros import aplicar_filtros
from src.eda.schema_eda import ANO_INICIO_COBERTURA_CLIMATICA_REAL

st.title("🌧️ Clima (CEMADEN)")
st.info(
    f"Cobertura climática real está concentrada em **{ANO_INICIO_COBERTURA_CLIMATICA_REAL}-2025** "
    "(backfill histórico do CEMADEN, 730 dias, para as 16 estações usadas pela Estratégia A). "
    "2013-2023 não têm clima real — ver "
    "`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`.",
    icon="🌦️",
)

df_gold = load_gold_data()
filtros_sel = renderizar_filtros(df_gold, key_prefix="clima")

df_filtrado = aplicar_filtros(
    df_gold,
    agravo=filtros_sel["agravo"],
    ano_inicio=filtros_sel["ano_inicio"],
    ano_fim=filtros_sel["ano_fim"],
    codigo_rpa=filtros_sel["codigo_rpa"],
    codigo_bairro=filtros_sel["codigo_bairro"],
)

resumo = clima.resumo_cobertura_climatica(df_filtrado)

st.subheader("Cobertura climática do recorte selecionado")
renderizar_kpis(
    [
        ("Linhas com clima real", f"{resumo['linhas_com_clima_real']:,}".replace(",", "."), None),
        ("% linhas com clima real", f"{resumo['percentual_linhas_com_clima_real']:.2f}%", None),
        (
            "Bairros com clima real",
            f"{resumo['bairros_com_clima_real']}/{resumo['total_bairros']}",
            None,
        ),
        ("% bairros com clima real", f"{resumo['percentual_bairros_com_clima_real']:.1f}%", None),
        ("Estações distintas usadas", str(resumo["estacoes_distintas"]), None),
        ("Fonte(s) climática(s)", ", ".join(resumo["fontes_climaticas"]) or "—", None),
    ]
)
if resumo["linhas_com_clima_real"] == 0:
    alerta_qualidade("Nenhuma linha com clima real no recorte selecionado.")

st.divider()

st.subheader("Cobertura climática por ano epidemiológico")
tabela_ano = clima.cobertura_por_ano(df_filtrado)
st.plotly_chart(grafico_cobertura_por_ano(tabela_ano), use_container_width=True)
st.caption("Nenhum ano é forçado a 100% — anos sem clima real aparecem como 0%, não são omitidos.")

st.subheader("Cobertura climática por ano × semana epidemiológica")
st.caption("A disponibilidade climática não é homogênea no tempo — este heatmap torna isso explícito.")
grade = clima.cobertura_ano_semana(df_filtrado)
if not grade.empty:
    st.plotly_chart(grafico_heatmap_cobertura(grade), use_container_width=True)

st.divider()

st.subheader("Precipitação semanal real")
serie_precip = clima.serie_precipitacao(df_filtrado)
if serie_precip.empty:
    alerta_qualidade("Sem observações de precipitação real no recorte selecionado.")
else:
    st.plotly_chart(grafico_precipitacao(serie_precip), use_container_width=True)
    st.caption(
        f"Série calculada sobre {serie_precip['bairros_considerados'].sum()} observações "
        "bairro-semana com leitura real (média entre bairros com clima real na semana)."
    )
