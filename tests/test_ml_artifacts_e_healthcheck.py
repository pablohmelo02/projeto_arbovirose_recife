"""Versionamento de artefato de ML (falhar fechado) e healthcheck.

O comportamento crítico testado: um artefato ausente, incompatível ou
gerado por outra versão de biblioteca **nunca** é carregado silenciosamente
— e o healthcheck detecta incoerência entre o estado publicado e os
arquivos presentes.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest
import sklearn

from src.healthcheck import FAIL, PASS, WARN, executar_healthcheck
from src.ml.artifacts import (
    ArtefatoAusenteError,
    ArtefatoIncompativelError,
    MetadadosModelo,
    assinatura_features,
    caminho_artefato,
    carregar_artefato_modelo,
    carregar_metadados,
    commit_atual,
    salvar_artefato_modelo,
)

VERSAO = "dengue_onset_ranking_candidate_v1"
FEATURES = ["casos_t", "media_4s", "semana_sin"]


class ModeloFalso:
    """Objeto trivialmente serializável, para não depender de treino real."""

    def __init__(self, rotulo: str = "falso") -> None:
        self.rotulo = rotulo


def _metadados(**sobrescritas) -> MetadadosModelo:
    base = dict(
        model_version=VERSAO,
        feature_schema_version=assinatura_features(FEATURES),
        feature_names=list(FEATURES),
        trained_until=2019,
        target_definition="onset em t+1..t+3",
        horizon=3,
        git_commit="abc123",
        created_at="2026-08-21T00:00:00+00:00",
        data_cutoff="2019-12-28",
        cutoff_epi_year=2019,
        cutoff_epi_week=52,
        sklearn_version=sklearn.__version__,
        gold_schema_version="1.1",
        hyperparameters={"max_depth": 4},
        seed=42,
        n_treino=1000,
    )
    base.update(sobrescritas)
    return MetadadosModelo(**base)


# ---------------------------------------------------------------------------
# Assinatura de features
# ---------------------------------------------------------------------------
def test_assinatura_muda_com_feature_nova():
    assert assinatura_features(FEATURES) != assinatura_features(FEATURES + ["nova"])


def test_assinatura_muda_com_reordenacao():
    """Reordenar features quebra um modelo sklearn treinado — a assinatura
    tem de detectar isso, não só a contagem."""
    invertida = list(reversed(FEATURES))
    assert assinatura_features(FEATURES) != assinatura_features(invertida)


def test_assinatura_e_estavel_para_a_mesma_lista():
    assert assinatura_features(FEATURES) == assinatura_features(list(FEATURES))


def test_assinatura_declara_a_contagem():
    assert assinatura_features(FEATURES).startswith("3-")


# ---------------------------------------------------------------------------
# caminho_artefato — defesa contra path traversal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "versao_invalida",
    ["../fora", "modelo/../..", "Modelo-Com-Maiuscula", "com espaco", "", "c:/windows"],
)
def test_caminho_rejeita_versao_fora_do_padrao(versao_invalida):
    with pytest.raises(ValueError):
        caminho_artefato(versao_invalida)


def test_caminho_rejeita_versao_desconhecida():
    with pytest.raises(ValueError, match="VERSOES_CONHECIDAS"):
        caminho_artefato("modelo_qualquer_v9")


def test_caminho_aceita_versao_conhecida(tmp_path):
    assert caminho_artefato(VERSAO, base=tmp_path) == tmp_path / VERSAO


# ---------------------------------------------------------------------------
# Salvar / carregar
# ---------------------------------------------------------------------------
def test_ciclo_salvar_e_carregar(tmp_path):
    salvar_artefato_modelo(ModeloFalso("A"), _metadados(), base=tmp_path)
    modelo, metadados = carregar_artefato_modelo(
        VERSAO, feature_names_esperadas=FEATURES, gold_schema_version_esperada="1.1", base=tmp_path
    )
    assert modelo.rotulo == "A"
    assert metadados["model_version"] == VERSAO
    assert metadados["cutoff_epi_week_formatada"] == "2019-52"


def test_carregar_sem_artefato_levanta_ausente(tmp_path):
    with pytest.raises(ArtefatoAusenteError):
        carregar_artefato_modelo(VERSAO, base=tmp_path)


def test_metadados_ausentes_levantam(tmp_path):
    with pytest.raises(ArtefatoAusenteError):
        carregar_metadados(VERSAO, base=tmp_path)


def test_features_diferentes_levantam_incompativel(tmp_path):
    salvar_artefato_modelo(ModeloFalso(), _metadados(), base=tmp_path)
    with pytest.raises(ArtefatoIncompativelError, match="assinatura de features"):
        carregar_artefato_modelo(VERSAO, feature_names_esperadas=FEATURES + ["extra"], base=tmp_path)


def test_reordenacao_de_features_levanta_incompativel(tmp_path):
    salvar_artefato_modelo(ModeloFalso(), _metadados(), base=tmp_path)
    with pytest.raises(ArtefatoIncompativelError):
        carregar_artefato_modelo(VERSAO, feature_names_esperadas=list(reversed(FEATURES)), base=tmp_path)


def test_schema_da_gold_diferente_levanta_incompativel(tmp_path):
    salvar_artefato_modelo(ModeloFalso(), _metadados(), base=tmp_path)
    with pytest.raises(ArtefatoIncompativelError, match="schema da Gold"):
        carregar_artefato_modelo(VERSAO, gold_schema_version_esperada="2.0", base=tmp_path)


def test_versao_de_sklearn_diferente_levanta_incompativel(tmp_path):
    salvar_artefato_modelo(ModeloFalso(), _metadados(sklearn_version="0.1.0"), base=tmp_path)
    with pytest.raises(ArtefatoIncompativelError, match="scikit-learn"):
        carregar_artefato_modelo(VERSAO, base=tmp_path)


def test_metadados_obrigatorios_estao_todos_presentes(tmp_path):
    salvar_artefato_modelo(ModeloFalso(), _metadados(), base=tmp_path)
    metadados = carregar_metadados(VERSAO, base=tmp_path)
    obrigatorios = {
        "model_version", "feature_schema_version", "trained_until", "target_definition",
        "horizon", "git_commit", "created_at", "data_cutoff", "cutoff_epi_year",
        "cutoff_epi_week", "sklearn_version", "gold_schema_version",
    }
    assert obrigatorios <= set(metadados)


def test_commit_atual_nunca_inventa_hash():
    valor = commit_atual()
    assert valor == "desconhecido" or (len(valor) == 40 and all(c in "0123456789abcdef" for c in valor))


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------
def _gold_minima() -> pd.DataFrame:
    linhas = []
    for i in range(94):
        for agravo in ("DENGUE", "ZIKA", "CHIKUNGUNYA"):
            inicio = pd.Timestamp("2025-01-05")
            linhas.append(
                {
                    "codigo_bairro": str(i), "nome_bairro": f"B{i}", "agravo": agravo,
                    "ano_epidemiologico": 2025, "semana_epidemiologica": 1,
                    "semana_epi_data_inicio": inicio,
                    "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                    "casos": 0,
                }
            )
    return pd.DataFrame(linhas)


def _preparar_pasta(tmp_path, com_status=True, com_latest=False, projecao_disponivel=False):
    _gold_minima().to_parquet(tmp_path / "gold_arboviroses_clima_bairro.parquet", index=False)
    (tmp_path / "bairro_geo.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    if com_status:
        (tmp_path / "_priority_status.json").write_text(
            json.dumps(
                {
                    "backtest_available": True,
                    "backtest_periodo": {"ano_inicio": 2023, "ano_fim": 2025, "semanas": 154},
                    "model_version": VERSAO,
                    "feature_schema_version": assinatura_features(FEATURES),
                    "current_projection_available": projecao_disponivel,
                    "reason": None if projecao_disponivel else "epidemiological_data_stale",
                }
            ),
            encoding="utf-8",
        )
    if com_latest:
        pd.DataFrame({"ranking": [1]}).to_parquet(tmp_path / "latest_priority.parquet", index=False)
    return tmp_path


def _por_nome(resultado: dict) -> dict:
    return {v["verificacao"]: v for v in resultado["verificacoes"]}


def test_healthcheck_falha_sem_gold(tmp_path):
    resultado = executar_healthcheck(tmp_path)
    assert resultado["status_geral"] == FAIL
    assert resultado["contagem"][FAIL] >= 1


def test_healthcheck_aprova_gold_valida(tmp_path):
    resultado = executar_healthcheck(_preparar_pasta(tmp_path))
    verificacoes = _por_nome(resultado)
    assert verificacoes["gold:legivel"]["status"] == PASS
    assert verificacoes["gold:portoes_qualidade"]["status"] == PASS


def test_healthcheck_detecta_parquet_corrompido(tmp_path):
    _preparar_pasta(tmp_path)
    (tmp_path / "gold_arboviroses_clima_bairro.parquet").write_bytes(b"nao eh parquet")
    resultado = executar_healthcheck(tmp_path)
    assert _por_nome(resultado)["gold:legivel"]["status"] == FAIL


def test_healthcheck_artefato_opcional_ausente_e_apenas_aviso(tmp_path):
    resultado = executar_healthcheck(_preparar_pasta(tmp_path, com_status=False))
    nomes = _por_nome(resultado)
    assert nomes["arquivo:_freshness.json"]["status"] == WARN
    assert resultado["contagem"][FAIL] == 0, "modo degradado não deve falhar o healthcheck"


def test_healthcheck_detecta_latest_priority_indevido(tmp_path):
    """Artefato de projeção presente enquanto o portão a bloqueia é
    potencialmente enganoso — tem de ser FAIL."""
    pasta = _preparar_pasta(tmp_path, com_latest=True, projecao_disponivel=False)
    resultado = executar_healthcheck(pasta)
    coerencia = _por_nome(resultado)["modelo:coerencia_projecao"]
    assert coerencia["status"] == FAIL
    assert "enganoso" in coerencia["mensagem"]


def test_healthcheck_detecta_latest_priority_faltando(tmp_path):
    pasta = _preparar_pasta(tmp_path, com_latest=False, projecao_disponivel=True)
    resultado = executar_healthcheck(pasta)
    assert _por_nome(resultado)["modelo:coerencia_projecao"]["status"] == FAIL


def test_healthcheck_aprova_bloqueio_coerente(tmp_path):
    pasta = _preparar_pasta(tmp_path, com_latest=False, projecao_disponivel=False)
    coerencia = _por_nome(executar_healthcheck(pasta))["modelo:coerencia_projecao"]
    assert coerencia["status"] == PASS
    assert "corretamente bloqueada" in coerencia["mensagem"]


def test_healthcheck_status_json_invalido_e_fail(tmp_path):
    pasta = _preparar_pasta(tmp_path)
    (pasta / "_priority_status.json").write_text("{ nao eh json", encoding="utf-8")
    assert _por_nome(executar_healthcheck(pasta))["modelo:status"]["status"] == FAIL
