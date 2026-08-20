"""Renderização de indicadores (KPIs) em linha, com `st.metric`."""
from __future__ import annotations

from typing import Optional, Sequence

import streamlit as st


def renderizar_kpis(itens: Sequence[tuple[str, str, Optional[str]]]) -> None:
    """`itens`: lista de (rótulo, valor formatado, ajuda opcional). Usa
    `st.columns` para distribuir em linha — no máximo 6 por linha, para não
    espremer o texto em telas menores."""
    max_por_linha = 6
    for inicio in range(0, len(itens), max_por_linha):
        bloco = itens[inicio : inicio + max_por_linha]
        colunas = st.columns(len(bloco))
        for coluna, (rotulo, valor, ajuda) in zip(colunas, bloco):
            coluna.metric(rotulo, valor, help=ajuda)


def alerta_qualidade(mensagem: str, tipo: str = "warning") -> None:
    """Alerta discreto de qualidade (`clima indisponível`, `amostra
    pequena` etc.) — nunca deixa o usuário interpretar um gráfico
    incompleto como completo."""
    if tipo == "warning":
        st.warning(mensagem, icon="⚠️")
    elif tipo == "error":
        st.error(mensagem, icon="🚫")
    else:
        st.info(mensagem, icon="ℹ️")
