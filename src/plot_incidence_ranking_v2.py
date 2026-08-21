"""Visualizações (PNG) do experimento V2 (onset/ranking por incidência).

Mesmo padrão de `src/plot_evidence_validation.py`: não recalcula nada, só
lê `reports/ml/resultado_incidence_v2_completo.json` + os CSVs já salvos
por `src/experiment_incidence_ranking_v2.py` e desenha.

Uso:
    python -m src.plot_incidence_ranking_v2
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RELATORIO = RAIZ / "reports" / "ml"
CAMINHO_RESULTADO = PASTA_RELATORIO / "resultado_incidence_v2_completo.json"

NOME_V2_PRINCIPAL = "v2_casos_incidencia"

CORES = {
    "v1": "#7f7f7f",
    "v2_incidencia": "#ff7f0e",
    "v2_casos_incidencia": "#1f77b4",
    "baseline": "#2ca02c",
}


def _salvar(fig, nome: str) -> Path:
    caminho = PASTA_RELATORIO / nome
    fig.tight_layout()
    fig.savefig(caminho, dpi=130)
    plt.close(fig)
    logger.info("Figura salva: %s", caminho.name)
    return caminho


def figura_1_v1_vs_v2_recall(recall_ic: pd.DataFrame, evidencia_v1: dict) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    v1_recall = pd.DataFrame(evidencia_v1["recall_ic"])
    v1_modelo = v1_recall[v1_recall["metodo"] == "modelo"].sort_values("k")
    ax.errorbar(
        v1_modelo["k"], v1_modelo["observado"] * 100,
        yerr=[
            (v1_modelo["observado"] - v1_modelo["ic_baixo"]) * 100,
            (v1_modelo["ic_alto"] - v1_modelo["observado"]) * 100,
        ],
        marker="o", capsize=4, label="V1 (casos)", color=CORES["v1"], linewidth=2,
    )
    for variante, cor in [("v2_incidencia", CORES["v2_incidencia"]), (NOME_V2_PRINCIPAL, CORES["v2_casos_incidencia"])]:
        sub = recall_ic[recall_ic["metodo"] == variante].sort_values("k")
        ax.errorbar(
            sub["k"], sub["observado"] * 100,
            yerr=[(sub["observado"] - sub["ic_baixo"]) * 100, (sub["ic_alto"] - sub["observado"]) * 100],
            marker="o", capsize=4, label=variante, color=cor, linewidth=2,
        )
    ax.set_xlabel("K (bairros priorizados por semana)")
    ax.set_ylabel("Recall@K por episódio (%)")
    ax.set_title("1. V1 x V2: Recall@K (IC 95%, bootstrap por episódio)")
    ax.set_xticks(sorted(recall_ic["k"].unique()))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    return _salvar(fig, "incidence_v2_fig01_v1_vs_v2_recall.png")


def figura_2_v2_vs_baselines_incidencia(recall_ic: pd.DataFrame) -> Path:
    metodos = [NOME_V2_PRINCIPAL, "incidencia_atual", "crescimento_incidencia", "razao_historica_incidencia"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for metodo in metodos:
        sub = recall_ic[recall_ic["metodo"] == metodo].sort_values("k")
        if sub.empty:
            continue
        cor = CORES["v2_casos_incidencia"] if metodo == NOME_V2_PRINCIPAL else None
        ax.errorbar(
            sub["k"], sub["observado"] * 100,
            yerr=[(sub["observado"] - sub["ic_baixo"]) * 100, (sub["ic_alto"] - sub["observado"]) * 100],
            marker="o", capsize=4, label=metodo, color=cor,
            linewidth=2.4 if metodo == NOME_V2_PRINCIPAL else 1.2,
        )
    ax.set_xlabel("K")
    ax.set_ylabel("Recall@K por episódio (%)")
    ax.set_title("2. V2 x baselines de incidência (IC 95%)")
    ax.set_xticks(sorted(recall_ic["k"].unique()))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    return _salvar(fig, "incidence_v2_fig02_v2_vs_baselines_incidencia.png")


def figura_3_delta_recall5_ic(delta: pd.DataFrame) -> Path:
    sub = delta.sort_values("k")
    fig, ax = plt.subplots(figsize=(8, 5))
    erro = [
        (sub["observado"] - sub["ic_baixo"]).to_numpy() * 100,
        (sub["ic_alto"] - sub["observado"]).to_numpy() * 100,
    ]
    cores = ["#2ca02c" if lo > 0 else ("#d62728" if hi < 0 else "#999999") for lo, hi in zip(sub["ic_baixo"], sub["ic_alto"])]
    ax.bar(sub["k"].astype(str), sub["observado"] * 100, color=cores, yerr=erro, capsize=5)
    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("K")
    ax.set_ylabel(f"Delta Recall@K: {NOME_V2_PRINCIPAL} - melhor baseline (pp)")
    ax.set_title("3. Delta V2 - melhor baseline, por K (IC 95%)")
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig03_delta_vs_baseline.png")


def figura_4_target_v1_x_v2(sobreposicao: dict) -> Path:
    fig, ax = plt.subplots(figsize=(7, 5))
    categorias = ["Só V1\n(casos)", "Em comum", "Só V2\n(incidência)"]
    valores = [
        sobreposicao["n_somente_v1"],
        sobreposicao["n_em_comum"],
        sobreposicao["n_somente_v2"],
    ]
    ax.bar(categorias, valores, color=[CORES["v1"], "#9467bd", CORES["v2_casos_incidencia"]])
    for i, v in enumerate(valores):
        ax.text(i, v, str(v), ha="center", va="bottom")
    ax.set_ylabel("N de episódios (teste 2023-2025)")
    ax.set_title(f"4. Episódios V1 x V2 — Jaccard = {sobreposicao['jaccard']:.2f}")
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig04_target_v1_x_v2.png")


def figura_5_desempenho_por_ano(por_ano: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    x = list(range(len(por_ano)))
    largura = 0.35
    ax.bar(
        [i - largura / 2 for i in x], por_ano[f"detectado_{NOME_V2_PRINCIPAL}_k5"] * 100,
        largura, label="Recall@5", color=CORES["v2_casos_incidencia"],
    )
    ax.bar(
        [i + largura / 2 for i in x], por_ano[f"detectado_{NOME_V2_PRINCIPAL}_k10"] * 100,
        largura, label="Recall@10", color=CORES["v2_incidencia"],
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(a)}\n(n={int(n)})" for a, n in zip(por_ano["inicio_ano"], por_ano["n_episodios"])])
    ax.set_ylabel("Recall (%)")
    ax.set_title(f"5. Desempenho por ano — {NOME_V2_PRINCIPAL}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig05_por_ano.png")


def figura_6_desempenho_por_rpa(por_rpa: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    x = list(range(len(por_rpa)))
    largura = 0.27
    ax.bar([i - largura for i in x], por_rpa[f"detectado_{NOME_V2_PRINCIPAL}_k5"] * 100, largura, label="Recall@5")
    ax.bar(x, por_rpa[f"detectado_{NOME_V2_PRINCIPAL}_k10"] * 100, largura, label="Recall@10")
    ax.bar([i + largura for i in x], por_rpa[f"detectado_{NOME_V2_PRINCIPAL}_k20"] * 100, largura, label="Recall@20")
    ax.set_xticks(x)
    ax.set_xticklabels([f"RPA {r}\n(n={int(n)})" for r, n in zip(por_rpa["codigo_rpa"], por_rpa["n_episodios"])])
    ax.set_ylabel("Recall (%)")
    ax.set_title(f"6. Desempenho territorial por RPA — {NOME_V2_PRINCIPAL}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig06_por_rpa.png")


def figura_7_bairros_pequenos(resultado: dict) -> Path:
    bp = resultado["bairros_pequenos"]
    fig, ax = plt.subplots(figsize=(7, 5))
    categorias = ["Incidência\nsemanal", "Incidência\nmóvel 4 sem."]
    pequenos = [bp["eventos_incidencia_semanal_pequenos"], bp["eventos_incidencia_4s_pequenos"]]
    grandes = [bp["eventos_incidencia_semanal_grandes"], bp["eventos_incidencia_4s_grandes"]]
    x = list(range(len(categorias)))
    largura = 0.35
    ax.bar([i - largura / 2 for i in x], pequenos, largura, label=f"Bairros pequenos (n={bp['n_bairros_pequenos']})", color="#d62728")
    ax.bar([i + largura / 2 for i in x], grandes, largura, label="Demais bairros", color=CORES["v2_casos_incidencia"])
    ax.set_xticks(x)
    ax.set_xticklabels(categorias)
    ax.set_ylabel("N de semanas em estado de risco elevado")
    ax.set_title("7. Bairros pequenos: incidência semanal x móvel de 4 semanas")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig07_bairros_pequenos.png")


def figura_8_onset_genuino(resultado: dict) -> Path:
    gr = resultado["genuino_vs_recaida"]
    fig, ax = plt.subplots(figsize=(7, 5))
    grupos = ["Antecipação\ngenuína", "Recaída"]
    ns = [gr["n_genuinos"], gr["n_recaidas"]]
    obs = [gr["recall10_genuino"]["observado"] * 100]
    obs.append(gr["recall10_recaida"]["observado"] * 100 if gr["recall10_recaida"] else 0)
    erro_baixo = [
        (gr["recall10_genuino"]["observado"] - gr["recall10_genuino"]["ic_baixo"]) * 100,
        (gr["recall10_recaida"]["observado"] - gr["recall10_recaida"]["ic_baixo"]) * 100 if gr["recall10_recaida"] else 0,
    ]
    erro_alto = [
        (gr["recall10_genuino"]["ic_alto"] - gr["recall10_genuino"]["observado"]) * 100,
        (gr["recall10_recaida"]["ic_alto"] - gr["recall10_recaida"]["observado"]) * 100 if gr["recall10_recaida"] else 0,
    ]
    cores = ["#9467bd", "#8c564b"]
    ax.bar([f"{g}\n(n={n})" for g, n in zip(grupos, ns)], obs, yerr=[erro_baixo, erro_alto], capsize=5, color=cores)
    ax.set_ylabel(f"Recall@10 — {NOME_V2_PRINCIPAL} (%)")
    ax.set_title("8. Antecipação genuína x recaída (IC 95%)")
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig08_onset_genuino.png")


def figura_9_grandes_episodios(resultado: dict) -> Path:
    ge = resultado["grandes_episodios"]
    fig, ax = plt.subplots(figsize=(7, 5))
    ks = ["Recall@5", "Recall@10"]
    obs = [ge["recall5"]["observado"] * 100, ge["recall10"]["observado"] * 100]
    erro_baixo = [(ge["recall5"]["observado"] - ge["recall5"]["ic_baixo"]) * 100, (ge["recall10"]["observado"] - ge["recall10"]["ic_baixo"]) * 100]
    erro_alto = [(ge["recall5"]["ic_alto"] - ge["recall5"]["observado"]) * 100, (ge["recall10"]["ic_alto"] - ge["recall10"]["observado"]) * 100]
    ax.bar(ks, obs, yerr=[erro_baixo, erro_alto], capsize=5, color="#d62728")
    ax.set_ylabel(f"Recall — {NOME_V2_PRINCIPAL} (%)")
    ax.set_title(f"9. Grandes episódios (top 10% por casos, n={ge['n']})")
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig09_grandes_episodios.png")


def figura_10_estabilidade(resultado: dict) -> Path:
    estab = resultado["estabilidade_top10"]
    fig, ax = plt.subplots(figsize=(8, 5))
    variantes = list(estab.keys())
    medias = [estab[v]["jaccard_medio"] if estab[v]["jaccard_medio"] is not None else 0 for v in variantes]
    cores = [CORES["v2_casos_incidencia"] if v == NOME_V2_PRINCIPAL else "#999999" for v in variantes]
    ax.bar(variantes, medias, color=cores)
    ax.set_ylabel("Jaccard médio do Top-10 (semanas consecutivas)")
    ax.set_title("10. Estabilidade do ranking por variante")
    ax.set_ylim(0, 1)
    ax.tick_params(axis="x", labelrotation=25)
    ax.grid(alpha=0.3, axis="y")
    return _salvar(fig, "incidence_v2_fig10_estabilidade.png")


def figura_11_sensibilidade_populacional(sensibilidade_b_csv: pd.DataFrame, resultado: dict) -> Path:
    sb = resultado["sensibilidade_b"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(sensibilidade_b_csv["recall5"].dropna() * 100, bins=10, color=CORES["v2_casos_incidencia"])
    ax.axvline(
        sb["recall5_sem_perturbacao"] * 100, color="#d62728", linestyle="--",
        label=f"sem perturbação: {sb['recall5_sem_perturbacao'] * 100:.1f}%",
    )
    ax.set_xlabel("Recall@5 sob população perturbada (%)")
    ax.set_ylabel(f"Réplicas (n={sb['n_replicas']})")
    ax.set_title("11. Sensibilidade populacional B — perturbação com erro real de reconstrução")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return _salvar(fig, "incidence_v2_fig11_sensibilidade_populacional.png")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)

    if not CAMINHO_RESULTADO.exists():
        logger.error("'%s' ausente. Rode 'python -m src.experiment_incidence_ranking_v2' primeiro.", CAMINHO_RESULTADO)
        return 1

    with open(CAMINHO_RESULTADO, encoding="utf-8") as f:
        resultado = json.load(f)

    recall_ic = pd.DataFrame(resultado["recall_ic"])
    delta = pd.DataFrame(resultado["delta_v2_vs_melhor_baseline"])
    por_ano = pd.read_csv(PASTA_RELATORIO / "incidence_v2_master_episodios.csv").groupby("inicio_ano").agg(
        n_episodios=("codigo_bairro", "size"),
        **{f"detectado_{NOME_V2_PRINCIPAL}_k5": (f"detectado_{NOME_V2_PRINCIPAL}_k5", "mean")},
        **{f"detectado_{NOME_V2_PRINCIPAL}_k10": (f"detectado_{NOME_V2_PRINCIPAL}_k10", "mean")},
    ).reset_index()
    por_rpa = pd.read_csv(PASTA_RELATORIO / "incidence_v2_por_rpa.csv")
    sensibilidade_b_csv = pd.read_csv(PASTA_RELATORIO / "incidence_v2_sensibilidade_b_replicas.csv")

    figuras = [
        figura_1_v1_vs_v2_recall(recall_ic, resultado["v1_evidencia_publicada"]),
        figura_2_v2_vs_baselines_incidencia(recall_ic),
        figura_3_delta_recall5_ic(delta[delta["k"] == 5]),
        figura_4_target_v1_x_v2(resultado["sobreposicao_episodios"]),
        figura_5_desempenho_por_ano(por_ano),
        figura_6_desempenho_por_rpa(por_rpa),
        figura_7_bairros_pequenos(resultado),
        figura_8_onset_genuino(resultado),
        figura_9_grandes_episodios(resultado),
        figura_10_estabilidade(resultado),
        figura_11_sensibilidade_populacional(sensibilidade_b_csv, resultado),
    ]
    logger.info("%d figuras geradas em %s", len(figuras), PASTA_RELATORIO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
