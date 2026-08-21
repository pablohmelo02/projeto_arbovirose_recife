"""Bloco "Atualização dos dados" — visível e derivado, nunca escrito à mão.

Toda data exibida no produto vem de `dashboard/data/_freshness.json`
(gerado por `python -m src.generate_freshness`). Nenhuma data é literal no
código ou no texto: se a fonte publicar um novo período, o painel passa a
dizer o novo período sozinho.

Regra de linguagem: quando o dado está atrasado, o painel diz isso
explicitamente e explica por quê (periodicidade declarada pela própria
fonte). Em nenhuma hipótese um dado antigo é apresentado como "tempo real".
"""
from __future__ import annotations

from typing import Any, Optional

import streamlit as st

ROTULOS_DATASET = {
    "epidemiologia": "Casos notificados",
    "territorio": "Limites territoriais",
    "clima_estacao": "Clima — estações",
    "clima_grade": "Clima — reanálise em grade",
    "modelo": "Modelo experimental",
}

TEXTO_SEM_FRESHNESS = (
    "Não foi possível determinar a atualidade dos dados: o arquivo de metadados "
    "de atualização não está disponível nesta publicação."
)


def _semana_legivel(valor: Optional[str]) -> str:
    """`2025-53` → `SE 53 / 2025`."""
    if not valor or "-" not in str(valor):
        return "—"
    ano, semana = str(valor).split("-", 1)
    return f"SE {int(semana)} / {ano}"


def _data_legivel(valor: Optional[str]) -> str:
    if not valor:
        return "—"
    texto = str(valor)[:10]
    partes = texto.split("-")
    return f"{partes[2]}/{partes[1]}/{partes[0]}" if len(partes) == 3 else texto


def faixa_atualizacao(freshness: Optional[dict[str, Any]]) -> None:
    """Faixa compacta, para o topo de qualquer página."""
    if not freshness:
        st.markdown(
            f'<div class="ra-faixa ra-faixa-atencao"><div class="ra-faixa-titulo">Atualização dos dados</div>'
            f'<div class="ra-faixa-linha">{TEXTO_SEM_FRESHNESS}</div></div>',
            unsafe_allow_html=True,
        )
        return

    epi = (freshness.get("datasets") or {}).get("epidemiologia") or {}
    atrasado = epi.get("status") == "ATRASADO"
    periodicidade = (epi.get("detalhe") or {}).get("periodicidade_declarada_pela_fonte")

    linhas = [
        f"<b>Dados epidemiológicos disponíveis até:</b> {_semana_legivel(epi.get('semana_epi_maxima'))} "
        f"(fim da semana em {_data_legivel(epi.get('data_maxima_evento'))})",
        f"<b>Última atualização da fonte:</b> {_data_legivel(epi.get('ultima_atualizacao_fonte'))}",
    ]
    nota = (
        "A disponibilidade do painel reflete o último período publicado pela fonte oficial"
        + (f" (periodicidade declarada: {periodicidade})." if periodicidade else ".")
    )
    if atrasado and epi.get("atraso_dias") is not None:
        nota += f" Atraso atual em relação a hoje: {epi['atraso_dias']} dias."

    classe = "ra-faixa ra-faixa-atencao" if atrasado else "ra-faixa"
    corpo = "".join(f'<div class="ra-faixa-linha">{linha}</div>' for linha in linhas)
    st.markdown(
        f'<div class="{classe}"><div class="ra-faixa-titulo">Atualização dos dados</div>'
        f'{corpo}<div class="ra-faixa-nota">{nota}</div></div>',
        unsafe_allow_html=True,
    )


def tabela_atualizacao(freshness: Optional[dict[str, Any]]) -> None:
    """Detalhe por conjunto de dados — para a página de qualidade."""
    if not freshness:
        st.info(TEXTO_SEM_FRESHNESS)
        return

    import pandas as pd

    linhas = []
    for nome, bloco in (freshness.get("datasets") or {}).items():
        linhas.append(
            {
                "Conjunto de dados": ROTULOS_DATASET.get(nome, nome),
                "Fonte": bloco.get("fonte"),
                "Atualizado até": _semana_legivel(bloco.get("semana_epi_maxima"))
                if bloco.get("semana_epi_maxima")
                else _data_legivel(bloco.get("data_maxima_evento")),
                "Última publicação da fonte": _data_legivel(bloco.get("ultima_atualizacao_fonte")),
                "Atraso (dias)": bloco.get("atraso_dias"),
                "Limiar (dias)": bloco.get("limiar_atraso_dias"),
                "Situação": bloco.get("status"),
            }
        )
    st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)
    st.caption(
        "**Situação** é uma regra objetiva: `ATUAL` = atraso dentro do limiar do conjunto; "
        "`ATRASADO` = acima do limiar (não é erro do sistema — é o estado real da publicação "
        "oficial); `DESCONHECIDO` = não foi possível determinar. Nada é considerado atual por omissão."
    )
    gerado = freshness.get("gerado_em")
    if gerado:
        st.caption(f"Metadados gerados em {_data_legivel(gerado)} pelo pipeline de atualização.")


def aviso_projecao_indisponivel(status: dict[str, Any]) -> None:
    """Mensagem única e honesta para o bloqueio da priorização do período
    atual (§13/§60 do produto): explica o motivo e oferece a alternativa
    legítima (backtest histórico)."""
    detalhe = status.get("detalhe") or "os dados disponíveis não cobrem um período recente o suficiente"
    st.warning(
        "**Priorização do período atual indisponível.** "
        f"{detalhe.capitalize()}.\n\n"
        "Para não apresentar um resultado sem base, o módulo experimental oferece apenas a "
        "**simulação histórica (backtest)**: escolha uma semana passada e veja o que o sistema "
        "teria priorizado naquele momento e o que aconteceu depois.",
        icon="⚠️",
    )
