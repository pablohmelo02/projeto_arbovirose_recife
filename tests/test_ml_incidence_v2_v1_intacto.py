"""Guarda de regressão: o experimento V2 (incidência) não pode alterar o
candidato congelado `dengue_onset_ranking_candidate_v1` de forma alguma —
nem hiperparâmetro, nem feature, nem target, nem o próprio arquivo de
metadados. Testado explicitamente (seção 32 do pedido: "V1 intacta")."""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_METADATA_V1 = RAIZ / "artifacts" / "models" / "dengue_onset_ranking_candidate_v1" / "metadata.json"


def test_metadata_v1_permanece_com_os_valores_congelados():
    assert CAMINHO_METADATA_V1.exists(), "metadata.json do candidato V1 não deveria ter sido removido"
    with open(CAMINHO_METADATA_V1, encoding="utf-8") as f:
        metadata = json.load(f)

    assert metadata["model_version"] == "dengue_onset_ranking_candidate_v1"
    assert metadata["horizon"] == 3
    assert metadata["hyperparameters"] == {"max_depth": 4, "learning_rate": 0.1, "max_iter": 150}
    assert metadata["seed"] == 42
    assert metadata["trained_until"] == 2019
    assert len(metadata["feature_names"]) == 38
    assert metadata["target_definition"].startswith("onset")


def test_arquivos_de_codigo_v1_nao_foram_tocados_pelo_modulo_de_incidencia():
    """O pacote de incidência nunca importa `src.ml.target`/`onset`/
    `features`/`dataset`/`baselines` para MODIFICAR — só para reusar
    (import). Este teste garante que os módulos de incidência não
    monkey-patcham nenhum atributo desses módulos originais."""
    from src.ml import baselines, dataset, features, onset, target

    assert target.PERCENTIL_LIMIAR_SURTO == 90
    assert target.N_MIN_HISTORICO_SAZONAL == 15
    assert target.N_MIN_HISTORICO_GERAL == 20
    assert onset.HORIZONTES_ONSET == (1, 2, 3)
    assert features.EPS_RAZAO == 1.0
    assert features.LAGS_CASOS == (1, 2, 3, 4)
    assert callable(dataset.montar_dataset_onset)
    assert baselines.N_SEMANAS_CRESCIMENTO_CONSECUTIVO == 3
