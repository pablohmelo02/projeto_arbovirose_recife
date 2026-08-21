"""Gera os artefatos da Projeção 2026 consumidos pelo dashboard — sem
treinar nada em tempo real dentro do Streamlit (mesma convenção de
`src/generate_priority_artifacts.py`).

Uso:
    python -m src.generate_forecast_artifacts

Produz, para cada agravo (DENGUE, ZIKA, CHIKUNGUNYA):

1. `dashboard/data/_forecast_2026.parquet` — uma linha por
   agravo × ano × semana, cobrindo o histórico observado (2013-2025,
   `is_observado=True`, sem banda) e a projeção 2026
   (`is_observado=False`, com `banda_80_*`/`banda_95_*`). É o único
   arquivo que a página "Projeção 2026" lê.
2. `dashboard/data/_forecast_2026_metadata.json` — por agravo: modelo
   escolhido no backtest, resumo do backtest (MAE/RMSE/MASE/erro de
   pico/timing por dobra), pico projetado, comparação com a média
   sazonal histórica, e se a incidência 2026 está disponível (não está —
   ver `src/forecast/projecao_2026.py`).

Isolado de `src/ml/` — ver `tests/test_forecast_v1_intacto.py`. Nunca
importa `src.ml`, nunca escreve em `artifacts/models/` nem em
`reports/ml/`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.forecast.dataset import (
    ULTIMO_ANO_HISTORICO_VALIDADO,
    construir_serie_semanal,
    garantir_sem_observado_futuro,
)
from src.forecast.projecao_2026 import ANO_PROJECAO, projetar_agravo
from src.eda.schema_eda import AGRAVOS
from src.logging_config import configurar_logging
from src.utils.io_atomico import escrever_json_atomico, escrever_parquet_atomico


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dashboard" / "data"
CAMINHO_GOLD = PASTA_DADOS / "gold_arboviroses_clima_bairro.parquet"
CAMINHO_FORECAST = PASTA_DADOS / "_forecast_2026.parquet"
CAMINHO_METADATA = PASTA_DADOS / "_forecast_2026_metadata.json"

COLUNAS_ARTEFATO = (
    "agravo",
    "ano_epidemiologico",
    "semana_epidemiologica",
    "semana_epi_data_inicio",
    "is_observado",
    "casos",
    "banda_80_inferior",
    "banda_80_superior",
    "banda_95_inferior",
    "banda_95_superior",
)


def _linhas_observadas(serie: pd.DataFrame, agravo: str) -> pd.DataFrame:
    linhas = serie.copy()
    linhas["agravo"] = agravo
    linhas["is_observado"] = True
    for coluna in ("banda_80_inferior", "banda_80_superior", "banda_95_inferior", "banda_95_superior"):
        linhas[coluna] = pd.NA
    return linhas[list(COLUNAS_ARTEFATO)]


def _linhas_projetadas(projecao: pd.DataFrame, agravo: str) -> pd.DataFrame:
    linhas = projecao.copy()
    linhas["agravo"] = agravo
    linhas["is_observado"] = False
    return linhas[list(COLUNAS_ARTEFATO)]


def _metadados_agravo(resultado: dict[str, Any]) -> dict[str, Any]:
    if not resultado.get("disponivel"):
        return {"disponivel": False, "motivo": resultado.get("motivo")}
    resumo_backtest = resultado["resumo_backtest"].to_dict(orient="records")
    modelo_escolhido = resultado["modelo_escolhido"]
    tabela_vencedor = resultado["backtest_por_modelo"][modelo_escolhido].drop(
        columns=["erros_pontuais"], errors="ignore"
    )
    return {
        "disponivel": True,
        "ultimo_ano_historico": resultado["ultimo_ano_historico"],
        "modelo_escolhido": modelo_escolhido,
        "metodo_banda": resultado["metodo_banda"],
        "backtest_por_dobra_do_modelo_escolhido": tabela_vencedor.to_dict(orient="records"),
        "resumo_backtest_por_modelo": resumo_backtest,
        "cobertura_intervalo_por_dobra": resultado["cobertura_intervalo_por_dobra"].to_dict(orient="records"),
        "cobertura_intervalo_media": resultado["cobertura_intervalo_media"],
        "pico_projetado": resultado["pico_projetado"],
        "media_semanal_historica_comparavel": resultado["media_semanal_historica_comparavel"],
        "incidencia_2026_disponivel": False,
        "motivo_incidencia_2026_indisponivel": (
            "não há estimativa municipal oficial do IBGE para a população de 2026 "
            "(verificado ao vivo — ver reports/forecast/arbovirus_2026_projection.md); "
            "a projeção é sempre em número de casos"
        ),
    }


def main() -> int:
    configurar_logging()

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrada.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    try:
        garantir_sem_observado_futuro(df_gold, ano_limite=ULTIMO_ANO_HISTORICO_VALIDADO)
    except ValueError as exc:
        logger.error("Gold contém dado além do último ano validado: %s", exc)
        return 1

    tabelas_agravo = []
    metadados: dict[str, Any] = {
        "gerado_em": _agora_iso(),
        "ano_projecao": ANO_PROJECAO,
        "ultimo_ano_historico_validado": ULTIMO_ANO_HISTORICO_VALIDADO,
        "por_agravo": {},
    }

    for agravo in AGRAVOS:
        serie = construir_serie_semanal(df_gold, agravo)
        resultado = projetar_agravo(df_gold, agravo)
        metadados["por_agravo"][agravo] = _metadados_agravo(resultado)

        if not resultado.get("disponivel"):
            logger.warning("Forecast indisponível para %s: %s", agravo, resultado.get("motivo"))
            continue

        tabelas_agravo.append(_linhas_observadas(serie, agravo))
        tabelas_agravo.append(_linhas_projetadas(resultado["projecao_2026"], agravo))

    if not tabelas_agravo:
        logger.error("Nenhum agravo produziu forecast — nada escrito.")
        return 1

    artefato = pd.concat(tabelas_agravo, ignore_index=True)

    def _validar(caminho: Path) -> None:
        verificacao = pd.read_parquet(caminho)
        if verificacao.empty:
            raise ValueError("artefato de forecast ficou vazio")
        if verificacao["casos"].lt(0).any():
            raise ValueError("artefato de forecast tem casos negativos")

    escrever_parquet_atomico(CAMINHO_FORECAST, artefato, validar=_validar)
    escrever_json_atomico(CAMINHO_METADATA, metadados)

    logger.info(
        "Forecast 2026 gerado: %d linhas em %s, metadados em %s",
        len(artefato), CAMINHO_FORECAST, CAMINHO_METADATA,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
