"""Qualidade e limitações — a página que impede qualquer outra de ser lida
fora de contexto.

Semáforos aqui existem **somente** para qualidade de dado, com regra
objetiva declarada (limiar de atraso por conjunto). Não há, em nenhum lugar
do produto, cor de "risco" epidemiológico.
"""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.atualizacao import tabela_atualizacao
from dashboard.components.erros import secao_protegida
from dashboard.components.graficos import grafico_matriz_correlacao
from dashboard.components.graficos_produto import grafico_cobertura_dupla
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero, percentual
from dashboard.utils.data_loader import (
    inventario_artefatos,
    load_export_profiling,
    load_manifest_clima_grade,
    load_priority_status,
    load_ultima_atualizacao,
)
from src.eda import clima, clima_grade, correlacao, epidemiologia

gold, freshness = iniciar_pagina(
    "Qualidade e limitações",
    "O que os dados cobrem, o que não cobrem, de onde vêm e o que pode ser afirmado a partir "
    "deles. Esta página existe para que nenhum gráfico do painel seja interpretado além do que "
    "os dados sustentam.",
    etiqueta="observado",
)
if gold is None:
    st.stop()

# ---------------------------------------------------------------------------
# 1. Atualidade
# ---------------------------------------------------------------------------
st.markdown("## Atualidade de cada conjunto de dados")
tabela_atualizacao(freshness)

st.divider()

# ---------------------------------------------------------------------------
# 2. Cobertura epidemiológica
# ---------------------------------------------------------------------------
st.markdown("## Cobertura epidemiológica")
resumo = epidemiologia.resumo_epidemiologico(gold)
linha_de_cartoes(
    [
        ("Linhas na tabela analítica", numero(len(gold)), "Bairro × semana × agravo"),
        (
            "Período",
            f"{resumo['ano_epidemiologico_min']}–{resumo['ano_epidemiologico_max']}",
            f"{resumo['total_semanas_distintas']} semanas epidemiológicas",
        ),
        ("Bairros", f"{resumo['total_bairros']} de 94", "Território oficial completo"),
        ("Casos notificados", numero(resumo["total_casos"]), "Soma dos três agravos"),
    ]
)
st.markdown(
    """
- **Grão:** bairro × semana epidemiológica × agravo. A semana vem do próprio SINAN
  (`semana_notificacao`), não é recalculada por este projeto.
- **`casos = 0` é dado real**, não ausência: a notificação de arboviroses é compulsória, então
  uma semana sem notificação significa nenhum caso notificado.
- **Ausência climática é diferente**: onde não houve leitura, o valor fica vazio, nunca `0 mm`.
  Confundir as duas coisas produziria séries de chuva artificialmente secas.
- **Nenhum dado individual** existe na tabela publicada: não há identificador de notificação,
  nome, documento, endereço, data de nascimento nem coordenada de paciente. A menor unidade é
  o bairro.
- **Incidência por 100 mil habitantes é calculada** a partir da Gold 1.2 (população por bairro/ano
  reconstruída 2010-2025: Censos 2010/2022 observados, estimativa institucional 2011-2017,
  reconstrução própria 2018-2021 e projeção pós-Censo 2023-2025 — ver
  `reports/population/population_incidence_integration.md` para o método e a margem de erro,
  MAPE ≈ 10,8% nos anos reconstruídos). Cada página que mostra incidência também mostra
  `tipo_populacao`, para nunca confundir ano observado com ano reconstruído/projetado.
"""
)

st.divider()

# ---------------------------------------------------------------------------
# 3. Cobertura climática
# ---------------------------------------------------------------------------
st.markdown("## Cobertura climática")
resumo_estacao = clima.resumo_cobertura_climatica(gold)
resumo_grade = clima_grade.resumo_cobertura_grade(gold)

linha_de_cartoes(
    [
        (
            "Reanálise em grade",
            percentual(resumo_grade.get("percentual_linhas")) if resumo_grade.get("disponivel") else "—",
            "Das linhas da tabela analítica",
        ),
        (
            "Estações físicas",
            percentual(resumo_estacao["percentual_linhas_com_clima_real"]),
            "Das linhas da tabela analítica",
        ),
        (
            "Células de grade para 94 bairros",
            str(resumo_grade.get("celulas_precipitacao") or "—"),
            "Precipitação — mede *quando* chove, não *onde* dentro do Recife",
        ),
        (
            "Estações distintas",
            str(resumo_estacao["estacoes_distintas"]),
            "Associadas por proximidade ao bairro",
        ),
    ]
)

with secao_protegida("Cobertura climática por ano"):
    tabela_dupla = clima_grade.cobertura_dupla_por_ano(gold)
    if not tabela_dupla.empty:
        st.plotly_chart(
            grafico_cobertura_dupla(tabela_dupla, "Cobertura por ano: reanálise × estações físicas"),
            use_container_width=True,
        )

