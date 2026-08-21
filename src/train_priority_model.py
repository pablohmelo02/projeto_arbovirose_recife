"""Treina e congela o modelo de priorização territorial (operação separada).

Uso:
    python -m src.train_priority_model

Etapa **deliberadamente separada** da atualização de dados
(`python -m src.update_recife_alerta`, que nunca treina): treinar é uma
operação controlada, com revisão humana do resultado, não um efeito
colateral de um refresh de dados.

## O que é treinado

Exatamente o candidato congelado `dengue_onset_ranking_candidate_v1`, sem
nenhuma liberdade de escolha:

- alvo: onset de novo episódio de dengue em `t+1..t+3` (`src/ml/onset.py`);
- features: 38, sem clima (`src/ml/features.py`, grupos padrão);
- algoritmo/hiperparâmetros: `HistGradientBoostingClassifier`,
  `max_depth=4, learning_rate=0.1, max_iter=150`, `random_state=42`;
- treino: linhas com `ano_epidemiologico <= 2019` (`src/ml/split.py`).

Se qualquer um desses itens mudar, isto passa a ser uma **versão nova** e
precisa de validação estatística própria — os números de
`reports/ml/dengue_ranking_evidence_validation.md` não podem ser
reaproveitados (ver `reports/ml/dengue_ranking_clima_experiment.md`, §7).

## Corte temporal do artefato

`data_cutoff`/`cutoff_epi_year`/`cutoff_epi_week` registram o último
período que o TREINO viu. Isso é diferente do cutoff de uma *inferência*,
que é registrado no artefato de priorização
(`src/generate_priority_artifacts.py`).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd
import sklearn

from src.logging_config import configurar_logging
from src.ml import models
from src.ml import split as split_mod
from src.ml.artifacts import (
    MetadadosModelo,
    agora_iso,
    assinatura_features,
    commit_atual,
    salvar_artefato_modelo,
)
from src.ml.dataset import montar_dataset_onset

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"

MODEL_VERSION = "dengue_onset_ranking_candidate_v1"
HORIZONTE_ONSET = 3
HIPERPARAMETROS = {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150}
SEED = 42
TARGET_DEFINITION = (
    "onset: existe inicio de novo episodio de risco elevado de dengue no bairro "
    "em alguma das semanas t+1..t+3 (percentil 90 historico-sazonal local)"
)

def main() -> int:
    configurar_logging()

    if not CAMINHO_GOLD.exists():
        logger.error("'%s' não encontrada.", CAMINHO_GOLD)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    gold_schema_version = str(df_gold["versao_schema_gold"].iloc[0]) if "versao_schema_gold" in df_gold.columns else "desconhecida"

    ctx, X, y, metricas = montar_dataset_onset(df_gold, agravo="DENGUE", horizonte=HORIZONTE_ONSET)
    idx_treino, _, _ = split_mod.split_temporal(ctx)
    if len(idx_treino) == 0:
        logger.error("Nenhuma linha de treino — split incompatível com os dados.")
        return 1

    modelo = models.treinar_arvore(X.loc[idx_treino], y.loc[idx_treino], **HIPERPARAMETROS)

    ctx_treino = ctx.loc[idx_treino]
    ultima = ctx_treino.sort_values(["ano_epidemiologico", "semana_epidemiologica"]).iloc[-1]
    metadados = MetadadosModelo(
        model_version=MODEL_VERSION,
        feature_schema_version=assinatura_features(list(X.columns)),
        feature_names=list(X.columns),
        trained_until=int(split_mod.ANO_TREINO_FIM),
        target_definition=TARGET_DEFINITION,
        horizon=HORIZONTE_ONSET,
        git_commit=commit_atual(),
        created_at=agora_iso(),
        data_cutoff=str(pd.Timestamp(ultima["semana_epi_data_fim"]).date()),
        cutoff_epi_year=int(ultima["ano_epidemiologico"]),
        cutoff_epi_week=int(ultima["semana_epidemiologica"]),
        sklearn_version=sklearn.__version__,
        gold_schema_version=gold_schema_version,
        hyperparameters=HIPERPARAMETROS,
        seed=SEED,
        n_treino=int(len(idx_treino)),
        observacoes=(
            "Candidato experimental congelado. Sem clima. Validacao estatistica em "
            "reports/ml/dengue_ranking_evidence_validation.md. Ganho sobre regras simples "
            "defensavel apenas em Top-5."
        ),
    )
    destino = salvar_artefato_modelo(modelo, metadados)

    logger.info(
        "Modelo treinado: %d features · %d linhas de treino · assinatura %s",
        len(X.columns), len(idx_treino), metadados.feature_schema_version,
    )
    print(json.dumps({"destino": str(destino), **metadados.como_dict(), "metricas_dataset": {
        "linhas_finais": metricas["linhas_finais"],
        "proporcao_positiva": metricas["proporcao_positiva"],
    }}, ensure_ascii=False, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
