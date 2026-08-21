"""Guarda de regressão: o pacote `src/forecast/` (projeção epidemiológica
sazonal 2026) não pode alterar nem importar o candidato congelado
`dengue_onset_ranking_candidate_v1`, nem qualquer artefato/relatório de
`src/ml/`/`reports/ml/`. Espelha `tests/test_ml_incidence_v2_v1_intacto.py`,
que já implementa esse isolamento para o experimento V2 de incidência."""
from __future__ import annotations

import ast
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_METADATA_V1 = RAIZ / "artifacts" / "models" / "dengue_onset_ranking_candidate_v1" / "metadata.json"
PASTA_FORECAST = RAIZ / "src" / "forecast"


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


def test_modulos_v1_permanecem_com_as_constantes_congeladas():
    """Mesma checagem de `test_ml_incidence_v2_v1_intacto.py` — repetida
    aqui para que o pacote de forecast tenha sua própria guarda
    independente (não depende de o outro arquivo de teste continuar
    existindo)."""
    from src.ml import baselines, dataset, features, onset, target

    assert target.PERCENTIL_LIMIAR_SURTO == 90
    assert target.N_MIN_HISTORICO_SAZONAL == 15
    assert target.N_MIN_HISTORICO_GERAL == 20
    assert onset.HORIZONTES_ONSET == (1, 2, 3)
    assert features.EPS_RAZAO == 1.0
    assert features.LAGS_CASOS == (1, 2, 3, 4)
    assert callable(dataset.montar_dataset_onset)
    assert baselines.N_SEMANAS_CRESCIMENTO_CONSECUTIVO == 3


def _arquivos_forecast() -> list[Path]:
    assert PASTA_FORECAST.exists(), "src/forecast/ deveria existir a partir desta etapa"
    return sorted(PASTA_FORECAST.glob("*.py"))


def _nomes_importados(caminho: Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes = set()
    for nodo in ast.walk(arvore):
        if isinstance(nodo, ast.Import):
            nomes.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nomes.add(nodo.module)
    return nomes


def test_nenhum_arquivo_de_forecast_importa_src_ml():
    arquivos = _arquivos_forecast()
    assert arquivos, "src/forecast/ não deveria estar vazio"
    for caminho in arquivos:
        importados = _nomes_importados(caminho)
        proibidos = {nome for nome in importados if nome == "src.ml" or nome.startswith("src.ml.")}
        assert not proibidos, f"{caminho.name} importa de src.ml: {proibidos}"


def test_nenhum_arquivo_de_forecast_escreve_em_artifacts_models_ou_reports_ml():
    """Checagem textual simples (não substitui revisão de código, mas pega
    o caso óbvio): nenhum caminho literal do pacote de forecast referencia
    os diretórios protegidos."""
    proibidos_literais = ("artifacts/models", "artifacts\\\\models", "reports/ml", "reports\\\\ml")
    for caminho in _arquivos_forecast():
        codigo = caminho.read_text(encoding="utf-8")
        for literal in proibidos_literais:
            assert literal not in codigo, f"{caminho.name} referencia caminho protegido: {literal!r}"


def test_pacote_ml_v1_nao_referencia_forecast():
    """Isolamento nos dois sentidos: `src/ml/` (V1) também não deveria
    precisar importar nada de `src/forecast/` — se algum dia importar, é
    sinal de acoplamento indevido entre os dois pacotes independentes."""
    pasta_ml = RAIZ / "src" / "ml"
    for caminho in pasta_ml.glob("*.py"):
        importados = _nomes_importados(caminho)
        proibidos = {nome for nome in importados if nome == "src.forecast" or nome.startswith("src.forecast.")}
        assert not proibidos, f"{caminho.name} (src/ml) importa de src.forecast: {proibidos}"
