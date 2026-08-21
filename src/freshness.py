"""Metadados de atualidade dos dados (*data freshness*) — cidadão de
primeira classe do produto.

## Por que isto existe

Um painel epidemiológico que não diz **até quando** os dados vão é
enganoso, mesmo que cada número individual esteja correto. Este módulo
produz um artefato reproduzível que responde, para cada conjunto de dados:

| campo | significado |
|---|---|
| `dataset` | nome do conjunto (epidemiologia, território, clima, modelo…) |
| `fonte` | de onde vem, em texto legível por um gestor |
| `ultima_atualizacao_fonte` | quando a FONTE publicou/alterou por último |
| `data_maxima_evento` | data do evento mais recente presente no dado |
| `semana_epi_maxima` | última semana epidemiológica coberta (`AAAA-SS`) |
| `pipeline_executado_em` | quando o nosso pipeline processou |
| `atraso_dias` | `hoje − data_maxima_evento` |
| `status` | `ATUAL`, `ATRASADO` ou `DESCONHECIDO` |

Nenhuma data é escrita à mão em texto de UI ou de relatório: tudo vem
daqui, derivado do dado real.

## Status — regra objetiva, não impressão

- `ATUAL`: `atraso_dias <= limiar_atual` do dataset.
- `ATRASADO`: passou do limiar. Não é erro: é o estado real de uma fonte
  oficial com publicação trimestral. A UI deve dizer isso com clareza, sem
  chamar o dado de "tempo real".
- `DESCONHECIDO`: não foi possível determinar (fonte fora do ar e sem
  metadado em cache). Nunca se assume "atual" por omissão.

## Consulta de rede é opcional

`ultima_atualizacao_fonte` do CKAN exige uma requisição HTTP. O produto
publicado **não** faz essa requisição em tempo de renderização — ele lê o
artefato `dashboard/data/_freshness.json` gerado pelo pipeline. Se a fonte
estiver fora do ar na hora de gerar, o campo fica `None` com
`status=DESCONHECIDO` e o restante do artefato continua válido.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

STATUS_ATUAL = "ATUAL"
STATUS_ATRASADO = "ATRASADO"
STATUS_DESCONHECIDO = "DESCONHECIDO"

#: Limiar de atraso, em dias, a partir do qual cada dataset deixa de ser
#: considerado "atual". Não são números arbitrários:
#:
#: - epidemiologia: a própria fonte declara periodicidade **trimestral**
#:   (metadado `Frequência de atualização` do CKAN). 120 dias = um trimestre
#:   com folga de um mês para o atraso de publicação.
#: - território: limites de bairro mudam raramente; 3 anos é generoso e
#:   suficiente para detectar um dataset abandonado.
#: - clima (estação e grade): séries diárias/telemetria; 30 dias já indica
#:   problema de coleta.
LIMIAR_ATRASO_DIAS = {
    "epidemiologia": 120,
    "territorio": 1095,
    "clima_estacao": 30,
    "clima_grade": 30,
}
LIMIAR_ATRASO_DIAS_PADRAO = 120

#: Quantas semanas epidemiológicas de atraso ainda permitem oferecer uma
#: priorização referente ao período **mais recente**.
#:
#: O modelo sinaliza o início de um episódio em `t+1..t+3`. Uma priorização
#: cujo instante de decisão `t` já esteja mais de 4 semanas no passado
#: aponta para uma janela-alvo inteiramente vencida — o gestor não pode
#: agir sobre ela. 4 semanas = horizonte (3) + 1 semana de folga.
LIMIAR_SEMANAS_PROJECAO_ATUAL = 4

MOTIVO_DADO_DESATUALIZADO = "epidemiological_data_stale"
MOTIVO_ARTEFATO_AUSENTE = "model_artifact_missing"
MOTIVO_ARTEFATO_INCOMPATIVEL = "model_artifact_incompatible"


@dataclass
class FreshnessDataset:
    dataset: str
    fonte: str
    ultima_atualizacao_fonte: Optional[str] = None
    data_maxima_evento: Optional[str] = None
    semana_epi_maxima: Optional[str] = None
    pipeline_executado_em: Optional[str] = None
    atraso_dias: Optional[int] = None
    status: str = STATUS_DESCONHECIDO
    limiar_atraso_dias: Optional[int] = None
    observacao: Optional[str] = None
    detalhe: dict[str, Any] = field(default_factory=dict)

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hoje() -> date:
    return datetime.now(timezone.utc).date()


def calcular_status(
    data_maxima_evento: Optional[str],
    chave_limiar: str,
    referencia: Optional[date] = None,
) -> tuple[Optional[int], str, int]:
    """Devolve `(atraso_dias, status, limiar_usado)`.

    `data_maxima_evento` ausente ou ilegível ⇒ `DESCONHECIDO` (nunca
    `ATUAL` por omissão)."""
    limiar = LIMIAR_ATRASO_DIAS.get(chave_limiar, LIMIAR_ATRASO_DIAS_PADRAO)
    if not data_maxima_evento:
        return None, STATUS_DESCONHECIDO, limiar
    try:
        maxima = date.fromisoformat(str(data_maxima_evento)[:10])
    except ValueError:
        return None, STATUS_DESCONHECIDO, limiar
    atraso = ((referencia or _hoje()) - maxima).days
    return atraso, (STATUS_ATUAL if atraso <= limiar else STATUS_ATRASADO), limiar


def formatar_semana_epi(ano: Optional[int], semana: Optional[int]) -> Optional[str]:
    """`AAAA-SS` — formato único usado em toda a UI. `None` se faltar
    qualquer das partes (nunca improvisa um valor parcial)."""
    if ano is None or semana is None:
        return None
    return f"{int(ano)}-{int(semana):02d}"


def freshness_epidemiologia(
    df_gold,
    ultima_atualizacao_fonte: Optional[str] = None,
    pipeline_executado_em: Optional[str] = None,
    fonte: str = "Portal de Dados Abertos do Recife (CKAN) — SINAN",
    referencia: Optional[date] = None,
) -> FreshnessDataset:
    """Deriva a atualidade epidemiológica da própria Gold: a semana
    epidemiológica mais recente **com dado**, e a data de fim dessa semana
    como `data_maxima_evento`."""
    import pandas as pd

    if df_gold is None or len(df_gold) == 0:
        return FreshnessDataset(
            dataset="epidemiologia", fonte=fonte,
            observacao="Gold vazia — atualidade indeterminada",
        )

    ultima = (
        df_gold[["ano_epidemiologico", "semana_epidemiologica", "semana_epi_data_fim"]]
        .sort_values(["ano_epidemiologico", "semana_epidemiologica"])
        .iloc[-1]
    )
    ano = int(ultima["ano_epidemiologico"])
    semana = int(ultima["semana_epidemiologica"])
    data_fim = pd.Timestamp(ultima["semana_epi_data_fim"]).date().isoformat()

    atraso, status, limiar = calcular_status(data_fim, "epidemiologia", referencia)
    return FreshnessDataset(
        dataset="epidemiologia",
        fonte=fonte,
        ultima_atualizacao_fonte=ultima_atualizacao_fonte,
        data_maxima_evento=data_fim,
        semana_epi_maxima=formatar_semana_epi(ano, semana),
        pipeline_executado_em=pipeline_executado_em,
        atraso_dias=atraso,
        status=status,
        limiar_atraso_dias=limiar,
        observacao=(
            "A disponibilidade do painel reflete o último período publicado pela fonte oficial."
        ),
        detalhe={
            "ano_epidemiologico_minimo": int(df_gold["ano_epidemiologico"].min()),
            "ano_epidemiologico_maximo": ano,
            "semanas_distintas": int(
                df_gold[["ano_epidemiologico", "semana_epidemiologica"]].drop_duplicates().shape[0]
            ),
            "bairros": int(df_gold["codigo_bairro"].nunique()),
            "agravos": sorted(df_gold["agravo"].dropna().unique().tolist()),
        },
    )


def freshness_clima_estacao(df_gold, referencia: Optional[date] = None) -> FreshnessDataset:
    """Atualidade do clima **de estação** (CEMADEN): última semana da Gold
    com pelo menos um dia de leitura real."""
    import pandas as pd

    fonte = "CEMADEN — rede de pluviômetros (estação física)"
    if df_gold is None or "dias_com_dado_valido_semana" not in getattr(df_gold, "columns", []):
        return FreshnessDataset(dataset="clima_estacao", fonte=fonte, observacao="coluna ausente na Gold")

    com_dado = df_gold[df_gold["dias_com_dado_valido_semana"].fillna(0) > 0]
    if com_dado.empty:
        return FreshnessDataset(
            dataset="clima_estacao", fonte=fonte,
            observacao="nenhuma linha com leitura real de estação",
        )
    ultima = com_dado.sort_values(["ano_epidemiologico", "semana_epidemiologica"]).iloc[-1]
    data_fim = pd.Timestamp(ultima["semana_epi_data_fim"]).date().isoformat()
    atraso, status, limiar = calcular_status(data_fim, "clima_estacao", referencia)
    return FreshnessDataset(
        dataset="clima_estacao",
        fonte=fonte,
        data_maxima_evento=data_fim,
        semana_epi_maxima=formatar_semana_epi(
            int(ultima["ano_epidemiologico"]), int(ultima["semana_epidemiologica"])
        ),
        atraso_dias=atraso,
        status=status,
        limiar_atraso_dias=limiar,
        detalhe={
            "linhas_com_leitura_real": int(len(com_dado)),
            "percentual_linhas": round(100 * len(com_dado) / len(df_gold), 4),
            "bairros_cobertos": int(com_dado["codigo_bairro"].nunique()),
            "anos_cobertos": sorted(int(a) for a in com_dado["ano_epidemiologico"].unique()),
        },
    )


def freshness_clima_grade(df_gold, referencia: Optional[date] = None) -> FreshnessDataset:
    """Atualidade do clima **em grade** (reanálise). Rotulada de forma que
    nunca possa ser lida como leitura de sensor."""
    import pandas as pd

    fonte = "ERA5 / ERA5-Land — reanálise em grade (0,25° precipitação · 0,10° temperatura)"
    colunas = getattr(df_gold, "columns", [])
    if df_gold is None or "dias_validos_precipitacao_grade_semana" not in colunas:
        return FreshnessDataset(
            dataset="clima_grade", fonte=fonte,
            observacao="Gold sem o bloco em grade (versão < 1.1)",
        )
    com_dado = df_gold[df_gold["dias_validos_precipitacao_grade_semana"].fillna(0) > 0]
    if com_dado.empty:
        return FreshnessDataset(dataset="clima_grade", fonte=fonte, observacao="nenhuma linha com valor em grade")
    ultima = com_dado.sort_values(["ano_epidemiologico", "semana_epidemiologica"]).iloc[-1]
    data_fim = pd.Timestamp(ultima["semana_epi_data_fim"]).date().isoformat()
    atraso, status, limiar = calcular_status(data_fim, "clima_grade", referencia)
    return FreshnessDataset(
        dataset="clima_grade",
        fonte=fonte,
        data_maxima_evento=data_fim,
        semana_epi_maxima=formatar_semana_epi(
            int(ultima["ano_epidemiologico"]), int(ultima["semana_epidemiologica"])
        ),
        atraso_dias=atraso,
        status=status,
        limiar_atraso_dias=limiar,
        observacao=(
            "Estimativa climática espacial derivada de reanálise em grade — não é leitura "
            "de estação meteorológica de bairro."
        ),
        detalhe={
            "percentual_linhas": round(100 * len(com_dado) / len(df_gold), 4),
            "celulas_precipitacao": int(com_dado["celula_grade_precipitacao"].nunique())
            if "celula_grade_precipitacao" in colunas else None,
            "celulas_temperatura": int(com_dado["celula_grade_temperatura"].nunique())
            if "celula_grade_temperatura" in colunas else None,
        },
    )


def freshness_territorio(df_gold, ultima_atualizacao_fonte: Optional[str] = None) -> FreshnessDataset:
    """Território não tem "evento" datado — a atualidade relevante é a da
    publicação da fonte. Sem essa informação, o status é `DESCONHECIDO`, não
    `ATUAL`."""
    fonte = "Portal de Dados Abertos do Recife (CKAN) — limites de bairros"
    n_bairros = int(df_gold["codigo_bairro"].nunique()) if df_gold is not None and len(df_gold) else None
    atraso, status, limiar = calcular_status(
        (ultima_atualizacao_fonte or "")[:10] or None, "territorio"
    )
    return FreshnessDataset(
        dataset="territorio",
        fonte=fonte,
        ultima_atualizacao_fonte=ultima_atualizacao_fonte,
        data_maxima_evento=(ultima_atualizacao_fonte or None),
        atraso_dias=atraso,
        status=status,
        limiar_atraso_dias=limiar,
        detalhe={"bairros": n_bairros},
    )


def freshness_modelo(metadados_modelo: Optional[dict[str, Any]]) -> FreshnessDataset:
    """Atualidade do artefato de ML: até que ano ele foi treinado e qual o
    último período que ele avaliou."""
    fonte = "modelo experimental de priorização territorial (dengue)"
    if not metadados_modelo:
        return FreshnessDataset(
            dataset="modelo", fonte=fonte,
            observacao="nenhum artefato de modelo encontrado",
        )
    return FreshnessDataset(
        dataset="modelo",
        fonte=fonte,
        ultima_atualizacao_fonte=metadados_modelo.get("created_at"),
        data_maxima_evento=metadados_modelo.get("data_cutoff"),
        semana_epi_maxima=metadados_modelo.get("cutoff_epi_week_formatada"),
        pipeline_executado_em=metadados_modelo.get("created_at"),
        status=STATUS_ATUAL if metadados_modelo.get("model_version") else STATUS_DESCONHECIDO,
        detalhe={
            "model_version": metadados_modelo.get("model_version"),
            "trained_until": metadados_modelo.get("trained_until"),
            "target_definition": metadados_modelo.get("target_definition"),
            "horizon": metadados_modelo.get("horizon"),
            "feature_schema_version": metadados_modelo.get("feature_schema_version"),
        },
    )


def avaliar_projecao_atual(
    freshness_epi: FreshnessDataset,
    semanas_limite: int = LIMIAR_SEMANAS_PROJECAO_ATUAL,
    referencia: Optional[date] = None,
) -> dict[str, Any]:
    """Decide se é legítimo oferecer uma priorização referente ao período
    **mais recente** — o portão do §13/§60 do produto.

    Regra: só é legítimo se a última semana epidemiológica com dado estiver
    a no máximo `semanas_limite` semanas de hoje. Caso contrário,
    `current_projection_available=false` com o motivo explícito, e a UI deve
    oferecer somente o backtest histórico.
    """
    if freshness_epi.atraso_dias is None:
        return {
            "current_projection_available": False,
            "reason": MOTIVO_DADO_DESATUALIZADO,
            "detalhe": "atualidade epidemiológica indeterminada",
            "semanas_de_atraso": None,
            "semanas_limite": semanas_limite,
            "semana_epi_maxima": freshness_epi.semana_epi_maxima,
        }
    semanas_atraso = freshness_epi.atraso_dias // 7
    disponivel = semanas_atraso <= semanas_limite
    return {
        "current_projection_available": bool(disponivel),
        "reason": None if disponivel else MOTIVO_DADO_DESATUALIZADO,
        "detalhe": (
            None
            if disponivel
            else (
                f"o último período epidemiológico publicado ({freshness_epi.semana_epi_maxima}) "
                f"está {semanas_atraso} semanas atrás do presente, acima do limite de "
                f"{semanas_limite} semanas para uma priorização referente ao período atual"
            )
        ),
        "semanas_de_atraso": int(semanas_atraso),
        "semanas_limite": semanas_limite,
        "semana_epi_maxima": freshness_epi.semana_epi_maxima,
        "data_maxima_evento": freshness_epi.data_maxima_evento,
    }


def montar_artefato_freshness(
    datasets: list[FreshnessDataset],
    projecao: dict[str, Any],
    gerado_em: Optional[str] = None,
) -> dict[str, Any]:
    """Artefato final consumido pelo dashboard e pelo healthcheck."""
    por_nome = {d.dataset: d.como_dict() for d in datasets}
    return {
        "gerado_em": gerado_em or datetime.now(timezone.utc).isoformat(),
        "datasets": por_nome,
        "projecao_atual": projecao,
        "resumo_status": {nome: bloco["status"] for nome, bloco in por_nome.items()},
    }
