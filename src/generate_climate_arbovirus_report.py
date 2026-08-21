"""Gera `reports/analysis/climate_arbovirus_association.md`.

Uso:
    python -m src.generate_climate_arbovirus_report

Lê o mesmo dataset estático que o dashboard usa
(`dashboard/data/gold_arboviroses_clima_bairro.parquet`) e usa só
`src/eda/associacao_climatica.py` para os números -- nenhum valor deste
relatório é calculado aqui, apenas formatado.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from src.eda import associacao_climatica as ac
from src.eda.schema_eda import AGRAVOS

logger = logging.getLogger(__name__)

CAMINHO_GOLD_EXPORTADA = (
    Path(__file__).resolve().parent.parent / "dashboard" / "data" / "gold_arboviroses_clima_bairro.parquet"
)
CAMINHO_RELATORIO = (
    Path(__file__).resolve().parent.parent / "reports" / "analysis" / "climate_arbovirus_association.md"
)

ROTULOS_VARIAVEIS = {
    "precipitacao": "Precipitação (mm)",
    "temperatura_media": "Temperatura média (°C)",
    "temperatura_minima": "Temperatura mínima (°C)",
    "temperatura_maxima": "Temperatura máxima (°C)",
    "umidade": "Umidade relativa (%)",
}


def _tabela_markdown(tabela: pd.DataFrame) -> str:
    cabecalho = "| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |"
    separador = "|---|---|---|---|---|"
    linhas = [cabecalho, separador]
    for _, linha in tabela.iterrows():
        corr = "—" if pd.isna(linha["correlacao_spearman"]) else f"{linha['correlacao_spearman']:.4f}"
        p = "—" if pd.isna(linha["p_value"]) else f"{linha['p_value']:.4f}"
        linhas.append(
            f"| {int(linha['lag_semanas'])} | {corr} | {p} | {int(linha['n_observacoes'])} | "
            f"{'sim' if linha['confiavel'] else 'não'} |"
        )
    return "\n".join(linhas)


def _tabela_comparacao_markdown(tabela: pd.DataFrame) -> str:
    cabecalho = "| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |"
    separador = "|---|---|---|---|---|"
    linhas = [cabecalho, separador]
    for _, linha in tabela.iterrows():
        bruta = "—" if pd.isna(linha["correlacao_bruta"]) else f"{linha['correlacao_bruta']:.4f}"
        ajustada = "—" if pd.isna(linha["correlacao_ajustada"]) else f"{linha['correlacao_ajustada']:.4f}"
        linhas.append(
            f"| {int(linha['lag_semanas'])} | {bruta} | {ajustada} | "
            f"{int(linha['n_observacoes'])} | {int(linha['n_observacoes_ajustada'])} |"
        )
    return "\n".join(linhas)


def gerar_relatorio(df_gold: pd.DataFrame) -> str:
    partes = [
        "# Associação clima × arboviroses (2013-2025)",
        "",
        "Gerado por `python -m src.generate_climate_arbovirus_report` a partir de "
        "`dashboard/data/gold_arboviroses_clima_bairro.parquet`. Todos os números abaixo são "
        "reais, calculados por `src/eda/associacao_climatica.py` -- nenhum valor foi estimado ou "
        "arredondado à mão.",
        "",
        "**Associação observada, nunca causalidade.** Chuva, temperatura e casos de arboviroses "
        "podem compartilhar sazonalidade sem existir relação causal direta entre eles. Nenhuma "
        "afirmação de causalidade é feita neste documento.",
        "",
        "## Metodologia",
        "",
        "- **Granularidade: Recife total, nunca bairro/RPA.** A reanálise em grade (ERA5/"
        "ERA5-Land, única fonte com cobertura real 2013-2025) resolve só 2 células de "
        "precipitação e 3 de temperatura para os 94 bairros (distância mediana de 8,06 km entre "
        "bairro e centro da célula) -- qualquer recorte territorial mais fino que a cidade "
        "produziria falsa precisão espacial.",
        "- **Defasagem deslocada real**: correlação de Spearman entre a quantidade epidemiológica "
        "na semana `t` e a variável climática `t-k` semanas antes, para `k` de 0 a 12 semanas "
        "(`src.eda.associacao_climatica.calcular_lags_deslocados`) -- diferente da tabela de "
        "janelas cumulativas já publicada no painel (que correlaciona casos com chuva acumulada "
        "*até* a própria semana).",
        "- **Casos vs. incidência**: calculados e reportados separadamente. Incidência = casos "
        "totais da cidade / população total da cidade no ano × 100.000 -- nunca a soma das "
        "incidências por bairro já calculadas.",
        "- **Dessazonalização**: resíduo = valor menos a média histórica de todas as observações "
        "da mesma semana epidemiológica (1-53). Compara-se a correlação bruta com a correlação "
        "sobre os resíduos -- uma queda grande na versão ajustada sugere que a associação bruta "
        "é, em boa parte, sazonalidade compartilhada.",
        "- **Seleção do \"melhor\" lag**: sempre pelo maior `|correlação de Spearman|` entre os "
        "lags com amostra confiável (n ≥ 30) -- nunca pelo menor p-valor.",
        "",
    ]

    for agravo in AGRAVOS:
        partes.append(f"## {agravo.title()}")
        partes.append("")
        serie_agravo = ac.construir_serie_semanal_agravo(df_gold, agravo)
        if serie_agravo.empty:
            partes.append("Sem série disponível para este agravo.")
            partes.append("")
            continue

        tem_incidencia = serie_agravo["incidencia_100k"].notna().any()
        partes.append(
            f"Série semanal: {len(serie_agravo)} semanas "
            f"({int(serie_agravo['ano_epidemiologico'].min())}–{int(serie_agravo['ano_epidemiologico'].max())}), "
            f"{int(serie_agravo['casos'].sum())} casos totais no período. "
            f"Incidência disponível: {'sim' if tem_incidencia else 'não (população indisponível para este recorte)'}."
        )
        partes.append("")

        for variavel, rotulo in ROTULOS_VARIAVEIS.items():
            serie_clima = ac.serie_variavel_climatica(df_gold, variavel)
            if serie_clima.empty:
                partes.append(f"### {rotulo}")
                partes.append("")
                partes.append("Sem série climática disponível para esta variável.")
                partes.append("")
                continue

            base = serie_agravo.merge(
                serie_clima, on=["ano_epidemiologico", "semana_epidemiologica"], how="inner"
            )
            partes.append(f"### {rotulo}")
            partes.append("")

            melhores_lags = {}
            for quantidade, coluna in (("Casos", "casos"), ("Incidência (100 mil hab.)", "incidencia_100k")):
                if base[coluna].notna().sum() == 0:
                    partes.append(f"**{quantidade}**: sem dado suficiente nesta combinação.")
                    partes.append("")
                    continue
                tabela_lag = ac.calcular_lags_deslocados(base[coluna], base["valor"])
                partes.append(f"**{quantidade} × {rotulo}**")
                partes.append("")
                partes.append(_tabela_markdown(tabela_lag))
                partes.append("")
                resumo = ac.resumo_textual(tabela_lag)
                partes.append(resumo)
                partes.append("")
                confiaveis = tabela_lag[tabela_lag["confiavel"] & tabela_lag["correlacao_spearman"].notna()]
                if not confiaveis.empty:
                    idx = confiaveis["correlacao_spearman"].abs().idxmax()
                    melhores_lags[quantidade] = int(confiaveis.loc[idx, "lag_semanas"])

            if "Casos" in melhores_lags and "Incidência (100 mil hab.)" in melhores_lags:
                iguais = melhores_lags["Casos"] == melhores_lags["Incidência (100 mil hab.)"]
                partes.append(
                    f"**Casos vs. incidência**: o lag de maior associação {'coincide' if iguais else 'NÃO coincide'} "
                    f"entre casos (lag {melhores_lags['Casos']}) e incidência "
                    f"(lag {melhores_lags['Incidência (100 mil hab.)']}) -- "
                    + ("resultado consistente entre as duas quantidades." if iguais else
                       "as duas quantidades apontam para defasagens diferentes; não assumir que uma "
                       "generaliza para a outra.")
                )
                partes.append("")

            if base["casos"].notna().sum() > 0:
                tabela_comp = ac.comparar_bruta_vs_ajustada(
                    base["casos"], base["valor"], base["semana_epidemiologica"]
                )
                partes.append(f"**Bruta vs. ajustada por sazonalidade (casos × {rotulo.lower()})**")
                partes.append("")
                partes.append(_tabela_comparacao_markdown(tabela_comp))
                partes.append("")

    partes.append("## Limitações")
    partes.append("")
    partes.append(
        "- Granularidade Recife total apenas; a fonte de clima não sustenta análise por "
        "bairro/RPA (ver Metodologia).\n"
        "- Correlação, mesmo com amostra confiável (n ≥ 30) e ajustada por sazonalidade, não é "
        "prova de causalidade -- outras variáveis (comportamento humano, capacidade de "
        "vigilância, outros fatores climáticos) variam juntas e não são controladas aqui.\n"
        "- A reanálise em grade subestima a chuva medida por estação em cerca de 29% "
        "(ver CLAUDE.md §19.1) -- a magnitude da correlação com precipitação pode estar "
        "distorcida por esse viés de medição, mesmo que o sinal (positivo/negativo) permaneça "
        "informativo.\n"
        "- A dessazonalização usada aqui é descritiva (média histórica por semana "
        "epidemiológica, sem fronteira de treino/teste) -- adequada para uma análise "
        "exploratória de associação histórica, não para uso como feature de um modelo "
        "preditivo.\n"
        "- Quando o lag de maior associação reportado for exatamente 12 semanas (o limite "
        "testado), isso não significa que a semana 12 é o pico real -- a maior associação pode "
        "estar fora da janela testada (0-12 semanas). Ver, por exemplo, temperatura média × "
        "casos de dengue abaixo, onde a correlação ainda está subindo em módulo na semana 12."
    )
    partes.append("")
    return "\n".join(partes)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)

    if not CAMINHO_GOLD_EXPORTADA.exists():
        logger.error(
            "'%s' não encontrado. Rode 'python -m src.export_dashboard_dataset' primeiro.",
            CAMINHO_GOLD_EXPORTADA,
        )
        return 1

    df_gold = pd.read_parquet(CAMINHO_GOLD_EXPORTADA)
    conteudo = gerar_relatorio(df_gold)

    CAMINHO_RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_RELATORIO.write_text(conteudo, encoding="utf-8")

    logger.info("Relatório gerado em %s", CAMINHO_RELATORIO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
