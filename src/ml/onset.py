"""Target prospectivo de ONSET — formulação B desta etapa, comparada à
formulação A já existente (`target.py`/`dataset.py`: "o bairro estará em
estado de risco elevado em t+1?").

## Onset ≠ persistência

Um **onset** é a PRIMEIRA semana de um novo episódio de risco (mesma
definição de episódio já usada em `alert_metrics.construir_episodios` —
não reimplementada aqui, só reaproveitada). Semanas seguintes do mesmo
episódio (continuação) NÃO são onset — testado explicitamente
(`tests/test_ml_onset.py::test_onset_nao_marca_semanas_de_continuacao`).

Exemplo (mesmo do pedido): se as semanas 21, 22, 23 são consecutivas em
risco elevado e a semana 20 não era, **onset = semana 21** — 22 e 23 não
contam como novos onsets independentes.

## `target_onset_h{N}`

Para uma linha em `t`: `target_onset_hN(t) = 1` se existir **pelo menos
um** onset do MESMO bairro em `(t, t+N]` (ou seja, em `t+1` até `t+N`
inclusive) — `0` se não existir nenhum, `NaN` se alguma semana da janela
tiver estado indefinido (`target.py`, histórico insuficiente) e nenhum
onset tiver sido encontrado antes disso (não dá para garantir "não houve
onset" se uma parte da janela é desconhecida).

**Se o bairro já está dentro de um episódio em `t`** (`estado_alto_risco`
da própria linha `t` = 1), a definição acima já trata isso corretamda:
como onset exige a semana anterior em `estado=0`, uma continuação nunca é
"descoberta" como onset novo — `target_onset_hN(t)` só vira `1` se o
episódio atual terminar E um novo episódio genuinamente começar dentro da
janela (com um "gap" de pelo menos 1 semana em `estado=0` entre os dois).
Testado explicitamente.

## Sem leakage

O TARGET usa deliberadamente o futuro (`t+1..t+N`) — é o que se quer
prever. As FEATURES (calculadas em `features.py`, reaproveitadas sem
mudança) usam só `t` ou antes. Teste adversarial: alterar `casos` depois
do cutoff de uma linha não pode mudar `target_onset_hN` de linhas
anteriores a esse cutoff, e não pode mudar NENHUMA feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.ml.alert_metrics import construir_episodios

HORIZONTES_ONSET = (1, 2, 3)


def construir_target_onset(df_estado_idx: pd.DataFrame, horizontes: tuple[int, ...] = HORIZONTES_ONSET) -> pd.DataFrame:
    """Recebe `df_estado_idx` (saída de `target.calcular_estado_alto_risco`
    + `features.construir_indice_semana_global`, uma linha por bairro x
    semana, SEM filtragem de linhas — o grão completo da Gold) e devolve o
    mesmo DataFrame com `target_onset_h{N}` para cada `N` em `horizontes`."""
    df = df_estado_idx.sort_values(["codigo_bairro", "indice_semana_global"]).reset_index(drop=True)
    episodios = construir_episodios(df)
    onset_por_bairro = episodios.groupby("codigo_bairro")["inicio_indice"].apply(set).to_dict()

    colunas_resultado = {f"target_onset_h{h}": np.full(len(df), np.nan) for h in horizontes}

    for bairro, idx in df.groupby("codigo_bairro", sort=False).groups.items():
        idx = np.asarray(idx)
        indices_semana = df["indice_semana_global"].to_numpy()[idx]
        estado_arr = df["estado_alto_risco"].to_numpy()[idx]
        n_bairro = len(idx)

        onset_set = onset_por_bairro.get(bairro, set())
        eh_onset = np.isin(indices_semana, list(onset_set)).astype(int) if onset_set else np.zeros(n_bairro, dtype=int)
        indefinido = np.isnan(estado_arr).astype(int)

        onset_cum = np.concatenate([[0], np.cumsum(eh_onset)])
        indef_cum = np.concatenate([[0], np.cumsum(indefinido)])

        for h in horizontes:
            if n_bairro <= h:
                continue
            validos = np.arange(n_bairro - h)
            tem_onset = (onset_cum[validos + h + 1] - onset_cum[validos + 1]) > 0
            tem_indef = (indef_cum[validos + h + 1] - indef_cum[validos + 1]) > 0
            valores = np.where(tem_onset, 1.0, np.where(tem_indef, np.nan, 0.0))
            colunas_resultado[f"target_onset_h{h}"][idx[validos]] = valores

    for h in horizontes:
        df[f"target_onset_h{h}"] = colunas_resultado[f"target_onset_h{h}"]
    return df
