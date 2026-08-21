"""Página inicial — responde em poucos segundos o que o painel é, o que
cobre, até quando vai e onde olhar primeiro."""
import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.graficos_produto import grafico_serie_com_media_movel
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero, variacao_com_sinal
from dashboard.utils.data_loader import load_priority_status
from src.eda import epidemiologia
from src.eda.filtros import aplicar_filtros
from src.eda.prioridade_observada import (
    JANELA_RECENTE_SEMANAS,
    prioridade_observada,
    resumo_situacao,
    ultima_semana_disponivel,
)

AGRAVO_PRINCIPAL = "DENGUE"

gold, freshness = iniciar_pagina(
    "Recife Alerta",
    "Plataforma de inteligência epidemiológica e priorização territorial para apoiar ações "
    "preventivas contra a dengue nos 94 bairros do Recife. Todos os números desta página são "
    "<b>observados</b> — o que os registros oficiais mostram, sem projeção.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

df_dengue = aplicar_filtros(gold, agravo=AGRAVO_PRINCIPAL)
ultima = ultima_semana_disponivel(df_dengue)
tabela = prioridade_observada(df_dengue)
situacao = resumo_situacao(df_dengue, tabela)
resumo_geral = epidemiologia.resumo_epidemiologico(gold)

# ---------------------------------------------------------------------------
# 1. Situação da dengue no último período disponível
# ---------------------------------------------------------------------------
st.markdown("## Dengue no último período disponível")
rotulo_semana = f"SE {ultima[1]} / {ultima[0]}" if ultima else "—"
linha_de_cartoes(
    [
        (
            f"Casos nas últimas {JANELA_RECENTE_SEMANAS} semanas",
            numero(situacao["casos_janela_recente_cidade"]),
            f"Período encerrado em {rotulo_semana}",
        ),
        (
            "Variação sobre as 4 semanas anteriores",
            variacao_com_sinal(situacao["variacao_pct_cidade"]),
            f"Tendência da cidade: {situacao['tendencia_cidade']}",
        ),
        (
            "Bairros em alta",
            f"{situacao['bairros_em_alta']} de {situacao['total_bairros']}",
            "Crescimento de 20% ou mais frente às 4 semanas anteriores",
        ),
        (
            "Bairros acima do próprio histórico",
            f"{situacao['bairros_acima_do_historico']} de {situacao['total_bairros']}",
            "Comparação com a mesma época do ano em anos anteriores",
        ),
    ]
)

with secao_protegida("Série semanal de dengue"):
    serie = epidemiologia.serie_temporal_semanal(df_dengue, por_agravo=False)
    if exigir_dados(not serie.empty, "Sem série temporal para o recorte carregado."):
        st.plotly_chart(
            grafico_serie_com_media_movel(
                serie, "Casos de dengue por semana epidemiológica — Recife (todos os bairros)"
            ),
            use_container_width=True,
        )
        st.caption(
            "As barras são o observado semana a semana; a linha é a média móvel de 4 semanas, "
            "que apenas torna a tendência legível — nenhum valor é suavizado ou estimado."
        )

st.divider()

# ---------------------------------------------------------------------------
# 2. Onde olhar primeiro
# ---------------------------------------------------------------------------
st.markdown("## Onde olhar primeiro")
st.markdown(
    "Bairros com mais casos de dengue nas últimas semanas, com a leitura de tendência e a "
    "comparação contra o próprio histórico. Ordenação por volume recente — sem categoria de risco, "
    "porque o projeto não tem população por bairro e, portanto, não calcula incidência."
)

with secao_protegida("Bairros a observar"):
    if exigir_dados(not tabela.empty, "Sem dados suficientes para montar a lista."):
        topo = tabela.head(10).copy()
        exibicao = topo.assign(
            Bairro=topo["nome_bairro"].str.title(),
            RPA=topo["codigo_rpa"],
            **{
                f"Casos ({JANELA_RECENTE_SEMANAS} sem.)": topo["casos_janela_recente"].astype("Int64"),
                "Variação": topo["variacao_pct"].map(variacao_com_sinal),
                "Tendência": topo["tendencia"],
                "Razão vs. histórico": topo["razao_historico"].map(
                    lambda v: "—" if v is None else f"{v:.2f}×"
                ),
            },
        )[
            ["Bairro", "RPA", f"Casos ({JANELA_RECENTE_SEMANAS} sem.)", "Variação", "Tendência",
             "Razão vs. histórico"]
        ]
        exibicao.insert(0, "Prioridade", range(1, len(exibicao) + 1))
        st.dataframe(exibicao, use_container_width=True, hide_index=True)
        st.caption(
            "**Razão vs. histórico**: casos recentes divididos pela média da mesma época do ano em "
            "anos anteriores. Acima de 1,00× = acima do padrão histórico daquele bairro. "
            "Ver a página **Bairros prioritários** para a lista completa e outros critérios de ordenação."
        )

st.divider()

# ---------------------------------------------------------------------------
# 3. Cobertura, período e módulo experimental
# ---------------------------------------------------------------------------
col_esq, col_dir = st.columns([3, 2], gap="large")

with col_esq:
    st.markdown("### O que este painel cobre")
    st.markdown(
        f"- **Território:** 94 bairros do Recife, agrupados em 6 RPAs.\n"
        f"- **Período:** {resumo_geral['ano_epidemiologico_min']}–{resumo_geral['ano_epidemiologico_max']} "
        f"({resumo_geral['total_semanas_distintas']} semanas epidemiológicas).\n"
        f"- **Agravos:** dengue (principal), zika e chikungunya (comparação).\n"
        f"- **Casos notificados no período:** {numero(resumo_geral['total_casos'])}.\n"
        "- **Grão dos dados:** bairro × semana epidemiológica × agravo. Semana sem notificação "
        "aparece como zero real, não como ausência de informação."
    )

with col_dir:
    st.markdown("### Módulo experimental de priorização")
    status = load_priority_status()
    if status is None:
        st.info(
            "O módulo experimental não está disponível nesta publicação. "
            "O painel histórico funciona normalmente.",
            icon="ℹ️",
        )
    else:
        if status.get("current_projection_available"):
            st.markdown(
                "Há dados recentes o suficiente para uma priorização referente ao período atual. "
                "Ver a página **Priorização experimental**."
            )
        else:
            st.markdown(
                "**Priorização do período atual indisponível** — os dados oficiais publicados não "
                "cobrem um período recente o bastante. O módulo oferece apenas **simulação "
                "histórica (backtest)**: escolher uma semana passada e ver o que o sistema teria "
                "priorizado e o que aconteceu depois."
            )
        st.caption(
            "Módulo experimental. Resultados retrospectivos e sinais de priorização não substituem "
            "avaliação epidemiológica nem representam previsão oficial da Prefeitura do Recife."
        )

st.divider()

with st.expander("Perguntas que o Recife Alerta ajuda a responder"):
    st.markdown(
        """
| Pergunta | Onde responder |
|---|---|
| Onde há maior concentração de casos? | **Mapa territorial** · **Bairros prioritários** |
| Quais bairros estão acelerando? | **Bairros prioritários** (tendência e variação) |
| Qual é o comportamento sazonal? | **Evolução histórica** (comparação entre anos) |
| Quais territórios merecem priorização? | **Bairros prioritários** (observado) e **Priorização experimental** (modelo) |
| Existe antecedência entre sinal e aumento observado? | **Priorização experimental** (lead time, backtest) |
| O modelo é igualmente confiável em todos os bairros? | **Priorização experimental** — não é; a heterogeneidade é mostrada |
| Como a capacidade operacional interfere? | **Priorização experimental** (Top-5/10/15/20) |
| O clima acrescenta informação ao modelo? | **Clima × Dengue** e **Qualidade e limitações** |
| Até quando os dados são confiáveis? | Faixa **Atualização dos dados**, no topo de cada página |

O objetivo de longo prazo do desafio — reduzir incidência e gravidade dos surtos por atuação
antecipada — orienta o produto, mas **este painel não demonstra redução de incidência nem de
internações**, e não faz essa afirmação em nenhum lugar.
        """
    )
