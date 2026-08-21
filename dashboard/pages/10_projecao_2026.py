"""Projeção epidemiológica sazonal 2026 — Recife total × agravo × semana.

Completamente separada da Priorização Experimental (`8_priorizacao_experimental.py`):
aqui não há bairro, não há ranking, não há modelo de risco territorial —
é uma série temporal agregada (baselines + ETS/Holt-Winters), escolhida por
backtest 2023-2025, nunca olhando 2026 (que não tem caso observado em
nenhuma fonte oficial verificada). Ver `src/forecast/` e
`reports/forecast/arbovirus_2026_projection.md`.

Página só lê o artefato já calculado por
`python -m src.generate_forecast_artifacts` — nunca ajusta modelo em tempo
real (mesma convenção da página experimental)."""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.filtros_sidebar import renderizar_filtros, tratar_entrada_invalida
from dashboard.components.graficos_produto import grafico_projecao_com_banda
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero
from dashboard.utils.data_loader import load_forecast_2026, load_forecast_2026_metadata
from dashboard.utils.validacao import EntradaInvalidaError

AVISO_PROJECAO = (
    "**Projeção estatística baseada nos dados históricos disponíveis até 2025.** "
    "Não representa casos observados em 2026 nem previsão oficial da Prefeitura do Recife."
)

gold, freshness = iniciar_pagina(
    "Projeção 2026",
    "Trajetória semanal esperada de casos em 2026, por agravo, a partir de baselines sazonais e "
    "de um modelo de série temporal (ETS/Holt-Winters) — o método vencedor é escolhido por "
    "desempenho em backtest (2023, 2024, 2025), nunca por preferência visual sobre 2026.",
    etiqueta="projecao",
)
if gold is None:
    st.stop()

st.warning(AVISO_PROJECAO, icon="📈")

try:
    filtros = renderizar_filtros(
        gold, key_prefix="projecao2026", permitir_escopo_geografico=False, permitir_todas=False,
    )
except EntradaInvalidaError as exc:
    tratar_entrada_invalida(exc)
    st.stop()

agravo = filtros["agravo"]

forecast = load_forecast_2026()
metadados = load_forecast_2026_metadata()

if forecast is None or metadados is None:
    st.info(
        "A projeção 2026 ainda não foi gerada nesta publicação. Rode "
        "`python -m src.generate_forecast_artifacts` antes de abrir esta página. "
        "As demais páginas do painel continuam disponíveis.",
        icon="ℹ️",
    )
    st.stop()

dados_agravo = metadados.get("por_agravo", {}).get(agravo, {})
if not dados_agravo.get("disponivel"):
    st.info(
        f"Não há histórico suficiente para projetar {agravo.lower()} nesta publicação "
        f"({dados_agravo.get('motivo', 'motivo não informado')}).",
        icon="ℹ️",
    )
    st.stop()

serie_agravo = forecast[forecast["agravo"] == agravo].sort_values("semana_epi_data_inicio")
observado = serie_agravo[serie_agravo["is_observado"]]
projetado = serie_agravo[~serie_agravo["is_observado"]]

st.markdown(f"## {agravo.capitalize()} — histórico observado e projeção 2026")
with secao_protegida("Série observada + projeção"):
    if exigir_dados(not observado.empty and not projetado.empty, "Sem dado suficiente para o gráfico."):
        st.plotly_chart(
            grafico_projecao_com_banda(
                observado, projetado,
                f"Casos de {agravo.lower()} — observado (2013-{dados_agravo['ultimo_ano_historico']}) "
                "e projeção 2026",
            ),
            use_container_width=True,
        )
        st.caption(
            "Linha sólida = observado. Linha tracejada = projeção central. Faixas sombreadas = "
            "intervalos de previsão de 80% e 95% — a projeção nunca é publicada como uma única linha."
        )

st.divider()

pico = dados_agravo["pico_projetado"]
media_historica = dados_agravo["media_semanal_historica_comparavel"]
razao_pico_media = (pico["casos_esperados"] / media_historica) if media_historica else None

linha_de_cartoes(
    [
        (
            "Semana de maior valor esperado",
            f"SE {pico['semana_epidemiologica']} / 2026",
            f"Início em {pd.Timestamp(pico['data_inicio']).date()}",
        ),
        (
            "Casos esperados na semana de pico",
            numero(pico["casos_esperados"]),
            "Valor central da projeção — ver as bandas de 80%/95% no gráfico para a incerteza",
        ),
        (
            "Média sazonal histórica (mesmas semanas)",
            numero(media_historica, decimais=1),
            "Média histórica nas mesmas semanas epidemiológicas — comparação sazonal, não meta",
        ),
    ]
)

