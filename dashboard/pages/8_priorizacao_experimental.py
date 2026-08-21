"""Priorização experimental — módulo de modelo, claramente separado do
painel observado.

Regras estruturais desta página:

- **Fail closed**: sem artefato, ou com artefato incompatível, nada de
  ranking. Mensagem de indisponibilidade, não um resultado aparente.
- **Nunca treina e nunca prevê aqui**: só lê Parquet/JSON já calculados
  pelo pipeline. Nenhum import de `src/ml/` (que exigiria scikit-learn).
- **Score e posição, nunca probabilidade** apresentada como confiança.
- **Modo atual só se o portão de atualidade permitir**; caso contrário,
  apenas simulação histórica.
"""
import _bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from dashboard.components.atualizacao import aviso_projecao_indisponivel
from dashboard.components.erros import exigir_dados, secao_protegida
from dashboard.components.graficos_produto import (
    grafico_backtest_bairro,
    grafico_delta_por_k,
    grafico_lead_time,
    grafico_recall_por_k,
)
from dashboard.components.pagina import iniciar_pagina
from dashboard.components.tema import linha_de_cartoes, numero, percentual
from dashboard.utils.data_loader import (
    load_evidence_summary,
    load_latest_priority,
    load_priority_backtest,
    load_priority_status,
)
from dashboard.utils.validacao import EntradaInvalidaError, validar_top_k

K_PERMITIDOS = (5, 10, 15, 20)

AVISO_EXPERIMENTAL = (
    "**Módulo experimental.** Resultados retrospectivos e sinais de priorização não substituem "
    "avaliação epidemiológica nem representam previsão oficial da Prefeitura do Recife."
)

LEITURA_POR_K = {
    5: (
        "**Top-5 — faixa com ganho robusto.** É a única faixa em que a vantagem do modelo sobre "
        "regras simples tem intervalo de confiança que não cruza zero, e o sinal se mantém "
        "positivo em todos os anos avaliados."
    ),
    10: (
        "**Top-10 — ganho não conclusivo.** O modelo aparece à frente, mas o intervalo de "
        "confiança cruza zero e o resultado agregado depende fortemente de um único ano. "
        "Não é possível afirmar vantagem nesta faixa."
    ),
    15: (
        "**Top-15 — regras simples são competitivas.** A diferença entre modelo e a melhor regra "
        "simples não é distinguível de zero."
    ),
    20: (
        "**Top-20 — regra simples é melhor.** Nesta faixa, o baseline de crescimento recente "
        "supera o modelo de forma estatisticamente detectável. Priorizar 20 bairros por semana "
        "não justifica usar o modelo."
    ),
}

gold, freshness = iniciar_pagina(
    "Priorização experimental",
    "Módulo de apoio à decisão baseado em modelo estatístico. Ele indica <b>posição relativa</b> "
    "(ranking de prioridade) entre bairros numa semana — nunca probabilidade de surto, nunca "
    "categoria de risco. Toda a avaliação abaixo é <b>retrospectiva</b>.",
    etiqueta="experimental",
)
if gold is None:
    st.stop()

st.warning(AVISO_EXPERIMENTAL, icon="🧪")

status = load_priority_status()
if status is None:
    st.error(
        "**Priorização indisponível** — o artefato de estado do módulo experimental não está "
        "presente nesta publicação. As demais páginas do painel continuam disponíveis.",
        icon="🚫",
    )
    st.stop()

backtest = load_priority_backtest()
if not status.get("backtest_available") or backtest is None:
    st.error(
        "**Priorização indisponível — artefato/modelo não validado para o período atual.** "
        f"Motivo registrado pelo pipeline: `{status.get('reason')}`.",
        icon="🚫",
    )
    st.caption(status.get("detalhe") or "")
    st.stop()

