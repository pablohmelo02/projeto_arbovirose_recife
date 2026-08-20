"""Transformação Gold: `gold_arboviroses_clima_bairro`.

Integra Silver de arboviroses + território + clima no grão
`bairro × semana epidemiológica × agravo` (ver
`schema_gold_arboviroses_clima.py` para a justificativa completa de cada
decisão). Cada função devolve `(df, metricas)` com cardinalidade antes/depois
— nenhum join perde ou explode linhas silenciosamente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.gold.epidemiologia import (
    extrair_ano_semana,
    gerar_calendario_epidemiologico,
)
from src.gold.schema_gold_arboviroses_clima import (
    AGRAVOS,
    COLUNAS_GOLD_ARBOVIROSES_CLIMA,
    JANELAS_RETROSPECTIVAS_DIAS,
    VERSAO_SCHEMA_GOLD,
)
from src.silver.quality import limpar_texto


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# 1. Preparação dos casos: dedup, período epidemiológico, bairro oficial
# --------------------------------------------------------------------------


def remover_duplicatas_exatas(df_arboviroses: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove linhas 100% idênticas em todas as colunas de negócio (não
    lineage) — achado real: 5/162.537 nesta execução. Não deduplica por
    `id_notificacao` sozinho (não é chave única entre anos/agravos, ver
    schema.py do domínio)."""
    colunas_negocio = [c for c in df_arboviroses.columns if not c.startswith("_")]
    linhas_antes = len(df_arboviroses)
    df = df_arboviroses.drop_duplicates(subset=colunas_negocio)
    return df, linhas_antes - len(df)