if razao_pico_media is not None:
    st.caption(
        f"O pico projetado equivale a {razao_pico_media:.1f}× a média sazonal histórica dessas "
        "mesmas semanas."
    )

st.divider()

st.markdown("## Metodologia")
st.markdown(
    f"""
Modelo escolhido para **{agravo.lower()}**: **{dados_agravo['modelo_escolhido']}**, entre 3
baselines obrigatórios (seasonal naive, média histórica da mesma semana, tendência + sazonalidade)
e 1 método adicional (ETS/Holt-Winters) — nunca deep learning, nunca AutoML.

A escolha usa a **mediana do MASE** (erro relativo ao seasonal naive) nas 3 dobras de backtest
walk-forward (treina até 2022 → prevê 2023; até 2023 → prevê 2024; até 2024 → prevê 2025),
com desempate pelo menor erro de timing do pico — **nunca** o modelo é escolhido olhando 2026,
que não tem caso observado em nenhuma fonte oficial verificada nesta sessão.

Banda de incerteza (80%/95%): {dados_agravo['metodo_banda']}.
"""
)

with secao_protegida("Desempenho histórico do modelo (backtest)"):
    tabela_backtest = pd.DataFrame(dados_agravo["backtest_por_dobra_do_modelo_escolhido"])
    if exigir_dados(not tabela_backtest.empty, "Sem dobra de backtest disponível para este agravo."):
        colunas_exibir = [
            c for c in ["ano_alvo", "mae", "rmse", "mase", "semana_pico_observada",
                        "semana_pico_prevista", "erro_timing_semanas", "erro_magnitude_pico"]
            if c in tabela_backtest.columns
        ]
        st.dataframe(
            tabela_backtest[colunas_exibir].round(2), use_container_width=True, hide_index=True,
        )
        st.caption(
            "Uma linha por ano de teste do backtest. `erro_timing_semanas` positivo = o modelo "
            "previu o pico depois do pico real; negativo = antes."
        )

    cobertura_media = dados_agravo.get("cobertura_intervalo_media", {})
    cobertura_80 = cobertura_media.get("cobertura_80_media")
    cobertura_95 = cobertura_media.get("cobertura_95_media")
    if cobertura_80 is not None or cobertura_95 is not None:
        st.markdown("**Cobertura das bandas de previsão no backtest** (leave-one-fold-out):")
        st.markdown(
            f"- Banda de 80%: {'—' if cobertura_80 is None else f'{cobertura_80:.0%}'} das observações "
            "dentro da faixa.\n"
            f"- Banda de 95%: {'—' if cobertura_95 is None else f'{cobertura_95:.0%}'} das observações "
            "dentro da faixa."
        )
        st.caption(
            "Cada dobra é avaliada com a banda construída a partir dos erros das OUTRAS dobras, "
            "nunca da própria — com só 3 dobras, é uma leitura aproximada, não uma taxa de "
            "cobertura estatisticamente precisa."
        )

st.divider()

st.markdown("## Limitações")
st.markdown(
    f"""
- **Não há caso observado de 2026** em nenhuma fonte oficial verificada nesta sessão — a fonte
  pública de casos (Portal de Dados Abertos do Recife) tem seus recursos mais recentes rotulados
  2025. Esta página nunca mistura dado observado com projeção na mesma cor/estilo de linha.
- **Sem incidência 2026**: não existe estimativa municipal oficial do IBGE para a população de
  2026 (verificado ao vivo nesta sessão) — a projeção é sempre em número de casos, nunca em
  incidência por 100 mil habitantes.
- **Granularidade Recife total apenas** — nenhuma projeção por bairro ou RPA é publicada. A
  instabilidade de uma série semanal por bairro (poucos casos, muito ruído) tornaria uma projeção
  nesse nível não confiável, e a regra deste produto é não publicar o que não é defensável.
- **Instabilidade estrutural**: anos epidêmicos atípicos (ex.: surtos grandes ou anos de baixa
  atividade) podem se desviar bastante do padrão sazonal médio — a banda de 95% existe exatamente
  para comunicar essa incerteza, não para ser ignorada.
- Este número **não é uma meta, não é um alerta de surto e não substitui avaliação
  epidemiológica** — é uma leitura estatística do padrão histórico, para planejamento sazonal.
"""
)
