"""Página técnica de validação do candidato de ranking territorial —
**separada do dashboard público** (`dashboard/`) por decisão explícita
desta etapa, para minimizar risco de confusão entre "material técnico de
validação" e "produto operacional Recife Alerta" (que continua NÃO
recebendo nenhuma funcionalidade preditiva, conforme decisão preservada
das etapas anteriores).

Uso:
    streamlit run tools/model_validation_app.py

Só LÊ artefatos de backtest já calculados por
`python -m src.validate_dengue_onset_ranking_evidence`
(`reports/ml/evidence_*.csv` + `resultado_evidence_validation_completo.json`)
— nunca treina modelo, nunca gera previsão nova, nunca calcula
probabilidade "ao vivo". Se os artefatos não existirem, mostra um aviso
em vez de quebrar.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent
if str(RAIZ_REPOSITORIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPOSITORIO))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ml.evidence_validation import carregar_artefatos_evidencia

PASTA_RELATORIO = RAIZ_REPOSITORIO / "reports" / "ml"

st.set_page_config(page_title="Validação do Modelo — Onset/Ranking (Dengue)", page_icon="🧪", layout="wide")

st.warning(
    "**Validação experimental — não representa ferramenta operacional de previsão.** "
    "Esta página mostra resultados de um backtest histórico (2023-2025) sobre dados já conhecidos. "
    "Não gera alerta, score ou previsão para uso operacional — não é o produto Recife Alerta.",
    icon="🧪",
)

st.title("🧪 Validação do candidato de ranking territorial — dengue por bairro")
st.caption(
    "Candidato avaliado: `dengue_onset_ranking_candidate_v1` (onset em t+1..t+3, ranking territorial, "
    "sem clima). Ver `reports/ml/dengue_ranking_evidence_validation.md` para a análise completa."
)

artefatos = carregar_artefatos_evidencia(PASTA_RELATORIO)
resumo = artefatos["resumo"]

if resumo is None:
    st.error(
        "Nenhum artefato de validação encontrado em `reports/ml/`. "
        "Rode `python -m src.validate_dengue_onset_ranking_evidence` primeiro."
    )
    st.stop()

config = resumo["configuracao"]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Episódios avaliados (2023-2025)", config["n_episodios_teste"])
col2.metric("Horizonte do onset", f"t+1..t+{config['horizonte_semanas']}")
col3.metric("Linhas de treino", f"{config['n_treino']:,}".replace(",", "."))
col4.metric("Janela de lead time", f"{config['janela_lead_time_semanas']} semanas")

st.divider()

# ----------------------------------------------------------------------
# A. Recall@K -- modelo x baselines, com IC
# ----------------------------------------------------------------------
st.header("A. Recall@K — modelo × baselines (com intervalo de confiança 95%)")
st.caption(
    "Recall@K = % de episódios reais em que o bairro apareceu no Top-K de risco em alguma semana "
    "das 4 anteriores ao início real. Bootstrap ao nível de episódio, 2.000 reamostragens, seed=42."
)

recall_ic = artefatos["recall_ic"]
if recall_ic is not None:
    fig = go.Figure()
    for metodo in recall_ic["metodo"].unique():
        sub = recall_ic[recall_ic["metodo"] == metodo].sort_values("k")
        fig.add_trace(
            go.Scatter(
                x=sub["k"],
                y=sub["observado"] * 100,
                error_y=dict(
                    type="data",
                    symmetric=False,
                    array=(sub["ic_alto"] - sub["observado"]) * 100,
                    arrayminus=(sub["observado"] - sub["ic_baixo"]) * 100,
                ),
                mode="lines+markers",
                name=metodo,
            )
        )
    fig.update_layout(
        xaxis_title="K (bairros priorizados/semana)",
        yaxis_title="Recall@K (%)",
        title="Recall@K por método, com IC 95% (bootstrap por episódio)",
        legend_title="Método",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(recall_ic, use_container_width=True)
else:
    st.info("`evidence_recall_ic.csv` não encontrado.")

st.divider()

# ----------------------------------------------------------------------
# B. Delta modelo vs melhor baseline
# ----------------------------------------------------------------------
st.header("B. Ganho do modelo sobre o melhor baseline (delta Recall@K)")
st.caption(
    "Delta = Recall@K(modelo) - Recall@K(melhor baseline observado nesse K). "
    "IC que NÃO cruza zero = diferença estatisticamente defensável nesta amostra."
)

delta = artefatos["delta_vs_baseline"]
if delta is not None:
    fig2 = go.Figure()
    cores = ["green" if (lo > 0 or hi < 0) else "gray" for lo, hi in zip(delta["ic_baixo"], delta["ic_alto"])]
    fig2.add_trace(
        go.Bar(
            x=delta["k"],
            y=delta["observado"] * 100,
            error_y=dict(
                type="data",
                symmetric=False,
                array=(delta["ic_alto"] - delta["observado"]) * 100,
                arrayminus=(delta["observado"] - delta["ic_baixo"]) * 100,
            ),
            marker_color=cores,
        )
    )
    fig2.add_hline(y=0, line_dash="dash", line_color="black")
    fig2.update_layout(xaxis_title="K", yaxis_title="Delta Recall@K (pontos percentuais)", title="Verde = IC não cruza zero (diferença defensável); Cinza = IC cruza zero")
    st.plotly_chart(fig2, use_container_width=True)
    st.dataframe(delta, use_container_width=True)
    st.caption(
        "Colunas `ic_*_cluster_bairro` e `ic_*_cluster_bairro_ano`: mesmo delta com bootstrap por CLUSTER "
        "(bairro inteiro, ou bairro×ano, reamostrado — nunca episódio individual dentro do cluster), "
        "preservando a correlação entre episódios do mesmo território. Análise de sensibilidade, mais "
        "conservadora que o IC principal."
    )
else:
    st.info("`evidence_delta_vs_baseline.csv` não encontrado.")

st.divider()

# ----------------------------------------------------------------------
# C. Performance por ano + leave-one-year-out
# ----------------------------------------------------------------------
st.header("C. Performance por ano")
por_ano = artefatos["por_ano"]
if por_ano is not None:
    st.dataframe(por_ano, use_container_width=True)
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=por_ano["inicio_ano"], y=por_ano["recall5_modelo"] * 100, name="Recall@5 modelo"))
    fig3.add_trace(go.Bar(x=por_ano["inicio_ano"], y=por_ano["recall5_melhor_baseline"] * 100, name="Recall@5 melhor baseline"))
    fig3.update_layout(barmode="group", xaxis_title="Ano", yaxis_title="Recall@5 (%)", title="Recall@5: modelo x melhor baseline, por ano")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("`evidence_por_ano.csv` não encontrado.")

st.subheader("Sensibilidade: leave-one-year-out (não é retreino, só reavaliação excluindo 1 ano)")
loyo = artefatos["leave_one_year_out"]
if loyo is not None:
    st.dataframe(loyo, use_container_width=True)
    st.caption(
        "Se o Recall@10 do modelo cair abaixo do baseline ao excluir 2025, isso indica que o ganho agregado "
        "em K=10 depende fortemente daquele ano específico — ver relatório para a leitura completa."
    )

st.divider()

# ----------------------------------------------------------------------
# D. Performance por RPA
# ----------------------------------------------------------------------
st.header("D. Performance territorial por RPA")
por_rpa = artefatos["por_rpa"]
if por_rpa is not None:
    st.dataframe(por_rpa, use_container_width=True)
    fig4 = go.Figure(go.Bar(x=por_rpa["codigo_rpa"].astype(str), y=por_rpa["recall10_modelo"] * 100, text=por_rpa["n_episodios"]))
    fig4.update_layout(xaxis_title="RPA", yaxis_title="Recall@10 (%)", title="Recall@10 por RPA (rótulo = nº de episódios)")
    st.plotly_chart(fig4, use_container_width=True)
else:
    st.info("`evidence_por_rpa.csv` não encontrado.")

st.subheader("Bairros críticos")
if resumo.get("ipsep"):
    st.write("**IPSEP:**", resumo["ipsep"])
bairros_criticos = resumo.get("bairros_criticos", {})
if bairros_criticos.get("muitos_episodios_baixa_deteccao"):
    st.write("**Bairros com ≥5 episódios e Recall@20 < 30%:**")
    st.dataframe(pd.DataFrame(bairros_criticos["muitos_episodios_baixa_deteccao"]), use_container_width=True)

st.divider()

# ----------------------------------------------------------------------
# E. Lead time
# ----------------------------------------------------------------------
st.header("E. Lead time (episódios detectados no Top-10)")
lead = resumo.get("lead_time_k10", {})
if lead:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mediana", f"{lead['mediana_ic']['observado']:.0f} sem.", help=f"IC 95%: [{lead['mediana_ic']['ic_baixo']:.1f}, {lead['mediana_ic']['ic_alto']:.1f}]")
    c2.metric("Média", f"{lead['media']:.2f} sem.")
    c3.metric("P25 / P75", f"{lead['p25']:.0f} / {lead['p75']:.0f} sem.")
    c4.metric("N detectados", lead["n"])
    st.write(
        f"% episódios com ≥1 semana: **{lead['pct_>=1_semana']:.1f}%** · "
        f"≥2 semanas: **{lead['pct_>=2_semanas']:.1f}%** · "
        f"≥3 semanas: **{lead['pct_>=3_semanas']:.1f}%**"
    )
    st.caption(
        "A janela de avaliação vai de `inicio-4` a `inicio-1` semanas: um destaque na PRÓPRIA semana de "
        "início nunca conta como antecipação, por isso `% ≥1 semana` é 100% por construção."
    )
    master = artefatos["master_episodios"]
    if master is not None:
        leads_detectados = master.loc[master["detectado_modelo_k10"] == 1, "lead_modelo"].dropna()
        contagem = leads_detectados.value_counts().sort_index()
        fig5 = go.Figure(go.Bar(x=[f"{int(v)} sem." for v in contagem.index], y=contagem.to_numpy()))
        fig5.update_layout(
            xaxis_title="Semanas de antecedência", yaxis_title="Episódios detectados no Top-10",
            title="Distribuição do lead time (episódios detectados no Top-10)",
        )
        st.plotly_chart(fig5, use_container_width=True)

st.divider()

# ----------------------------------------------------------------------
# F. Grandes episódios
# ----------------------------------------------------------------------
st.header("F. Grandes episódios (top 10% por volume de casos) × todos")
grandes = resumo.get("grandes_episodios", {})
if grandes:
    st.write(f"N grandes episódios: {grandes['n']}")
    linhas = []
    for k in (5, 10):
        linhas.append(
            {
                "k": k,
                "recall_grandes": grandes[f"recall{k}_grandes"]["observado"],
                "ic_grandes": (grandes[f"recall{k}_grandes"]["ic_baixo"], grandes[f"recall{k}_grandes"]["ic_alto"]),
                "recall_todos": grandes[f"recall{k}_todos"]["observado"],
                "ic_todos": (grandes[f"recall{k}_todos"]["ic_baixo"], grandes[f"recall{k}_todos"]["ic_alto"]),
            }
        )
    st.dataframe(pd.DataFrame(linhas), use_container_width=True)
    st.caption(
        "Os ICs de 'grandes episódios' são mais largos (N menor, 92 episódios) — sobreposição com "
        "o IC de 'todos' indica que a diferença pode não ser estatisticamente conclusiva."
    )

st.divider()

# ----------------------------------------------------------------------
# G. Antecipação genuína x recaída
# ----------------------------------------------------------------------
st.header("G. Antecipação genuína × recaída")
genuino = resumo.get("genuino_vs_recaida", {})
if genuino:
    st.write(f"Episódios genuínos: {genuino['n_genuinos']} · Episódios após atividade recente (recaída): {genuino['n_recaidas']}")
    linhas_g = []
    for k in (5, 10, 20):
        linhas_g.append(
            {
                "k": k,
                "recall_genuino": genuino[f"recall{k}_genuino"]["observado"],
                "ic_genuino": (genuino[f"recall{k}_genuino"]["ic_baixo"], genuino[f"recall{k}_genuino"]["ic_alto"]),
                "recall_recaida": genuino[f"recall{k}_recaida"]["observado"],
                "ic_recaida": (genuino[f"recall{k}_recaida"]["ic_baixo"], genuino[f"recall{k}_recaida"]["ic_alto"]),
            }
        )
    st.dataframe(pd.DataFrame(linhas_g), use_container_width=True)
    fig6 = go.Figure()
    for grupo, rotulo in (("genuino", f"antecipação genuína (n={genuino['n_genuinos']})"), ("recaida", f"recaída (n={genuino['n_recaidas']})")):
        fig6.add_trace(
            go.Bar(
                x=[f"Recall@{k}" for k in (5, 10, 20)],
                y=[genuino[f"recall{k}_{grupo}"]["observado"] * 100 for k in (5, 10, 20)],
                name=rotulo,
                error_y=dict(
                    type="data", symmetric=False,
                    array=[(genuino[f"recall{k}_{grupo}"]["ic_alto"] - genuino[f"recall{k}_{grupo}"]["observado"]) * 100 for k in (5, 10, 20)],
                    arrayminus=[(genuino[f"recall{k}_{grupo}"]["observado"] - genuino[f"recall{k}_{grupo}"]["ic_baixo"]) * 100 for k in (5, 10, 20)],
                ),
            )
        )
    fig6.update_layout(barmode="group", yaxis_title="Recall (%)", title="Antecipação genuína × recaída (IC 95%)")
    st.plotly_chart(fig6, use_container_width=True)
    st.warning(
        "Antecipação genuína (sem atividade recente) é o cenário mais comum e o mais difícil — "
        "é justamente o cenário mais relevante para o desafio da Prefeitura.",
        icon="⚠️",
    )

st.divider()

# ----------------------------------------------------------------------
# H. Estabilidade do Top-10 + I. Carga operacional
# ----------------------------------------------------------------------
st.header("H. Estabilidade do Top-10 entre semanas consecutivas")
estab = resumo.get("estabilidade_top10", {})
if estab:
    c1, c2, c3 = st.columns(3)
    c1.metric("Jaccard médio", f"{estab['jaccard_medio']:.2f}")
    c2.metric("Jaccard mediano", f"{estab['jaccard_mediano']:.2f}")
    c3.metric("Pares de semanas", estab["n_pares_consecutivos"])
    st.caption("0 = ranking completamente diferente semana a semana; 1 = ranking idêntico.")

caminho_serie = PASTA_RELATORIO / "evidence_estabilidade_top10_semanal.csv"
if caminho_serie.exists():
    serie = pd.read_csv(caminho_serie)
    fig7 = go.Figure(go.Scatter(x=serie["indice_semana_alvo"], y=serie["jaccard"], mode="lines"))
    if estab:
        fig7.add_hline(y=estab["jaccard_medio"], line_dash="dash", line_color="red")
    fig7.update_layout(
        xaxis_title="Índice de semana global", yaxis_title="Jaccard do Top-10 (t × t+1)",
        yaxis_range=[0, 1], title="Série semanal da sobreposição do Top-10 (linha vermelha = média)",
    )
    st.plotly_chart(fig7, use_container_width=True)

st.divider()

st.header("I. Carga operacional e desempenho por bairro")
carga = artefatos["carga_operacional"]
if carga is not None:
    st.dataframe(carga, use_container_width=True)
    st.caption(
        "`episodios_antecipados`/`episodios_perdidos`: unidade = episódio real. "
        "`priorizacoes_sem_episodio_futuro`: unidade = priorização (bairro × semana) que, retrospectivamente, "
        "não precedeu nenhum início de episódio na janela t+1..t+3 — é o custo de olhar K bairros toda semana."
    )

por_bairro = artefatos["por_bairro"]
if por_bairro is not None:
    sub = por_bairro[por_bairro["n_episodios"] >= 3].sort_values("recall10_modelo")
    fig8 = go.Figure(
        go.Bar(
            x=sub["recall10_modelo"] * 100,
            y=[f"{n} (n={int(e)})" for n, e in zip(sub["nome_bairro"], sub["n_episodios"])],
            orientation="h",
        )
    )
    fig8.update_layout(
        xaxis_title="Recall@10 (%)", title="Recall@10 por bairro (apenas bairros com ≥3 episódios)",
        height=max(420, len(sub) * 16),
    )
    st.plotly_chart(fig8, use_container_width=True)
    n_ate_2 = int((por_bairro["n_episodios"] <= 2).sum())
    st.caption(
        f"93 dos 94 bairros tiveram ao menos 1 episódio no teste; apenas {n_ate_2} tem N ≤ 2 "
        "(mínimo 2, mediana 9, máximo 22 episódios). Como quase não há bairro de amostra minúscula, "
        "os zeros observados são sobre amostras utilizáveis — evidência de limitação sistemática, não "
        "de percentual instável. Tabela completa em `reports/ml/evidence_por_bairro.csv`."
    )

st.divider()
st.header("Limitações")
st.markdown(
    "- Ganho estatisticamente defensável do modelo só em **Top-5** (IC não cruza zero); em Top-10 o IC "
    "cruza zero e o resultado agregado depende fortemente do ano de 2025 (ver seção C); em Top-20 o "
    "modelo é **estatisticamente pior** que o baseline simples.\n"
    "- Antecipação genuína (o cenário mais importante) tem desempenho bem inferior à recaída.\n"
    "- Forte disparidade regional (RPA 5 muito acima de RPA 6).\n"
    "- IPSEP e outros bairros de volume relevante seguem com detecção baixa.\n"
    "- Ver `reports/ml/dengue_ranking_evidence_validation.md` para a análise completa e a tabela de "
    "claims permitidos/proibidos."
)