def extrair_periodo_epidemiologico(df_arboviroses: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Deriva `ano_epidemiologico`/`semana_epidemiologica` de `semana_notificacao`
    (não de `ano_notificacao` — o ano "administrativo" da notificação pode
    divergir do ano epidemiológico da semana em casos de virada de ano;
    verificado nos dados reais: 131/162.462 casos com `semana_notificacao`
    válida têm essa divergência). Linhas sem `semana_notificacao` parseável
    são excluídas do grão semanal — contadas, nunca descartadas em
    silêncio."""
    linhas_antes = len(df_arboviroses)
    periodo = df_arboviroses["semana_notificacao"].map(extrair_ano_semana)
    sem_periodo = periodo.isna()

    df = df_arboviroses.loc[~sem_periodo].copy()
    df["ano_epidemiologico"] = [p[0] for p in periodo[~sem_periodo]]
    df["semana_epidemiologica"] = [p[1] for p in periodo[~sem_periodo]]

    metricas = {
        "linhas_antes": linhas_antes,
        "linhas_sem_semana_epidemiologica_valida": int(sem_periodo.sum()),
        "linhas_depois": len(df),
    }
    return df, metricas


def juntar_bairro_oficial(
    df_arboviroses: pd.DataFrame, gdf_bairros: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Junta arboviroses aos 94 bairros oficiais por `nome_bairro`
    normalizado — não por `codigo_bairro` (ver docstring do schema para a
    verificação real que descartou o código como chave). Linhas sem
    correspondência (nome nulo, ou nome fora dos 94 oficiais) são excluídas
    do grão espacial da Gold — contadas explicitamente, nunca silenciosas.
    """
    linhas_antes = len(df_arboviroses)
    bairros_oficiais = gdf_bairros[["codigo_bairro", "nome_bairro"]]

    df = df_arboviroses.copy()
    df["_nome_bairro_norm"] = df["nome_bairro"].map(limpar_texto)
    # o nome_bairro bruto da notificacao (grafia/caixa inconsistente) e'
    # descartado aqui de proposito -- o canonico e' o oficial de
    # bairros_oficiais, que entra no merge abaixo sem colisao de nome.
    df = df.drop(columns=["codigo_bairro", "nome_bairro"])

    sem_nome = df["_nome_bairro_norm"].isna()
    linhas_sem_nome = int(sem_nome.sum())

    df_valido = df.loc[~sem_nome].merge(
        bairros_oficiais, left_on="_nome_bairro_norm", right_on="nome_bairro", how="inner"
    )
    # cardinalidade: nome_bairro e' unico em bairros_oficiais (94/94, verificado
    # em schema_territorio.py), entao este merge e' many-to-one -- nunca
    # multiplica linhas de casos. Verificado abaixo, nao assumido.
    if len(df_valido) > len(df.loc[~sem_nome]):
        raise ValueError(
            "Join bairro oficial multiplicou linhas (many-to-many inesperado) — "
            f"antes={len(df.loc[~sem_nome])}, depois={len(df_valido)}"
        )

    linhas_nome_nao_oficial = len(df.loc[~sem_nome]) - len(df_valido)

    metricas = {
        "linhas_antes": linhas_antes,
        "linhas_sem_nome_bairro": linhas_sem_nome,
        "linhas_com_nome_fora_dos_94_oficiais": linhas_nome_nao_oficial,
        "linhas_depois": len(df_valido),
        "percentual_aproveitado": round(100 * len(df_valido) / linhas_antes, 2) if linhas_antes else 0.0,
    }
    return df_valido.drop(columns=["_nome_bairro_norm"]), metricas


# --------------------------------------------------------------------------
# 2. Agregação epidemiológica e materialização do grão completo
# --------------------------------------------------------------------------


def agregar_casos(df_arboviroses_preparado: pd.DataFrame) -> pd.DataFrame:
    """Agrega para o grão `codigo_bairro, nome_bairro, agravo, ano_epidemiologico,
    semana_epidemiologica` — `casos` = contagem de notificações (não de
    `id_notificacao` distinto, que não é chave única entre agravos/anos)."""
    agrupado = (
        df_arboviroses_preparado.groupby(
            ["codigo_bairro", "nome_bairro", "tipo_arbovirose", "ano_epidemiologico", "semana_epidemiologica"],
            observed=True,
        )
        .size()
        .reset_index(name="casos")
        .rename(columns={"tipo_arbovirose": "agravo"})
    )
    return agrupado


def materializar_grao_completo(
    df_casos: pd.DataFrame, gdf_bairros: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Expande para o produto cartesiano completo (94 bairros x todas as
    semanas epidemiológicas do intervalo real observado x 3 agravos),
    preenchendo `casos=0` onde não há notificação — decisão explícita (ver
    docstring do schema): ausência de notificação compulsória é `0` real,
    não dado ausente."""
    ano_min = int(df_casos["ano_epidemiologico"].min())
    ano_max = int(df_casos["ano_epidemiologico"].max())
    calendario = gerar_calendario_epidemiologico(ano_min, ano_max)

    bairros = gdf_bairros[["codigo_bairro", "nome_bairro"]].drop_duplicates()

    grao = bairros.merge(pd.DataFrame({"agravo": AGRAVOS}), how="cross").merge(calendario, how="cross")

    grao_completo = grao.merge(
        df_casos,
        on=["codigo_bairro", "nome_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica"],
        how="left",
    )
    grao_completo["casos"] = grao_completo["casos"].fillna(0).astype("int64")

    metricas = {
        "total_bairros": len(bairros),
        "total_agravos": len(AGRAVOS),
        "ano_epidemiologico_min": ano_min,
        "ano_epidemiologico_max": ano_max,
        "total_semanas_epidemiologicas": len(calendario),
        "linhas_grao_completo": len(grao_completo),
        "linhas_com_pelo_menos_1_caso": int((grao_completo["casos"] > 0).sum()),
        "linhas_com_zero_casos": int((grao_completo["casos"] == 0).sum()),
        "total_casos_preservados": int(df_casos["casos"].sum()),
        "total_casos_no_grao": int(grao_completo["casos"].sum()),
    }
    if metricas["total_casos_preservados"] != metricas["total_casos_no_grao"]:
        raise ValueError(
            "Materializacao do grao completo perdeu ou inventou casos: "
            f"{metricas['total_casos_preservados']} != {metricas['total_casos_no_grao']}"
        )
    return grao_completo, metricas


def juntar_atributos_territorio(df_grao: pd.DataFrame, gdf_bairros: pd.DataFrame) -> pd.DataFrame:
    """Adiciona os atributos territoriais (área, RPA, microrregião,
    centroide) por `codigo_bairro` — join many-to-one (94 bairros únicos em
    `gdf_bairros`), nunca multiplica linhas do grão. **Não inclui
    população/densidade**: não existe em nenhuma fonte deste projeto (ver
    docstring do schema) — não inventado aqui."""
    atributos = gdf_bairros[
        ["codigo_bairro", "area_km2", "codigo_rpa", "codigo_microrregiao", "centroide_lat", "centroide_lon"]
    ]
    linhas_antes = len(df_grao)
    df = df_grao.merge(atributos, on="codigo_bairro", how="left")
    if len(df) != linhas_antes:
        raise ValueError(
            f"Join de atributos territoriais alterou a cardinalidade: {linhas_antes} -> {len(df)}"
        )
    return df


# --------------------------------------------------------------------------
# 3. Features climáticas — sem leakage: nunca usa dado posterior a
#    `semana_epi_data_fim` da própria linha.
# --------------------------------------------------------------------------


def _construir_serie_diaria_estacao(
    df_clima_diario_estacao: pd.DataFrame, data_minima: pd.Timestamp, data_maxima: pd.Timestamp
) -> pd.DataFrame:
    """Reindexação diária contínua (com `NaN` nos dias sem leitura) de uma
    única estação, com janelas móveis retrospectivas pré-calculadas
    (`min_periods=1`: soma/conta só os dias com leitura real, nunca trata
    ausência como zero)."""
    serie = (
        df_clima_diario_estacao.groupby("data")["precipitacao_mm"].sum(min_count=1).sort_index()
    )
    indice_completo = pd.date_range(data_minima, data_maxima, freq="D")
    serie = serie.reindex(indice_completo)

    resultado = pd.DataFrame({"precipitacao_mm": serie})
    for janela in JANELAS_RETROSPECTIVAS_DIAS:
        resultado[f"chuva_{janela}d_mm"] = serie.rolling(window=janela, min_periods=1).sum()
        resultado[f"dias_com_dado_valido_{janela}d"] = serie.notna().rolling(window=janela, min_periods=1).sum()

    # A "propria semana" (inicio..fim) tem exatamente 7 dias — matematicamente
    # identico a janela retrospectiva de 7 dias terminando em `fim`. Reusa o
    # rolling(7) acima (`chuva_7d_mm`/`dias_com_dado_valido_7d`) em vez de
    # recalcular; so precisa de media/maxima/dias-com-chuva, que a janela
    # generica de 7d acima nao guarda.
    resultado["precipitacao_media_semana_mm"] = serie.rolling(window=7, min_periods=1).mean()
    resultado["precipitacao_maxima_semana_mm"] = serie.rolling(window=7, min_periods=1).max()
    # comparacao com NaN retorna False, nao NaN -- sem mascarar explicitamente,
    # uma semana com ZERO leituras validas contaria como "0 dias de chuva" em
    # vez de "sem dado", violando a regra missing != 0. Mascara pelo mesmo
    # `dias_com_dado_valido_7d` usado como fonte de verdade de completude.
    dias_com_chuva_bruto = (serie > 0).rolling(window=7, min_periods=1).sum()
    resultado["dias_com_chuva_semana"] = dias_com_chuva_bruto.where(resultado["dias_com_dado_valido_7d"] > 0)
    return resultado


def calcular_features_climaticas(
    df_grao: pd.DataFrame, df_bairro_estacao: pd.DataFrame, df_clima_diario: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Para cada linha do grão (bairro, ano_epi, semana_epi), calcula as
    features climáticas usando a estação atualmente associada ao bairro
    (Estratégia A, `silver_bairro_estacao` — associação única por bairro,
    aplicada retroativamente a todos os anos; ver limitação no relatório).

    Regra de leakage (testada explicitamente): toda feature de uma linha usa
    somente `data <= semana_epi_data_fim` da própria linha — as janelas
    retrospectivas são calculadas ANTES do merge, por estação, e o merge
    final busca o valor da janela EXATAMENTE em `semana_epi_data_fim` (nunca
    numa data posterior).
    """
    df = df_grao.merge(
        df_bairro_estacao[["codigo_bairro", "codigo_estacao", "fonte", "distancia_km", "metodo_associacao"]],
        on="codigo_bairro",
        how="left",
    ).rename(
        columns={
            "codigo_estacao": "codigo_estacao_clima",
            "fonte": "fonte_clima",
            "distancia_km": "distancia_estacao_km",
            "metodo_associacao": "metodo_associacao_clima",
        }
    )

    bairros_sem_estacao = (
        int(df["codigo_estacao_clima"].isna().groupby(df["codigo_bairro"]).any().sum()) if len(df) else 0
    )

    colunas_clima = [
        "precipitacao_total_semana_mm", "precipitacao_media_diaria_mm", "precipitacao_maxima_diaria_mm",
        "dias_com_chuva", "dias_com_dado_valido_semana", "completude_climatica_semana",
    ] + [f"chuva_{j}d_mm" for j in JANELAS_RETROSPECTIVAS_DIAS] + [
        "dias_com_dado_valido_7d", "dias_com_dado_valido_28d",
    ]
    for coluna in colunas_clima:
        df[coluna] = np.nan

    if not df_clima_diario.empty:
        data_minima_necessaria = df["semana_epi_data_inicio"].min() - pd.Timedelta(days=max(JANELAS_RETROSPECTIVAS_DIAS))
        data_maxima_necessaria = df["semana_epi_data_fim"].max()

        for (fonte, codigo_estacao), grupo_idx in df.groupby(["fonte_clima", "codigo_estacao_clima"], dropna=True).groups.items():
            clima_estacao = df_clima_diario[
                (df_clima_diario["fonte"] == fonte) & (df_clima_diario["codigo_estacao"] == codigo_estacao)
            ]
            if clima_estacao.empty:
                continue

            serie = _construir_serie_diaria_estacao(clima_estacao, data_minima_necessaria, data_maxima_necessaria)

            datas_fim = df.loc[grupo_idx, "semana_epi_data_fim"]
            # busca vetorizada: o valor de cada janela EXATAMENTE em `semana_epi_data_fim`
            # da linha -- nunca numa data posterior (regra de leakage, testada).
            valores_fim = serie.reindex(datas_fim.values)

            for janela in JANELAS_RETROSPECTIVAS_DIAS:
                df.loc[grupo_idx, f"chuva_{janela}d_mm"] = valores_fim[f"chuva_{janela}d_mm"].values
            df.loc[grupo_idx, "dias_com_dado_valido_7d"] = valores_fim["dias_com_dado_valido_7d"].values
            df.loc[grupo_idx, "dias_com_dado_valido_28d"] = valores_fim["dias_com_dado_valido_28d"].values

            # "propria semana" (inicio..fim, 7 dias exatos) e' matematicamente
            # identica a janela retrospectiva de 7 dias terminando em `fim` --
            # reusa os mesmos valores em vez de recalcular (ver docstring de
            # _construir_serie_diaria_estacao).
            df.loc[grupo_idx, "precipitacao_total_semana_mm"] = valores_fim["chuva_7d_mm"].values
            df.loc[grupo_idx, "dias_com_dado_valido_semana"] = valores_fim["dias_com_dado_valido_7d"].values
            df.loc[grupo_idx, "precipitacao_media_diaria_mm"] = valores_fim["precipitacao_media_semana_mm"].values
            df.loc[grupo_idx, "precipitacao_maxima_diaria_mm"] = valores_fim["precipitacao_maxima_semana_mm"].values
            df.loc[grupo_idx, "dias_com_chuva"] = valores_fim["dias_com_chuva_semana"].values

    # As contagens de dias (diferente dos valores de mm) sao sempre um fato
    # conhecido quando existe estacao associada, mesmo que essa estacao nao
    # tenha nenhuma leitura real (0 leituras validas e' uma contagem real, nao
    # um "nao sei"): preenche com 0 so onde ha estacao associada (nao onde o
    # bairro nao tem nenhuma estacao elegivel -- ai sim fica None, ver
    # `bairros_sem_estacao`).
    tem_estacao = df["codigo_estacao_clima"].notna()
    colunas_contagem = ["dias_com_dado_valido_semana", "dias_com_dado_valido_7d", "dias_com_dado_valido_28d", "dias_com_chuva"]
    for coluna in colunas_contagem:
        df.loc[tem_estacao & df[coluna].isna(), coluna] = 0

    df["completude_climatica_semana"] = (df["dias_com_dado_valido_semana"] / 7).round(3)

    linhas_com_clima_real = int(df["dias_com_dado_valido_semana"].fillna(0).gt(0).sum())
    metricas = {
        "bairros_sem_estacao_associada": bairros_sem_estacao,
        "linhas_com_alguma_feature_climatica_real": linhas_com_clima_real,
        "percentual_linhas_com_clima_real": round(100 * linhas_com_clima_real / len(df), 4) if len(df) else 0.0,
    }
    return df, metricas


# --------------------------------------------------------------------------
# 4. Orquestração (sem I/O — pipeline_gold_arboviroses_clima.py cuida disso)
# --------------------------------------------------------------------------


def montar_gold_arboviroses_clima(
    df_arboviroses: pd.DataFrame,
    gdf_bairros: pd.DataFrame,
    df_bairro_estacao: pd.DataFrame,
    df_clima_diario: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Orquestra ponta a ponta: dedup -> período epidemiológico -> bairro
    oficial -> agregação -> grão completo -> features climáticas -> schema
    final. Retorna a Gold pronta + métricas de cardinalidade de cada etapa
    (nenhuma perda/explosão de linha passa sem ser contada)."""
    processado_em = _agora()
    metricas: dict[str, Any] = {}

    df, n_duplicados = remover_duplicatas_exatas(df_arboviroses)
    metricas["duplicatas_exatas_removidas"] = n_duplicados

    df, metricas["periodo_epidemiologico"] = extrair_periodo_epidemiologico(df)
    df, metricas["join_bairro_oficial"] = juntar_bairro_oficial(df, gdf_bairros)

    df_casos = agregar_casos(df)
    metricas["casos_agregados_linhas"] = len(df_casos)

    df_grao, metricas["grao_completo"] = materializar_grao_completo(df_casos, gdf_bairros)
    df_grao = juntar_atributos_territorio(df_grao, gdf_bairros)

    df_gold, metricas["features_climaticas"] = calcular_features_climaticas(
        df_grao, df_bairro_estacao, df_clima_diario
    )

    df_gold["versao_schema_gold"] = VERSAO_SCHEMA_GOLD
    df_gold["_processed_at"] = processado_em
    df_gold = df_gold[list(COLUNAS_GOLD_ARBOVIROSES_CLIMA)]

    chave = ["codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica"]
    duplicados_chave = df_gold.duplicated(subset=chave).sum()
    if duplicados_chave:
        raise ValueError(f"Chave da Gold duplicada: {duplicados_chave} linhas — grão quebrado.")
    metricas["chave_gold_unica"] = True
    metricas["total_linhas_gold"] = len(df_gold)

    return df_gold, metricas