manifest_grade = load_manifest_clima_grade()
if manifest_grade:
    resolucao = manifest_grade.get("resolucao_graus") or {}
    st.markdown(
        f"**Resolução declarada da reanálise:** precipitação em células de "
        f"{resolucao.get('ERA5', '—')}° (≈ 28 km) e temperatura/umidade em células de "
        f"{resolucao.get('ERA5-LAND', '—')}° (≈ 11 km). Os 94 bairros do Recife ocupam menos de "
        "0,2° de extensão, então essas células cobrem a cidade quase inteira de uma vez. "
        "É por isso que a reanálise **não** é descrita como 'a estação meteorológica do bairro'."
    )

comparacao = clima_grade.comparar_estacao_com_grade(gold)
if comparacao:
    st.markdown(
        f"**Concordância entre as duas fontes** (nas {numero(comparacao['n_bairro_semana'])} "
        f"observações em que ambas existem): correlação de {comparacao['pearson']:.2f}; a reanálise "
        f"capta {percentual((comparacao['razao_grade_sobre_estacao'] or 0) * 100)} do volume de chuva "
        "medido pelos pluviômetros — ou seja, **subestima extremos**."
    )

st.divider()

# ---------------------------------------------------------------------------
# 4. Correlação exploratória
# ---------------------------------------------------------------------------
st.markdown("## Correlação exploratória (clima × casos)")
st.caption(
    "Calculada apenas sobre observações com valor climático real; identificadores (códigos de "
    "bairro, RPA, estação) nunca entram como variável numérica. **Correlação não implica causalidade.**"
)
with secao_protegida("Matriz de correlação"):
    matriz, n_obs = correlacao.matriz_correlacao(gold)
    if n_obs == 0:
        st.info("Sem observações com clima de estação para calcular a matriz.", icon="ℹ️")
    else:
        st.plotly_chart(grafico_matriz_correlacao(matriz, n_obs), use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# 5. Módulo experimental — cobertura e elegibilidade
# ---------------------------------------------------------------------------
st.markdown("## Módulo experimental: cobertura e elegibilidade")
status = load_priority_status()
if status is None:
    st.info("Módulo experimental indisponível nesta publicação.", icon="ℹ️")
else:
    periodo = status.get("backtest_periodo") or {}
    linha_de_cartoes(
        [
            (
                "Período avaliado",
                f"{periodo.get('ano_inicio')}–{periodo.get('ano_fim')}",
                f"{periodo.get('semanas')} semanas de backtest",
            ),
            (
                "Priorização do período atual",
                "disponível" if status.get("current_projection_available") else "bloqueada",
                status.get("reason") or "dados recentes o suficiente",
            ),
            (
                "Modelo treinado até",
                str(status.get("trained_until")),
                "Avaliação sempre em período posterior ao treino",
            ),
            (
                "Bairros elegíveis por semana",
                "varia",
                "Um bairro sem histórico suficiente não recebe alvo definido e fica fora do ranking",
            ),
        ]
    )
    st.markdown(
        "- O modelo **não** cobre todos os bairros em todas as semanas: bairros sem histórico "
        "suficiente para definir o estado de risco ficam com alvo indefinido e são excluídos, "
        "nunca forçados a zero.\n"
        "- O desempenho **não** é uniforme entre territórios (ver a página **Priorização "
        "experimental**, seção de desempenho territorial).\n"
        "- Nenhuma probabilidade é publicada; apenas posição e score relativo dentro da semana."
    )

st.divider()

# ---------------------------------------------------------------------------
# 6. Proveniência e integridade
# ---------------------------------------------------------------------------
st.markdown("## Proveniência dos artefatos publicados")
st.markdown(
    "O painel consome apenas arquivos pré-gerados. Ele não acessa banco de dados, não chama API "
    "externa e não treina modelo em tempo de uso. A tabela abaixo é o inventário do que está "
    "efetivamente publicado."
)
inventario = pd.DataFrame(inventario_artefatos())
st.dataframe(
    pd.DataFrame(
        {
            "Arquivo": inventario["arquivo"],
            "Conteúdo": inventario["descricao"],
            "Obrigatório": inventario["obrigatorio"].map({True: "sim", False: "não"}),
            "Presente": inventario["presente"].map({True: "sim", False: "não"}),
            "Tamanho (MB)": inventario["tamanho_mb"],
        }
    ),
    use_container_width=True, hide_index=True,
)

profiling = load_export_profiling()
if profiling:
    linha_de_cartoes(
        [
            ("Linhas exportadas", numero(profiling.get("linhas_gold", 0)), ""),
            ("Chaves duplicadas", str(profiling.get("chave_gold_duplicadas", "—")), ""),
            (
                "Colunas identificáveis encontradas",
                str(len(profiling.get("colunas_proibidas_encontradas", []))),
                "",
            ),
        ]
    )
    st.caption(
        "A exportação verifica, a cada execução, que nenhuma coluna potencialmente identificável "
        "chega ao dataset publicado — e aborta se encontrar alguma."
    )

ultima_atualizacao = load_ultima_atualizacao()
if ultima_atualizacao:
    with st.expander("Última execução do pipeline de atualização"):
        etapas = pd.DataFrame(ultima_atualizacao.get("etapas") or [])
        if not etapas.empty:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Etapa": etapas["etapa"],
                        "Resultado": etapas["ok"].map({True: "ok", False: "falhou"}),
                        "Duração (s)": etapas["duracao_s"],
                    }
                ),
                use_container_width=True, hide_index=True,
            )
        st.caption(
            f"Concluída: {'sim' if ultima_atualizacao.get('concluido') else 'não'} · "
            f"duração total {ultima_atualizacao.get('duracao_total_s')} s · "
            f"{ultima_atualizacao.get('n_falhas')} falha(s)."
        )