# ---------------------------------------------------------------------------
# Linhagem do modelo — sempre visível
# ---------------------------------------------------------------------------
periodo = status.get("backtest_periodo") or {}
with st.expander("Modelo e período avaliado (linhagem)", expanded=False):
    st.markdown(
        f"""
| Campo | Valor |
|---|---|
| Versão do modelo | `{status.get('model_version')}` |
| Definição do alvo | {status.get('target_definition')} |
| Horizonte | {status.get('horizon')} semanas (t+1 a t+{status.get('horizon')}) |
| Treinado com dados até | {status.get('trained_until')} |
| Assinatura do conjunto de features | `{status.get('feature_schema_version')}` |
| Versão do schema da tabela analítica | `{status.get('gold_schema_version')}` |
| Commit do código | `{str(status.get('git_commit'))[:12]}` |
| Período do backtest | {periodo.get('ano_inicio')}–{periodo.get('ano_fim')} · {periodo.get('semanas')} semanas |
| Artefatos gerados em | {status.get('gerado_em')} |
"""
    )
    st.caption(
        "O modelo é carregado apenas pelo pipeline, com validação de compatibilidade (assinatura "
        "de features, versão do schema e versão do scikit-learn). Se algo não bater, os artefatos "
        "não são publicados e esta página mostra indisponibilidade."
    )

aba_backtest, aba_atual, aba_desempenho = st.tabs(
    ["Simulação histórica (backtest)", "Período atual", "Desempenho histórico"]
)

