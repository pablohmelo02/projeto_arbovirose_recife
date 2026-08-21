"""Bairros prioritários — priorização observada, sem modelo.

Responde à pergunta operacional central "onde devemos olhar primeiro?"
usando apenas o que os registros mostram. A priorização preditiva
(experimental) é outra página, com aviso próprio.
"""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import (
    descrever_recorte,
    renderizar_filtros,
    tratar_entrada_invalida,
)
from dashboard.components.graficos_produto import (
    grafico_dispersao_prioridade,
    grafico_prioridade_observada,
)
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero, variacao_com_sinal
from dashboard.utils.validacao import EntradaInvalidaError, validar_escolha, validar_semana_epidemiologica
from src.eda.filtros import aplicar_filtros, total_arboviroses
from src.eda.prioridade_observada import (
    JANELA_RECENTE_SEMANAS,
    ROTULO_RANKING_CRESCIMENTO,
    ROTULO_RANKING_DESVIO,
    ROTULO_RANKING_INCIDENCIA,
    ROTULO_RANKING_VOLUME,
    prioridade_observada,
    resumo_situacao,
    semanas_disponiveis,
)

#: Os 4 rankings distintos do produto (nunca combinados num único ranking
#: misto) -- ver `src/eda/prioridade_observada.py::RANKINGS_OBSERVADOS`.
ORDENACOES = {
    ROTULO_RANKING_VOLUME: "casos_janela_recente",
    ROTULO_RANKING_INCIDENCIA: "incidencia_4s_100k",
    ROTULO_RANKING_CRESCIMENTO: "variacao_pct",
    ROTULO_RANKING_DESVIO: "razao_historico",
}

#: População abaixo da qual uma incidência de 4 semanas é considerada
#: instável demais para leitura isolada (poucos casos alteram muito a taxa).
LIMITE_POPULACAO_INCIDENCIA_INSTAVEL = 5000

TAMANHOS_LISTA = (5, 10, 15, 20, 94)

