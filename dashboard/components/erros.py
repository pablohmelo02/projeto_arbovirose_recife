"""Tratamento de erro na interface: nunca um *stack trace* para o público.

Regra: uma seção que falha degrada sozinha. O restante da página continua
utilizável, o usuário recebe uma frase compreensível, e o detalhe técnico
vai para o log do servidor (onde a equipe consegue ver), não para a tela.

Uso:

    with secao_protegida("Mapa territorial"):
        st.plotly_chart(...)

Se o bloco levantar exceção, a seção mostra a mensagem amigável e a
execução da página continua na linha seguinte ao `with`.
"""
from __future__ import annotations

import logging
import traceback
from contextlib import contextmanager
from typing import Iterator, Optional

import streamlit as st

logger = logging.getLogger("recife_alerta.ui")

MENSAGEM_PADRAO = (
    "Não foi possível carregar esta análise. Os demais módulos do painel continuam disponíveis."
)


@contextmanager
def secao_protegida(nome: str, mensagem: Optional[str] = None) -> Iterator[None]:
    """Isola uma seção da página. `nome` só aparece no log e numa linha
    discreta na tela — nunca a exceção crua."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - fronteira de UI: qualquer falha degrada
        logger.error("Falha ao renderizar a seção %r: %s\n%s", nome, exc, traceback.format_exc())
        st.error(f"{mensagem or MENSAGEM_PADRAO}", icon="⚠️")
        st.caption(
            f"Seção afetada: {nome}. O detalhe técnico foi registrado no log da aplicação."
        )


def exigir_dados(condicao: bool, mensagem: str) -> bool:
    """Guarda declarativa para estado vazio. Devolve `False` (e mostra a
    mensagem) quando não há dado suficiente — a página decide se para ali ou
    segue sem aquela seção. Estado vazio **não** é erro e não usa cor de
    erro."""
    if condicao:
        return True
    st.info(mensagem, icon="ℹ️")
    return False