# ===========================================================================
# ABA 1 — BACKTEST NAVEGÁVEL
# ===========================================================================
with aba_backtest:
    st.markdown("## O que o sistema saberia naquele momento")
    st.markdown(
        "Escolha uma semana passada. O painel mostra o ranking que o modelo produziria **com a "
        "informação disponível até o fim daquela semana**, e depois o que efetivamente aconteceu "
        "nas três semanas seguintes. Acertos e erros aparecem juntos — nenhuma semana é "
        "pré-selecionada por ser favorável."
    )

    semanas = (
        backtest[["ano_epidemiologico", "semana_epidemiologica"]]
        .drop_duplicates()
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"], ascending=False)
    )
    pares = [(int(a), int(s)) for a, s in zip(semanas["ano_epidemiologico"], semanas["semana_epidemiologica"])]

    col_sem, col_k = st.columns([3, 1], gap="medium")
    with col_sem:
        escolha = st.selectbox(
            "Semana de decisão",
            options=pares,
            index=0,
            format_func=lambda p: f"SE {p[1]:02d} / {p[0]}",
            key="backtest_semana",
        )
    with col_k:
        try:
            k = validar_top_k(
                st.selectbox("Bairros priorizados", options=K_PERMITIDOS, index=0, key="backtest_k"),
                K_PERMITIDOS,
            )
        except EntradaInvalidaError as exc:
            st.error("Seleção de K inválida.", icon="⚠️")
            st.caption(str(exc))
            st.stop()

    st.info(LEITURA_POR_K[k], icon="ℹ️")

    semana = backtest[
        (backtest["ano_epidemiologico"] == escolha[0])
        & (backtest["semana_epidemiologica"] == escolha[1])
    ].sort_values("ranking")

    if exigir_dados(not semana.empty, "Sem ranking para a semana selecionada."):
        topk = semana.head(k)
        alvo_conhecido = semana[semana["onset_real_em_3_semanas"].notna()]
        episodios_na_janela = alvo_conhecido[alvo_conhecido["onset_real_em_3_semanas"] == 1]
        acertos = topk[topk["onset_real_em_3_semanas"] == 1]
        falsos = topk[topk["onset_real_em_3_semanas"] == 0]
        perdidos = episodios_na_janela[~episodios_na_janela["codigo_bairro"].isin(topk["codigo_bairro"])]

        linha_de_cartoes(
            [
                (
                    f"Bairros priorizados (Top-{k})",
                    str(len(topk)),
                    f"De {len(semana)} bairros com ranking nesta semana",
                ),
                (
                    "Acertos",
                    str(len(acertos)),
                    "Priorizados em que um novo episódio realmente começou em t+1 a t+3",
                ),
                (
                    "Falsos alertas",
                    str(len(falsos)),
                    "Priorizados sem início de episódio na janela",
                ),
                (
                    "Episódios perdidos",
                    str(len(perdidos)),
                    f"Começaram na janela, mas ficaram fora do Top-{k}",
                ),
            ]
        )

        st.markdown(f"### Ranking de prioridade — SE {escolha[1]:02d} / {escolha[0]}")
        tabela_topk = pd.DataFrame(
            {
                "Prioridade": topk["ranking"].astype(int),
                "Bairro": topk["nome_bairro"].str.title(),
                "RPA": topk["codigo_rpa"],
                "Score de prioridade": topk["score_prioridade"].map(lambda v: f"{v:.0f}"),
                "Casos na semana": topk["casos_t"].astype("Int64"),
                "Razão vs. histórico": topk["razao_limiar_historico"].map(lambda v: f"{v:.2f}×"),
                "Novo episódio em t+1..t+3?": topk["onset_real_em_3_semanas"].map(
                    {1.0: "sim", 0.0: "não"}
                ).fillna("indefinido"),
                "Antecedência (semanas)": topk["semanas_ate_onset"].map(
                    lambda v: "—" if pd.isna(v) else f"{int(v)}"
                ),
                "Casos observados em t+1..t+3": topk["casos_proximas_3_semanas"].map(
                    lambda v: "—" if pd.isna(v) else f"{int(v)}"
                ),
            }
        )
        st.dataframe(tabela_topk, use_container_width=True, hide_index=True)
        st.caption(
            "**Score de prioridade** é uma posição relativa normalizada de 0 a 100 dentro da "
            "própria semana (100 = topo do ranking daquela semana). **Não é probabilidade** e não "
            "deve ser lido como 'chance de surto'. 'indefinido' aparece quando o bairro não tinha "
            "histórico suficiente para definir o desfecho — nunca é forçado a 'não'."
        )

        if len(perdidos):
            st.markdown(f"### Episódios que começaram e ficaram fora do Top-{k}")
            st.dataframe(
                pd.DataFrame(
                    {
                        "Bairro": perdidos["nome_bairro"].str.title(),
                        "RPA": perdidos["codigo_rpa"],
                        "Posição no ranking": perdidos["ranking"].astype(int),
                        "Casos na semana da decisão": perdidos["casos_t"].astype("Int64"),
                        "Antecedência (semanas)": perdidos["semanas_ate_onset"].map(
                            lambda v: "—" if pd.isna(v) else f"{int(v)}"
                        ),
                    }
                ).sort_values("Posição no ranking"),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "Esta tabela existe de propósito: mostrar só os acertos daria uma leitura falsa da "
                "capacidade do modelo."
            )
        else:
            st.caption(
                f"Nenhum episódio da janela ficou fora do Top-{k} nesta semana. Isso vale para esta "
                "semana específica, não para o desempenho médio (ver a aba **Desempenho histórico**)."
            )

        st.markdown("### Trajetória de um bairro priorizado")
        with secao_protegida("Trajetória do bairro"):
            nomes = topk["nome_bairro"].str.title().tolist()
            if nomes:
                nome_escolhido = st.selectbox("Bairro", options=nomes, key="backtest_bairro")
                codigo = topk.loc[topk["nome_bairro"].str.title() == nome_escolhido, "codigo_bairro"].iloc[0]
                serie_bairro = backtest[backtest["codigo_bairro"] == codigo].copy()
                serie_bairro = serie_bairro.sort_values(["ano_epidemiologico", "semana_epidemiologica"])
                serie_bairro["ordem"] = range(len(serie_bairro))
                indice_decisao = serie_bairro.index[
                    (serie_bairro["ano_epidemiologico"] == escolha[0])
                    & (serie_bairro["semana_epidemiologica"] == escolha[1])
                ]
                if len(indice_decisao):
                    ordem_decisao = int(serie_bairro.loc[indice_decisao[0], "ordem"])
                    janela = serie_bairro[
                        serie_bairro["ordem"].between(ordem_decisao - 8, ordem_decisao + 3)
                    ].copy()
                    janela["momento"] = [
                        "decisao" if o == ordem_decisao else ("desfecho" if o > ordem_decisao else "antes")
                        for o in janela["ordem"]
                    ]
                    janela["rotulo_semana"] = [
                        f"SE {int(s):02d}/{int(a)}"
                        for a, s in zip(janela["ano_epidemiologico"], janela["semana_epidemiologica"])
                    ]
                    janela = janela.rename(columns={"casos_t": "casos"})
                    posicao = int(topk.loc[topk["codigo_bairro"] == codigo, "ranking"].iloc[0])
                    st.plotly_chart(
                        grafico_backtest_bairro(
                            janela, posicao, nome_escolhido, f"SE {escolha[1]:02d}/{escolha[0]}"
                        ),
                        use_container_width=True,
                    )

