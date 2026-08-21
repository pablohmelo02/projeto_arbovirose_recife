from __future__ import annotations

import pytest

from src.generate_forecast_report import AVISO_PERMANENTE, gerar_relatorio, _carregar_metadados


def test_carregar_metadados_none_quando_artefato_ausente(monkeypatch, tmp_path):
    import src.generate_forecast_report as modulo

    monkeypatch.setattr(modulo, "CAMINHO_METADATA", tmp_path / "nao_existe.json")
    assert modulo._carregar_metadados() is None


def test_gerar_relatorio_levanta_erro_sem_metadados(monkeypatch, tmp_path):
    import src.generate_forecast_report as modulo

    monkeypatch.setattr(modulo, "CAMINHO_METADATA", tmp_path / "nao_existe.json")
    with pytest.raises(RuntimeError):
        modulo.gerar_relatorio()


def test_gerar_relatorio_real_contem_aviso_permanente_e_os_tres_agravos():
    """Roda contra o artefato real já gerado nesta sessão
    (`python -m src.generate_forecast_artifacts`) -- se o artefato não
    existir neste ambiente de teste, o teste é pulado, não falha."""
    try:
        texto = gerar_relatorio()
    except RuntimeError:
        pytest.skip("artefato de forecast não gerado neste ambiente")
        return
    assert AVISO_PERMANENTE in texto
    for agravo in ("DENGUE", "ZIKA", "CHIKUNGUNYA"):
        assert f"## {agravo}" in texto
    assert "causa" not in texto.lower() or "não causalidade" in texto.lower()