st.divider()

# ---------------------------------------------------------------------------
# 7. O que pode e o que não pode ser afirmado
# ---------------------------------------------------------------------------
st.markdown("## O que pode e o que não pode ser afirmado")
st.markdown(
    """
| Afirmação | Permitida? | Por quê |
|---|---|---|
| Acompanha o histórico territorial de arboviroses no Recife | **Sim** | Série completa por bairro e semana, direto da fonte oficial |
| Identifica os bairros com maior número de casos observados | **Sim** | Contagem direta; sem incidência, é volume absoluto |
| Compara o padrão sazonal entre anos | **Sim** | Derivado da própria série |
| Aponta bairros acima do próprio padrão histórico | **Sim** | Razão contra a mesma época em anos anteriores, com N informado |
| Fornece um ranking experimental de priorização | **Sim, com ressalva** | Retrospectivo, experimental, não é previsão oficial |
| O modelo supera regras simples ao priorizar 5 bairros por semana | **Sim, com ressalva** | Vale para Top-5, no período de teste, com intervalo de confiança declarado |
| O modelo supera regras simples ao priorizar 10 ou mais bairros | **Não** | Intervalo de confiança cruza zero; em Top-20 a regra simples é melhor |
| Identifica antecipadamente bairros prioritários | **Sim, com ressalva** | Mediana de 2 semanas em Top-10, com taxa de acerto e limitações declaradas |
| Prevê surtos | **Não** | O produto ordena prioridades relativas; não estima ocorrência nem magnitude |
| Reduz a incidência de dengue | **Não** | Não foi medido e não poderia ser, com os dados disponíveis |
| Reduz internações | **Não** | O projeto não tem dado de internação |
| Os dados são de tempo real | **Não** | A fonte publica em periodicidade trimestral; o painel mostra o último período publicado |
| Existe associação histórica entre clima e casos | **Sim, com ressalva** | Correlação por defasagem real, bruta e ajustada por sazonalidade — nunca causalidade |
| O clima antecipa/causa casos | **Não** | Associação histórica só; sazonalidade compartilhada não é relação causal |
| Projeta a trajetória sazonal esperada de 2026 | **Sim, com ressalva** | Baselines + ETS, escolhidos por backtest 2023-2025, com intervalo de previsão |
| Há caso observado de 2026 | **Não** | Nenhuma fonte oficial verificada tem dado de 2026; a página de projeção nunca mistura as duas coisas |
"""
)

st.divider()
st.markdown("## Riscos conhecidos que o painel não corrige")
st.markdown(
    """
- **Subnotificação.** Casos que não chegam ao SINAN não existem para nenhuma análise aqui. Bairros
  com menor acesso a serviços de saúde podem aparecer com menos casos por esse motivo, não por
  menor transmissão.
- **Atraso de publicação.** A fonte oficial publica em lotes; o painel mostra até onde a fonte foi
  e diz isso explicitamente em toda página.
- **Mudança de padrão epidemiológico.** O modelo aprendeu com anos anteriores; a introdução de um
  novo sorotipo ou uma mudança de comportamento pode invalidar o que ele aprendeu.
- **Mudanças climáticas.** A série climática de reanálise descreve o passado; não projeta cenários
  futuros.
- **Capacidade operacional.** Priorizar 5 bairros e priorizar 20 são decisões diferentes com
  desempenho diferente — e o painel mostra as duas faixas, inclusive aquela em que o modelo
  não ajuda.
- **População reconstruída, não sempre observada.** Fora dos anos de Censo (2010, 2022), a
  população por bairro usada para calcular incidência é estimada/projetada — a página mostra
  `tipo_populacao` sempre que exibe incidência, e a margem de erro conhecida (MAPE ≈ 10,8%) está
  documentada em `reports/population/population_incidence_integration.md`.
"""
)
