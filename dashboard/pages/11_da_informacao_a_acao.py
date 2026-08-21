"""Da informação à ação — como a Prefeitura usa o sistema.

Página de apoio à decisão em si: não mostra dado novo, organiza o que as
outras páginas já mostram como pergunta → indicador → decisão apoiada
(item 21 do pedido de produto). Reaproveita a matriz de
`reports/product/product_overview.md` §3 e a expande com as 9 perguntas
operacionais explicitamente pedidas.

A plataforma **apoia, prioriza, informa e contextualiza** — ela não ordena
equipes, não substitui epidemiologista, não garante redução de casos e não
diagnostica surto (item 22)."""
import _bootstrap  # noqa: F401

import streamlit as st

from dashboard.components.pagina import iniciar_pagina

gold, freshness = iniciar_pagina(
    "Da informação à ação",
    "Como cada pergunta operacional da Prefeitura se conecta a um indicador do painel e à decisão "
    "que ele apoia — nunca executa.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

st.error(
    "**Esta plataforma apoia, prioriza, informa e contextualiza. Ela NÃO ordena equipes "
    "automaticamente, NÃO substitui avaliação epidemiológica, NÃO garante redução de casos/"
    "internações e NÃO diagnostica surto.** Toda decisão final é humana.",
    icon="🛑",
)

st.markdown("## Pergunta → indicador → decisão apoiada")

LINHAS = [
    (
        "Onde há mais volume de casos?",
        "Casos acumulados/recentes",
        "Dimensionamento operacional (onde alocar mais equipe/insumo por quantidade absoluta)",
        "Mapa territorial · Bairros prioritários (ranking de volume)",
    ),
    (
        "Onde há maior intensidade relativa?",
        "Incidência por 100 mil habitantes",
        "Priorização proporcional ao tamanho da população, não só ao volume bruto",
        "Mapa territorial · Situação epidemiológica · Bairros prioritários (ranking de incidência)",
    ),
    (
        "Onde está crescendo agora?",
        "Tendência / variação % recente",
        "Atenção precoce a um movimento que ainda não virou volume grande",
        "Bairros prioritários (ranking de crescimento)",
    ),
    (
        "Está fora do padrão daquele lugar?",
        "Razão contra o próprio histórico sazonal",
        "Investigação local — o bairro está acima do que a própria história dele sugere",
        "Bairros prioritários (ranking de desvio histórico)",
    ),
    (
        "Onde olhar primeiro, com recursos restritos?",
        "Top-5 experimental (único K com ganho estatístico validado)",
        "Uso de capacidade operacional restrita — nunca Top-15/20, onde o modelo não supera regras simples",
        "Priorização experimental",
    ),
    (
        "Quando, historicamente, os casos aumentam?",
        "Sazonalidade (semana epidemiológica de pico histórico)",
        "Planejamento de campanha antes da época de maior risco histórico",
        "Evolução histórica · Projeção 2026 (comparação sazonal)",
    ),
    (
        "O clima antecede os casos?",
        "Associação por defasagem (lag), bruta e ajustada por sazonalidade",
        "Insumo para planejamento sazonal — nunca causalidade, nunca gatilho automático",
        "Clima × Arboviroses",
    ),
    (
        "O que esperar de 2026?",
        "Projeção estatística sazonal (casos, intervalo de 80%/95%, pico esperado)",
        "Planejamento — nunca meta, nunca previsão oficial, nunca substitui dado observado",
        "Projeção 2026",
    ),
    (
        "Os dados estão atuais?",
        "Freshness (atraso da fonte em dias/semanas)",
        "Confiabilidade da decisão — uma leitura desatualizada não deve orientar ação imediata",
        "Faixa \"Atualização dos dados\", no topo de toda página",
    ),
]

st.dataframe(
    {
        "Pergunta": [l[0] for l in LINHAS],
        "Indicador": [l[1] for l in LINHAS],
        "Decisão apoiada": [l[2] for l in LINHAS],
        "Onde ver": [l[3] for l in LINHAS],
    },
    use_container_width=True,
    hide_index=True,
    height=38 * (len(LINHAS) + 1),
)

st.divider()

st.markdown("## Os dois modos observado × os dois modos projetivo")
st.markdown(
    """
- **Observado** (Situação epidemiológica, Mapa territorial, Bairros prioritários, Evolução
  histórica, Clima × Arboviroses): descreve o que os registros já mostram. Nunca prevê o futuro.
- **Priorização experimental**: modelo de ranking territorial para dengue, validado só em Top-5,
  fora do escopo de qualquer promessa de redução de casos.
- **Projeção 2026**: série temporal agregada (Recife total, por agravo), separada da priorização
  territorial — nenhuma das duas usa a outra como insumo.

Nenhum dos três modos ordena ação automaticamente. Todos existem para que uma pessoa com
conhecimento epidemiológico decida com mais informação — não para decidir por ela.
"""
)
