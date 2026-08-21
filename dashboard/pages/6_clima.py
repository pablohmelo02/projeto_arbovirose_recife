"""Clima — duas fontes com naturezas diferentes, nunca misturadas."""
import _bootstrap  # noqa: F401

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import renderizar_filtros, tratar_entrada_invalida
from dashboard.components.graficos import (
    COR_ATENCAO,
    COR_INSTITUCIONAL,
    LAYOUT_PADRAO,
    grafico_heatmap_cobertura,
    grafico_precipitacao,
)
from dashboard.components.graficos_produto import grafico_cobertura_dupla
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero, percentual
from dashboard.utils.validacao import EntradaInvalidaError
from src.eda import clima, clima_grade
from src.eda.filtros import aplicar_filtros

gold, freshness = iniciar_pagina(
    "Clima",
    "O painel usa duas fontes climáticas com naturezas diferentes: a rede de <b>estações físicas</b> "
    "(pluviômetros do CEMADEN), que mede chuva num ponto mas só cobre o período recente; e a "
    "<b>reanálise em grade</b> (ERA5 / ERA5-Land), que cobre todo o período mas em células muito "
    "maiores que um bairro. Elas aparecem separadas e nunca são somadas ou substituídas uma pela outra.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

try:
    filtros = renderizar_filtros(gold, key_prefix="clima", permitir_escopo_geografico=True)
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

df = aplicar_filtros(
    gold,
    agravo=filtros["agravo"],
    ano_inicio=filtros["ano_inicio"],
    ano_fim=filtros["ano_fim"],
    codigo_rpa=filtros["codigo_rpa"],
    codigo_bairro=filtros["codigo_bairro"],
)
if not exigir_dados(not df.empty, "Nenhum registro para o recorte selecionado."):
    st.stop()

tem_grade = clima_grade.gold_tem_clima_grade(df)

# ---------------------------------------------------------------------------
# Cobertura comparada
# ---------------------------------------------------------------------------
st.markdown("## Cobertura das duas fontes")
resumo_estacao = clima.resumo_cobertura_climatica(df)
resumo_grade = clima_grade.resumo_cobertura_grade(df)

linha_de_cartoes(
    [
        (
            "Reanálise em grade",
            percentual(resumo_grade.get("percentual_linhas")) if tem_grade else "indisponível",
            (
                f"{resumo_grade.get('celulas_precipitacao')} célula(s) de precipitação para 94 bairros"
                if tem_grade else "Bloco em grade ausente nesta publicação"
            ),
        ),
        (
            "Estações físicas",
            percentual(resumo_estacao["percentual_linhas_com_clima_real"]),
            f"{resumo_estacao['estacoes_distintas']} estação(ões) distinta(s) usada(s)",
        ),
        (
            "Bairros com estação associada",
            f"{resumo_estacao['bairros_com_clima_real']} de {resumo_estacao['total_bairros']}",
            "Associação pela estação elegível mais próxima",
        ),
        (
            "Anos com estação",
            ", ".join(str(a) for a in resumo_estacao["anos_com_clima_real"]) or "—",
            "Fora desses anos, só a reanálise tem valor",
        ),
    ]
)

with secao_protegida("Cobertura por ano"):
    tabela_dupla = clima_grade.cobertura_dupla_por_ano(df)
    if exigir_dados(not tabela_dupla.empty, "Sem dados de cobertura no recorte."):
        st.plotly_chart(
            grafico_cobertura_dupla(
                tabela_dupla, "Cobertura climática por ano: reanálise × estações físicas"
            ),
            use_container_width=True,
        )
        st.caption(
            "Nenhum ano é forçado a 100%: anos sem estação aparecem como 0%, não são omitidos. "
            "Ausência de leitura nunca é convertida em 0 mm."
        )

st.divider()

# ---------------------------------------------------------------------------
# Reanálise em grade — série e sazonalidade
# ---------------------------------------------------------------------------
if tem_grade:
    st.markdown("## Reanálise em grade — série longa")
    st.markdown(
        "Estimativa climática espacial derivada de reanálise em grade. **Não** é a leitura de uma "
        f"estação meteorológica de bairro: a precipitação vem de células de 0,25° (≈ 28 km) e a "
        f"temperatura/umidade de células de 0,10° (≈ 11 km). Para os 94 bairros do Recife isso "
        f"resolve apenas {resumo_grade.get('celulas_precipitacao')} célula(s) de chuva — o sinal diz "
        "*quando* chove na cidade, não *onde dentro dela*."
    )

    with secao_protegida("Série climática em grade"):
        serie = clima_grade.serie_climatica_grade(df)
        if exigir_dados(not serie.empty, "Sem série em grade no recorte."):
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Bar(
                    x=serie["semana_epi_data_inicio"], y=serie["precipitacao_mm"],
                    name="Precipitação semanal (mm)", marker_color=COR_INSTITUCIONAL, opacity=0.6,
                ),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=serie["semana_epi_data_inicio"], y=serie["temperatura_media_c"],
                    name="Temperatura média (°C)", line=dict(color=COR_ATENCAO, width=1.8),
                ),
                secondary_y=True,
            )
            fig.update_layout(**LAYOUT_PADRAO, title_text="Precipitação e temperatura semanais (reanálise)")
            fig.update_yaxes(title_text="Precipitação (mm)", secondary_y=False)
            fig.update_yaxes(title_text="Temperatura média (°C)", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

    with secao_protegida("Sazonalidade climática"):
        sazonal = clima_grade.sazonalidade_climatica_grade(df)
        if exigir_dados(not sazonal.empty, "Sem base para a sazonalidade climática."):
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            fig2.add_trace(
                go.Bar(
                    x=sazonal["semana_epidemiologica"], y=sazonal["precipitacao_media_mm"],
                    name="Chuva média (mm)", marker_color=COR_INSTITUCIONAL,
                ),
                secondary_y=False,
            )
            fig2.add_trace(
                go.Scatter(
                    x=sazonal["semana_epidemiologica"], y=sazonal["umidade_relativa_media_pct"],
                    name="Umidade relativa média (%)", line=dict(color=COR_ATENCAO, width=1.8),
                ),
                secondary_y=True,
            )
            fig2.update_layout(
                **LAYOUT_PADRAO,
                title_text="Perfil climático médio por semana epidemiológica (todos os anos do recorte)",
            )
            fig2.update_xaxes(title_text="Semana epidemiológica")
            fig2.update_yaxes(title_text="Chuva média (mm)", secondary_y=False)
            fig2.update_yaxes(title_text="Umidade relativa (%)", secondary_y=True)
            st.plotly_chart(fig2, use_container_width=True)
            st.caption(
                "A umidade relativa vem pronta do produto de reanálise (ERA5-Land) — não é derivada "
                "por este projeto a partir de temperatura e ponto de orvalho."
            )

    st.divider()

# ---------------------------------------------------------------------------
# Estações físicas
# ---------------------------------------------------------------------------
st.markdown("## Estações físicas (CEMADEN)")
if resumo_estacao["linhas_com_clima_real"] == 0:
    st.info(
        "Nenhuma linha do recorte selecionado tem leitura de estação. Isso é esperado para anos "
        "anteriores ao início da série do CEMADEN — não é um erro.",
        icon="ℹ️",
    )
else:
    with secao_protegida("Precipitação medida por estação"):
        serie_estacao = clima.serie_precipitacao(df)
        if exigir_dados(not serie_estacao.empty, "Sem leitura de estação no recorte."):
            st.plotly_chart(grafico_precipitacao(serie_estacao), use_container_width=True)
            st.caption(
                f"Série sobre {numero(int(serie_estacao['bairros_considerados'].sum()))} observações "
                "bairro × semana com leitura real."
            )

    with secao_protegida("Disponibilidade das estações no tempo"):
        grade_cobertura = clima.cobertura_ano_semana(df)
        if not grade_cobertura.empty:
            st.plotly_chart(grafico_heatmap_cobertura(grade_cobertura), use_container_width=True)
            st.caption(
                "A disponibilidade das estações não é homogênea no tempo — este mapa de calor "
                "torna isso explícito antes de qualquer leitura da série acima."
            )

st.divider()

# ---------------------------------------------------------------------------
# Concordância entre as duas fontes
# ---------------------------------------------------------------------------
st.markdown("## As duas fontes concordam?")
comparacao = clima_grade.comparar_estacao_com_grade(df)
if comparacao is None:
    st.info(
        "Não há linhas em que as duas fontes existam simultaneamente no recorte selecionado, "
        "então a comparação não pode ser feita aqui.",
        icon="ℹ️",
    )
else:
    linha_de_cartoes(
        [
            (
                "Observações comparáveis",
                numero(comparacao["n_bairro_semana"]),
                f"Bairro × semana com as duas fontes ({', '.join(str(a) for a in comparacao['anos'])})",
            ),
            ("Correlação (Pearson)", f"{comparacao['pearson']:.2f}", "Entre chuva em grade e chuva medida"),
            (
                "Chuva média",
                f"{comparacao['media_grade_mm']:.1f} × {comparacao['media_estacao_mm']:.1f} mm",
                "Reanálise × estação, na mesma amostra",
            ),
            (
                "Volume captado pela reanálise",
                percentual((comparacao["razao_grade_sobre_estacao"] or 0) * 100),
                "Proporção do total medido pelas estações",
            ),
        ]
    )
    st.markdown(
        "A reanálise **subestima sistematicamente** a chuva medida pelo pluviômetro — comportamento "
        "esperado de modelo de grade numa faixa costeira com convecção local intensa, que suaviza "
        "extremos. Por isso ela é usada para descrever a *variação no tempo*, e não para substituir "
        "a medição onde ela existe."
    )
    st.caption(
        "Metodologia completa da comparação em "
        "`reports/climate_source_analysis/gridded_climate_investigation.md`."
    )
