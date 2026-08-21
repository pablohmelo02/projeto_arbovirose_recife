"""Identidade visual institucional do Recife Alerta.

Objetivo declarado: parecer um painel de gestão pública, não um notebook.
Isso significa poucas cores, hierarquia tipográfica clara, densidade
controlada e nenhuma decoração que não carregue informação.

## Paleta

Uma cor institucional (azul) para estrutura e ênfase neutra; uma cor de
destaque (âmbar) apenas para "atenção"; uma cor de série (vermelho
contido) reservada exclusivamente à dengue, que é o agravo principal.
Cinzas para tudo o mais. Não existe escala verde-amarelo-vermelho de
"risco" em nenhum lugar do produto — a validação estatística não sustenta
categorizar risco, e cor de semáforo comunicaria exatamente essa
categorização proibida.

## Acessibilidade

- Nenhuma informação depende só de cor: tendência, situação e status
  aparecem também como texto.
- Contraste do texto sobre os fundos usados verificado para ficar acima de
  4,5:1 (texto normal) — `#1b2631` sobre `#ffffff` e sobre `#f4f6f7`.
- Tabelas mantêm rótulos completos em vez de siglas sem legenda.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

COR_INSTITUCIONAL = "#1f4e79"
COR_INSTITUCIONAL_CLARA = "#2e6da4"
COR_TEXTO = "#1b2631"
COR_TEXTO_SUAVE = "#5b6b7b"
COR_FUNDO_SUAVE = "#f4f6f7"
COR_BORDA = "#dde3e8"
COR_ATENCAO = "#b9770e"
COR_ATENCAO_FUNDO = "#fdf6e3"
COR_DENGUE = "#a93226"

_CSS = f"""
<style>
  /* ---------- tipografia e espaçamento ---------- */
  .main .block-container {{ padding-top: 1.6rem; max-width: 1400px; }}
  h1, h2, h3, h4 {{ color: {COR_TEXTO}; letter-spacing: -0.01em; }}
  h1 {{ font-size: 1.85rem !important; font-weight: 650 !important; margin-bottom: .15rem !important; }}
  h2 {{ font-size: 1.25rem !important; font-weight: 620 !important; margin-top: 1.6rem !important; }}
  h3 {{ font-size: 1.05rem !important; font-weight: 600 !important; }}

  /* ---------- cabeçalho de página ---------- */
  .ra-subtitulo {{ color: {COR_TEXTO_SUAVE}; font-size: .97rem; line-height: 1.5;
                   margin: .1rem 0 1.1rem 0; max-width: 78ch; }}
  .ra-regua {{ height: 3px; width: 56px; background: {COR_INSTITUCIONAL};
               border-radius: 2px; margin: .45rem 0 .85rem 0; }}

  /* ---------- etiquetas ---------- */
  .ra-tag {{ display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .04em;
             text-transform: uppercase; padding: .18rem .5rem; border-radius: 4px;
             vertical-align: middle; margin-left: .5rem; }}
  .ra-tag-observado {{ background: #e8eef4; color: {COR_INSTITUCIONAL}; border: 1px solid #cfdce8; }}
  .ra-tag-experimental {{ background: {COR_ATENCAO_FUNDO}; color: {COR_ATENCAO}; border: 1px solid #f0d9a8; }}

  /* ---------- cartões ---------- */
  .ra-cartao {{ background: #fff; border: 1px solid {COR_BORDA}; border-radius: 8px;
                padding: .9rem 1.05rem; height: 100%; }}
  .ra-cartao-titulo {{ font-size: .78rem; font-weight: 700; letter-spacing: .05em;
                       text-transform: uppercase; color: {COR_TEXTO_SUAVE}; margin-bottom: .3rem; }}
  .ra-cartao-valor {{ font-size: 1.55rem; font-weight: 660; color: {COR_TEXTO}; line-height: 1.15; }}
  .ra-cartao-nota {{ font-size: .82rem; color: {COR_TEXTO_SUAVE}; margin-top: .25rem; line-height: 1.4; }}

  /* ---------- faixa de atualização ---------- */
  .ra-faixa {{ background: {COR_FUNDO_SUAVE}; border: 1px solid {COR_BORDA};
               border-left: 4px solid {COR_INSTITUCIONAL}; border-radius: 6px;
               padding: .7rem .95rem; margin-bottom: 1rem; }}
  .ra-faixa-titulo {{ font-size: .75rem; font-weight: 700; letter-spacing: .06em;
                      text-transform: uppercase; color: {COR_INSTITUCIONAL}; }}
  .ra-faixa-linha {{ font-size: .9rem; color: {COR_TEXTO}; margin-top: .28rem; }}
  .ra-faixa-nota {{ font-size: .82rem; color: {COR_TEXTO_SUAVE}; margin-top: .28rem; }}
  .ra-faixa-atencao {{ border-left-color: {COR_ATENCAO}; background: {COR_ATENCAO_FUNDO}; }}

  /* ---------- sidebar ---------- */
  section[data-testid="stSidebar"] {{ background: {COR_FUNDO_SUAVE};
                                      border-right: 1px solid {COR_BORDA}; }}
  section[data-testid="stSidebar"] h1 {{ font-size: 1.1rem !important; }}

  /* ---------- responsividade ---------- */
  @media (max-width: 900px) {{
    .main .block-container {{ padding-left: .8rem; padding-right: .8rem; }}
    h1 {{ font-size: 1.5rem !important; }}
    .ra-cartao-valor {{ font-size: 1.3rem; }}
  }}

  /* tabelas largas rolam dentro do próprio contêiner, nunca a página */
  div[data-testid="stDataFrame"] {{ overflow-x: auto; }}
</style>
"""


def aplicar_tema() -> None:
    """Injeta o CSS uma única vez por execução de página."""
    st.markdown(_CSS, unsafe_allow_html=True)


def cabecalho_pagina(titulo: str, subtitulo: str, etiqueta: Optional[str] = None) -> None:
    """Cabeçalho consistente: título, régua, subtítulo explicativo e uma
    etiqueta opcional que diz a natureza do conteúdo.

    `etiqueta="observado"` = o que os dados registram.
    `etiqueta="experimental"` = saída de modelo, não previsão oficial.
    """
    mapa = {
        "observado": ("Dados observados", "ra-tag-observado"),
        "experimental": ("Experimental", "ra-tag-experimental"),
    }
    tag_html = ""
    if etiqueta in mapa:
        texto, classe = mapa[etiqueta]
        tag_html = f'<span class="ra-tag {classe}">{texto}</span>'
    st.markdown(
        f'<h1>{titulo}{tag_html}</h1><div class="ra-regua"></div>'
        f'<div class="ra-subtitulo">{subtitulo}</div>',
        unsafe_allow_html=True,
    )


def cartao(titulo: str, valor: str, nota: str = "") -> str:
    """HTML de um cartão de indicador. Use dentro de `st.columns` com
    `st.markdown(..., unsafe_allow_html=True)`.

    Preferido a `st.metric` quando o indicador precisa de uma nota
    explicativa visível (não escondida num tooltip) — um gestor não deve
    ter de passar o mouse para saber o que o número significa.
    """
    nota_html = f'<div class="ra-cartao-nota">{nota}</div>' if nota else ""
    return (
        f'<div class="ra-cartao"><div class="ra-cartao-titulo">{titulo}</div>'
        f'<div class="ra-cartao-valor">{valor}</div>{nota_html}</div>'
    )


def linha_de_cartoes(itens: list[tuple[str, str, str]]) -> None:
    """Renderiza cartões em colunas iguais. No máximo 4 por linha para não
    espremer texto em tela de tablet."""
    maximo = 4
    for inicio in range(0, len(itens), maximo):
        bloco = itens[inicio : inicio + maximo]
        colunas = st.columns(len(bloco), gap="small")
        for coluna, (titulo, valor, nota) in zip(colunas, bloco):
            coluna.markdown(cartao(titulo, valor, nota), unsafe_allow_html=True)


def numero(valor: float | int, decimais: int = 0) -> str:
    """Formatação numérica pt-BR (ponto de milhar, vírgula decimal)."""
    if valor is None:
        return "—"
    texto = f"{valor:,.{decimais}f}"
    return texto.replace(",", " ").replace(".", ",").replace(" ", ".")


def percentual(valor: Optional[float], decimais: int = 1) -> str:
    if valor is None:
        return "—"
    return f"{numero(valor, decimais)}%"


def variacao_com_sinal(valor: Optional[float], decimais: int = 1) -> str:
    """Variação percentual com sinal explícito — o sinal textual é o que
    carrega a informação, não a cor."""
    if valor is None:
        return "sem base de comparação"
    if valor == float("inf"):
        return "novo (não havia casos no período anterior)"
    sinal = "+" if valor > 0 else ""
    return f"{sinal}{numero(valor, decimais)}%"