# ===========================================================================
# ABA 2 — PERÍODO ATUAL (COM PORTÃO)
# ===========================================================================
with aba_atual:
    st.markdown("## Priorização referente ao período mais recente")
    if not status.get("current_projection_available"):
        aviso_projecao_indisponivel(status)
        epi = status.get("epidemiologia") or {}
        linha_de_cartoes(
            [
                (
                    "Último período publicado",
                    (epi.get("semana_epi_maxima") or "—").replace("-", " / SE ")[::1]
                    if epi.get("semana_epi_maxima") else "—",
                    "Semana epidemiológica mais recente com dado oficial",
                ),
                (
                    "Atraso em relação a hoje",
                    f"{status.get('semanas_de_atraso')} semanas"
                    if status.get("semanas_de_atraso") is not None else "—",
                    f"Limite para priorização do período atual: {status.get('semanas_limite')} semanas",
                ),
                (
                    "Situação do módulo",
                    "somente backtest",
                    "A projeção do período atual permanece desativada até a fonte publicar dados recentes",
                ),
            ]
        )
        st.markdown(
            "**Por que desativar em vez de mostrar o último ranking disponível?** Porque o modelo "
            f"sinaliza o início de um episódio nas {status.get('horizon')} semanas seguintes à "
            "semana de decisão. Com o último dado publicado muitos meses atrás, essa janela-alvo já "
            "passou por completo: o gestor não teria sobre o que agir, e o número pareceria atual "
            "sem ser. A alternativa honesta é a simulação histórica."
        )
    else:
        latest = load_latest_priority()
        if latest is None:
            st.error(
                "O estado indica projeção disponível, mas o artefato de priorização não foi "
                "encontrado. Por segurança, nenhum ranking é exibido.",
                icon="🚫",
            )
        else:
            referencia = latest.iloc[0]
            linha_de_cartoes(
                [
                    (
                        "Semana de referência",
                        f"SE {int(referencia['reference_week']):02d} / {int(referencia['reference_year'])}",
                        f"Horizonte: t+1 a t+{int(referencia['forecast_horizon'])}",
                    ),
                    ("Versão do modelo", str(referencia["model_version"]), "Modelo congelado"),
                    ("Dados até", str(referencia["data_cutoff"]), "Nenhuma feature usa dado posterior"),
                    ("Gerado em", str(referencia["generated_at"])[:10], "Pelo pipeline de atualização"),
                ]
            )
            st.markdown("### Cinco bairros no topo do ranking experimental")
            st.markdown(
                "*Se houver capacidade para priorizar cinco bairros nesta semana, estes seriam os "
                "cinco primeiros do ranking experimental.*"
            )
            top5 = latest.head(5)
            st.dataframe(
                pd.DataFrame(
                    {
                        "Prioridade": top5["ranking"].astype(int),
                        "Bairro": top5["bairro"].str.title(),
                        "RPA": top5["rpa"],
                        "Score de prioridade": top5["score_prioridade"].map(lambda v: f"{v:.0f}"),
                    }
                ),
                use_container_width=True, hide_index=True,
            )
            st.caption(AVISO_EXPERIMENTAL)
            with st.expander("Ranking completo"):
                st.dataframe(latest, use_container_width=True, hide_index=True)

