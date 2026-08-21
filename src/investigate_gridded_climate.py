"""Investigação controlada de fontes climáticas em GRADE para o período
2013-2025 — a lacuna que nenhuma rede de estações do projeto cobre.

Uso:
    python -m src.investigate_gridded_climate

Esta é uma etapa de **investigação**, não de incorporação: ela mede a
acessibilidade real das fontes candidatas e valida a candidata escolhida
contra o CEMADEN no período em que os dois existem (2024-2025), gravando
tudo em `reports/climate_source_analysis/`. Nada é gravado na Silver/Gold
aqui — a incorporação é uma etapa separada
(`python -m src.ingest_climate_grade` / `transform_gold_arboviroses_clima`),
condicionada ao resultado desta.

## Candidatas e por que a escolha caiu onde caiu (medido, não presumido)

- **ERA5 / ERA5-Land via Open-Meteo Archive** — HTTP público, sem chave,
  série diária 2013-2025 completa em ~2 s por requisição multi-ponto.
  Escolhida.
- **ERA5-Land via CDS (Copernicus) direto** — exige credencial de conta
  (`.cdsapirc`); nenhuma disponível neste ambiente. Não testável aqui.
- **CHIRPS (0,05°)** — diretório público acessível
  (`data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/`), mas o
  produto é GeoTIFF global diário: ~4.700 arquivos para 2013-2025 e
  dependência de leitura raster (GDAL/rasterio), ecossistema pesado que o
  projeto evita deliberadamente. Descartada por custo de ingestão, não por
  qualidade.
- **NASA POWER** — HTTP público sem chave, funciona; resolução
  0,5° × 0,625° (~55 × 70 km), pior que ERA5 para uma cidade de ~0,19° de
  extensão. Descartada por resolução.

## Critério de decisão desta investigação

A fonte em grade só é recomendada se, no período sobreposto com o CEMADEN,
ela reproduzir o **sinal temporal** de chuva com correlação materialmente
positiva. Ela NÃO é avaliada pela capacidade de distinguir bairros — e não
poderia ser: a grade resolve poucas células para os 94 bairros (número
medido e reportado aqui). Essa limitação é a conclusão principal, não uma
ressalva de rodapé.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.clients.gridded_climate_client import (
    MODELO_PRECIPITACAO,
    MODELO_TEMPERATURA,
    VARIAVEIS_PRECIPITACAO,
    VARIAVEIS_TEMPERATURA,
    GriddedClimateClientError,
    OpenMeteoArchiveClient,
)
from src.gold.clima_grade import calcular_features_clima_grade
from src.logging_config import configurar_logging
from src.silver.climate_grade import (
    extrair_series_diarias_grade,
    identificador_celula,
    montar_mapeamento_bairro_celula,
    normalizar_clima_grade_diario,
)
from src.silver.schema_climate_grade import (
    GRADE_PRECIPITACAO,
    GRADE_TEMPERATURA,
    RESOLUCAO_GRAUS_POR_GRADE,
)

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
PASTA_RELATORIO = RAIZ / "reports" / "climate_source_analysis"

#: Janela de sondagem usada só para descobrir em qual célula cada bairro cai
#: (2 dias — resposta minúscula, evita baixar a série inteira 94 vezes).
JANELA_SONDAGEM = ("2024-09-01", "2024-09-02")

LIMIAR_SEMANA_CHUVOSA_MM = 20.0

def descobrir_celulas(
    cliente: OpenMeteoArchiveClient,
    centroides: pd.DataFrame,
    modelo: str,
    variaveis: tuple[str, ...],
) -> dict[str, str]:
    """`codigo_bairro -> celula_id`, medido pelas coordenadas que o próprio
    provedor devolve (nunca por arredondamento local — o alinhamento exato
    da grade é do provedor, não uma suposição nossa)."""
    pontos = [
        (float(r["centroide_lat"]), float(r["centroide_lon"])) for _, r in centroides.iterrows()
    ]
    conteudo = cliente.baixar_series_diarias(
        pontos, JANELA_SONDAGEM[0], JANELA_SONDAGEM[1], variaveis, modelo
    )
    payload = json.loads(conteudo.decode("utf-8"))
    itens = payload if isinstance(payload, list) else [payload]
    return {
        str(codigo): identificador_celula(float(item["latitude"]), float(item["longitude"]))
        for codigo, item in zip(centroides["codigo_bairro"], itens)
    }

def baixar_series_das_celulas(
    cliente: OpenMeteoArchiveClient,
    celulas: dict[str, tuple[float, float]],
    data_inicio: str,
    data_fim: str,
    variaveis: tuple[str, ...],
    modelo: str,
    grade: str,
) -> pd.DataFrame:
    """Baixa a série completa de cada célula distinta (uma requisição
    multi-ponto) e devolve a tabela longa da Silver diária."""
    ordem = sorted(celulas)
    pontos = [celulas[c] for c in ordem]
    conteudo = cliente.baixar_series_diarias(pontos, data_inicio, data_fim, variaveis, modelo)
    return extrair_series_diarias_grade(conteudo, grade=grade)

def comparar_grade_com_estacao(df_comparacao: pd.DataFrame) -> dict[str, Any]:
    """Métricas de concordância entre precipitação semanal em grade e a
    medida pela estação CEMADEN, sobre as MESMAS linhas bairro × semana."""
    sub = df_comparacao.dropna(subset=["precipitacao_semana_grade_mm", "precipitacao_total_semana_mm"])
    if len(sub) < 3:
        return {"n": len(sub), "insuficiente": True}

    grade = sub["precipitacao_semana_grade_mm"].to_numpy(dtype=float)
    estacao = sub["precipitacao_total_semana_mm"].to_numpy(dtype=float)
    erro = grade - estacao

    chuvosa_grade = grade >= LIMIAR_SEMANA_CHUVOSA_MM
    chuvosa_estacao = estacao >= LIMIAR_SEMANA_CHUVOSA_MM

    return {
        "n_bairro_semana": int(len(sub)),
        "pearson": round(float(np.corrcoef(grade, estacao)[0, 1]), 4),
        "spearman": round(float(pd.Series(grade).corr(pd.Series(estacao), method="spearman")), 4),
        "mae_mm": round(float(np.mean(np.abs(erro))), 3),
        "rmse_mm": round(float(np.sqrt(np.mean(erro**2))), 3),
        "vies_medio_mm": round(float(np.mean(erro)), 3),
        "media_grade_mm": round(float(np.mean(grade)), 3),
        "media_estacao_mm": round(float(np.mean(estacao)), 3),
        "razao_total_grade_sobre_estacao": round(float(np.sum(grade) / np.sum(estacao)), 4)
        if np.sum(estacao) > 0
        else None,
        "limiar_semana_chuvosa_mm": LIMIAR_SEMANA_CHUVOSA_MM,
        "concordancia_semana_chuvosa_pct": round(float(np.mean(chuvosa_grade == chuvosa_estacao) * 100), 2),
        "recall_semana_chuvosa_pct": round(
            float(np.mean(chuvosa_grade[chuvosa_estacao]) * 100), 2
        )
        if chuvosa_estacao.any()
        else None,
    }

def _comparar_serie_agregada_cidade(df_comparacao: pd.DataFrame) -> dict[str, Any]:
    """Mesma comparação, mas agregando os bairros por semana (média da
    cidade) — separa "a grade acerta o *quando*" de "a grade acerta o
    *onde*"."""
    cidade = (
        df_comparacao.dropna(subset=["precipitacao_semana_grade_mm", "precipitacao_total_semana_mm"])
        .groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)[
            ["precipitacao_semana_grade_mm", "precipitacao_total_semana_mm"]
        ]
        .mean()
        .reset_index()
    )
    if len(cidade) < 3:
        return {"n_semanas": len(cidade), "insuficiente": True}
    return {
        "n_semanas": int(len(cidade)),
        "pearson": round(
            float(cidade["precipitacao_semana_grade_mm"].corr(cidade["precipitacao_total_semana_mm"])), 4
        ),
        "spearman": round(
            float(
                cidade["precipitacao_semana_grade_mm"].corr(
                    cidade["precipitacao_total_semana_mm"], method="spearman"
                )
            ),
            4,
        ),
    }

