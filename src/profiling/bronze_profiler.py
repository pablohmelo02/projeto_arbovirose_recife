"""Profiling da camada Bronze.

Lê a última ingestão válida de cada `resource_id` (a partir dos manifests
gravados no MinIO), perfila cada CSV (colunas, tipo aparente, nulos,
cardinalidade, duplicados) e compara os schemas entre anos da mesma doença e
entre as três doenças.

Não corrige, não transforma e não agrega nada — é só diagnóstico, para
orientar o desenho do contrato Silver (`src/silver/schema.py`). Nunca baixa
dados do CKAN: lê exclusivamente o que já está na Bronze/MinIO.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.clients.minio_client import MinioClient
from src.ingestion.bronze_ingestion import PREFIXO_BRONZE
from src.ingestion.bronze_validation import carregar_manifest
from src.utils.csv_bruto import CsvBrutoError, ler_csv_bruto

logger = logging.getLogger(__name__)

ENTIDADES_FATO = ("dengue", "zika", "chikungunya")

_PADRAO_INTEIRO = re.compile(r"^-?\d+$")
_PADRAO_DECIMAL = re.compile(r"^-?\d+[.,]\d+$")
_PADRAO_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def listar_manifests(minio_client: MinioClient) -> list[str]:
    """Lista as chaves de todos os manifests de ingestão, em ordem cronológica."""
    prefixo_controle = f"{PREFIXO_BRONZE}/_controle/"
    prefixo_manifest = f"{prefixo_controle}manifest_"
    chaves = minio_client.listar_chaves(prefixo_controle)
    return sorted(chave for chave in chaves if chave.startswith(prefixo_manifest))


def selecionar_ultima_ingestao_valida(minio_client: MinioClient) -> dict[str, dict[str, Any]]:
    """Para cada `resource_id`, retorna a entrada SUCCESS mais recente entre todos os manifests.

    Os manifests são lidos em ordem cronológica (o `run_id` é ordenável como
    string, pois é um timestamp UTC no formato `%Y%m%dT%H%M%SZ`), e a última
    atribuição para um `resource_id` sempre vence — nunca há duas versões do
    mesmo recurso consideradas ao mesmo tempo, mesmo que existam múltiplas
    ingestões históricas do mesmo dataset.
    """
    melhor_por_resource: dict[str, dict[str, Any]] = {}

    for chave_manifest in listar_manifests(minio_client):
        manifest = carregar_manifest(minio_client, chave_manifest)
        run_id = manifest.get("run_id")
        for entrada in manifest.get("recursos", []):
            if entrada.get("status") != "SUCCESS":
                continue
            resource_id = entrada.get("resource_id")
            if not resource_id:
                continue
            # O run_id não vem dentro da entrada (é um campo do manifest como
            # um todo), então anexamos aqui para preservar a rastreabilidade
            # de qual execução da Bronze originou este recurso.
            entrada_com_lineage = {**entrada, "_manifest_run_id": run_id}
            melhor_por_resource[resource_id] = entrada_com_lineage

    return melhor_por_resource


def inferir_tipo_coluna(serie: pd.Series) -> str:
    """Classifica heuristicamente uma coluna textual como inteiro/decimal/data/texto.

    É uma inferência descritiva (para o relatório de profiling), não uma
    conversão de tipo real — os dados continuam como string em `ler_csv_bruto`.
    """
    valores = serie.dropna()
    if valores.empty:
        return "vazio"

    if (valores.str.match(_PADRAO_DATA)).all():
        return "data"
    if (valores.str.match(_PADRAO_INTEIRO)).all():
        return "inteiro"
    if (valores.str.match(_PADRAO_DECIMAL)).all():
        return "decimal"
    return "texto"


def _identificador(entrada: dict[str, Any]) -> str:
    if entrada.get("tipo") == "fato":
        return f"{entrada.get('entidade')}_{entrada.get('ano')}"
    return str(entrada.get("entidade"))


def perfilar_arquivo(
    minio_client: MinioClient, entrada: dict[str, Any]
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """Perfila um único recurso da Bronze. Retorna (None, []) se não conseguir lê-lo."""
    object_key = entrada.get("object_key")
    identificador = _identificador(entrada)

    if not object_key:
        logger.error("Recurso '%s' sem object_key, ignorado no profiling", entrada.get("nome"))
        return None, []

    try:
        conteudo = minio_client.download_bytes(object_key)
        df = ler_csv_bruto(conteudo)
    except CsvBrutoError as exc:
        logger.error("Falha ao perfilar '%s' (%s): %s", entrada.get("nome"), object_key, exc)
        return None, []

    resumo = {
        "identificador": identificador,
        "tipo": entrada.get("tipo"),
        "entidade": entrada.get("entidade"),
        "ano": entrada.get("ano"),
        "resource_id": entrada.get("resource_id"),
        "object_key": object_key,
        "quantidade_registros": len(df),
        "quantidade_colunas": len(df.columns),
        "quantidade_duplicados": int(df.duplicated().sum()),
    }

    colunas: list[dict[str, Any]] = []
    total_linhas = len(df)
    for coluna in df.columns:
        serie = df[coluna]
        nulos = int(serie.isna().sum())
        colunas.append(
            {
                "identificador": identificador,
                "tipo": entrada.get("tipo"),
                "entidade": entrada.get("entidade"),
                "ano": entrada.get("ano"),
                "coluna": coluna,
                "coluna_normalizada": coluna.strip().upper(),
                "dtype_inferido": inferir_tipo_coluna(serie),
                "quantidade_null": nulos,
                "percentual_null": round(100 * nulos / total_linhas, 2) if total_linhas else 0.0,
                "quantidade_valores_unicos": int(serie.nunique(dropna=True)),
            }
        )

    return resumo, colunas


def construir_resumo_schemas(perfil_colunas: list[dict[str, Any]]) -> dict[str, Any]:
    """Deriva, a partir do profiling de colunas, as comparações estruturais pedidas:
    colunas presentes em todos os anos, ausentes em algum ano, exclusivas de uma
    doença, comuns às três doenças, e colunas com tipo aparente inconsistente.
    """
    fatos = [c for c in perfil_colunas if c["tipo"] == "fato"]

    colunas_por_entidade_ano: dict[tuple[str, Any], set[str]] = {}
    for coluna in fatos:
        chave = (coluna["entidade"], coluna["ano"])
        colunas_por_entidade_ano.setdefault(chave, set()).add(coluna["coluna_normalizada"])

    anos_por_entidade: dict[str, list[int]] = {}
    uniao_por_entidade: dict[str, set[str]] = {}
    intersecao_por_entidade: dict[str, set[str]] = {}

    for entidade in ENTIDADES_FATO:
        conjuntos = [
            cols for (ent, _ano), cols in colunas_por_entidade_ano.items() if ent == entidade
        ]
        anos_por_entidade[entidade] = sorted(
            ano for (ent, ano) in colunas_por_entidade_ano if ent == entidade
        )
        uniao_por_entidade[entidade] = set().union(*conjuntos) if conjuntos else set()
        intersecao_por_entidade[entidade] = set.intersection(*conjuntos) if conjuntos else set()

    intersecoes_nao_vazias = [
        intersecao_por_entidade[e] for e in ENTIDADES_FATO if intersecao_por_entidade[e]
    ]
    comuns_as_tres = (
        set.intersection(*intersecoes_nao_vazias)
        if len(intersecoes_nao_vazias) == len(ENTIDADES_FATO)
        else set()
    )

    exclusivas_por_doenca: dict[str, list[str]] = {}
    for entidade in ENTIDADES_FATO:
        outras = set().union(
            *[uniao_por_entidade[e] for e in ENTIDADES_FATO if e != entidade]
        )
        exclusivas_por_doenca[entidade] = sorted(uniao_por_entidade[entidade] - outras)

    ausentes_em_algum_ano = {
        entidade: sorted(uniao_por_entidade[entidade] - intersecao_por_entidade[entidade])
        for entidade in ENTIDADES_FATO
    }

    tipos_por_coluna: dict[str, set[str]] = {}
    for coluna in fatos:
        tipos_por_coluna.setdefault(coluna["coluna_normalizada"], set()).add(
            coluna["dtype_inferido"]
        )
    mudancas_de_tipo = {
        nome: sorted(tipos - {"vazio"})
        for nome, tipos in tipos_por_coluna.items()
        if len(tipos - {"vazio"}) > 1
    }

    return {
        "anos_disponiveis_por_entidade": anos_por_entidade,
        "colunas_presentes_em_todos_os_anos": {
            e: sorted(intersecao_por_entidade[e]) for e in ENTIDADES_FATO
        },
        "colunas_ausentes_em_algum_ano": ausentes_em_algum_ano,
        "colunas_comuns_as_tres_doencas": sorted(comuns_as_tres),
        "colunas_exclusivas_por_doenca": exclusivas_por_doenca,
        "colunas_com_tipo_aparente_inconsistente": mudancas_de_tipo,
    }


def executar_profiling(minio_client: MinioClient) -> dict[str, Any]:
    """Executa o profiling completo da Bronze e retorna os dados brutos e o resumo."""
    recursos = selecionar_ultima_ingestao_valida(minio_client)
    if not recursos:
        raise ValueError(
            "Nenhum recurso SUCCESS encontrado nos manifests da Bronze. "
            "Rode 'python -m src.main' antes do profiling."
        )
    logger.info(
        "%d recursos selecionados (última ingestão SUCCESS por resource_id)", len(recursos)
    )

    perfil_arquivos: list[dict[str, Any]] = []
    perfil_colunas: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []

    for entrada in recursos.values():
        resumo, colunas = perfilar_arquivo(minio_client, entrada)
        if resumo is None:
            falhas.append(
                {"resource_id": entrada.get("resource_id"), "nome": entrada.get("nome")}
            )
            continue
        logger.info(
            "Perfilado: %s (%d registros, %d colunas)",
            resumo["identificador"],
            resumo["quantidade_registros"],
            resumo["quantidade_colunas"],
        )
        perfil_arquivos.append(resumo)
        perfil_colunas.extend(colunas)

    resumo_schemas = construir_resumo_schemas(perfil_colunas)

    return {
        "perfil_arquivos": perfil_arquivos,
        "perfil_colunas": perfil_colunas,
        "resumo_schemas": resumo_schemas,
        "falhas_leitura": falhas,
        "total_recursos_selecionados": len(recursos),
        "total_recursos_perfilados": len(perfil_arquivos),
    }


_COLUNAS_NULL_PROFILE = [
    "identificador", "tipo", "entidade", "ano", "coluna", "quantidade_null", "percentual_null",
]
_COLUNAS_CARDINALITY_PROFILE = [
    "identificador", "tipo", "entidade", "ano", "coluna", "quantidade_valores_unicos", "dtype_inferido",
]
_COLUNAS_DUPLICATES_PROFILE = [
    "identificador", "tipo", "entidade", "ano", "quantidade_registros", "quantidade_duplicados",
]


def gravar_relatorios(resultado: dict[str, Any], pasta_saida: Path) -> None:
    """Grava os relatórios de profiling (CSVs + summary.json) em `pasta_saida`."""
    pasta_saida.mkdir(parents=True, exist_ok=True)

    df_arquivos = pd.DataFrame(resultado["perfil_arquivos"])
    df_colunas = pd.DataFrame(resultado["perfil_colunas"])

    if not df_arquivos.empty:
        df_arquivos.to_csv(pasta_saida / "schema_por_arquivo.csv", index=False, encoding="utf-8")
        df_arquivos[_COLUNAS_DUPLICATES_PROFILE].to_csv(
            pasta_saida / "duplicates_profile.csv", index=False, encoding="utf-8"
        )

    if not df_colunas.empty:
        comparacao = df_colunas.assign(presente=True).pivot_table(
            index="coluna_normalizada",
            columns="identificador",
            values="presente",
            fill_value=False,
            aggfunc="any",
        )
        comparacao.to_csv(pasta_saida / "schema_comparison.csv", encoding="utf-8")

        df_colunas[_COLUNAS_NULL_PROFILE].to_csv(
            pasta_saida / "null_profile.csv", index=False, encoding="utf-8"
        )
        df_colunas[_COLUNAS_CARDINALITY_PROFILE].to_csv(
            pasta_saida / "cardinality_profile.csv", index=False, encoding="utf-8"
        )

    resumo_json = {
        "total_recursos_selecionados": resultado["total_recursos_selecionados"],
        "total_recursos_perfilados": resultado["total_recursos_perfilados"],
        "falhas_leitura": resultado["falhas_leitura"],
        **resultado["resumo_schemas"],
    }
    (pasta_saida / "summary.json").write_text(
        json.dumps(resumo_json, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
