"""Filtros da barra lateral — combináveis, reutilizados pelas páginas.

Este módulo decide *o que* filtrar; a filtragem em si é sempre
`src/eda/filtros.py` (nunca reimplementada aqui). Toda seleção passa por
`dashboard/utils/validacao.py` antes de virar filtro: os widgets só
oferecem opções válidas, mas o valor é validado de novo contra o domínio
real do dataset carregado — defesa contra estado de sessão corrompido ou
divergência entre código e dado.
"""
from __future__ import annotations

from typing import Optional, TypedDict

import pandas as pd
import streamlit as st

from dashboard.utils.validacao import (
    EntradaInvalidaError,
    validar_escolha,
    validar_intervalo_de_anos,
)
from src.eda.schema_eda import AGRAVOS

OPCAO_TODOS_AGRAVOS = "Todas as arboviroses (soma dos 3 agravos)"

ROTULOS_ESCOPO = {
    "recife": "Recife inteiro",
    "rpa": "Uma RPA",
    "bairro": "Um bairro",
}


class Filtros(TypedDict):
    agravo: Optional[str]
    ano_inicio: int
    ano_fim: int
    escopo: str
    codigo_rpa: Optional[str]
    codigo_bairro: Optional[str]


def opcoes_agravo(permitir_todas: bool = True) -> list[str]:
    """Lista de opções do seletor de agravo, extraída para ser testável sem
    depender do Streamlit."""
    return [*AGRAVOS] if not permitir_todas else [OPCAO_TODOS_AGRAVOS, *AGRAVOS]


def renderizar_filtros(
    df_gold: pd.DataFrame,
    key_prefix: str,
    permitir_escopo_geografico: bool = True,
    agravo_padrao: Optional[str] = "DENGUE",
    permitir_todas: bool = True,
) -> Filtros:
    """`key_prefix` evita colisão de estado entre páginas.

    `agravo_padrao="DENGUE"` reflete a decisão de produto: dengue é o agravo
    principal; Zika e Chikungunya permanecem disponíveis como comparação.

    `permitir_todas=False` remove a opção "Todas as arboviroses" do seletor
    — usado por páginas onde a soma dos 3 agravos não tem interpretação
    válida (ex.: associação climática por defasagem, projeção 2026: cada
    agravo tem sazonalidade/processo próprio, somar os três não é uma série
    válida para essas análises). Quando `False`, `agravo_padrao` não pode
    ser `None` e o usuário sempre escolhe uma das três doenças.
    """
    st.sidebar.markdown("### Filtros")

    opcoes = opcoes_agravo(permitir_todas)
    padrao_efetivo = agravo_padrao if agravo_padrao in opcoes else opcoes[0]
    indice_padrao = opcoes.index(padrao_efetivo)
    agravo_escolhido = st.sidebar.selectbox(
        "Agravo",
        options=opcoes,
        index=indice_padrao,
        key=f"{key_prefix}_agravo",
        help=(
            "Dengue é o agravo principal do painel. 'Todas as arboviroses' soma os três "
            "agravos e nunca é tratada como uma quarta doença."
            if permitir_todas
            else "Esta análise depende do processo de cada agravo — não é possível somar os três."
        ),
    )
    agravo = None if agravo_escolhido == OPCAO_TODOS_AGRAVOS else agravo_escolhido
    agravo = validar_escolha(agravo, AGRAVOS, "Agravo")

    anos_disponiveis = sorted(int(a) for a in df_gold["ano_epidemiologico"].dropna().unique())
    ano_min, ano_max = min(anos_disponiveis), max(anos_disponiveis)
    if ano_min == ano_max:
        ano_inicio, ano_fim = ano_min, ano_max
        st.sidebar.caption(f"Ano epidemiológico: {ano_min} (único disponível)")
    else:
        ano_inicio, ano_fim = st.sidebar.slider(
            "Ano epidemiológico",
            min_value=ano_min,
            max_value=ano_max,
            value=(ano_min, ano_max),
            key=f"{key_prefix}_anos",
        )
    ano_inicio, ano_fim = validar_intervalo_de_anos(ano_inicio, ano_fim, anos_disponiveis)

    codigo_rpa: Optional[str] = None
    codigo_bairro: Optional[str] = None
    escopo = "recife"

    if permitir_escopo_geografico:
        rotulo = st.sidebar.radio(
            "Recorte territorial",
            options=list(ROTULOS_ESCOPO.values()),
            key=f"{key_prefix}_escopo",
            help="RPA = Região Político-Administrativa (as 6 macrorregiões do Recife).",
        )
        escopo = next(chave for chave, valor in ROTULOS_ESCOPO.items() if valor == rotulo)

        if escopo == "rpa":
            rpas = sorted(str(r) for r in df_gold["codigo_rpa"].dropna().unique())
            escolhida = st.sidebar.selectbox(
                "RPA", options=rpas, key=f"{key_prefix}_rpa", format_func=lambda r: f"RPA {r}"
            )
            codigo_rpa = validar_escolha(escolhida, rpas, "RPA", permitir_nulo=False)
        elif escopo == "bairro":
            bairros = (
                df_gold[["codigo_bairro", "nome_bairro"]].drop_duplicates().sort_values("nome_bairro")
            )
            nome = st.sidebar.selectbox(
                "Bairro", options=bairros["nome_bairro"].tolist(), key=f"{key_prefix}_bairro"
            )
            nome = validar_escolha(nome, bairros["nome_bairro"].tolist(), "Bairro", permitir_nulo=False)
            codigo_bairro = str(bairros.loc[bairros["nome_bairro"] == nome, "codigo_bairro"].iloc[0])

    return Filtros(
        agravo=agravo,
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
        escopo=escopo,
        codigo_rpa=codigo_rpa,
        codigo_bairro=codigo_bairro,
    )


def descrever_recorte(filtros: Filtros, df_gold: pd.DataFrame) -> str:
    """Frase legível do recorte ativo — para o usuário nunca ler um gráfico
    sem saber a que ele se refere."""
    agravo = filtros["agravo"] or "todas as arboviroses"
    periodo = (
        f"{filtros['ano_inicio']}"
        if filtros["ano_inicio"] == filtros["ano_fim"]
        else f"{filtros['ano_inicio']}–{filtros['ano_fim']}"
    )
    if filtros["escopo"] == "rpa":
        local = f"RPA {filtros['codigo_rpa']}"
    elif filtros["escopo"] == "bairro" and filtros["codigo_bairro"]:
        nomes = df_gold.loc[df_gold["codigo_bairro"] == filtros["codigo_bairro"], "nome_bairro"]
        local = nomes.iloc[0].title() if len(nomes) else "bairro selecionado"
    else:
        local = "Recife (94 bairros)"
    return f"{agravo.capitalize()} · {periodo} · {local}"


def tratar_entrada_invalida(erro: EntradaInvalidaError) -> None:
    """Mensagem amigável para filtro inválido (não deve acontecer pela UI,
    mas acontece se o estado de sessão for corrompido)."""
    st.error(
        "A combinação de filtros selecionada não é válida para os dados carregados. "
        "Reverta a seleção na barra lateral para continuar.",
        icon="⚠️",
    )
    st.caption(f"Detalhe: {erro}")