# ===========================================================================
# ABA 3 — DESEMPENHO HISTÓRICO
# ===========================================================================
with aba_desempenho:
    evidencia = load_evidence_summary()
    if evidencia is None:
        st.info(
            "O resumo da validação estatística não está disponível nesta publicação. "
            "A simulação histórica continua funcionando.",
            icon="ℹ️",
        )
    else:
        config = evidencia.get("configuracao") or {}
        st.markdown("## Quanto o modelo acrescenta sobre regras simples")
        st.markdown(
            f"Avaliação sobre **{config.get('n_episodios_teste')} episódios reais** de dengue no "
            f"período de teste, com reamostragem *bootstrap* ao nível de episódio "
            f"({evidencia.get('n_reamostragens')} reamostragens, semente fixa). "
            "A métrica é: *em quantos episódios reais o bairro apareceu entre os K primeiros do "
            "ranking em alguma das 4 semanas anteriores ao início observado?*"
        )

        recall_ic = pd.DataFrame(evidencia.get("recall_ic") or [])
        delta = pd.DataFrame(evidencia.get("delta_vs_melhor_baseline") or [])

        with secao_protegida("Recall por K"):
            if not recall_ic.empty:
                st.plotly_chart(
                    grafico_recall_por_k(
                        recall_ic, "Episódios antecipados por K — modelo × regras simples (IC 95%)"
                    ),
                    use_container_width=True,
                )

        with secao_protegida("Ganho sobre o baseline"):
            if not delta.empty:
                st.plotly_chart(
                    grafico_delta_por_k(
                        delta, "Ganho do modelo sobre a melhor regra simples, por K"
                    ),
                    use_container_width=True,
                )
                st.caption(
                    "Barra preenchida = intervalo de confiança que não cruza zero (diferença "
                    "conclusiva). Barra hachurada = intervalo cruza zero (inconclusiva). "
                    "A distinção também está escrita no rótulo de cada barra."
                )

                st.markdown("### Como ler cada faixa de capacidade operacional")
                for _, linha in delta.iterrows():
                    k_linha = int(linha["k"])
                    if k_linha in LEITURA_POR_K:
                        st.markdown(
                            f"- {LEITURA_POR_K[k_linha]} "
                            f"*(diferença observada: {linha['observado'] * 100:+.2f} pontos percentuais; "
                            f"IC 95%: {linha['ic_baixo'] * 100:+.2f} a {linha['ic_alto'] * 100:+.2f}; "
                            f"melhor regra simples nesta faixa: `{linha['melhor_baseline']}`)*"
                        )

        st.divider()

        # ---------------- Antecipação ----------------
        st.markdown("## Antecipação (lead time)")
        lead = evidencia.get("lead_time_k10") or {}
        if lead:
            st.markdown(
                f"Medido em **Top-10**, no período de teste "
                f"({config.get('split_validacao_ate', 0) + 1}–"
                f"{(evidencia.get('por_ano') or [{}])[-1].get('inicio_ano', '')}), "
                f"sobre os **{lead.get('n')} episódios detectados nessa faixa**."
            )
            linha_de_cartoes(
                [
                    (
                        "Antecedência mediana",
                        f"{(lead.get('mediana_ic') or {}).get('observado', 0):.0f} semanas",
                        f"IC 95%: {(lead.get('mediana_ic') or {}).get('ic_baixo')}–"
                        f"{(lead.get('mediana_ic') or {}).get('ic_alto')} semanas",
                    ),
                    ("≥ 2 semanas", percentual(lead.get("pct_>=2_semanas")), "Dos episódios detectados"),
                    ("≥ 3 semanas", percentual(lead.get("pct_>=3_semanas")), "Dos episódios detectados"),
                    (
                        "Antecedência média",
                        f"{lead.get('media', 0):.2f} semanas",
                        f"P25/P75: {lead.get('p25')}/{lead.get('p75')}",
                    ),
                ]
            )
            st.caption(
                "A janela de avaliação vai de 4 a 1 semanas antes do início observado, portanto um "
                "destaque na própria semana de início nunca conta como antecipação — é por isso que "
                "'≥ 1 semana' seria 100% por construção e não é apresentado como resultado. "
                "**Esta medida é de Top-10 e não deve ser combinada com a afirmação de ganho de "
                "Top-5**, que é outra faixa."
            )
            with secao_protegida("Distribuição do lead time"):
                if not backtest.empty:
                    detectados = backtest[
                        (backtest["ranking"] <= 10) & backtest["semanas_ate_onset"].notna()
                    ]
                    if not detectados.empty:
                        contagem = detectados["semanas_ate_onset"].value_counts().sort_index()
                        st.plotly_chart(
                            grafico_lead_time(
                                contagem,
                                "Antecedência observada entre priorização no Top-10 e início do episódio",
                            ),
                            use_container_width=True,
                        )

        st.divider()

        # ---------------- Desempenho territorial ----------------
        st.markdown("## Desempenho territorial")
        st.markdown(
            "O modelo **não** é igualmente confiável em todos os territórios. Os números abaixo "
            "vêm sempre com o número de episódios (N) que os sustenta."
        )
        por_rpa = pd.DataFrame(evidencia.get("por_rpa") or [])
        if not por_rpa.empty:
            st.dataframe(
                pd.DataFrame(
                    {
                        "RPA": por_rpa["codigo_rpa"],
                        "Episódios (N)": por_rpa["n_episodios"].astype(int),
                        "Top-5": (por_rpa["recall5_modelo"] * 100).map(lambda v: f"{v:.1f}%"),
                        "Top-10": (por_rpa["recall10_modelo"] * 100).map(lambda v: f"{v:.1f}%"),
                        "Top-20": (por_rpa["recall20_modelo"] * 100).map(lambda v: f"{v:.1f}%"),
                    }
                ).sort_values("Top-10", ascending=False),
                use_container_width=True, hide_index=True,
            )
            melhor = por_rpa.loc[por_rpa["recall10_modelo"].idxmax()]
            pior = por_rpa.loc[por_rpa["recall10_modelo"].idxmin()]
            st.markdown(
                f"**Disparidade regional observada:** RPA {melhor['codigo_rpa']} alcança "
                f"{melhor['recall10_modelo'] * 100:.1f}% em Top-10 (N = {int(melhor['n_episodios'])}), "
                f"enquanto RPA {pior['codigo_rpa']} fica em {pior['recall10_modelo'] * 100:.1f}% "
                f"(N = {int(pior['n_episodios'])}). A causa não foi investigada."
            )

        criticos = (evidencia.get("bairros_criticos") or {}).get("muitos_episodios_baixa_deteccao") or []
        if criticos:
            st.markdown("### Bairros com desempenho persistentemente baixo")
            df_criticos = pd.DataFrame(criticos)
            st.dataframe(
                pd.DataFrame(
                    {
                        "Bairro": df_criticos["nome_bairro"].str.title(),
                        "Episódios (N)": df_criticos["n_episodios"].astype(int),
                        "Top-10": (df_criticos["recall10_modelo"] * 100).map(lambda v: f"{v:.1f}%"),
                        "Top-20": (df_criticos["recall20_modelo"] * 100).map(lambda v: f"{v:.1f}%"),
                    }
                ),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "Critério: ao menos 5 episódios no período e menos de 30% de detecção em Top-20. "
                "Como quase todos os bairros têm amostra utilizável, esses zeros indicam limitação "
                "sistemática do modelo naqueles territórios, não instabilidade de percentual."
            )

        st.divider()

        # ---------------- Recortes difíceis ----------------
        st.markdown("## Onde o modelo é mais fraco")
        col_g, col_e = st.columns(2, gap="large")

        genuino = evidencia.get("genuino_vs_recaida") or {}
        with col_g:
            st.markdown("### Início genuíno × recaída")
            if genuino:
                st.markdown(
                    f"Dos episódios avaliados, **{genuino.get('n_genuinos')}** começaram após um "
                    f"período sem atividade (início genuíno) e **{genuino.get('n_recaidas')}** "
                    "logo após atividade recente (recaída)."
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "K": k,
                                "Início genuíno": f"{genuino[f'recall{k}_genuino']['observado'] * 100:.1f}%",
                                "Recaída": f"{genuino[f'recall{k}_recaida']['observado'] * 100:.1f}%",
                            }
                            for k in (5, 10, 20)
                            if f"recall{k}_genuino" in genuino
                        ]
                    ),
                    use_container_width=True, hide_index=True,
                )
                st.warning(
                    "O cenário mais comum e mais relevante para a Prefeitura — detectar algo que "
                    "está **começando** — é justamente o mais difícil para o modelo. Os intervalos "
                    "de confiança dos dois grupos não se sobrepõem em nenhuma faixa.",
                    icon="⚠️",
                )

        grandes = evidencia.get("grandes_episodios") or {}
        with col_e:
            st.markdown("### Grandes episódios")
            if grandes:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "K": k,
                                f"Grandes (N={grandes.get('n')})":
                                    f"{grandes[f'recall{k}_grandes']['observado'] * 100:.1f}%",
                                "Todos os episódios":
                                    f"{grandes[f'recall{k}_todos']['observado'] * 100:.1f}%",
                            }
                            for k in (5, 10)
                            if f"recall{k}_grandes" in grandes
                        ]
                    ),
                    use_container_width=True, hide_index=True,
                )
                st.markdown(
                    "Sob **ranking**, os grandes episódios têm desempenho **pior** que a média — o "
                    "oposto do que uma formulação de classificação binária sugeria numa etapa "
                    "anterior. O motivo é que o ranking é relativo: numa epidemia ampla, vários "
                    "bairros sobem ao mesmo tempo e competem pelas mesmas K posições. "
                    "**Os números de detecção da formulação binária anterior não se aplicam a este "
                    "módulo** e não são reaproveitados aqui."
                )

        st.divider()

        # ---------------- Carga operacional e estabilidade ----------------
        st.markdown("## Custo operacional da priorização")
        carga = pd.DataFrame(evidencia.get("carga_operacional") or [])
        if not carga.empty:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Bairros por semana (K)": carga["k"].astype(int),
                        "Episódios antecipados": carga["episodios_antecipados"].astype(int),
                        "Episódios perdidos": carga["episodios_perdidos"].astype(int),
                        "Taxa de antecipação": (carga["taxa_antecipacao"] * 100).map(lambda v: f"{v:.1f}%"),
                        "Priorizações totais": carga["priorizacoes_total"].astype(int),
                        "Sem episódio na sequência": carga["pct_priorizacoes_sem_episodio_futuro"].map(
                            lambda v: f"{v:.1f}%"
                        ),
                    }
                ),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "Duas unidades diferentes, de propósito: **episódio** (quantos surtos foram "
                "antecipados) e **priorização** (quantas visitas bairro × semana o ranking pede). "
                "A última coluna é o custo real: a fração de priorizações que, olhando para trás, "
                "não precedeu início de episódio."
            )

        estab = evidencia.get("estabilidade_top10") or {}
        if estab:
            st.markdown("### Estabilidade da lista entre semanas")
            linha_de_cartoes(
                [
                    (
                        "Sobreposição média do Top-10",
                        f"{estab.get('jaccard_medio', 0):.2f}",
                        "Índice de Jaccard entre semanas consecutivas (0 = troca total, 1 = lista idêntica)",
                    ),
                    (
                        "Sobreposição mediana",
                        f"{estab.get('jaccard_mediano', 0):.2f}",
                        f"Sobre {estab.get('n_pares_consecutivos')} pares de semanas consecutivas",
                    ),
                    (
                        "Leitura prática",
                        "~2 a 4 de 10 bairros permanecem",
                        "A lista muda substancialmente de uma semana para a seguinte",
                    ),
                ]
            )

        # ---------------- Clima ----------------
        clima_exp = evidencia.get("experimento_clima") or {}
        if clima_exp:
            st.divider()
            st.markdown("## O clima acrescenta informação a este modelo?")
            conclusao = clima_exp.get("conclusao") or {}
            st.markdown(
                f"Experimento controlado (mesmas linhas, mesmo split, mesmos hiperparâmetros, "
                f"variando apenas as variáveis climáticas): na faixa **Top-5**, a diferença "
                f"observada foi de **{conclusao.get('delta5_observado', 0) * 100:+.2f} pontos "
                f"percentuais**, com intervalo de confiança que "
                f"{'cruza' if conclusao.get('delta5_ic_cruza_zero') else 'não cruza'} zero. "
                f"Decisão: **{'incorporar' if conclusao.get('incorporar_clima_ao_modelo') else 'não incorporar'}** "
                "o clima ao modelo do produto."
            )
            secundario = conclusao.get("achado_secundario_k10") or {}
            if secundario:
                st.caption(
                    f"Achado secundário registrado por transparência: em Top-10 a diferença foi de "
                    f"{secundario.get('delta10_B_menos_A', 0) * 100:+.2f} pontos percentuais com "
                    "intervalo acima de zero nos três esquemas de reamostragem. Como Top-10 não é a "
                    "faixa de afirmação do produto e essa variante não passou pelo protocolo completo "
                    "de validação, ela fica registrada como candidata a uma versão futura — não como "
                    "resultado."
                )

st.divider()
st.markdown("### Limitações que acompanham qualquer uso deste módulo")
st.markdown(
    "- Ganho sobre regras simples é defensável **apenas em Top-5**; em Top-10 é inconclusivo e em "
    "Top-20 a regra simples é melhor.\n"
    "- O desempenho **varia muito entre anos** e entre RPAs; a média esconde essa instabilidade.\n"
    "- O cenário de **início genuíno** — o mais relevante — é o de pior desempenho.\n"
    "- A lista de prioridade **muda substancialmente** de uma semana para a outra.\n"
    "- A maior parte das priorizações, olhando para trás, **não** precedeu início de episódio.\n"
    "- O modelo foi avaliado retrospectivamente. Ele **não** demonstra redução de incidência nem de "
    "internações, e nenhuma afirmação nesse sentido é feita.\n"
    "- Subnotificação, mudança de padrão epidemiológico e limitações da fonte afetam tanto o dado "
    "observado quanto o modelo."
)
st.caption(
    "Metodologia e resultados completos em `reports/ml/dengue_ranking_evidence_validation.md` e "
    "`reports/ml/dengue_ranking_clima_experiment.md`."
)
