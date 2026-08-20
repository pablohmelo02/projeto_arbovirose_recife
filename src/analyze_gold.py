"""Profiling e visualizações de validação da Gold `gold_arboviroses_clima_bairro`.

Uso:
    python -m src.analyze_gold

Lê a Gold já persistida no MinIO (rode `python -m src.transform_gold_arboviroses_clima`
antes) e grava em `reports/gold_analysis/`: profiling em JSON/CSV e os
gráficos de validação (PNG). **Não é dashboard nem EDA completa** — é a
validação mínima de que a Gold representa os dados reais (ver
`reports/gold_analysis/README.md` gerado por este script).

Separado da transformação de propósito: nenhuma função de
`src/gold/arboviroses_clima.py` importa matplotlib nem sabe que gráficos
existem.
"""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")  # backend não-interativo: só gera arquivo, nunca abre janela
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.clients.minio_client import MinioClient, MinioClientError  # noqa: E402
from src.config import load_config  # noqa: E402
from src.gold.pipeline_gold_arboviroses_clima import (  # noqa: E402
    CHAVE_BAIRRO_GEO,
    PREFIXO_GOLD_ARBOVIROSES_CLIMA,
)
from src.gold.profiling_gold import (  # noqa: E402
    calcular_cobertura_temporal,
    calcular_metricas_por_bairro,
    perfilar_gold,
)

PASTA_RELATORIOS = Path("reports") / "gold_analysis"

CORES_AGRAVO = {"DENGUE": "#c0392b", "ZIKA": "#2980b9", "CHIKUNGUNYA": "#f39c12"}


def _configurar_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)


def _eixo_tempo(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["semana_epi_data_inicio"])


def grafico_cobertura_temporal(df_gold: pd.DataFrame, cobertura: pd.DataFrame, destino: Path) -> None:
    """(A) Cobertura temporal: quais semanas têm caso notificado, quais têm
    clima real, e onde as duas coisas se sobrepõem (a interseção Gold)."""
    fig, ax = plt.subplots(figsize=(14, 4))
    tempo = _eixo_tempo(cobertura)

    tem_epi = cobertura["casos"] > 0
    tem_clima = cobertura["linhas_com_clima_real"] > 0

    ax.fill_between(tempo, 0, 1, where=tem_epi, color="#c0392b", alpha=0.35, step="mid", label="Arboviroses (semana com caso)")
    ax.fill_between(tempo, 1, 2, where=tem_clima, color="#2980b9", alpha=0.35, step="mid", label="Clima (semana com leitura real)")
    ax.fill_between(tempo, 2, 3, where=tem_epi & tem_clima, color="#27ae60", alpha=0.6, step="mid", label="Interseção (Gold utilizável)")

    ax.set_yticks([0.5, 1.5, 2.5])
    ax.set_yticklabels(["Arboviroses", "Clima", "Interseção"])
    ax.set_ylim(0, 3)
    ax.set_xlabel("Semana epidemiológica (data de início)")
    ax.set_title("(A) Cobertura temporal por domínio — Gold arboviroses × clima")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(destino, dpi=120)
    plt.close(fig)


def grafico_casos_por_agravo(df_gold: pd.DataFrame, destino: Path) -> None:
    """(B) Série temporal de casos, uma linha por agravo."""
    por_agravo = (
        df_gold.groupby(["agravo", "ano_epidemiologico", "semana_epidemiologica"])
        .agg(casos=("casos", "sum"), semana_epi_data_inicio=("semana_epi_data_inicio", "first"))
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(14, 5))
    for agravo, grupo in por_agravo.groupby("agravo"):
        grupo = grupo.sort_values("semana_epi_data_inicio")
        ax.plot(
            pd.to_datetime(grupo["semana_epi_data_inicio"]), grupo["casos"],
            label=agravo, color=CORES_AGRAVO.get(agravo), linewidth=1.2,
        )
    ax.set_xlabel("Semana epidemiológica (data de início)")
    ax.set_ylabel("Casos notificados")
    ax.set_title("(B) Casos por semana epidemiológica e agravo — Recife")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(destino, dpi=120)
    plt.close(fig)


