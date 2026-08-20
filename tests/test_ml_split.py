import pandas as pd

from src.ml.split import ANO_TREINO_FIM, ANO_VALIDACAO_FIM, split_temporal, walk_forward_splits


def _df_contexto(anos: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"ano_epidemiologico": anos})


def test_split_temporal_nao_mistura_anos_entre_conjuntos():
    df = _df_contexto(list(range(2013, 2026)) * 10)
    idx_treino, idx_val, idx_teste = split_temporal(df)
    assert df.loc[idx_treino, "ano_epidemiologico"].max() <= ANO_TREINO_FIM
    assert df.loc[idx_val, "ano_epidemiologico"].min() > ANO_TREINO_FIM
    assert df.loc[idx_val, "ano_epidemiologico"].max() <= ANO_VALIDACAO_FIM
    assert df.loc[idx_teste, "ano_epidemiologico"].min() > ANO_VALIDACAO_FIM


def test_split_temporal_cobre_todas_as_linhas_sem_sobreposicao():
    df = _df_contexto(list(range(2013, 2026)))
    idx_treino, idx_val, idx_teste = split_temporal(df)
    todos = set(idx_treino) | set(idx_val) | set(idx_teste)
    assert todos == set(df.index)
    assert set(idx_treino).isdisjoint(idx_val)
    assert set(idx_val).isdisjoint(idx_teste)
    assert set(idx_treino).isdisjoint(idx_teste)


def test_walk_forward_treino_e_sempre_estritamente_anterior_ao_teste():
    df = _df_contexto(list(range(2013, 2026)) * 5)
    for ano_teste, idx_treino, idx_teste in walk_forward_splits(df):
        assert df.loc[idx_treino, "ano_epidemiologico"].max() < ano_teste
        assert (df.loc[idx_teste, "ano_epidemiologico"] == ano_teste).all()
