"""Exporta a camada semântica para Power BI (`powerbi/data/`).

## Por que existe uma camada separada, e não "conecte no Parquet da Gold"

A Gold publicada (`gold_arboviroses_clima_bairro.parquet`) é uma tabela
larga (55 colunas) no grão bairro × semana × agravo — ótima para pandas,
ruim para um modelo Power BI: obrigaria o Power BI a lidar com colunas
climáticas repetidas 3× (uma por agravo, embora o clima seja o mesmo) e
não separa dimensão de fato. Este módulo faz **só reformatação** — nenhum
join/agregação/cálculo novo: cada tabela aqui é uma projeção/dedup de
colunas que já existem na Gold publicada ou no backtest de priorização já
gerado (`historical_priority_backtest.parquet`).

## Modelo estrela

```
dim_bairro (94)         dim_tempo (679+ semanas)     dim_agravo (3)
      \\                        |                        /
       \\                       |                       /
        +---- fact_epidemiologia_semanal (bairro×semana×agravo) ----+
        |
        +---- fact_clima_semanal (bairro×semana, sem agravo) -------+
        |
        +---- fact_priorizacao_backtest (bairro×semana-alvo) -------+

fact_associacao_climatica (agravo×variável×lag×tipo série×ajustada, sem bairro/tempo — só dim_agravo)
fact_projecao_2026 (agravo×semana, sem bairro — dim_agravo + dim_tempo, inclui 2026)

data_freshness (tabela solta, sem relacionamento — metadados de atualidade)
```

`fact_associacao_climatica` e `fact_projecao_2026` são fontes **novas e
opcionais** (item 28 do pedido de produto): a primeira sempre é calculada
(só depende da Gold, já obrigatória); a segunda só existe se
`dashboard/data/_forecast_2026.parquet` estiver presente — sua ausência
não bloqueia a exportação das tabelas originais.

`id_semana_epi = ano_epidemiologico * 100 + semana_epidemiologica` é a
chave surrogate de `dim_tempo`: Power BI relaciona por **uma** coluna, não
por chave composta, então usar `(ano, semana)` direto exigiria concatenar
uma chave de qualquer forma — mais simples já entregar pronta.

## Nenhuma probabilidade, nenhuma categoria de risco

`fact_priorizacao_backtest` repassa exatamente as colunas que já existem
no backtest do candidato congelado (`score_prioridade` = posição relativa,
nunca probabilidade) — nenhum campo novo é calculado aqui, e nada muda no
modelo/artefato de ML (regra de parada explícita: não retreinar, não
alterar `dengue_onset_ranking_candidate_v1`).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.eda import associacao_climatica as ac
from src.eda.clima_grade import gold_tem_clima_grade
from src.eda.schema_eda import AGRAVOS
from src.logging_config import configurar_logging

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_GOLD = RAIZ / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
CAMINHO_BACKTEST = RAIZ / "dashboard" / "data" / "historical_priority_backtest.parquet"
CAMINHO_FRESHNESS = RAIZ / "dashboard" / "data" / "_freshness.json"
#: Fontes NOVAS e opcionais (item 28 do pedido de produto). Tratadas como
#: degradação graciosa, não "fail closed" como as 3 fontes originais acima:
#: associação climática e projeção 2026 são extratos analíticos mais novos
#: e ainda evolutivos -- perdê-los não deveria bloquear a exportação das 7
#: tabelas originais, das quais o Power BI já depende em produção.
CAMINHO_FORECAST_2026 = RAIZ / "dashboard" / "data" / "_forecast_2026.parquet"
PASTA_SAIDA = RAIZ / "powerbi" / "data"

COLUNAS_DIM_BAIRRO = (
    "codigo_bairro", "nome_bairro", "codigo_rpa", "codigo_microrregiao",
    "area_km2", "centroide_lat", "centroide_lon",
)
COLUNAS_FATO_EPIDEMIOLOGIA = (
    "id_semana_epi", "codigo_bairro", "agravo", "casos",
    "populacao_bairro_ano", "tipo_populacao", "densidade_populacional_hab_km2",
    "incidencia_100k", "incidencia_4s_100k", "incidencia_8s_100k",
    "incidencia_12s_100k", "incidencia_anual_100k",
)
COLUNAS_FATO_CLIMA = (
    "id_semana_epi", "codigo_bairro",
    "fonte_clima", "codigo_estacao_clima", "distancia_estacao_km", "metodo_associacao_clima",
    "precipitacao_total_semana_mm", "precipitacao_media_diaria_mm", "precipitacao_maxima_diaria_mm",
    "dias_com_chuva", "dias_com_dado_valido_semana", "completude_climatica_semana",
    "chuva_7d_mm", "chuva_14d_mm", "chuva_21d_mm", "chuva_28d_mm",
    "dias_com_dado_valido_7d", "dias_com_dado_valido_28d",
    "fonte_clima_grade", "celula_grade_precipitacao", "celula_grade_temperatura",
    "precipitacao_semana_grade_mm", "precipitacao_2s_grade_mm", "precipitacao_3s_grade_mm",
    "precipitacao_4s_grade_mm", "temperatura_media_grade_c", "temperatura_minima_grade_c",
    "temperatura_maxima_grade_c", "umidade_relativa_media_grade_pct",
    "dias_validos_precipitacao_grade_semana", "dias_validos_temperatura_grade_semana",
    "cobertura_grade_semana",
)
COLUNAS_FATO_BACKTEST = (
    "id_semana_epi", "codigo_bairro", "cutoff_epi_year", "cutoff_epi_week",
    "ranking", "score_prioridade", "casos_t", "casos_proximas_3_semanas",
    "estado_alto_risco_t", "razao_limiar_historico", "taxa_crescimento_suavizada",
    "onset_real_em_3_semanas", "semanas_ate_onset",
    "ranking_baseline_razao_historica", "ranking_baseline_crescimento",
)
#: `fact_associacao_climatica`: grão agravo × variável × lag × tipo de série
#: (casos/incidência) × bruta-ou-ajustada -- SEM chave de bairro/tempo (só
#: Recife total, ver docstring de `src/eda/associacao_climatica.py`: a
#: grade climática só resolve 2-3 células para os 94 bairros, então nenhuma
#: tabela deste módulo finge granularidade territorial que a fonte não tem).
COLUNAS_FATO_ASSOCIACAO_CLIMATICA = (
    "agravo", "variavel_climatica", "tipo_serie", "ajustada_por_sazonalidade",
    "lag_semanas", "correlacao_spearman", "p_value", "n_observacoes", "confiavel",
)
#: `fact_projecao_2026`: grão agravo × semana (2013-2025 observado +
#: 2026 projetado, distinguidos por `is_observado`). Sem chave de bairro
#: (Recife total apenas, mesma regra de granularidade do forecast).
COLUNAS_FATO_PROJECAO_2026 = (
    "id_semana_epi", "agravo", "ano_epidemiologico", "semana_epidemiologica",
    "is_observado", "casos", "banda_80_inferior", "banda_80_superior",
    "banda_95_inferior", "banda_95_superior",
)


def _id_semana_epi(ano: pd.Series, semana: pd.Series) -> pd.Series:
    return (ano.astype("int64") * 100 + semana.astype("int64")).astype("int64")


def montar_dim_bairro(df_gold: pd.DataFrame) -> pd.DataFrame:
    return (
        df_gold[list(COLUNAS_DIM_BAIRRO)]
        .drop_duplicates("codigo_bairro")
        .sort_values("codigo_bairro")
        .reset_index(drop=True)
    )


def montar_dim_tempo(df_gold: pd.DataFrame, semanas_extra: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """`semanas_extra`, se passado, precisa ter `ano_epidemiologico`,
    `semana_epidemiologica`, `semana_epi_data_inicio`, `semana_epi_data_fim`
    -- usado para incluir as semanas de 2026 (que não existem na Gold
    observada) sem duplicar `id_semana_epi` com o que já vem da Gold."""
    dim = (
        df_gold[["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio", "semana_epi_data_fim"]]
        .drop_duplicates(subset=["ano_epidemiologico", "semana_epidemiologica"])
        .reset_index(drop=True)
    )
    if semanas_extra is not None and not semanas_extra.empty:
        dim = pd.concat(
            [dim, semanas_extra[list(dim.columns)]], ignore_index=True
        ).drop_duplicates(subset=["ano_epidemiologico", "semana_epidemiologica"])
    dim.insert(0, "id_semana_epi", _id_semana_epi(dim["ano_epidemiologico"], dim["semana_epidemiologica"]))
    return dim.sort_values("id_semana_epi").reset_index(drop=True)


def montar_semanas_2026_para_dim_tempo(df_forecast: pd.DataFrame) -> pd.DataFrame:
    """Deriva `semana_epi_data_fim` (domingo a sábado, +6 dias) das semanas
    de 2026 do artefato de forecast, que só carrega `semana_epi_data_inicio`
    -- reformatação simples, não um novo cálculo de calendário epidemiológico
    (esse já existe em `src/gold/epidemiologia.py`, usado por
    `src/forecast/projecao_2026.py` para gerar o próprio artefato)."""
    extra = (
        df_forecast[["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_inicio"]]
        .drop_duplicates(subset=["ano_epidemiologico", "semana_epidemiologica"])
        .copy()
    )
    extra["semana_epi_data_inicio"] = pd.to_datetime(extra["semana_epi_data_inicio"])
    extra["semana_epi_data_fim"] = extra["semana_epi_data_inicio"] + pd.Timedelta(days=6)
    return extra.reset_index(drop=True)


def montar_dim_agravo(df_gold: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"agravo": sorted(df_gold["agravo"].unique())})


def montar_fact_epidemiologia_semanal(df_gold: pd.DataFrame) -> pd.DataFrame:
    df = df_gold.copy()
    df["id_semana_epi"] = _id_semana_epi(df["ano_epidemiologico"], df["semana_epidemiologica"])
    return df[list(COLUNAS_FATO_EPIDEMIOLOGIA)].reset_index(drop=True)


def montar_fact_clima_semanal(df_gold: pd.DataFrame) -> pd.DataFrame:
    df = df_gold.copy()
    df["id_semana_epi"] = _id_semana_epi(df["ano_epidemiologico"], df["semana_epidemiologica"])
    # Grão bairro x semana (sem agravo): o clima é idêntico para os 3 agravos
    # da mesma semana no mesmo bairro -- manter em 3 linhas duplicaria sem
    # motivo e criaria um relacionamento many-to-many desnecessário.
    return (
        df[list(COLUNAS_FATO_CLIMA)]
        .drop_duplicates(subset=["id_semana_epi", "codigo_bairro"])
        .reset_index(drop=True)
    )


def montar_fact_priorizacao_backtest(df_backtest: pd.DataFrame) -> pd.DataFrame:
    df = df_backtest.copy()
    df["id_semana_epi"] = _id_semana_epi(df["ano_epidemiologico"], df["semana_epidemiologica"])
    return df[list(COLUNAS_FATO_BACKTEST)].reset_index(drop=True)


def montar_fact_associacao_climatica(df_gold: pd.DataFrame) -> pd.DataFrame:
    """Recalcula (nunca copia de relatório em Markdown) a associação por
    defasagem real de `src/eda/associacao_climatica.py` para os 3 agravos,
    5 variáveis climáticas, casos e incidência, bruta e ajustada por
    sazonalidade -- mesmas funções que alimentam
    `reports/analysis/climate_arbovirus_association.md` e a página
    "Clima × Arboviroses". Se a Gold recebida não tiver o bloco climático em
    grade (colunas `*_grade_*` ausentes ou incompletas), devolve a tabela
    vazia (com as colunas certas) em vez de propagar exceção — mesma
    filosofia de degradação graciosa do restante deste módulo."""
    if not gold_tem_clima_grade(df_gold):
        return pd.DataFrame(columns=list(COLUNAS_FATO_ASSOCIACAO_CLIMATICA))

    tabelas: list[pd.DataFrame] = []
    for agravo in AGRAVOS:
        serie_agravo = ac.construir_serie_semanal_agravo(df_gold, agravo)
        if serie_agravo.empty:
            continue
        for variavel in ac.VARIAVEIS_CLIMATICAS:
            try:
                serie_clima = ac.serie_variavel_climatica(df_gold, variavel)
            except KeyError:
                # coluna da grade para esta variável especificamente ausente
                # (ex.: Gold parcial/sintética) -- pula só esta variável.
                continue
            if serie_clima.empty or "valor" not in serie_clima.columns:
                continue
            base = serie_agravo.merge(
                serie_clima, on=["ano_epidemiologico", "semana_epidemiologica"], how="inner"
            )
            if base.empty:
                continue
            for tipo_serie, coluna_alvo in (("casos", "casos"), ("incidencia", "incidencia_100k")):
                if coluna_alvo not in base.columns or base[coluna_alvo].notna().sum() == 0:
                    continue
                combinacoes = (
                    (False, base[coluna_alvo], base["valor"]),
                    (
                        True,
                        ac.dessazonalizar(base[coluna_alvo], base["semana_epidemiologica"]),
                        ac.dessazonalizar(base["valor"], base["semana_epidemiologica"]),
                    ),
                )
                for ajustada, serie_alvo_calc, serie_clima_calc in combinacoes:
                    tabela = ac.calcular_lags_deslocados(serie_alvo_calc, serie_clima_calc)
                    tabela["agravo"] = agravo
                    tabela["variavel_climatica"] = variavel
                    tabela["tipo_serie"] = tipo_serie
                    tabela["ajustada_por_sazonalidade"] = ajustada
                    tabelas.append(tabela)

    if not tabelas:
        return pd.DataFrame(columns=list(COLUNAS_FATO_ASSOCIACAO_CLIMATICA))
    resultado = pd.concat(tabelas, ignore_index=True)
    return resultado[list(COLUNAS_FATO_ASSOCIACAO_CLIMATICA)]


def montar_fact_projecao_2026(df_forecast: pd.DataFrame) -> pd.DataFrame:
    """Reformata `dashboard/data/_forecast_2026.parquet` (observado +
    projetado, ver `src/generate_forecast_artifacts.py`) para o modelo
    estrela -- nenhum recálculo, só a chave surrogate de tempo."""
    df = df_forecast.copy()
    df["id_semana_epi"] = _id_semana_epi(df["ano_epidemiologico"], df["semana_epidemiologica"])
    return df[list(COLUNAS_FATO_PROJECAO_2026)].reset_index(drop=True)


def montar_data_freshness(bruto: dict[str, Any]) -> pd.DataFrame:
    linhas = []
    for nome, info in bruto.get("datasets", {}).items():
        linha = {k: v for k, v in info.items() if k != "detalhe"}
        linha["gerado_em"] = bruto.get("gerado_em")
        linhas.append(linha)
    return pd.DataFrame(linhas)


def montar_dataset_powerbi(
    df_gold: pd.DataFrame,
    df_backtest: pd.DataFrame,
    freshness_bruto: dict[str, Any],
    df_forecast: Optional[pd.DataFrame] = None,
) -> dict[str, pd.DataFrame]:
    """Núcleo puro: Gold publicada + backtest + freshness -> tabelas do
    modelo estrela. Nenhum I/O aqui (testável sem tocar disco).

    `fact_associacao_climatica` é sempre incluída (só depende da Gold, já
    obrigatória). `fact_projecao_2026` só é incluída quando `df_forecast`
    é passado -- o artefato de forecast é uma fonte nova e opcional
    (degradação graciosa, ver comentário de `CAMINHO_FORECAST_2026`);
    quando incluída, `dim_tempo` também passa a cobrir as semanas de 2026.
    """
    semanas_extra = montar_semanas_2026_para_dim_tempo(df_forecast) if df_forecast is not None else None
    tabelas = {
        "dim_bairro": montar_dim_bairro(df_gold),
        "dim_tempo": montar_dim_tempo(df_gold, semanas_extra=semanas_extra),
        "dim_agravo": montar_dim_agravo(df_gold),
        "fact_epidemiologia_semanal": montar_fact_epidemiologia_semanal(df_gold),
        "fact_clima_semanal": montar_fact_clima_semanal(df_gold),
        "fact_priorizacao_backtest": montar_fact_priorizacao_backtest(df_backtest),
        "fact_associacao_climatica": montar_fact_associacao_climatica(df_gold),
        "data_freshness": montar_data_freshness(freshness_bruto),
    }
    if df_forecast is not None:
        tabelas["fact_projecao_2026"] = montar_fact_projecao_2026(df_forecast)
    return tabelas


#: Número oficial de bairros do Recife (mesma constante de
#: `src/quality_gates.py::N_BAIRROS_ESPERADO`) — parametrizado na função
#: para permitir testes unitários com fixtures menores.
N_BAIRROS_ESPERADO = 94


def validar_star_schema(
    tabelas: dict[str, pd.DataFrame], n_bairros_esperado: int = N_BAIRROS_ESPERADO
) -> dict[str, Any]:
    """Portões de QA do star schema (seção 27 do pedido) — retorna métricas e
    levanta `ValueError` no primeiro problema crítico encontrado."""
    dim_bairro = tabelas["dim_bairro"]
    if dim_bairro["codigo_bairro"].nunique() != n_bairros_esperado:
        raise ValueError(
            f"dim_bairro: esperado {n_bairros_esperado} bairros, "
            f"encontrado {dim_bairro['codigo_bairro'].nunique()}"
        )
    if dim_bairro["codigo_bairro"].duplicated().any():
        raise ValueError("dim_bairro: codigo_bairro duplicado")

    dim_tempo = tabelas["dim_tempo"]
    if dim_tempo["id_semana_epi"].duplicated().any():
        raise ValueError("dim_tempo: id_semana_epi duplicado")

    dim_agravo = tabelas["dim_agravo"]
    if dim_agravo["agravo"].duplicated().any():
        raise ValueError("dim_agravo: agravo duplicado")

    codigos_bairro = set(dim_bairro["codigo_bairro"])
    ids_tempo = set(dim_tempo["id_semana_epi"])
    agravos = set(dim_agravo["agravo"])

    fato_epi = tabelas["fact_epidemiologia_semanal"]
    if not set(fato_epi["codigo_bairro"]).issubset(codigos_bairro):
        raise ValueError("fact_epidemiologia_semanal: codigo_bairro fora de dim_bairro")
    if not set(fato_epi["id_semana_epi"]).issubset(ids_tempo):
        raise ValueError("fact_epidemiologia_semanal: id_semana_epi fora de dim_tempo")
    if not set(fato_epi["agravo"]).issubset(agravos):
        raise ValueError("fact_epidemiologia_semanal: agravo fora de dim_agravo")
    if fato_epi.duplicated(subset=["id_semana_epi", "codigo_bairro", "agravo"]).any():
        raise ValueError("fact_epidemiologia_semanal: chave (semana, bairro, agravo) duplicada")
    if (fato_epi["casos"] < 0).any():
        raise ValueError("fact_epidemiologia_semanal: casos negativo")
    if (fato_epi["populacao_bairro_ano"].dropna() <= 0).any():
        raise ValueError("fact_epidemiologia_semanal: populacao_bairro_ano <= 0")

    fato_clima = tabelas["fact_clima_semanal"]
    if fato_clima.duplicated(subset=["id_semana_epi", "codigo_bairro"]).any():
        raise ValueError("fact_clima_semanal: chave (semana, bairro) duplicada")

    fato_backtest = tabelas["fact_priorizacao_backtest"]
    if not set(fato_backtest["codigo_bairro"]).issubset(codigos_bairro):
        raise ValueError("fact_priorizacao_backtest: codigo_bairro fora de dim_bairro")
    if not set(fato_backtest["id_semana_epi"]).issubset(ids_tempo):
        raise ValueError("fact_priorizacao_backtest: id_semana_epi fora de dim_tempo")

    metricas = {
        "n_bairros": int(dim_bairro["codigo_bairro"].nunique()),
        "n_semanas": int(dim_tempo["id_semana_epi"].nunique()),
        "n_agravos": int(dim_agravo["agravo"].nunique()),
        "linhas_fact_epidemiologia_semanal": int(len(fato_epi)),
        "linhas_fact_clima_semanal": int(len(fato_clima)),
        "linhas_fact_priorizacao_backtest": int(len(fato_backtest)),
        "integridade_referencial": "ok",
    }

    fato_associacao = tabelas.get("fact_associacao_climatica")
    if fato_associacao is not None:
        colunas_proibidas = {"probabilidade", "risco", "cor_risco", "categoria_risco"}
        if colunas_proibidas & set(fato_associacao.columns):
            raise ValueError("fact_associacao_climatica: coluna de probabilidade/risco não permitida")
        if not set(fato_associacao["agravo"]).issubset(agravos):
            raise ValueError("fact_associacao_climatica: agravo fora de dim_agravo")
        chave_associacao = ["agravo", "variavel_climatica", "tipo_serie", "ajustada_por_sazonalidade", "lag_semanas"]
        if fato_associacao.duplicated(subset=chave_associacao).any():
            raise ValueError("fact_associacao_climatica: chave duplicada")
        if not fato_associacao["lag_semanas"].between(0, 12).all():
            raise ValueError("fact_associacao_climatica: lag_semanas fora da faixa 0-12")
        if (fato_associacao["n_observacoes"] < 0).any():
            raise ValueError("fact_associacao_climatica: n_observacoes negativo")
        metricas["linhas_fact_associacao_climatica"] = int(len(fato_associacao))

    fato_projecao = tabelas.get("fact_projecao_2026")
    if fato_projecao is not None:
        colunas_proibidas = {"probabilidade", "risco", "cor_risco", "categoria_risco"}
        if colunas_proibidas & set(fato_projecao.columns):
            raise ValueError("fact_projecao_2026: coluna de probabilidade/risco não permitida")
        if not set(fato_projecao["agravo"]).issubset(agravos):
            raise ValueError("fact_projecao_2026: agravo fora de dim_agravo")
        if not set(fato_projecao["id_semana_epi"]).issubset(ids_tempo):
            raise ValueError("fact_projecao_2026: id_semana_epi fora de dim_tempo")
        if fato_projecao.duplicated(subset=["id_semana_epi", "agravo"]).any():
            raise ValueError("fact_projecao_2026: chave (semana, agravo) duplicada")
        if (fato_projecao["casos"] < 0).any():
            raise ValueError("fact_projecao_2026: casos negativo")
        metricas["linhas_fact_projecao_2026"] = int(len(fato_projecao))

    return metricas


def gravar_tabelas(tabelas: dict[str, pd.DataFrame], pasta_saida: Path = PASTA_SAIDA) -> list[str]:
    pasta_saida.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for nome, tabela in tabelas.items():
        caminho_parquet = pasta_saida / f"{nome}.parquet"
        tabela.to_parquet(caminho_parquet, engine="pyarrow", index=False)
        caminho_csv = pasta_saida / f"{nome}.csv"
        tabela.to_csv(caminho_csv, index=False, encoding="utf-8")
        arquivos.append(str(caminho_parquet.relative_to(RAIZ)))
        arquivos.append(str(caminho_csv.relative_to(RAIZ)))
    return arquivos


def main() -> int:
    configurar_logging()

    faltando = [str(p) for p in (CAMINHO_GOLD, CAMINHO_BACKTEST, CAMINHO_FRESHNESS) if not p.exists()]
    if faltando:
        logger.error("Arquivo(s) ausente(s): %s", faltando)
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD)
    df_backtest = pd.read_parquet(CAMINHO_BACKTEST)
    with open(CAMINHO_FRESHNESS, encoding="utf-8") as f:
        freshness_bruto = json.load(f)

    df_forecast: Optional[pd.DataFrame] = None
    if CAMINHO_FORECAST_2026.exists():
        df_forecast = pd.read_parquet(CAMINHO_FORECAST_2026)
    else:
        logger.warning(
            "'%s' não encontrado — exportando sem fact_projecao_2026 (degradação graciosa, "
            "as demais tabelas não são afetadas).", CAMINHO_FORECAST_2026,
        )

    tabelas = montar_dataset_powerbi(df_gold, df_backtest, freshness_bruto, df_forecast=df_forecast)

    try:
        metricas = validar_star_schema(tabelas)
    except ValueError as exc:
        logger.error("QA do star schema falhou — nada foi gravado: %s", exc)
        return 1

    arquivos = gravar_tabelas(tabelas)
    metricas["arquivos"] = arquivos

    print(json.dumps(metricas, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