def grafico_precipitacao(cobertura: pd.DataFrame, destino: Path) -> None:
    """(C) Série temporal da precipitação no mesmo grão da Gold. Só desenha
    onde há dado real — nunca preenche lacuna com zero."""
    com_clima = cobertura[cobertura["linhas_com_clima_real"] > 0]

    fig, ax = plt.subplots(figsize=(14, 4))
    if com_clima.empty:
        ax.text(
            0.5, 0.5,
            "Nenhuma semana da Gold tem precipitação real\n"
            "(ver limitação de cobertura temporal no relatório)",
            ha="center", va="center", transform=ax.transAxes, fontsize=12, color="#7f8c8d",
        )
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        ax.bar(
            _eixo_tempo(com_clima), com_clima["precipitacao_media_mm"],
            width=5, color="#2980b9", alpha=0.8,
        )
        ax.set_ylabel("Precipitação média semanal (mm)")
        ax.grid(alpha=0.3)
    ax.set_xlabel("Semana epidemiológica (data de início)")
    ax.set_title("(C) Precipitação por semana epidemiológica (média entre bairros, só dado real)")
    fig.tight_layout()
    fig.savefig(destino, dpi=120)
    plt.close(fig)


def grafico_casos_vs_precipitacao(cobertura: pd.DataFrame, destino: Path) -> None:
    """(D) Casos × precipitação, duas séries no mesmo eixo temporal.
    Exploratório — não implica causalidade."""
    fig, ax_casos = plt.subplots(figsize=(14, 5))
    tempo = _eixo_tempo(cobertura)

    ax_casos.plot(tempo, cobertura["casos"], color="#c0392b", linewidth=1.2, label="Casos (todos os agravos)")
    ax_casos.set_xlabel("Semana epidemiológica (data de início)")
    ax_casos.set_ylabel("Casos notificados", color="#c0392b")
    ax_casos.tick_params(axis="y", labelcolor="#c0392b")
    ax_casos.grid(alpha=0.3)

    ax_chuva = ax_casos.twinx()
    com_clima = cobertura[cobertura["linhas_com_clima_real"] > 0]
    if not com_clima.empty:
        ax_chuva.bar(
            _eixo_tempo(com_clima), com_clima["precipitacao_media_mm"],
            width=5, color="#2980b9", alpha=0.5, label="Precipitação média (mm)",
        )
    ax_chuva.set_ylabel("Precipitação média semanal (mm)", color="#2980b9")
    ax_chuva.tick_params(axis="y", labelcolor="#2980b9")

    titulo = "(D) Casos × precipitação por semana epidemiológica (exploratório — não implica causalidade)"
    if com_clima.empty:
        titulo += "\n[sem sobreposição temporal real entre clima e casos nesta execução]"
    ax_casos.set_title(titulo, fontsize=10)
    fig.tight_layout()
    fig.savefig(destino, dpi=120)
    plt.close(fig)


