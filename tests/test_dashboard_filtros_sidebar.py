"""`opcoes_agravo` é a parte pura (sem Streamlit) do seletor de agravo da
barra lateral -- garante que `permitir_todas=False` de fato remove a opção
"Todas as arboviroses" das páginas onde a soma dos 3 agravos não tem
interpretação válida (clima x arboviroses, projeção 2026)."""
from __future__ import annotations

from dashboard.components.filtros_sidebar import OPCAO_TODOS_AGRAVOS, opcoes_agravo
from src.eda.schema_eda import AGRAVOS


def test_opcoes_agravo_padrao_inclui_todas():
    opcoes = opcoes_agravo()
    assert OPCAO_TODOS_AGRAVOS in opcoes
    for agravo in AGRAVOS:
        assert agravo in opcoes


def test_opcoes_agravo_permitir_todas_false_nao_inclui_opcao_todas():
    opcoes = opcoes_agravo(permitir_todas=False)
    assert OPCAO_TODOS_AGRAVOS not in opcoes
    assert list(opcoes) == list(AGRAVOS)