gold, freshness = iniciar_pagina(
    "Bairros prioritários",
    "Onde devemos olhar primeiro, segundo o que os dados já registram. Quatro critérios "
    "complementares — volume recente, incidência por 100 mil habitantes, aceleração e desvio do "
    "próprio histórico — porque eles respondem a perguntas diferentes e frequentemente apontam "
    "bairros diferentes.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

try:
    filtros = renderizar_filtros(gold, key_prefix="prioritarios", permitir_escopo_geografico=False)
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

df = aplicar_filtros(
    gold, agravo=filtros["agravo"], ano_inicio=filtros["ano_inicio"], ano_fim=filtros["ano_fim"]
)
if not exigir_dados(not df.empty, "Nenhum registro para o recorte selecionado."):
    st.stop()

base = df if filtros["agravo"] else total_arboviroses(df)
if "codigo_rpa" not in base.columns:
    base = base.merge(
        gold[["codigo_bairro", "codigo_rpa"]].drop_duplicates(), on="codigo_bairro", how="left"
    )
if "populacao_bairro_ano" not in base.columns:
    # população/densidade não dependem do agravo -- seguros para repor depois
    # de `total_arboviroses` colapsar as colunas não-chave. Incidência é
    # recalculada dentro de `prioridade_observada`, nunca repassada pronta.
    base = base.merge(
        gold[
            ["codigo_bairro", "ano_epidemiologico", "populacao_bairro_ano",
             "tipo_populacao", "densidade_populacional_hab_km2"]
        ].drop_duplicates(["codigo_bairro", "ano_epidemiologico"]),
        on=["codigo_bairro", "ano_epidemiologico"], how="left",
    )

# ---------------------------------------------------------------------------
# Semana de referência — escolhida a partir do dado real
# ---------------------------------------------------------------------------
pares = semanas_disponiveis(base)
if not exigir_dados(bool(pares), "Sem semanas disponíveis no recorte."):
    st.stop()

col_semana, col_ordem, col_tamanho = st.columns([2, 2, 1], gap="medium")
with col_semana:
    escolha = st.selectbox(
        "Semana de referência",
        options=pares,
        index=0,
        format_func=lambda p: f"SE {p[1]:02d} / {p[0]}",
        key="prioritarios_semana",
        help="A lista vem das semanas que realmente existem nos dados carregados.",
    )
    ano_ref, semana_ref = validar_semana_epidemiologica(escolha[0], escolha[1], pares)
with col_ordem:
    rotulo_ordem = st.selectbox("Ordenar por", options=list(ORDENACOES), key="prioritarios_ordem")
    rotulo_ordem = validar_escolha(rotulo_ordem, list(ORDENACOES), "Ordenação", permitir_nulo=False)
with col_tamanho:
    tamanho = st.selectbox(
        "Mostrar", options=TAMANHOS_LISTA, index=1, key="prioritarios_tamanho",
        format_func=lambda n: "Todos" if n >= 94 else f"Top {n}",
    )

st.caption(
    f"Recorte ativo: **{descrever_recorte(filtros, gold)}** · semana de referência "
    f"**SE {semana_ref:02d} / {ano_ref}**"
)

tabela = prioridade_observada(base, ano_referencia=ano_ref, semana_referencia=semana_ref)
if not exigir_dados(not tabela.empty, "Sem dados na semana de referência escolhida."):
    st.stop()

coluna_ordem = ORDENACOES[rotulo_ordem]
tabela_ordenada = tabela.sort_values(coluna_ordem, ascending=False, na_position="last").reset_index(drop=True)

situacao = resumo_situacao(base, tabela)
linha_de_cartoes(
    [
        (
            f"Casos na cidade ({JANELA_RECENTE_SEMANAS} sem.)",
            numero(situacao["casos_janela_recente_cidade"]),
            f"Até SE {semana_ref:02d} / {ano_ref}",
        ),
        (
            "Variação sobre o período anterior",
            variacao_com_sinal(situacao["variacao_pct_cidade"]),
            f"Tendência: {situacao['tendencia_cidade']}",
        ),
        (
            "Bairros em alta",
            f"{situacao['bairros_em_alta']} de {situacao['total_bairros']}",
            "Crescimento de 20% ou mais",
        ),
        (
            "Acima do próprio histórico",
            f"{situacao['bairros_acima_do_historico']} de {situacao['total_bairros']}",
            "Razão maior que 1,00×",
        ),
    ]
)

st.divider()

# ---------------------------------------------------------------------------
# Tabela operacional
# ---------------------------------------------------------------------------
st.markdown("## Lista de priorização")
exibicao = tabela_ordenada.head(94 if tamanho >= 94 else tamanho).copy()
exibicao_formatada = pd.DataFrame(
    {
        "Prioridade": range(1, len(exibicao) + 1),
        "Bairro": exibicao["nome_bairro"].str.title(),
        "RPA": exibicao["codigo_rpa"],
        "Casos na semana": exibicao["casos_semana"].astype("Int64"),
        f"Casos ({JANELA_RECENTE_SEMANAS} sem.)": exibicao["casos_janela_recente"].astype("Int64"),
        f"Incidência ({JANELA_RECENTE_SEMANAS} sem.)/100k": exibicao["incidencia_4s_100k"].map(
            lambda v: "—" if pd.isna(v) else f"{v:.1f}"
        ),
        "População usada": exibicao["populacao_bairro_ano"].map(
            lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", ".")
        ),
        "Tipo pop.": exibicao["tipo_populacao"].fillna("—"),
        "Variação": exibicao["variacao_pct"].map(variacao_com_sinal),
        "Tendência": exibicao["tendencia"],
        "Razão vs. histórico": exibicao["razao_historico"].map(
            lambda v: "—" if pd.isna(v) else f"{v:.2f}×"
        ),
        "Base histórica (n)": exibicao["n_observacoes_historicas"].astype("Int64"),
    }
)
st.dataframe(exibicao_formatada, use_container_width=True, hide_index=True, height=min(620, 42 + 36 * len(exibicao)))
st.caption(
    "**Prioridade** é apenas a posição segundo o critério escolhido acima — não é uma classificação "
    "de risco validada. **Base histórica (n)** é o número de observações de anos anteriores usadas na "
    "comparação sazonal: um `n` pequeno torna a razão instável, e por isso é exibido. **Tipo pop.** "
    "indica se a população usada naquele ano é Censo observado, estimativa intercensitária ou projeção "
    "pós-Censo — ver a página de Qualidade e limitações."
)
if rotulo_ordem == ROTULO_RANKING_INCIDENCIA:
    st.warning(
        "Taxas de curto prazo (incidência de 4 semanas) podem variar fortemente em bairros de menor "
        "população: um único caso a mais ou a menos muda a taxa de forma desproporcional. Os valores "
        "não são ocultados, mas devem ser lidos com essa ressalva — compare também com a incidência "
        "anual (janela mais longa) na página de Evolução histórica.",
        icon="⚠️",
    )

st.divider()

col_a, col_b = st.columns(2, gap="large")
with col_a:
    with secao_protegida("Ranking por volume recente"):
        st.plotly_chart(
            grafico_prioridade_observada(
                tabela.sort_values("casos_janela_recente", ascending=False),
                top_n=min(15, len(tabela)),
                titulo=f"Bairros com mais casos até SE {semana_ref:02d} / {ano_ref}",
            ),
            use_container_width=True,
        )
with col_b:
    with secao_protegida("Volume × desvio do histórico"):
        st.plotly_chart(
            grafico_dispersao_prioridade(
                tabela, "Volume recente × razão contra o histórico do bairro"
            ),
            use_container_width=True,
        )
        st.caption(
            "Bairros no alto à direita têm muitos casos **e** estão acima do próprio padrão. "
            "Bairros no alto à esquerda têm poucos casos em termos absolutos, mas muito acima do "
            "que é normal para eles nesta época — situação que a contagem absoluta esconde."
        )

st.caption(
    "Esta página é inteiramente descritiva. Ela não usa modelo, não prevê e não afirma "
    "antecipação. A antecipação é avaliada — de forma experimental e retrospectiva — na página "
    "**Priorização experimental**."
)
