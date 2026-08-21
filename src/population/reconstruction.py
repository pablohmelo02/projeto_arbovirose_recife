"""Reconstrução da série 2010-2025 de população por bairro do Recife.

## Checkpoints reais usados (ver `data/bronze/populacao/*` para proveniência completa)

- **2010**: IBGE Censo 2010, via a tabela por bairro publicada pela
  Secretaria de Saúde do Recife/CIEVS (documento "População do Recife:
  Censo Demográfico 2010 e Projeções 2010 a 2017", dez/2017). Soma dos 94
  bairros bate **exatamente** com o total municipal oficial do Censo 2010
  (IBGE/SIDRA tabela 202: 1.537.704) — por isso é tratado como
  `CENSO_OBSERVADO`, não como estimativa.
- **2011-2017**: mesma fonte CIEVS — projeções ano a ano publicadas pela
  Secretaria de Saúde (partilha proporcional fixa do Censo 2010 aplicada às
  projeções municipais do IBGE). Usadas diretamente, sem reconstrução
  própria: é a melhor fonte institucional já disponível para esses anos,
  reconstruir por cima dela seria perder informação real.
- **2022**: IBGE Censo 2022, produto "Agregados por Bairro" (arquivo
  `Agregados_por_bairros_basico_BR`, filtrado para `CD_MUN=2611606`). Soma
  dos 94 bairros bate **exatamente** com o total municipal oficial
  (SIDRA tabela 9514: 1.488.920).
- **2018-2021**: sem checkpoint oficial por bairro. Reconstruído neste
  módulo por CAGR (taxa de crescimento composta) por bairro entre os
  checkpoints 2017 e 2022, reconciliado ano a ano ao total municipal oficial
  do IBGE (SIDRA tabela 6579) — ver `reconstruir_segmento_cagr`.
- **2023-2025**: sem checkpoint oficial por bairro (Censo 2022 é a última
  observação). Projeção pós-censo — três métodos comparados em
  `comparar_metodos_pos_censo`, o mais estável é escolhido
  automaticamente por `escolher_metodo_pos_censo` (nunca pelo que produz o
  número mais alto/baixo em algum bairro específico).

## Validação cruzada (obrigatória, sem trapacear)

`validar_reconstrucao_sem_checkpoint_intermediario` reconstrói 2010→2022
**sem usar o checkpoint de 2017**, prediz 2017 e compara com o valor real
publicado pela CIEVS — isso mede se o método de reconstrução (CAGR +
reconciliação municipal) seria confiável nos anos em que não há checkpoint
intermediário real (2018-2021), já que ali não há como comparar contra a
verdade.

## Chave de junção: nome normalizado, nunca fuzzy matching

Nenhuma fonte de população publica o `codigo_bairro` interno de
`silver_bairro_geo`. O join é por nome normalizado (maiúsculo, sem acento,
sem pontuação) mais um crosswalk de exatamente duas correções documentadas
(`CROSSWALK_NOMES`) — nunca por similaridade aproximada. Qualquer nome que
não bater depois disso é reportado, não descartado silenciosamente (ver
`_relatorio_discrepancias`).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.silver.schema_population import (
    TIPO_CENSO_OBSERVADO,
    TIPO_ESTIMATIVA_INTERCENSITARIA,
    TIPO_PROJECAO_POS_CENSO,
    VERSAO_SCHEMA_POPULACAO,
)

#: Correções pontuais de grafia entre fontes de população e `silver_bairro_geo`.
#: Cada entrada é uma decisão manual, verificada e citada — não é fuzzy matching.
CROSSWALK_NOMES = {
    "ALTO STA TERESINHA": "ALTO SANTA TEREZINHA",  # CIEVS 2010-2017
    "SITIO DOS PINTOS SAO BRAS": "SITIO DOS PINTOS",  # IBGE Censo 2022
}

ANOS_CIEVS = tuple(range(2010, 2018))
ANOS_GAP_INTERCENSITARIO = (2018, 2019, 2020, 2021)
ANOS_POS_CENSO = (2023, 2024, 2025)

LIMITE_POPULACAO_PEQUENA = 1000
LIMITE_CRESCIMENTO_ALTO_PCT = 50.0


def normalizar_nome_bairro(nome: str) -> str:
    """Maiúsculo, sem acento, sem pontuação, espaços colapsados; aplica o crosswalk."""
    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = " ".join(s.split())
    return CROSSWALK_NOMES.get(s, s)


def carregar_dimensao_bairro(caminho_gold_publicada: Path) -> pd.DataFrame:
    """`codigo_bairro`/`nome_bairro` oficiais (94 bairros), a partir da Gold já
    publicada — mesma fonte usada por `src/build_climate_grade.py` quando não
    há MinIO disponível (ver CLAUDE.md §9)."""
    df = pd.read_parquet(caminho_gold_publicada, columns=["codigo_bairro", "nome_bairro"])
    return df.drop_duplicates("codigo_bairro").reset_index(drop=True)


def _relatorio_discrepancias(nomes_faltantes: list[str], nomes_sobrando: list[str]) -> pd.DataFrame:
    linhas = [{"tipo": "bairro_territorio_sem_checkpoint", "nome": n} for n in nomes_faltantes]
    linhas += [{"tipo": "checkpoint_sem_bairro_territorio", "nome": n} for n in nomes_sobrando]
    return pd.DataFrame(linhas, columns=["tipo", "nome"])


def carregar_checkpoint_cievs(
    caminho_json: Path, df_territorio: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê `cievs_populacao_bairro_2010_2017.json` e junta aos 94 bairros oficiais.

    Devolve `(df[codigo_bairro, nome_bairro, ano, populacao], discrepancias)`.
    """
    with open(caminho_json, encoding="utf-8") as f:
        bruto = json.load(f)

    linhas = []
    for item in bruto["bairros"]:
        norm = item["nome_bairro_normalizado"]
        for ano_str, pop in item["populacao_por_ano"].items():
            linhas.append({"nome_bairro_fonte": norm, "ano": int(ano_str), "populacao": int(pop)})
    df = pd.DataFrame(linhas)

    nomes_fonte = sorted(df["nome_bairro_fonte"].unique())
    faltantes = sorted(set(df_territorio["nome_bairro"]) - set(nomes_fonte))
    sobrando = sorted(set(nomes_fonte) - set(df_territorio["nome_bairro"]))
    discrepancias = _relatorio_discrepancias(faltantes, sobrando)

    juntado = df_territorio.merge(df, left_on="nome_bairro", right_on="nome_bairro_fonte", how="inner")
    return juntado[["codigo_bairro", "nome_bairro", "ano", "populacao"]], discrepancias


