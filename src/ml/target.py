"""Definição de "surto"/"risco elevado" e do target de treino — isolada de
feature engineering e de treinamento, conforme pedido explicitamente (a
lógica do target não deve se misturar com a de features/modelo).

## Por que limiar histórico local + sazonal (Opção A + Opção C), não um
   corte absoluto (ex.: "casos > 10")

Verificado nos dados reais antes de decidir (ver
`reports/gold_analysis/README.md` e a exploração desta sessão): a escala de
casos de dengue por bairro varia em ordens de grandeza — COHAB acumula 6.817
casos em 13 anos contra 1 único caso em PAU FERRO. Nenhuma fonte do projeto
tem população por bairro (`incidencia_por_100k` não existe, ver
`src/gold/schema_gold_arboviroses_clima.py`), então não é possível normalizar
por incidência. Um corte absoluto (`casos > N`) seria arbitrário e
sistematicamente enviesado: N pequeno o suficiente para capturar surtos em
bairros pequenos dispararia constantemente em bairros grandes; N grande o
suficiente para ser raro em bairros grandes nunca dispararia nos pequenos.

A alternativa adotada usa **o próprio histórico do bairro** como
normalizador implícito (Opção A do pedido) — sem precisar de população —
comparado **contra o mesmo período do ano** em anos anteriores (Opção C),
porque a EDA já mostrou sazonalidade real e forte (pico médio na semana
epidemiológica 11, ver `reports/eda/README.md`). Não foi encontrado, nos
dados/fontes deste projeto, nenhum método epidemiológico oficial já
implementado e diretamente reutilizável (Opção D) além do próprio SINAN
bruto — a literatura de vigilância brasileira usa amplamente o "canal
endêmico" (comparação da semana atual contra a distribuição histórica da
mesma semana), que é exatamente o princípio A+C aplicado aqui.

## Regra

Para cada linha (`codigo_bairro`, `ano_epidemiologico`, `semana_epidemiologica`):

1. Reúne a distribuição de `casos` do MESMO bairro, em semanas dentro de uma
   janela sazonal de `±LARGURA_JANELA_SAZONAL_SEMANAS` em torno da semana
   alvo, usando **somente anos estritamente anteriores** ao ano da linha
   (nunca o próprio ano nem anos futuros — ver seção "Sem leakage" abaixo).
2. Se essa amostra tiver pelo menos `N_MIN_HISTORICO_SAZONAL` observações,
   o limiar é o percentil `PERCENTIL_LIMIAR_SURTO` dessa amostra
   (`tipo_limiar="sazonal"`).
3. Senão, cai para a distribuição geral do bairro (todas as semanas,
   também só anos anteriores). Se essa tiver pelo menos
   `N_MIN_HISTORICO_GERAL` observações, o limiar é o mesmo percentil dessa
   amostra maior, porém sem controle sazonal (`tipo_limiar="geral"`).
4. Senão (bairro com pouco histórico, ou primeiros anos da série — ver
   `README` da etapa para a contagem real), o estado fica **indefinido**
   (`tipo_limiar="indefinido"`, `estado_alto_risco=NaN`) — nunca é forçado
   a 0 ou 1 sem base estatística. Linhas indefinidas são excluídas do
   dataset de treino/avaliação (ver `dataset.py`), e contadas explicitamente
   no relatório.

`estado_alto_risco = 1` se `casos > limiar_historico_local`, `0` caso
contrário, `NaN` se indefinido.

## Tratamento de semanas 52/53 e virada de ano

A janela sazonal usa `semana_epidemiologica` (1-53) **sem wraparound**:
para uma semana alvo próxima da borda (ex.: semana 1 ou semana 53), a janela
é truncada (`max(1, semana-largura)` a `min(53, semana+largura)`) em vez de
"dar a volta" para o fim/início do ano anterior/seguinte. Isso reduz
ligeiramente o tamanho da amostra sazonal perto das bordas do ano
epidemiológico, mas evita a complexidade (e o risco de erro sutil) de
aritmética circular sobre um calendário que já tem anos de 52 **ou** 53
semanas (`total_semanas_epidemiologicas`, `src/gold/epidemiologia.py`).
Dado que a janela sazonal (`±2` semanas) já é pequena frente ao total de 53,
o efeito prático é marginal — documentado, não escondido.

## Sem leakage na definição do target

O limiar de uma linha do ano Y usa **apenas** dados de anos `< Y` — nunca do
próprio ano Y nem de anos posteriores. Isso é deliberado: o objetivo é que o
limiar seja **calculável no momento em que a semana Y ainda não aconteceu**
(reprodutível operacionalmente), e evita que o julgamento de "isso foi um
surto" para um ano antigo dependa de dados de anos futuros (ex.: usar 2015
inteiro, incluindo a própria epidemia, para decidir se uma semana de 2013 foi
"alta"). Testado explicitamente em `tests/test_ml_target.py`
(`test_limiar_nao_usa_anos_futuros_nem_o_proprio_ano`).

Isso é diferente da regra de leakage entre feature(t) e target(t+horizonte)
(ver `dataset.py`) — aqui a preocupação é apenas com que anos alimentam o
LIMIAR, não com a relação feature/target de uma linha de treino.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LARGURA_JANELA_SAZONAL_SEMANAS = 2
PERCENTIL_LIMIAR_SURTO = 90
N_MIN_HISTORICO_SAZONAL = 15
N_MIN_HISTORICO_GERAL = 20

COLUNAS_ESTADO = (
    "limiar_historico_local",
    "tipo_limiar",
    "n_historico_usado",
    "estado_alto_risco",
    "media_historica_semana_exata",
    "std_historica_semana_exata",
    "n_historico_semana_exata",
)


def agregar_semanal_agravo(df_gold: pd.DataFrame, agravo: str) -> pd.DataFrame:
    """Recorta a Gold para um único agravo, no grão que já é nativo dela
    (`bairro x semana epidemiológica`, uma linha por agravo). Não agrega
    nada — a Gold já materializa o grão completo (`casos=0` incluso)."""
    colunas = [
        "codigo_bairro",
        "nome_bairro",
        "agravo",
        "ano_epidemiologico",
        "semana_epidemiologica",
        "semana_epi_data_inicio",
        "semana_epi_data_fim",
        "casos",
        "area_km2",
        "codigo_rpa",
        "codigo_microrregiao",
        "centroide_lat",
        "centroide_lon",
        "dias_com_dado_valido_semana",
        "precipitacao_total_semana_mm",
        "precipitacao_media_diaria_mm",
        "precipitacao_maxima_diaria_mm",
        "dias_com_chuva",
        "completude_climatica_semana",
        "chuva_7d_mm",
        "chuva_14d_mm",
        "chuva_21d_mm",
        "chuva_28d_mm",
        "dias_com_dado_valido_7d",
        "dias_com_dado_valido_28d",
    ]
    colunas_existentes = [c for c in colunas if c in df_gold.columns]
    df = df_gold.loc[df_gold["agravo"] == agravo, colunas_existentes].copy()
    return df.sort_values(["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]).reset_index(drop=True)


def calcular_estado_alto_risco(df_semanal: pd.DataFrame) -> pd.DataFrame:
    """Adiciona `COLUNAS_ESTADO` a `df_semanal` (uma linha por bairro x
    semana epidemiológica, já filtrada para um único agravo — ver
    `agregar_semanal_agravo`). Não modifica `df_semanal` no lugar."""
    df = df_semanal.sort_values(["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]).reset_index(
        drop=True
    )
    n = len(df)
    limiares = np.full(n, np.nan)
    tipos = np.array(["indefinido"] * n, dtype=object)
    n_hist = np.zeros(n, dtype=int)
    media_semana_exata = np.full(n, np.nan)
    std_semana_exata = np.full(n, np.nan)
    n_hist_semana_exata = np.zeros(n, dtype=int)

    for _, idx in df.groupby("codigo_bairro", sort=False).groups.items():
        idx = np.asarray(idx)
        casos_arr = df["casos"].to_numpy()[idx]
        semanas_arr = df["semana_epidemiologica"].to_numpy()[idx]
        anos_arr = df["ano_epidemiologico"].to_numpy()[idx]

        for pos_local in range(len(idx)):
            semana_alvo = semanas_arr[pos_local]
            ano_alvo = anos_arr[pos_local]
            pos_global = idx[pos_local]

            passado = anos_arr < ano_alvo

            lo = max(1, semana_alvo - LARGURA_JANELA_SAZONAL_SEMANAS)
            hi = min(53, semana_alvo + LARGURA_JANELA_SAZONAL_SEMANAS)
            mask_sazonal = passado & (semanas_arr >= lo) & (semanas_arr <= hi)
            ref_sazonal = casos_arr[mask_sazonal]

            mask_exata = passado & (semanas_arr == semana_alvo)
            ref_exata = casos_arr[mask_exata]
            if len(ref_exata) > 0:
                media_semana_exata[pos_global] = float(np.mean(ref_exata))
                n_hist_semana_exata[pos_global] = len(ref_exata)
                # ddof=0 (populacional): amostra sazonal costuma ser pequena
                # (poucos anos anteriores); std amostral (ddof=1) com n=1
                # daria NaN e quebraria o z-score logo nos primeiros anos
                # utilizáveis -- ver `features.py::z_score_historico_local`.
                std_semana_exata[pos_global] = float(np.std(ref_exata, ddof=0))

            if len(ref_sazonal) >= N_MIN_HISTORICO_SAZONAL:
                limiares[pos_global] = np.percentile(ref_sazonal, PERCENTIL_LIMIAR_SURTO)
                tipos[pos_global] = "sazonal"
                n_hist[pos_global] = len(ref_sazonal)
                continue

            ref_geral = casos_arr[passado]
            if len(ref_geral) >= N_MIN_HISTORICO_GERAL:
                limiares[pos_global] = np.percentile(ref_geral, PERCENTIL_LIMIAR_SURTO)
                tipos[pos_global] = "geral"
                n_hist[pos_global] = len(ref_geral)
            else:
                tipos[pos_global] = "indefinido"
                n_hist[pos_global] = len(ref_geral)

    df["limiar_historico_local"] = limiares
    df["tipo_limiar"] = tipos
    df["n_historico_usado"] = n_hist
    df["media_historica_semana_exata"] = media_semana_exata
    df["std_historica_semana_exata"] = std_semana_exata
    df["n_historico_semana_exata"] = n_hist_semana_exata
    df["estado_alto_risco"] = np.where(
        df["tipo_limiar"].to_numpy() == "indefinido",
        np.nan,
        (df["casos"].to_numpy() > df["limiar_historico_local"].to_numpy()).astype(float),
    )
    return df


def calcular_estado_alto_risco_v2_experimental(df_estado: pd.DataFrame) -> pd.DataFrame:
    """Definição ALTERNATIVA de "surto" — **experimento comparável, não
    substitui o target oficial** (`estado_alto_risco`, calculado por
    `calcular_estado_alto_risco` acima). Usada só para diagnóstico (etapa de
    otimização, ver `reports/ml/dengue_early_warning_optimization.md`,
    seção "target alternativo").

    Combina anomalia sazonal (`casos_t > média histórica da mesma semana`,
    mais permissivo que o P90 usado no target oficial) **com** crescimento
    sustentado (`casos_t > casos_t-1 > casos_t-2`, 2 semanas consecutivas —
    mesmo espírito do `baselines.baseline_crescimento_recente`, mas com
    `n_semanas=3`; aqui simplificado para 2 para não exigir 4 lags só para
    o diagnóstico).

    ## Por que isso NÃO é adotado como target principal sem mais evidência
    (risco de "target auto-realizável", seção 12 do pedido)

    Se este target fosse adotado e o modelo treinado incluísse features de
    crescimento/momentum (`delta_1s`, `n_semanas_consecutivas_crescimento`,
    ver `features.py`), o modelo estaria essencialmente aprendendo a
    reproduzir a PRÓPRIA definição do target a partir de uma feature quase
    idêntica a ela — não estaria "antecipando" nada, só recalculando a
    regra que já define o evento. Por isso esta função existe separada do
    pipeline de treino: serve para comparar propriedades descritivas
    (quantidade de eventos, duração, sobreposição com o target oficial,
    estabilidade por ano) — nunca para re-treinar o modelo principal com
    momentum como feature E este target ao mesmo tempo sem controlar esse
    risco explicitamente.

    Requer que `df_estado` já tenha passado por `calcular_estado_alto_risco`
    (usa `media_historica_semana_exata` calculada lá, sem recalcular)."""
    df = df_estado.sort_values(["codigo_bairro", "ano_epidemiologico", "semana_epidemiologica"]).reset_index(
        drop=True
    )
    grp_casos = df.groupby("codigo_bairro", sort=False)["casos"]
    casos_t_menos_1 = grp_casos.shift(1)
    casos_t_menos_2 = grp_casos.shift(2)

    crescimento_2s = (df["casos"] > casos_t_menos_1) & (casos_t_menos_1 > casos_t_menos_2)
    anomalia_sazonal = df["casos"] > df["media_historica_semana_exata"]
    indefinido = df["media_historica_semana_exata"].isna() | casos_t_menos_2.isna()

    df["estado_alto_risco_v2_experimental"] = np.where(
        indefinido,
        np.nan,
        (anomalia_sazonal & crescimento_2s).astype(float),
    )
    return df