def grafico_mapa_casos_por_bairro(
    gdf_bairros: gpd.GeoDataFrame, por_bairro: pd.DataFrame, destino: Path
) -> None:
    """(E) Distribuição espacial: mapa coroplético de casos totais por bairro,
    usando a geometria real de `silver_bairro_geo`."""
    gdf = gdf_bairros.merge(por_bairro[["codigo_bairro", "casos_total"]], on="codigo_bairro", how="left")

    fig, ax = plt.subplots(figsize=(9, 9))
    gdf.plot(
        column="casos_total", cmap="OrRd", linewidth=0.4, edgecolor="#555555",
        legend=True, ax=ax, missing_kwds={"color": "#eeeeee", "label": "sem dado"},
        legend_kwds={"label": "Casos notificados (total do período)", "shrink": 0.6},
    )
    ax.set_title("(E) Casos de arboviroses por bairro — Recife (total do período da Gold)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(destino, dpi=120)
    plt.close(fig)


def grafico_completude(perfil: dict, destino: Path) -> None:
    """(F) Completude das variáveis principais da Gold."""
    campos = [
        "casos", "area_km2", "fonte_clima", "codigo_estacao_clima",
        "precipitacao_total_semana_mm", "dias_com_dado_valido_semana",
        "chuva_7d_mm", "chuva_28d_mm",
    ]
    presentes = [
        (campo, 100 - perfil["missing_por_campo"][campo]["percentual_null"])
        for campo in campos
        if campo in perfil["missing_por_campo"]
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    nomes = [c for c, _ in presentes]
    valores = [v for _, v in presentes]
    cores = ["#27ae60" if v > 99 else "#f39c12" if v > 1 else "#c0392b" for v in valores]
    ax.barh(nomes, valores, color=cores)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% de linhas preenchidas (não nulas)")
    ax.set_title("(F) Completude das principais variáveis da Gold")
    for i, valor in enumerate(valores):
        ax.text(min(valor + 1, 95), i, f"{valor:.2f}%", va="center", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(destino, dpi=120)
    plt.close(fig)


def main() -> int:
    _configurar_logging()
    logger = logging.getLogger(__name__)

    try:
        config = load_config()
    except RuntimeError as exc:
        logger.error("Erro de configuração: %s", exc)
        return 1

    minio_client = MinioClient(
        endpoint=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket=config.minio_bucket,
    )

    try:
        conteudo_gold = minio_client.download_bytes(
            f"{PREFIXO_GOLD_ARBOVIROSES_CLIMA}/gold_arboviroses_clima_bairro.parquet"
        )
        conteudo_bairros = minio_client.download_bytes(CHAVE_BAIRRO_GEO)
    except MinioClientError as exc:
        logger.error(
            "%s — rode 'python -m src.transform_gold_arboviroses_clima' antes de analisar a Gold.", exc
        )
        return 1

    df_gold = pd.read_parquet(io.BytesIO(conteudo_gold))
    gdf_bairros = gpd.read_parquet(io.BytesIO(conteudo_bairros))

    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)

    perfil = perfilar_gold(df_gold)
    cobertura = calcular_cobertura_temporal(df_gold)
    por_bairro = calcular_metricas_por_bairro(df_gold)

    (PASTA_RELATORIOS / "profiling.json").write_text(
        json.dumps(perfil, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    cobertura.to_csv(PASTA_RELATORIOS / "cobertura_temporal.csv", index=False, encoding="utf-8")
    por_bairro.to_csv(PASTA_RELATORIOS / "metricas_por_bairro.csv", index=False, encoding="utf-8")

    grafico_cobertura_temporal(df_gold, cobertura, PASTA_RELATORIOS / "a_cobertura_temporal.png")
    grafico_casos_por_agravo(df_gold, PASTA_RELATORIOS / "b_casos_por_agravo.png")
    grafico_precipitacao(cobertura, PASTA_RELATORIOS / "c_precipitacao.png")
    grafico_casos_vs_precipitacao(cobertura, PASTA_RELATORIOS / "d_casos_vs_precipitacao.png")
    grafico_mapa_casos_por_bairro(gdf_bairros, por_bairro, PASTA_RELATORIOS / "e_mapa_casos_por_bairro.png")
    grafico_completude(perfil, PASTA_RELATORIOS / "f_completude.png")

    logger.info("Relatórios e gráficos salvos em %s", PASTA_RELATORIOS.resolve())
    logger.info(
        "Gold: %d linhas | %d bairros | %d agravos | %d-%d | chave duplicada: %d",
        perfil["total_linhas"], perfil["total_bairros"], perfil["total_agravos"],
        perfil["ano_epidemiologico_min"], perfil["ano_epidemiologico_max"],
        perfil["chave_gold_duplicadas"],
    )
    logger.info(
        "Casos: %d total (%.2f%% das linhas com ao menos 1) | Clima real: %.4f%% das linhas",
        perfil["casos"]["total"], perfil["casos"]["percentual_linhas_com_caso"],
        perfil["clima"]["percentual_linhas_com_clima_real"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