def carregar_checkpoint_censo2022(
    caminho_csv: Path, df_territorio: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê `censo2022_ibge_bairro_recife.csv` e junta aos 94 bairros oficiais."""
    df = pd.read_csv(caminho_csv, dtype=str)
    df["populacao"] = df["v0001"].astype(int)

    nomes_fonte = sorted(df["nome_bairro_normalizado"].unique())
    faltantes = sorted(set(df_territorio["nome_bairro"]) - set(nomes_fonte))
    sobrando = sorted(set(nomes_fonte) - set(df_territorio["nome_bairro"]))
    discrepancias = _relatorio_discrepancias(faltantes, sobrando)

    juntado = df_territorio.merge(
        df, left_on="nome_bairro", right_on="nome_bairro_normalizado", how="inner"
    )
    juntado["ano"] = 2022
    return juntado[["codigo_bairro", "nome_bairro", "ano", "populacao"]], discrepancias


def carregar_serie_municipal(caminho_json: Path) -> dict[int, float | None]:
    """Total municipal oficial por ano (IBGE/SIDRA). 2023 não tem publicação
    oficial (ano de transição pós-Censo 2022) — interpolado geometricamente
    entre 2022 e 2024, documentado explicitamente (nunca tratado como dado
    observado)."""
    with open(caminho_json, encoding="utf-8") as f:
        bruto = json.load(f)
    serie: dict[int, float | None] = {int(ano): info["valor"] for ano, info in bruto["series"].items()}
    if serie.get(2023) is None and serie.get(2022) and serie.get(2024):
        serie[2023] = (serie[2022] * serie[2024]) ** 0.5
    return serie


def reconstruir_segmento_cagr(
    pop_ancora_inicio: pd.Series,
    pop_ancora_fim: pd.Series,
    ano_inicio: int,
    ano_fim: int,
    anos_alvo: list[int],
    serie_municipal: dict[int, float | None],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """CAGR por bairro entre duas âncoras, reconciliado ano a ano ao total
    municipal oficial: `pop_final = pop_preliminar * (total_oficial / soma_preliminar)`.
    """
    n_anos_total = ano_fim - ano_inicio
    taxa = (pop_ancora_fim / pop_ancora_inicio) ** (1.0 / n_anos_total) - 1.0

    linhas = []
    fatores: dict[int, float] = {}
    for ano in anos_alvo:
        delta = ano - ano_inicio
        preliminar = pop_ancora_inicio * (1.0 + taxa) ** delta
        total_oficial = serie_municipal.get(ano)
        soma_preliminar = float(preliminar.sum())
        fator = (total_oficial / soma_preliminar) if total_oficial else 1.0
        final = preliminar * fator
        fatores[ano] = fator
        for codigo, valor in final.items():
            linhas.append(
                {
                    "codigo_bairro": codigo,
                    "ano": ano,
                    "populacao": valor,
                    "populacao_municipal_referencia": total_oficial,
                    "fator_reconciliacao": fator,
                }
            )
    df = pd.DataFrame(linhas)
    metricas = {
        "fatores_reconciliacao": fatores,
        "taxa_cagr_minima": float(taxa.min()),
        "taxa_cagr_maxima": float(taxa.max()),
        "taxa_cagr_mediana": float(taxa.median()),
    }
    return df, metricas


def validar_reconstrucao_sem_checkpoint_intermediario(
    pop_2010: pd.Series,
    pop_2022: pd.Series,
    pop_2017_real: pd.Series,
    serie_municipal: dict[int, float | None],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reconstrói 2010→2022 SEM usar o checkpoint de 2017 (CAGR direto de 12
    anos + reconciliação), prediz 2017 e compara com o valor real da CIEVS.

    Isso mede se o método (CAGR + reconciliação municipal) seria confiável
    nos anos 2018-2021, onde não há como comparar contra a verdade — ver
    seção 10 do pedido original.
    """
    df_pred, _ = reconstruir_segmento_cagr(pop_2010, pop_2022, 2010, 2022, [2017], serie_municipal)
    pred_2017 = df_pred.set_index("codigo_bairro")["populacao"]

    comparacao = pd.DataFrame(
        {
            "codigo_bairro": pred_2017.index,
            "populacao_2017_predita_sem_checkpoint": pred_2017.values,
            "populacao_2017_real_cievs": pop_2017_real.reindex(pred_2017.index).values,
        }
    )
    comparacao["erro_absoluto"] = (
        comparacao["populacao_2017_predita_sem_checkpoint"] - comparacao["populacao_2017_real_cievs"]
    ).abs()
    comparacao["erro_percentual"] = (
        100 * comparacao["erro_absoluto"] / comparacao["populacao_2017_real_cievs"]
    )
    comparacao["bias"] = (
        comparacao["populacao_2017_predita_sem_checkpoint"] - comparacao["populacao_2017_real_cievs"]
    )

    pior = comparacao.loc[comparacao["erro_percentual"].idxmax()]
    metricas = {
        "mae": float(comparacao["erro_absoluto"].mean()),
        "mape_pct": float(comparacao["erro_percentual"].mean()),
        "bias_medio": float(comparacao["bias"].mean()),
        "erro_percentual_maximo": float(pior["erro_percentual"]),
        "bairro_maior_erro_percentual": str(pior["codigo_bairro"]),
        "n_bairros": int(len(comparacao)),
    }
    return comparacao, metricas


def identificar_areas_atipicas(
    pop_2010: pd.Series, pop_2022: pd.Series, limite_pequeno: int = LIMITE_POPULACAO_PEQUENA
) -> pd.DataFrame:
    """Bairros pequenos, com crescimento muito alto ou com redução
    populacional entre 2010 e 2022 — reportados, nunca suavizados (seção 11
    do pedido)."""
    pop_2022_alinhada = pop_2022.reindex(pop_2010.index)
    variacao_pct = 100 * (pop_2022_alinhada - pop_2010) / pop_2010
    df = pd.DataFrame(
        {
            "codigo_bairro": pop_2010.index,
            "populacao_2010": pop_2010.values,
            "populacao_2022": pop_2022_alinhada.values,
            "variacao_pct_2010_2022": variacao_pct.values,
        }
    )
    df["muito_pequeno_2022"] = df["populacao_2022"] < limite_pequeno
    df["crescimento_muito_alto"] = df["variacao_pct_2010_2022"] > LIMITE_CRESCIMENTO_ALTO_PCT
    df["reducao_populacional"] = df["variacao_pct_2010_2022"] < 0
    atipicos = df[df["muito_pequeno_2022"] | df["crescimento_muito_alto"] | df["reducao_populacional"]]
    return atipicos.sort_values("variacao_pct_2010_2022").reset_index(drop=True)


def _dispersao_crescimento(df_serie_anos: pd.DataFrame) -> float:
    """Média (entre anos) do desvio-padrão (entre bairros) da taxa de
    crescimento ano a ano implícita pelo método — proxy de estabilidade."""
    crescimento = df_serie_anos.pct_change(axis=1).iloc[:, 1:]
    return float(crescimento.std(axis=0).mean())


def comparar_metodos_pos_censo(
    pop_2010: pd.Series,
    pop_2017: pd.Series,
    pop_2022: pd.Series,
    serie_municipal: dict[int, float | None],
    anos_alvo: tuple[int, ...] = ANOS_POS_CENSO,
) -> dict[str, Any]:
    """Compara 3 métodos para projetar 2023-2025 (seção 8 do pedido) e
    escolhe o mais estável — nunca o que maximiza/minimiza algum bairro.

    Nota de honestidade metodológica: "manter participação de 2022" e
    "distribuir o crescimento municipal oficial proporcionalmente à
    participação 2022" são **algebricamente idênticos**
    (`share_i * total(ano) == pop_2022_i + share_i * (total(ano) - total_2022)`
    quando `share_i = pop_2022_i / total_2022`) — por isso aparecem aqui como
    um único método (A), não dois.
    """
    total_2022 = float(pop_2022.sum())
    share_2022 = pop_2022 / total_2022

    # Método A (= "D" do pedido, ver nota acima): participação de 2022 fixa.
    serie_a = {ano: share_2022 * serie_municipal[ano] for ano in anos_alvo}
    df_a = pd.DataFrame(serie_a)

    # Método B: extrapola o CAGR longo 2010->2022 (12 anos) por bairro, reconciliado.
    taxa_longa = (pop_2022 / pop_2010) ** (1 / 12) - 1
    bruto_b = {ano: pop_2022 * (1 + taxa_longa) ** (ano - 2022) for ano in anos_alvo}
    df_b = pd.DataFrame(
        {ano: bruto_b[ano] * (serie_municipal[ano] / bruto_b[ano].sum()) for ano in anos_alvo}
    )

    # Método C: extrapola o CAGR do último segmento 2017->2022 (5 anos) por bairro, reconciliado.
    taxa_recente = (pop_2022 / pop_2017) ** (1 / 5) - 1
    bruto_c = {ano: pop_2022 * (1 + taxa_recente) ** (ano - 2022) for ano in anos_alvo}
    df_c = pd.DataFrame(
        {ano: bruto_c[ano] * (serie_municipal[ano] / bruto_c[ano].sum()) for ano in anos_alvo}
    )

    series = {"A": df_a, "B": df_b, "C": df_c}
    metricas = {
        "metodo_a_participacao_fixa_2022": {
            "descricao": (
                "Mantem a participacao de cada bairro no Censo 2022, escalada pelo total "
                "municipal oficial do ano (identico algebricamente a distribuir o "
                "crescimento municipal proporcionalmente a participacao 2022)."
            ),
            "dispersao_crescimento_entre_bairros": _dispersao_crescimento(df_a),
        },
        "metodo_b_tendencia_longa_2010_2022": {
            "descricao": "Extrapola o CAGR de 12 anos (2010-2022) de cada bairro, reconciliado ao total municipal oficial.",
            "dispersao_crescimento_entre_bairros": _dispersao_crescimento(df_b),
        },
        "metodo_c_tendencia_recente_2017_2022": {
            "descricao": "Extrapola o CAGR do ultimo segmento (2017-2022) de cada bairro, reconciliado ao total municipal oficial.",
            "dispersao_crescimento_entre_bairros": _dispersao_crescimento(df_c),
        },
    }
    return {"series": series, "metricas": metricas}


def escolher_metodo_pos_censo(metricas: dict[str, Any]) -> str:
    """Escolhe o método com menor dispersão de crescimento entre bairros
    (mais estável) — critério declarado antes de olhar o resultado final."""
    return min(metricas, key=lambda chave: metricas[chave]["dispersao_crescimento_entre_bairros"])


_LETRA_METODO = {
    "metodo_a_participacao_fixa_2022": "A",
    "metodo_b_tendencia_longa_2010_2022": "B",
    "metodo_c_tendencia_recente_2017_2022": "C",
}


def construir_serie_populacao(
    caminho_cievs: Path,
    caminho_censo2022: Path,
    caminho_municipal: Path,
    df_territorio: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Orquestra a reconstrução completa 2010-2025 e devolve
    `(df_populacao_bairro_ano, metricas)`, no formato de
    `COLUNAS_SILVER_POPULACAO_BAIRRO_ANO`."""
    df_cievs, disc_cievs = carregar_checkpoint_cievs(caminho_cievs, df_territorio)
    df_censo2022, disc_2022 = carregar_checkpoint_censo2022(caminho_censo2022, df_territorio)
    serie_municipal = carregar_serie_municipal(caminho_municipal)
    nomes_por_codigo = df_territorio.set_index("codigo_bairro")["nome_bairro"]

    pop_2010 = df_cievs.loc[df_cievs["ano"] == 2010].set_index("codigo_bairro")["populacao"]
    pop_2017 = df_cievs.loc[df_cievs["ano"] == 2017].set_index("codigo_bairro")["populacao"]
    pop_2022 = df_censo2022.set_index("codigo_bairro")["populacao"]

    _, metricas_validacao = validar_reconstrucao_sem_checkpoint_intermediario(
        pop_2010, pop_2022, pop_2017, serie_municipal
    )
    areas_atipicas = identificar_areas_atipicas(pop_2010, pop_2022)

    linhas_finais: list[dict[str, Any]] = []

    for _, row in df_cievs.iterrows():
        ano = int(row["ano"])
        if ano == 2010:
            tipo, checkpoint_ant, checkpoint_pos = TIPO_CENSO_OBSERVADO, 2010, 2010
            fonte_base, metodo = "IBGE Censo 2010 (via CIEVS/Sesau Recife)", "censo_direto"
        elif ano == 2017:
            tipo, checkpoint_ant, checkpoint_pos = TIPO_ESTIMATIVA_INTERCENSITARIA, 2017, 2017
            fonte_base = "CIEVS/Secretaria de Saude do Recife (Dez/2017)"
            metodo = "participacao_proporcional_fixa_censo2010_cievs"
        else:
            tipo, checkpoint_ant, checkpoint_pos = TIPO_ESTIMATIVA_INTERCENSITARIA, 2010, 2017
            fonte_base = "CIEVS/Secretaria de Saude do Recife (Dez/2017)"
            metodo = "participacao_proporcional_fixa_censo2010_cievs"
        linhas_finais.append(
            {
                "codigo_bairro": row["codigo_bairro"],
                "nome_bairro": row["nome_bairro"],
                "ano": ano,
                "populacao": row["populacao"],
                "tipo_valor": tipo,
                "fonte_base": fonte_base,
                "metodo": metodo,
                "checkpoint_anterior": checkpoint_ant,
                "checkpoint_posterior": checkpoint_pos,
                "populacao_municipal_referencia": serie_municipal.get(ano),
                "fator_reconciliacao": 1.0,
            }
        )

    df_gap, metricas_gap = reconstruir_segmento_cagr(
        pop_2017, pop_2022, 2017, 2022, list(ANOS_GAP_INTERCENSITARIO), serie_municipal
    )
    for _, row in df_gap.iterrows():
        linhas_finais.append(
            {
                "codigo_bairro": row["codigo_bairro"],
                "nome_bairro": nomes_por_codigo.loc[row["codigo_bairro"]],
                "ano": int(row["ano"]),
                "populacao": row["populacao"],
                "tipo_valor": TIPO_ESTIMATIVA_INTERCENSITARIA,
                "fonte_base": "reconstrucao propria (CAGR 2017-2022 + reconciliacao municipal IBGE)",
                "metodo": "cagr_piecewise_reconciliado",
                "checkpoint_anterior": 2017,
                "checkpoint_posterior": 2022,
                "populacao_municipal_referencia": row["populacao_municipal_referencia"],
                "fator_reconciliacao": row["fator_reconciliacao"],
            }
        )

    for _, row in df_censo2022.iterrows():
        linhas_finais.append(
            {
                "codigo_bairro": row["codigo_bairro"],
                "nome_bairro": row["nome_bairro"],
                "ano": 2022,
                "populacao": row["populacao"],
                "tipo_valor": TIPO_CENSO_OBSERVADO,
                "fonte_base": "IBGE Censo 2022 (Agregados por Bairro)",
                "metodo": "censo_direto",
                "checkpoint_anterior": 2022,
                "checkpoint_posterior": 2022,
                "populacao_municipal_referencia": serie_municipal.get(2022),
                "fator_reconciliacao": 1.0,
            }
        )

    comparacao_pos_censo = comparar_metodos_pos_censo(pop_2010, pop_2017, pop_2022, serie_municipal)
    metodo_escolhido = escolher_metodo_pos_censo(comparacao_pos_censo["metricas"])
    df_escolhida = comparacao_pos_censo["series"][_LETRA_METODO[metodo_escolhido]]
    for ano in ANOS_POS_CENSO:
        for codigo, valor in df_escolhida[ano].items():
            linhas_finais.append(
                {
                    "codigo_bairro": codigo,
                    "nome_bairro": nomes_por_codigo.loc[codigo],
                    "ano": ano,
                    "populacao": valor,
                    "tipo_valor": TIPO_PROJECAO_POS_CENSO,
                    "fonte_base": f"projecao pos-censo ({metodo_escolhido})",
                    "metodo": metodo_escolhido,
                    "checkpoint_anterior": 2022,
                    "checkpoint_posterior": None,
                    "populacao_municipal_referencia": serie_municipal.get(ano),
                    "fator_reconciliacao": None,
                }
            )

    df_final = pd.DataFrame(linhas_finais)
    df_final["populacao"] = df_final["populacao"].round().astype("int64")
    df_final["versao_schema_populacao"] = VERSAO_SCHEMA_POPULACAO
    df_final["_processed_at"] = datetime.now(timezone.utc).isoformat()
    df_final = df_final.sort_values(["codigo_bairro", "ano"]).reset_index(drop=True)

    reconciliacao_por_ano = (
        df_final.groupby("ano")
        .agg(
            soma_bairros=("populacao", "sum"),
            populacao_municipal_referencia=("populacao_municipal_referencia", "first"),
        )
        .reset_index()
    )
    reconciliacao_por_ano["diferenca_absoluta"] = (
        reconciliacao_por_ano["soma_bairros"] - reconciliacao_por_ano["populacao_municipal_referencia"]
    )
    reconciliacao_por_ano["diferenca_percentual"] = (
        100
        * reconciliacao_por_ano["diferenca_absoluta"]
        / reconciliacao_por_ano["populacao_municipal_referencia"]
    ).round(4)

    metricas = {
        "n_bairros": int(df_final["codigo_bairro"].nunique()),
        "anos_cobertos": sorted(int(a) for a in df_final["ano"].unique()),
        "discrepancias_join_cievs": disc_cievs.to_dict("records"),
        "discrepancias_join_censo2022": disc_2022.to_dict("records"),
        "validacao_cruzada_2017_sem_checkpoint": metricas_validacao,
        "reconciliacao_segmento_2018_2021": metricas_gap,
        "comparacao_metodos_pos_censo": comparacao_pos_censo["metricas"],
        "metodo_pos_censo_escolhido": metodo_escolhido,
        "areas_atipicas": areas_atipicas.to_dict("records"),
        "reconciliacao_por_ano": reconciliacao_por_ano.to_dict("records"),
    }
    return df_final, metricas
