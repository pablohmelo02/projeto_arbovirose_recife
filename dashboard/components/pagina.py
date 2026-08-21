"""Preâmbulo comum das páginas: tema, cabeçalho, faixa de atualização e
carregamento do dado principal com tratamento de erro amigável.

Existe para que nenhuma página repita esse bloco (e, principalmente, para
que nenhuma página **esqueça** a faixa de atualização — a regra do produto
é que o usuário sempre saiba até quando os dados vão).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st

from dashboard.components.atualizacao import faixa_atualizacao
from dashboard.components.tema import aplicar_tema, cabecalho_pagina
from dashboard.utils.data_loader import (
    DatasetNaoEncontradoError,
    load_freshness,
    load_gold_data,
)


def iniciar_pagina(
    titulo: str,
    subtitulo: str,
    etiqueta: Optional[str] = "observado",
    mostrar_atualizacao: bool = True,
) -> tuple[Optional[pd.DataFrame], Optional[dict[str, Any]]]:
    """Monta o preâmbulo e devolve `(gold, freshness)`.

    Se o dado principal estiver ausente, devolve `(None, freshness)` depois
    de mostrar uma mensagem acionável — a página deve então chamar
    `st.stop()`. Nunca deixa vazar *stack trace* para o público.
    """
    aplicar_tema()
    cabecalho_pagina(titulo, subtitulo, etiqueta)

    freshness = load_freshness()
    if mostrar_atualizacao:
        faixa_atualizacao(freshness)

    try:
        gold = load_gold_data()
    except DatasetNaoEncontradoError as exc:
        st.error(
            "Os dados do painel não estão disponíveis nesta publicação. "
            "Nenhuma análise pode ser exibida até que o pipeline de atualização seja executado.",
            icon="🚫",
        )
        st.caption(f"Detalhe técnico: {exc}")
        return None, freshness

    return gold, freshness


def rodape_fonte(texto: str) -> None:
    """Nota de fonte/limitação ao pé de uma seção. Sempre em texto, nunca
    apenas num tooltip."""
    st.caption(texto)
