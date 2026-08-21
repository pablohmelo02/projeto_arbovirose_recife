"""Validação de entradas da interface.

Todo valor que vem de um widget do Streamlit é tratado como entrada não
confiável, mesmo que os widgets ofereçam apenas opções válidas: um `st.query_params`
manipulado, um estado de sessão corrompido ou uma futura refatoração podem
introduzir um valor inesperado. As funções aqui garantem que:

- somente valores presentes no **domínio real do dado carregado** passam
  (nunca uma lista fixa no código, que poderia divergir do dataset);
- ano e semana epidemiológica são inteiros dentro de faixas válidas;
- vazio e ausência são tratados explicitamente, com mensagem, em vez de
  propagarem `None` para dentro de um filtro pandas;
- nenhum parâmetro do usuário é usado para montar caminho de arquivo.

Nada aqui monta SQL, executa código, importa módulo por nome ou compõe
caminho a partir de texto do usuário — as três fontes de dado do painel são
arquivos fixos declarados em `dashboard/utils/data_loader.py`.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, TypeVar

T = TypeVar("T")

SEMANA_MINIMA = 1
SEMANA_MAXIMA = 53


class EntradaInvalidaError(ValueError):
    """Valor de filtro fora do domínio permitido."""


def validar_escolha(
    valor: Optional[T],
    permitidos: Iterable[T],
    rotulo: str,
    permitir_nulo: bool = True,
) -> Optional[T]:
    """Aceita `valor` somente se estiver em `permitidos` (comparação por
    igualdade, não por conversão implícita)."""
    if valor is None:
        if permitir_nulo:
            return None
        raise EntradaInvalidaError(f"{rotulo} é obrigatório")
    permitidos_lista = list(permitidos)
    if valor not in permitidos_lista:
        raise EntradaInvalidaError(
            f"{rotulo} inválido: {valor!r} não está entre os {len(permitidos_lista)} valores disponíveis"
        )
    return valor


def validar_intervalo_de_anos(
    ano_inicio: int, ano_fim: int, anos_disponiveis: Sequence[int]
) -> tuple[int, int]:
    """Garante inteiros, ordem correta e presença no domínio real."""
    if not anos_disponiveis:
        raise EntradaInvalidaError("nenhum ano disponível no dataset")
    try:
        inicio, fim = int(ano_inicio), int(ano_fim)
    except (TypeError, ValueError) as exc:
        raise EntradaInvalidaError(f"intervalo de anos não numérico: {ano_inicio!r}-{ano_fim!r}") from exc
    minimo, maximo = min(anos_disponiveis), max(anos_disponiveis)
    if inicio > fim:
        inicio, fim = fim, inicio
    if inicio < minimo or fim > maximo:
        raise EntradaInvalidaError(
            f"intervalo {inicio}-{fim} fora do disponível ({minimo}-{maximo})"
        )
    return inicio, fim


def validar_semana_epidemiologica(ano: int, semana: int, pares_disponiveis: Sequence[tuple[int, int]]) -> tuple[int, int]:
    """Valida `(ano, semana)` contra os pares que realmente existem no
    dataset — não basta `1 <= semana <= 53`, porque nem todo ano tem 53
    semanas e nem todo par existe no recorte carregado."""
    try:
        ano_i, semana_i = int(ano), int(semana)
    except (TypeError, ValueError) as exc:
        raise EntradaInvalidaError(f"semana epidemiológica não numérica: {ano!r}-{semana!r}") from exc
    if not (SEMANA_MINIMA <= semana_i <= SEMANA_MAXIMA):
        raise EntradaInvalidaError(
            f"semana epidemiológica fora da faixa {SEMANA_MINIMA}-{SEMANA_MAXIMA}: {semana_i}"
        )
    if (ano_i, semana_i) not in set(pares_disponiveis):
        raise EntradaInvalidaError(
            f"semana {ano_i}-{semana_i:02d} não existe nos dados carregados"
        )
    return ano_i, semana_i


def validar_top_k(valor: int, permitidos: Sequence[int]) -> int:
    """`K` do ranking — sempre um dos valores para os quais existe evidência
    publicada, nunca um número arbitrário digitado."""
    try:
        k = int(valor)
    except (TypeError, ValueError) as exc:
        raise EntradaInvalidaError(f"K não numérico: {valor!r}") from exc
    if k not in set(permitidos):
        raise EntradaInvalidaError(f"K inválido: {k} (permitidos: {sorted(permitidos)})")
    return k
