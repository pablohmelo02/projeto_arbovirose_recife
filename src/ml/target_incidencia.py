"""Target baseado em INCIDÊNCIA — mesma definição estatística de `target.py`
(limiar histórico-sazonal local, P90, só anos anteriores), aplicada sobre
`incidencia_100k` em vez de `casos`. Não duplica o algoritmo: reusa
`target.calcular_estado_alto_risco` por substituição temporária de coluna.

## Por que reusar em vez de reimplementar

O loop de `calcular_estado_alto_risco` (janela sazonal ±2 semanas, fallback
geral, mínimos de amostra, `NaN` quando indefinido) não depende
semanticamente de a variável ser "casos" — é um algoritmo genérico de
"limiar histórico-sazonal local sobre uma série". Reescrevê-lo para
incidência duplicaria ~70 linhas de lógica não-trivial e criaria risco de
divergência silenciosa entre as duas versões (ex.: uma correção de bug no
futuro que só é aplicada em uma das duas cópias). Em vez disso,
`calcular_estado_alto_risco_incidencia` troca a coluna de entrada por uma
cópia descartável, chama a função original **sem alteração**, e renomeia
só as colunas de SAÍDA — nunca toca em `target.py`.

## Nunca sobrescreve as colunas baseadas em casos

`agregar_semanal_agravo_com_populacao` mantém `casos` como está (para as
variantes "V1 features" e "casos + incidência" do experimento) e adiciona
as colunas de população/incidência que `target.agregar_semanal_agravo` não
inclui. As colunas de saída desta função usam sufixo `_incidencia` — nunca
sobrescrevem `limiar_historico_local`/`estado_alto_risco`/etc. (as versões
baseadas em casos, calculadas por `target.calcular_estado_alto_risco`,
continuam intactas no mesmo DataFrame).
"""
from __future__ import annotations

import pandas as pd

from src.ml.target import calcular_estado_alto_risco

COLUNAS_POPULACAO_INCIDENCIA = (
    "populacao_bairro_ano",
    "tipo_populacao",
    "densidade_populacional_hab_km2",
    "incidencia_100k",
    "incidencia_4s_100k",
    "incidencia_8s_100k",
    "incidencia_12s_100k",
    "incidencia_anual_100k",
)

#: Colunas de saída de `target.calcular_estado_alto_risco` — todas
#: dependentes da coluna de valor de entrada, por isso todas renomeadas
#: com sufixo `_incidencia` para nunca colidir com a versão baseada em
#: casos (que permanece no mesmo DataFrame, calculada separadamente).
_COLUNAS_SAIDA_ESTADO = (
    "limiar_historico_local",
    "tipo_limiar",
    "n_historico_usado",
    "estado_alto_risco",
    "media_historica_semana_exata",
    "std_historica_semana_exata",
    "n_historico_semana_exata",
)


def agregar_semanal_agravo_com_populacao(df_gold: pd.DataFrame, agravo: str) -> pd.DataFrame:
    """Como `target.agregar_semanal_agravo`, mas inclui também as colunas
    de população/incidência (ausentes na função original porque ela
    existia antes da Gold 1.2). Reusa a mesma função para as colunas que
    já cobre, só complementa."""
    from src.ml.target import agregar_semanal_agravo

    df_base = agregar_semanal_agravo(df_gold, agravo)
    colunas_pop_existentes = [c for c in COLUNAS_POPULACAO_INCIDENCIA if c in df_gold.columns]
    faltando = set(COLUNAS_POPULACAO_INCIDENCIA) - set(colunas_pop_existentes)
    if faltando:
        raise ValueError(
            f"Gold sem as colunas de população esperadas: {sorted(faltando)}. "
            "Rode 'python -m src.enrich_gold_populacao' antes."
        )
    chave = ["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]
    df_pop = df_gold.loc[df_gold["agravo"] == agravo, chave + colunas_pop_existentes]
    return df_base.merge(df_pop, on=chave, how="left", validate="one_to_one")


def calcular_estado_alto_risco_incidencia(
    df_semanal: pd.DataFrame, coluna_valor: str = "incidencia_100k"
) -> pd.DataFrame:
    """Aplica o algoritmo de `target.calcular_estado_alto_risco` sobre
    `coluna_valor` em vez de `casos`, devolvendo as mesmas colunas de
    saída com sufixo `_incidencia`. Não modifica `df_semanal`; as colunas
    baseadas em `casos` (se já presentes) não são tocadas."""
    entrada = df_semanal.copy()
    entrada["casos"] = df_semanal[coluna_valor]
    calculado = calcular_estado_alto_risco(entrada)

    saida = df_semanal.copy()
    for coluna in _COLUNAS_SAIDA_ESTADO:
        saida[f"{coluna}_incidencia"] = calculado[coluna].to_numpy()
    return saida
