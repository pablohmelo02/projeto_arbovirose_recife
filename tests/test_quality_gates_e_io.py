"""Portões de qualidade e escrita atômica de artefatos.

Estes dois mecanismos, juntos, são a garantia de que **um artefato inválido
nunca substitui um artefato válido anterior**. Os testes cobrem tanto o
"detectou o problema" quanto o "preservou o arquivo bom".
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from src.quality_gates import (
    AVISO,
    CRITICO,
    N_BAIRROS_ESPERADO,
    QualityGateError,
    achados_para_dict,
    exigir_aprovacao,
    separar_por_severidade,
    validar_dataset_publicavel,
    validar_gold,
)
from src.utils.io_atomico import (
    SUFIXO_TEMPORARIO,
    ValidacaoArtefatoError,
    escrever_bytes_atomico,
    escrever_json_atomico,
    escrever_parquet_atomico,
)


# ---------------------------------------------------------------------------
# Gold sintética válida
# ---------------------------------------------------------------------------
def _gold_valida(n_bairros: int = N_BAIRROS_ESPERADO) -> pd.DataFrame:
    linhas = []
    for i in range(n_bairros):
        for agravo in ("DENGUE", "ZIKA", "CHIKUNGUNYA"):
            for semana in (1, 2):
                inicio = pd.Timestamp("2025-01-05") + pd.Timedelta(weeks=semana - 1)
                linhas.append(
                    {
                        "codigo_bairro": str(i),
                        "nome_bairro": f"BAIRRO {i}",
                        "agravo": agravo,
                        "ano_epidemiologico": 2025,
                        "semana_epidemiologica": semana,
                        "semana_epi_data_inicio": inicio,
                        "semana_epi_data_fim": inicio + pd.Timedelta(days=6),
                        "casos": i % 5,
                        "precipitacao_semana_grade_mm": 10.0,
                        "umidade_relativa_media_grade_pct": 78.0,
                    }
                )
    return pd.DataFrame(linhas)


def _mensagens(achados) -> str:
    return " | ".join(a.mensagem for a in achados)


# ---------------------------------------------------------------------------
# validar_gold
# ---------------------------------------------------------------------------
def test_gold_valida_passa_sem_critico():
    achados = validar_gold(_gold_valida(), codigos_bairro_territorio=[str(i) for i in range(94)])
    criticos, _ = separar_por_severidade(achados)
    assert criticos == [], _mensagens(achados)


def test_gold_vazia_e_critico():
    achados = validar_gold(pd.DataFrame())
    assert any(a.severidade == CRITICO for a in achados)


def test_chave_duplicada_e_critico():
    gold = _gold_valida(3)
    duplicada = pd.concat([gold, gold.head(1)], ignore_index=True)
    achados = validar_gold(duplicada)
    assert "chave duplicada" in _mensagens(achados)


def test_numero_de_bairros_diferente_do_esperado_e_critico():
    achados = validar_gold(_gold_valida(50))
    assert "50 bairros" in _mensagens(achados)


def test_caso_negativo_e_caso_nulo_sao_criticos():
    gold = _gold_valida(3)
    gold.loc[0, "casos"] = -1
    gold.loc[1, "casos"] = None
    achados = validar_gold(gold)
    mensagens = _mensagens(achados)
    assert "casos < 0" in mensagens
    assert "casos nulo" in mensagens


def test_semana_epidemiologica_invalida_e_critico():
    gold = _gold_valida(3)
    gold.loc[0, "semana_epidemiologica"] = 60
    assert "semana epidemiológica inválida" in _mensagens(validar_gold(gold))


def test_semana_que_nao_tem_7_dias_e_critico():
    gold = _gold_valida(3)
    gold.loc[0, "semana_epi_data_fim"] = gold.loc[0, "semana_epi_data_inicio"] + pd.Timedelta(days=3)
    assert "não tem exatamente 7 dias" in _mensagens(validar_gold(gold))


def test_data_invertida_e_critico():
    gold = _gold_valida(3)
    gold.loc[0, "semana_epi_data_fim"] = gold.loc[0, "semana_epi_data_inicio"] - pd.Timedelta(days=1)
    assert "data_fim < data_inicio" in _mensagens(validar_gold(gold))


def test_precipitacao_negativa_e_critico():
    gold = _gold_valida(3)
    gold.loc[0, "precipitacao_semana_grade_mm"] = -5.0
    assert "negativo" in _mensagens(validar_gold(gold))


def test_umidade_fora_de_0_100_e_critico():
    gold = _gold_valida(3)
    gold.loc[0, "umidade_relativa_media_grade_pct"] = 140.0
    assert "fora de 0-100%" in _mensagens(validar_gold(gold))


def test_precipitacao_ausente_nao_e_erro():
    """`missing != 0` — ausência de leitura é legítima e não pode falhar."""
    gold = _gold_valida(94)
    gold["precipitacao_semana_grade_mm"] = None
    criticos, _ = separar_por_severidade(
        validar_gold(gold, codigos_bairro_territorio=[str(i) for i in range(94)])
    )
    assert criticos == []


def test_integridade_referencial_detecta_bairro_sobrando_e_faltando():
    gold = _gold_valida(94)
    achados = validar_gold(gold, codigos_bairro_territorio=[str(i) for i in range(93)])
    assert "sem correspondência no território" in _mensagens(achados)

    achados = validar_gold(gold, codigos_bairro_territorio=[str(i) for i in range(95)])
    assert "ausente(s) na Gold" in _mensagens(achados)


def test_territorio_nao_informado_gera_aviso_nao_critico():
    achados = validar_gold(_gold_valida())
    avisos = [a for a in achados if a.severidade == AVISO]
    assert any("portão de integridade referencial pulado" in a.mensagem for a in avisos)


def test_coluna_obrigatoria_ausente_e_critico():
    achados = validar_gold(_gold_valida(94), colunas_obrigatorias=("coluna_inexistente",))
    assert "colunas obrigatórias ausentes" in _mensagens(achados)


# ---------------------------------------------------------------------------
# Privacidade
# ---------------------------------------------------------------------------
def test_dataset_publicavel_rejeita_coluna_identificavel():
    df = pd.DataFrame({"codigo_bairro": ["1"], "CPF": ["000"]})
    achados = validar_dataset_publicavel(df, colunas_proibidas=("cpf", "nome"))
    assert achados and achados[0].severidade == CRITICO


def test_dataset_publicavel_aceita_dataset_agregado():
    df = pd.DataFrame({"codigo_bairro": ["1"], "casos": [3]})
    assert validar_dataset_publicavel(df, colunas_proibidas=("cpf", "nome")) == []


# ---------------------------------------------------------------------------
# exigir_aprovacao
# ---------------------------------------------------------------------------
def test_exigir_aprovacao_levanta_em_critico():
    with pytest.raises(QualityGateError):
        exigir_aprovacao(validar_gold(pd.DataFrame()), contexto="teste")


def test_exigir_aprovacao_devolve_avisos_sem_levantar():
    avisos = exigir_aprovacao(validar_gold(_gold_valida()), contexto="teste")
    assert all(a.severidade == AVISO for a in avisos)


def test_achados_para_dict_e_serializavel():
    dados = achados_para_dict(validar_gold(_gold_valida()))
    json.dumps(dados)  # não deve levantar
    assert all({"portao", "severidade", "mensagem", "detalhe"} <= set(d) for d in dados)


# ---------------------------------------------------------------------------
# Escrita atômica
# ---------------------------------------------------------------------------
def test_escrita_atomica_grava_e_nao_deixa_temporario(tmp_path):
    destino = tmp_path / "sub" / "arquivo.json"
    escrever_json_atomico(destino, {"a": 1})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"a": 1}
    assert not list(tmp_path.rglob(f"*{SUFIXO_TEMPORARIO}"))


def test_validacao_que_falha_preserva_o_arquivo_anterior(tmp_path):
    destino = tmp_path / "arquivo.json"
    escrever_json_atomico(destino, {"versao": "boa"})

    def validador_que_rejeita(_caminho):
        raise ValidacaoArtefatoError("conteúdo rejeitado")

    with pytest.raises(ValidacaoArtefatoError):
        escrever_json_atomico(destino, {"versao": "ruim"}, validar=validador_que_rejeita)

    assert json.loads(destino.read_text(encoding="utf-8")) == {"versao": "boa"}
    assert not list(tmp_path.rglob(f"*{SUFIXO_TEMPORARIO}"))


def test_excecao_durante_a_escrita_preserva_o_anterior(tmp_path):
    destino = tmp_path / "dados.parquet"
    escrever_parquet_atomico(destino, pd.DataFrame({"a": [1, 2, 3]}))
    original = destino.read_bytes()

    class DataFrameQueFalha(pd.DataFrame):
        def to_parquet(self, *args, **kwargs):  # noqa: D102
            raise OSError("disco cheio")

    with pytest.raises(OSError):
        escrever_parquet_atomico(destino, DataFrameQueFalha({"a": [1]}))

    assert destino.read_bytes() == original


def test_nada_escrito_levanta_e_preserva(tmp_path):
    destino = tmp_path / "vazio.bin"
    escrever_bytes_atomico(destino, b"conteudo original")

    from src.utils.io_atomico import caminho_temporario

    with pytest.raises(ValidacaoArtefatoError):
        with caminho_temporario(destino):
            pass  # não escreve nada no temporário

    assert destino.read_bytes() == b"conteudo original"


def test_reescrita_substitui_no_lugar(tmp_path):
    destino = tmp_path / "arquivo.json"
    escrever_json_atomico(destino, {"v": 1})
    inode_ou_nome = destino.name
    escrever_json_atomico(destino, {"v": 2})
    assert destino.name == inode_ou_nome
    assert json.loads(destino.read_text(encoding="utf-8")) == {"v": 2}
    assert len(list(tmp_path.iterdir())) == 1, "não deve sobrar arquivo intermediário"