def _correlacao_por_bairro(df_comparacao: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for (codigo, nome), grupo in df_comparacao.groupby(["codigo_bairro", "nome_bairro"], observed=True):
        sub = grupo.dropna(subset=["precipitacao_semana_grade_mm", "precipitacao_total_semana_mm"])
        if len(sub) < 10:
            continue
        linhas.append(
            {
                "codigo_bairro": codigo,
                "nome_bairro": nome,
                "n_semanas": len(sub),
                "pearson": round(
                    float(sub["precipitacao_semana_grade_mm"].corr(sub["precipitacao_total_semana_mm"])), 4
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values("pearson", ascending=False).reset_index(drop=True)

def main() -> int:
    configurar_logging()
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrado. Rode 'python -m src.export_dashboard_dataset' primeiro.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    logger.info("Gold carregada: %d linhas", len(df_gold))

    # Grão bairro x semana (clima é idêntico entre os 3 agravos na Gold).
    colunas_bairro_semana = [
        "codigo_bairro", "nome_bairro", "centroide_lat", "centroide_lon",
        "ano_epidemiologico", "semana_epidemiologica",
        "semana_epi_data_inicio", "semana_epi_data_fim",
        "precipitacao_total_semana_mm", "dias_com_dado_valido_semana",
    ]
    df_bs = (
        df_gold[colunas_bairro_semana]
        .drop_duplicates(subset=["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"])
        .reset_index(drop=True)
    )
    centroides = (
        df_bs[["codigo_bairro", "nome_bairro", "centroide_lat", "centroide_lon"]]
        .drop_duplicates("codigo_bairro")
        .reset_index(drop=True)
    )
    logger.info("Bairro x semana: %d linhas · %d bairros", len(df_bs), len(centroides))

    data_inicio = str(pd.Timestamp(df_bs["semana_epi_data_inicio"].min()).date())
    data_fim = str(pd.Timestamp(df_bs["semana_epi_data_fim"].max()).date())
    logger.info("Janela epidemiológica a cobrir: %s -> %s", data_inicio, data_fim)

    resultado: dict[str, Any] = {
        "janela_epidemiologica": {"inicio": data_inicio, "fim": data_fim},
        "n_bairros": len(centroides),
        "extensao_graus": {
            "latitude": round(float(centroides["centroide_lat"].max() - centroides["centroide_lat"].min()), 4),
            "longitude": round(float(centroides["centroide_lon"].max() - centroides["centroide_lon"].min()), 4),
        },
        "candidatas": {
            "era5_open_meteo": "testada e escolhida",
            "cds_copernicus_direto": "nao testavel (exige credencial, ausente neste ambiente)",
            "chirps_0_05_graus": "acessivel, descartada por custo de ingestao (GeoTIFF diario global + GDAL)",
            "nasa_power": "acessivel, descartada por resolucao (0,5 x 0,625 graus)",
        },
    }

    cliente = OpenMeteoArchiveClient()

    # ------------------------------------------------------------------
    # 1. Descobrir as células e baixar as séries completas
    # ------------------------------------------------------------------
    try:
        mapa_precip = descobrir_celulas(cliente, centroides, MODELO_PRECIPITACAO, VARIAVEIS_PRECIPITACAO)
        mapa_temp = descobrir_celulas(cliente, centroides, MODELO_TEMPERATURA, VARIAVEIS_TEMPERATURA)
    except GriddedClimateClientError as exc:
        logger.error("Fonte em grade indisponível: %s", exc)
        resultado["erro"] = str(exc)
        (PASTA_RELATORIO / "gridded_climate_investigation.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 1

    celulas_precip = {c: tuple(map(float, c.split("_"))) for c in set(mapa_precip.values())}
    celulas_temp = {c: tuple(map(float, c.split("_"))) for c in set(mapa_temp.values())}
    logger.info(
        "Células distintas: %d em %s (%.2f°) · %d em %s (%.2f°)",
        len(celulas_precip), GRADE_PRECIPITACAO, RESOLUCAO_GRAUS_POR_GRADE[GRADE_PRECIPITACAO],
        len(celulas_temp), GRADE_TEMPERATURA, RESOLUCAO_GRAUS_POR_GRADE[GRADE_TEMPERATURA],
    )
    resultado["celulas"] = {
        GRADE_PRECIPITACAO: {
            "resolucao_graus": RESOLUCAO_GRAUS_POR_GRADE[GRADE_PRECIPITACAO],
            "n_celulas_para_94_bairros": len(celulas_precip),
            "celulas": sorted(celulas_precip),
        },
        GRADE_TEMPERATURA: {
            "resolucao_graus": RESOLUCAO_GRAUS_POR_GRADE[GRADE_TEMPERATURA],
            "n_celulas_para_94_bairros": len(celulas_temp),
            "celulas": sorted(celulas_temp),
        },
    }

    df_p = baixar_series_das_celulas(
        cliente, celulas_precip, data_inicio, data_fim, VARIAVEIS_PRECIPITACAO,
        MODELO_PRECIPITACAO, GRADE_PRECIPITACAO,
    )
    df_t = baixar_series_das_celulas(
        cliente, celulas_temp, data_inicio, data_fim, VARIAVEIS_TEMPERATURA,
        MODELO_TEMPERATURA, GRADE_TEMPERATURA,
    )
    df_grade_diario, metricas_silver = normalizar_clima_grade_diario(pd.concat([df_p, df_t], ignore_index=True))
    logger.info("Silver diária em grade: %s", metricas_silver)
    resultado["silver_diaria"] = metricas_silver

    mapa_bairro_celula = {
        **{(codigo, GRADE_PRECIPITACAO): cid for codigo, cid in mapa_precip.items()},
        **{(codigo, GRADE_TEMPERATURA): cid for codigo, cid in mapa_temp.items()},
    }
    df_bairro_celula = montar_mapeamento_bairro_celula(centroides, df_grade_diario, mapa_bairro_celula)
    resultado["mapeamento_bairro_celula"] = {
        "linhas": len(df_bairro_celula),
        "distancia_centroide_celula_km_mediana": round(
            float(df_bairro_celula["distancia_centroide_celula_km"].median()), 3
        ),
        "distancia_centroide_celula_km_maxima": round(
            float(df_bairro_celula["distancia_centroide_celula_km"].max()), 3
        ),
    }

    # ------------------------------------------------------------------
    # 2. Agregar para bairro x semana epidemiológica
    # ------------------------------------------------------------------
    df_semana_grade, metricas_gold = calcular_features_clima_grade(
        df_bs, df_bairro_celula, df_grade_diario
    )
    logger.info("Features em grade no grão da Gold: %s", metricas_gold)
    resultado["features_grao_gold"] = metricas_gold

    cobertura_ano = (
        df_semana_grade.assign(
            tem_grade=df_semana_grade["dias_validos_precipitacao_grade_semana"].fillna(0) > 0,
            tem_estacao=df_semana_grade["dias_com_dado_valido_semana"].fillna(0) > 0,
        )
        .groupby("ano_epidemiologico", observed=True)
        .agg(
            linhas=("codigo_bairro", "size"),
            bairro_semana_com_grade=("tem_grade", "sum"),
            bairro_semana_com_estacao=("tem_estacao", "sum"),
        )
        .reset_index()
    )
    cobertura_ano["pct_com_grade"] = (100 * cobertura_ano["bairro_semana_com_grade"] / cobertura_ano["linhas"]).round(2)
    cobertura_ano["pct_com_estacao"] = (100 * cobertura_ano["bairro_semana_com_estacao"] / cobertura_ano["linhas"]).round(2)
    cobertura_ano.to_csv(PASTA_RELATORIO / "gridded_climate_cobertura_por_ano.csv", index=False)
    resultado["cobertura_por_ano"] = cobertura_ano.to_dict("records")

    # ------------------------------------------------------------------
    # 3. Validação contra o CEMADEN no período sobreposto
    # ------------------------------------------------------------------
    sobreposicao = df_semana_grade[
        (df_semana_grade["dias_com_dado_valido_semana"].fillna(0) > 0)
        & (df_semana_grade["dias_validos_precipitacao_grade_semana"].fillna(0) > 0)
    ].copy()
    logger.info("Sobreposição grade x estação: %d linhas bairro x semana", len(sobreposicao))

    resultado["validacao_vs_cemaden"] = comparar_grade_com_estacao(sobreposicao)
    resultado["validacao_vs_cemaden_agregado_cidade"] = _comparar_serie_agregada_cidade(sobreposicao)

    por_bairro = _correlacao_por_bairro(sobreposicao)
    if not por_bairro.empty:
        por_bairro.to_csv(PASTA_RELATORIO / "gridded_climate_correlacao_por_bairro.csv", index=False)
        resultado["validacao_vs_cemaden_por_bairro"] = {
            "n_bairros_avaliados": len(por_bairro),
            "pearson_mediano": round(float(por_bairro["pearson"].median()), 4),
            "pearson_minimo": round(float(por_bairro["pearson"].min()), 4),
            "pearson_maximo": round(float(por_bairro["pearson"].max()), 4),
        }

    # Quantos valores distintos a grade produz numa mesma semana (mede
    # diretamente a incapacidade de discriminar bairros).
    variacao_intra_semana = (
        df_semana_grade[df_semana_grade["dias_validos_precipitacao_grade_semana"].fillna(0) > 0]
        .groupby(["ano_epidemiologico", "semana_epidemiologica"], observed=True)[
            "precipitacao_semana_grade_mm"
        ]
        .nunique()
    )
    resultado["valores_distintos_por_semana_entre_94_bairros"] = {
        "mediana": float(variacao_intra_semana.median()) if len(variacao_intra_semana) else None,
        "maximo": int(variacao_intra_semana.max()) if len(variacao_intra_semana) else None,
    }

    amostra = sobreposicao[
        [
            "codigo_bairro", "nome_bairro", "ano_epidemiologico", "semana_epidemiologica",
            "precipitacao_total_semana_mm", "precipitacao_semana_grade_mm",
            "dias_com_dado_valido_semana", "dias_validos_precipitacao_grade_semana",
        ]
    ]
    amostra.to_csv(PASTA_RELATORIO / "gridded_climate_comparacao_bairro_semana.csv", index=False)

    (PASTA_RELATORIO / "gridded_climate_investigation.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    logger.info("Resultado salvo em %s", PASTA_RELATORIO / "gridded_climate_investigation.json")
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str)[:6000])
    return 0

if __name__ == "__main__":
    sys.exit(main())
