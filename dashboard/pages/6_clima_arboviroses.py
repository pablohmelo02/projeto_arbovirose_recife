import _bootstrap  # noqa: F401

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.components.filtros_sidebar import renderizar_filtros
from dashboard.components.graficos import CORES_AGRAVOS, grafico_dispersao_lag, grafico_lag_correlacoes
from dashboard.components.kpi import alerta_qualidade, renderizar_kpis
from dashboard.utils.data_loader import load_gold_data
from src.eda import correlacao, epidemiologia
from src.eda.filtros import aplicar_filtros, linhas_com_clima_real
from src.eda.schema_eda import AGRAVOS, JANELAS_LAG_DIAS

st.title("🔗 Clima × Arboviroses")
st.warning(
    "Esta página é **restrita automaticamente** às linhas com clima real (nunca `fillna(0)`). "
    "A janela climática é curta (2024-2025) — qualquer correlação aqui **não deve ser generalizada "
    "para 2013-2025**, nem interpretada como causalidade.",
    icon="⚠️",
)

df_gold = load_gold_data()
filtros_sel = renderizar_filtros(df_gold, key_prefix="clima_arbo", permitir_escopo_geografico=False)

agravo_selecionado = filtros_sel["agravo"] or AGRAVOS[0]
if filtros_sel["agravo"] is None:
    st.caption(f"Nenhum agravo selecionado no filtro — usando **{agravo_selecionado}** por padrão nesta página (lags são específicos por agravo).")

df_filtrado = aplicar_filtros(
    df_gold, agravo=agravo_selecionado, ano_inicio=filtros_sel["ano_inicio"], ano_fim=filtros_sel["ano_fim"],
)
df_com_clima = linhas_com_clima_real(df_filtrado)

resumo = epidemiologia.resumo_epidemiologico(df_com_clima)
st.subheader("Tamanho da amostra desta análise (sempre visível)")
renderizar_kpis(
    [
        ("Observações com clima real", f"{len(df_com_clima):,}".replace(",", "."), None),
        ("Bairros considerados", str(resumo["total_bairros"]), None),
        (
            "Período real",
            f"{resumo['ano_epidemiologico_min']}-{resumo['ano_epidemiologico_max']}"
            if resumo["ano_epidemiologico_min"]
            else "—",
            None,
        ),
        ("Casos no recorte com clima", f"{resumo['total_casos']:,}".replace(",", "."), None),
    ]
)

if len(df_com_clima) == 0:
    alerta_qualidade("Nenhuma observação com clima real neste recorte — não é possível calcular correlação.")
    st.stop()

st.divider()

st.subheader("Casos × precipitação no tempo")
serie_casos = epidemiologia.serie_temporal_semanal(df_com_clima, por_agravo=False)
serie_precip = df_com_clima.groupby(
    ["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"], observed=True
)["precipitacao_total_semana_mm"].mean().reset_index()

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(
    go.Bar(x=serie_precip["semana_epi_data_inicio"], y=serie_precip["precipitacao_total_semana_mm"], name="Precipitação média (mm)", marker_color="#2471a3", opacity=0.6),
    secondary_y=False,
)
fig.add_trace(
    go.Scatter(x=serie_casos["semana_epi_data_inicio"], y=serie_casos["casos"], name=f"Casos ({agravo_selecionado})", line=dict(color=CORES_AGRAVOS.get(agravo_selecionado, "#c0392b"))),
    secondary_y=True,
)
fig.update_layout(template="plotly_white", title="Casos × precipitação (exploratório — não implica causalidade)")
fig.update_yaxes(title_text="Precipitação média (mm)", secondary_y=False)
fig.update_yaxes(title_text="Casos", secondary_y=True)
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Correlação exploratória por janela de lag")
tabela_lag = correlacao.compute_lag_correlations(df_filtrado)
st.plotly_chart(grafico_lag_correlacoes(tabela_lag, agravo_selecionado), use_container_width=True)
st.dataframe(tabela_lag, use_container_width=True)
st.caption("'Confiável' aqui só significa n ≥ 30 observações — não é um teste de significância estatística formal.")

st.divider()

st.subheader("Dispersão: precipitação acumulada × casos")
janela_escolhida = st.select_slider("Janela de lag (dias)", options=list(JANELAS_LAG_DIAS), value=7, key="clima_arbo_janela")
dispersao = correlacao.dados_dispersao_lag(df_filtrado, janela_dias=janela_escolhida)
if dispersao.empty:
    alerta_qualidade("Sem observações suficientes para esta janela de lag.")
else:
    st.plotly_chart(grafico_dispersao_lag(dispersao, janela_escolhida, agravo_selecionado), use_container_width=True)
