"""Visualizações (PNG) da validação de evidência do candidato congelado
`dengue_onset_ranking_candidate_v1`.

Separado de `src/validate_dengue_onset_ranking_evidence.py` de propósito,
seguindo o padrão já usado na Gold (`profiling_gold.py` x `analyze_gold.py`):
nenhuma função de análise/estatística importa matplotlib, e este script
**não recalcula nada** — só lê os artefatos já salvos em `reports/ml/`
(`evidence_*.csv` + `resultado_evidence_validation_completo.json`) e desenha.

Uso:
    python -m src.plot_evidence_validation
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sem display — obrigatório neste ambiente
import matplotlib.pyplot as plt
import pandas as pd

from src.ml.evidence_validation import carregar_artefatos_evidencia

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RELATORIO = RAIZ / "reports" / "ml"

CORES_METODO = {
    "modelo": "#1f77b4",
    "casos_atuais": "#aec7e8",
    "crescimento_recente": "#ff7f0e",
    "razao_historica_local": "#2ca02c",
}


def _salvar(fig, nome: str) -> Path:
    caminho = PASTA_RELATORIO / nome
    fig.tight_layout()
    fig.savefig(caminho, dpi=130)
    plt.close(fig)
    logger.info("Figura salva: %s", caminho.name)
    return caminho


def figura_a_recall_por_metodo(recall_ic: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    for metodo in ["modelo", "casos_atuais", "crescimento_recente", "razao_historica_local"]:
        sub = recall_ic[recall_ic["metodo"] == metodo].sort_values("k")
        if sub.empty:
            continue
        erro = [
            (sub["observado"] - sub["ic_baixo"]).to_numpy() * 100,
            (sub["ic_alto"] - sub["observado"]).to_numpy() * 100,
        ]
        ax.errorbar(
            sub["k"],
            sub["observado"] * 100,
            yerr=erro,
            marker="o",
            capsize=4,
            label=metodo,
            color=CORES_METODO.get(metodo),
            linewidth=2.2 if metodo == "modelo" else 1.2,
        )
    ax.set_xlabel("K (bairros priorizados por semana)")
    ax.set_ylabel("Recall@K por episodio (%)")
    ax.set_title("A. Recall@K: modelo x rankings simples (IC 95%, bootstrap por episodio)")
    ax.set_xticks(sorted(recall_ic["k"].unique()))
    ax.grid(alpha=0.3)
    ax.legend(title="Metodo", fontsize=8)
    return _salvar(fig, "evidence_a_recall_modelo_vs_baselines.png")


def figura_b_delta_ic(delta: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    erro = [
        (delta["observado"] - delta["ic_baixo"]).to_numpy() * 100,
        (delta["ic_alto"] - delta["observado"]).to_numpy() * 100,
    ]
    cores = [
        "#2ca02c" if lo > 0 else ("#d62728" if hi < 0 else "#999999")
        for lo, hi in zip(delta["ic_baixo"], delta["ic_alto"])
    ]
    x = list(range(len(delta)))
    ax.bar(x, delta["observado"] * 100, color=cores, yerr=erro, capsize=5)
    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"K={k}\nvs {b}" for k, b in zip(delta["k"], delta["melhor_baseline"])], fontsize=8)
    ax.set_ylabel("Delta Recall@K (pontos percentuais)")
    ax.set_title("B. Ganho sobre o melhor baseline (verde: IC>0; vermelho: IC<0; cinza: IC cruza zero)")
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "evidence_b_delta_vs_baseline_ic.png")


def figura_c_por_ano(por_ano: pd.DataFrame) -> Path:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    largura = 0.35
    x = list(range(len(por_ano)))
    rotulos = [f"{int(a)}\n(n={int(n)})" for a, n in zip(por_ano["inicio_ano"], por_ano["n_episodios"])]

    for ax, k in ((ax1, 5), (ax2, 10)):
        ax.bar(
            [i - largura / 2 for i in x],
            por_ano[f"recall{k}_modelo"] * 100,
            largura,
            label="modelo",
            color=CORES_METODO["modelo"],
        )
        ax.bar(
            [i + largura / 2 for i in x],
            por_ano[f"recall{k}_melhor_baseline"] * 100,
            largura,
            label="melhor baseline",
            color=CORES_METODO["razao_historica_local"],
        )
        ax.set_xticks(x)
        ax.set_xticklabels(rotulos)
        ax.set_ylabel(f"Recall@{k} (%)")
        ax.set_title(f"Recall@{k} por ano")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, axis="y")

    fig.suptitle("C. Desempenho por ano de inicio do episodio (N sempre explicito)")
    return _salvar(fig, "evidence_c_por_ano.png")


def figura_d_por_rpa(por_rpa: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    x = list(range(len(por_rpa)))
    largura = 0.27
    ax.bar([i - largura for i in x], por_rpa["recall5_modelo"] * 100, largura, label="Recall@5")
    ax.bar(x, por_rpa["recall10_modelo"] * 100, largura, label="Recall@10")
    ax.bar([i + largura for i in x], por_rpa["recall20_modelo"] * 100, largura, label="Recall@20")
    ax.set_xticks(x)
    ax.set_xticklabels([f"RPA {r}\n(n={int(n)})" for r, n in zip(por_rpa["codigo_rpa"], por_rpa["n_episodios"])])
    ax.set_ylabel("Recall (%)")
    ax.set_title("D. Desempenho territorial por RPA (modelo) - rotulo = n de episodios")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "evidence_d_por_rpa.png")


def figura_e_lead_time(master: pd.DataFrame, resumo: dict) -> Path:
    leads = master.loc[master["detectado_modelo_k10"] == 1, "lead_modelo"].dropna()
    fig, ax = plt.subplots(figsize=(8, 5))
    valores = sorted(leads.unique())
    contagens = [int((leads == v).sum()) for v in valores]
    ax.bar([str(int(v)) for v in valores], contagens, color=CORES_METODO["modelo"])
    total = len(leads)
    for i, c in enumerate(contagens):
        ax.text(i, c, f"{c}\n({c / total * 100:.1f}%)", ha="center", va="bottom", fontsize=8)
    lead = resumo["lead_time_k10"]
    mediana = lead["mediana_ic"]
    pct2 = lead["pct_>=2_semanas"]
    ax.set_xlabel("Semanas de antecedencia (nunca a propria semana de inicio)")
    ax.set_ylabel("Episodios detectados no Top-10")
    ax.set_title(
        f"E. Lead time (n={total}) - mediana {mediana['observado']:.0f} sem. "
        f"[IC {mediana['ic_baixo']:.0f}-{mediana['ic_alto']:.0f}], >=2 sem.: {pct2:.1f}%"
    )
    ax.set_ylim(0, max(contagens) * 1.18)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "evidence_e_lead_time.png")


def figura_f_grandes_episodios(resumo: dict) -> Path:
    g = resumo["grandes_episodios"]
    fig, ax = plt.subplots(figsize=(8, 5))
    x = [0, 1]
    largura = 0.35
    for desloc, grupo, cor, rotulo in [
        (-largura / 2, "grandes", "#d62728", f"grandes episodios (n={g['n']})"),
        (largura / 2, "todos", CORES_METODO["modelo"], f"todos (n={g['recall5_todos']['n']})"),
    ]:
        obs = [g[f"recall{k}_{grupo}"]["observado"] * 100 for k in (5, 10)]
        erro = [
            [(g[f"recall{k}_{grupo}"]["observado"] - g[f"recall{k}_{grupo}"]["ic_baixo"]) * 100 for k in (5, 10)],
            [(g[f"recall{k}_{grupo}"]["ic_alto"] - g[f"recall{k}_{grupo}"]["observado"]) * 100 for k in (5, 10)],
        ]
        ax.bar([i + desloc for i in x], obs, largura, yerr=erro, capsize=5, color=cor, label=rotulo)
    ax.set_xticks(x)
    ax.set_xticklabels(["Recall@5", "Recall@10"])
    ax.set_ylabel("Recall (%)")
    ax.set_title("F. Grandes episodios (top 10% por casos) x todos os episodios (IC 95%)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "evidence_f_grandes_episodios.png")


def figura_g_genuino_vs_recaida(resumo: dict) -> Path:
    gr = resumo["genuino_vs_recaida"]
    ks = (5, 10, 20)
    fig, ax = plt.subplots(figsize=(8, 5))
    x = list(range(len(ks)))
    largura = 0.35
    for desloc, grupo, cor, rotulo in [
        (-largura / 2, "genuino", "#9467bd", f"antecipacao genuina (n={gr['n_genuinos']})"),
        (largura / 2, "recaida", "#8c564b", f"recaida (n={gr['n_recaidas']})"),
    ]:
        obs = [gr[f"recall{k}_{grupo}"]["observado"] * 100 for k in ks]
        erro = [
            [(gr[f"recall{k}_{grupo}"]["observado"] - gr[f"recall{k}_{grupo}"]["ic_baixo"]) * 100 for k in ks],
            [(gr[f"recall{k}_{grupo}"]["ic_alto"] - gr[f"recall{k}_{grupo}"]["observado"]) * 100 for k in ks],
        ]
        ax.bar([i + desloc for i in x], obs, largura, yerr=erro, capsize=5, color=cor, label=rotulo)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Recall@{k}" for k in ks])
    ax.set_ylabel("Recall (%)")
    ax.set_title("G. Antecipacao genuina x recaida - o cenario mais comum e o mais dificil")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "evidence_g_genuino_vs_recaida.png")


def figura_h_estabilidade(serie: pd.DataFrame, resumo: dict) -> Path:
    estab = resumo["estabilidade_top10"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), gridspec_kw={"width_ratios": [2, 1]})
    ax1.plot(serie["indice_semana_alvo"], serie["jaccard"], color=CORES_METODO["modelo"], linewidth=1)
    ax1.axhline(estab["jaccard_medio"], color="#d62728", linestyle="--", label=f"media {estab['jaccard_medio']:.2f}")
    ax1.set_xlabel("Indice de semana global")
    ax1.set_ylabel("Jaccard do Top-10 (semana t x t+1)")
    ax1.set_title(f"Serie semanal (n={len(serie)} pares consecutivos)")
    ax1.set_ylim(0, 1)
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)
    ax2.hist(serie["jaccard"], bins=12, color=CORES_METODO["modelo"])
    ax2.axvline(estab["jaccard_mediano"], color="#d62728", linestyle="--", label=f"mediana {estab['jaccard_mediano']:.2f}")
    ax2.set_xlabel("Jaccard")
    ax2.set_ylabel("Pares de semanas")
    ax2.set_title("Distribuicao")
    ax2.legend(fontsize=8)
    fig.suptitle("H. Estabilidade do Top-10 entre semanas consecutivas (0 = troca total, 1 = identico)")
    return _salvar(fig, "evidence_h_estabilidade_top10.png")


def figura_i_por_bairro(por_bairro: pd.DataFrame) -> Path:
    df = por_bairro[por_bairro["n_episodios"] >= 3].sort_values("recall10_modelo")
    fig, ax = plt.subplots(figsize=(9, max(5.0, len(df) * 0.16)))
    cores = ["#d62728" if v == 0 else CORES_METODO["modelo"] for v in df["recall10_modelo"]]
    ax.barh(
        [f"{n} (n={int(e)})" for n, e in zip(df["nome_bairro"], df["n_episodios"])],
        df["recall10_modelo"] * 100,
        color=cores,
    )
    ax.set_xlabel("Recall@10 (%)")
    ax.set_title("I. Recall@10 por bairro (>=3 episodios) - vermelho = nenhuma deteccao")
    ax.tick_params(axis="y", labelsize=6)
    ax.grid(alpha=0.3, axis="x")
    return _salvar(fig, "evidence_i_por_bairro.png")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
    artefatos = carregar_artefatos_evidencia(PASTA_RELATORIO)
    resumo = artefatos["resumo"]
    if resumo is None:
        logger.error("Artefatos ausentes. Rode 'python -m src.validate_dengue_onset_ranking_evidence' primeiro.")
        return 1

    caminho_serie = PASTA_RELATORIO / "evidence_estabilidade_top10_semanal.csv"
    serie_jaccard = pd.read_csv(caminho_serie) if caminho_serie.exists() else pd.DataFrame()

    figuras = [
        figura_a_recall_por_metodo(artefatos["recall_ic"]),
        figura_b_delta_ic(artefatos["delta_vs_baseline"]),
        figura_c_por_ano(artefatos["por_ano"]),
        figura_d_por_rpa(artefatos["por_rpa"]),
        figura_e_lead_time(artefatos["master_episodios"], resumo),
        figura_f_grandes_episodios(resumo),
        figura_g_genuino_vs_recaida(resumo),
        figura_i_por_bairro(artefatos["por_bairro"]),
    ]
    if not serie_jaccard.empty:
        figuras.append(figura_h_estabilidade(serie_jaccard, resumo))
    else:
        logger.warning("Serie semanal de Jaccard ausente - figura H nao gerada.")

    logger.info("%d figuras geradas em %s", len(figuras), PASTA_RELATORIO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
