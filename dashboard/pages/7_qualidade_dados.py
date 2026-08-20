import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.graficos import grafico_antes_depois, grafico_matriz_correlacao
from dashboard.components.kpi import renderizar_kpis
from dashboard.utils.data_loader import load_export_profiling, load_gold_data
from src.eda import clima, correlacao

st.title("✅ Qualidade dos dados")
st.caption(
    "Esta página existe para que nenhum gráfico das outras páginas seja interpretado fora de contexto — "
    "a disponibilidade de clima real influencia qualquer relação aparente entre chuva e casos."
)

df_gold = load_gold_data()

st.subheader("Gold: antes × depois do backfill histórico do CEMADEN")
resumo_geral = clima.resumo_cobertura_climatica(df_gold)
st.plotly_chart(grafico_antes_depois(0.0, resumo_geral["percentual_linhas_com_clima_real"]), use_container_width=True)
renderizar_kpis(
    [
        ("Linhas Gold totais", f"{len(df_gold):,}".replace(",", "."), None),
        ("Linhas com clima real", f"{resumo_geral['linhas_com_clima_real']:,}".replace(",", "."), None),
        ("% com clima real", f"{resumo_geral['percentual_linhas_com_clima_real']:.4f}%", None),
        (
            "Bairros com clima real (algum período)",
            f"{resumo_geral['bairros_com_clima_real']}/{resumo_geral['total_bairros']}",
            None,
        ),
    ]
)
st.caption(
    "Ver `reports/climate_source_analysis/cemaden_historical_backfill_analysis.md` para a investigação "
    "completa de profundidade histórica e o backfill aplicado."
)

st.divider()

st.subheader("Matriz de correlação exploratória (casos × variáveis climáticas)")
st.caption(
    "Calculada só sobre linhas com clima real; nunca inclui códigos/IDs como variável numérica. "
    "Correlação não implica causalidade."
)
matriz, n_obs = correlacao.matriz_correlacao(df_gold)
if n_obs == 0:
    st.info("Sem observações com clima real para calcular a matriz.")
else:
    st.plotly_chart(grafico_matriz_correlacao(matriz, n_obs), use_container_width=True)

st.divider()

st.subheader("Proveniência do dataset publicado")
profiling = load_export_profiling()
if profiling:
    col1, col2, col3 = st.columns(3)
    col1.metric("Linhas exportadas", f"{profiling.get('linhas_gold', 0):,}".replace(",", "."))
    col2.metric("Tamanho do arquivo Gold", f"{profiling.get('tamanho_gold_bytes', 0) / 1e6:.2f} MB")
    col3.metric("Chaves duplicadas", str(profiling.get("chave_gold_duplicadas", "—")))
    with st.expander("Colunas publicadas"):
        st.write(profiling.get("colunas_gold", []))
else:
    st.info("Profiling da exportação não encontrado (rode `python -m src.export_dashboard_dataset`).")

st.divider()

st.subheader("Avisos gerais de viés de disponibilidade")
st.markdown(
    "- Qualquer relação aparente entre chuva e casos pode ser influenciada pela disponibilidade dos "
    "sensores CEMADEN (16 estações cobrindo os 94 bairros, distância mediana ~1,4 km, ver README §26).\n"
    "- A janela climática real (2024-2025) é curta frente aos 13 anos de dado epidemiológico — "
    "conclusões da página Clima × Arboviroses **não devem ser generalizadas** para 2013-2023.\n"
    "- `incidência por 100 mil` não está disponível em nenhuma página (sem dado de população por bairro)."
)
