"""Portões de qualidade (*quality gates*) executados ANTES de publicar
qualquer artefato consumido pelo produto.

Princípio: um artefato só substitui o anterior se passar. Se um portão
crítico falhar, a publicação é abortada e a versão anterior — válida —
permanece intacta (ver `src/utils/io_atomico.py` para o mecanismo de
substituição atômica que torna isso possível).

## Severidade

- `CRITICO`: bloqueia a publicação. Indica que o artefato está quebrado
  (chave duplicada, bairro faltando, caso negativo, semana inválida).
- `AVISO`: não bloqueia, mas é registrado e exibido. Indica algo que muda
  a leitura do dado sem invalidá-lo (ex.: cobertura climática abaixo do
  esperado, último período disponível mais antigo que o habitual).

Nenhum portão "corrige" dado. Corrigir silenciosamente é exatamente o que
este módulo existe para impedir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

CRITICO = "CRITICO"
AVISO = "AVISO"

#: Número oficial de bairros do Recife na fonte territorial do projeto
#: (`silver_bairro_geo`, 94 features do GeoJSON do CKAN). Não é um palpite:
#: é o valor verificado na ingestão de território desde a Fase 2.
N_BAIRROS_ESPERADO = 94

AGRAVOS_ESPERADOS = ("CHIKUNGUNYA", "DENGUE", "ZIKA")

SEMANA_EPIDEMIOLOGICA_MINIMA = 1
SEMANA_EPIDEMIOLOGICA_MAXIMA = 53

CHAVE_GOLD = ("codigo_bairro", "agravo", "ano_epidemiologico", "semana_epidemiologica")


@dataclass
class Achado:
    portao: str
    severidade: str
    mensagem: str
    detalhe: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - conveniência de log
        return f"[{self.severidade}] {self.portao}: {self.mensagem}"


class QualityGateError(RuntimeError):
    """Um ou mais portões críticos falharam — publicação abortada."""

    def __init__(self, achados: list[Achado]) -> None:
        self.achados = achados
        super().__init__(
            "portões de qualidade críticos falharam: "
            + "; ".join(a.mensagem for a in achados)
        )


def _add(achados: list[Achado], portao: str, severidade: str, mensagem: str, **detalhe: Any) -> None:
    achados.append(Achado(portao=portao, severidade=severidade, mensagem=mensagem, detalhe=detalhe))


def validar_gold(
    df_gold: pd.DataFrame,
    codigos_bairro_territorio: Optional[Iterable[str]] = None,
    colunas_obrigatorias: Optional[Iterable[str]] = None,
) -> list[Achado]:
    """Valida a Gold `bairro × semana epidemiológica × agravo`.

    `codigos_bairro_territorio`: códigos vindos da fonte territorial, para
    checar integridade referencial (todo bairro da Gold existe no
    território, e vice-versa). Se `None`, esse portão é pulado com aviso.
    """
    achados: list[Achado] = []

    if df_gold.empty:
        _add(achados, "gold_nao_vazia", CRITICO, "Gold está vazia")
        return achados

    # ---- colunas obrigatórias ----
    if colunas_obrigatorias:
        faltando = [c for c in colunas_obrigatorias if c not in df_gold.columns]
        if faltando:
            _add(
                achados, "gold_colunas_obrigatorias", CRITICO,
                f"colunas obrigatórias ausentes: {faltando}", colunas=faltando,
            )

    # ---- chave única ----
    colunas_chave = [c for c in CHAVE_GOLD if c in df_gold.columns]
    if len(colunas_chave) == len(CHAVE_GOLD):
        n_dup = int(df_gold.duplicated(subset=colunas_chave).sum())
        if n_dup:
            _add(achados, "gold_chave_unica", CRITICO, f"{n_dup} linha(s) com chave duplicada", n=n_dup)
    else:
        _add(achados, "gold_chave_unica", CRITICO, "colunas da chave da Gold ausentes")

    # ---- bairros ----
    if "codigo_bairro" in df_gold.columns:
        n_bairros = int(df_gold["codigo_bairro"].nunique())
        if n_bairros != N_BAIRROS_ESPERADO:
            _add(
                achados, "gold_n_bairros", CRITICO,
                f"{n_bairros} bairros na Gold (esperado {N_BAIRROS_ESPERADO})",
                observado=n_bairros, esperado=N_BAIRROS_ESPERADO,
            )

    # ---- agravos ----
    if "agravo" in df_gold.columns:
        agravos = tuple(sorted(df_gold["agravo"].dropna().unique().tolist()))
        if agravos != AGRAVOS_ESPERADOS:
            _add(
                achados, "gold_agravos", CRITICO,
                f"agravos presentes {agravos} != esperado {AGRAVOS_ESPERADOS}",
                observado=list(agravos),
            )

    # ---- casos ----
    if "casos" in df_gold.columns:
        n_negativos = int((df_gold["casos"] < 0).sum())
        if n_negativos:
            _add(achados, "gold_casos_nao_negativos", CRITICO, f"{n_negativos} linha(s) com casos < 0", n=n_negativos)
        n_nulos = int(df_gold["casos"].isna().sum())
        if n_nulos:
            _add(
                achados, "gold_casos_sem_nulo", CRITICO,
                f"{n_nulos} linha(s) com casos nulo (notificação compulsória: ausência é 0, não nulo)",
                n=n_nulos,
            )

    # ---- semana epidemiológica ----
    if "semana_epidemiologica" in df_gold.columns:
        semanas = pd.to_numeric(df_gold["semana_epidemiologica"], errors="coerce")
        fora = int(
            ((semanas < SEMANA_EPIDEMIOLOGICA_MINIMA) | (semanas > SEMANA_EPIDEMIOLOGICA_MAXIMA) | semanas.isna()).sum()
        )
        if fora:
            _add(achados, "gold_semana_valida", CRITICO, f"{fora} linha(s) com semana epidemiológica inválida", n=fora)

    # ---- datas da semana ----
    if {"semana_epi_data_inicio", "semana_epi_data_fim"} <= set(df_gold.columns):
        inicio = pd.to_datetime(df_gold["semana_epi_data_inicio"], errors="coerce")
        fim = pd.to_datetime(df_gold["semana_epi_data_fim"], errors="coerce")
        invertidas = int((fim < inicio).sum())
        if invertidas:
            _add(achados, "gold_datas_coerentes", CRITICO, f"{invertidas} linha(s) com data_fim < data_inicio", n=invertidas)
        duracao = (fim - inicio).dt.days
        fora_de_7 = int((duracao != 6).sum())
        if fora_de_7:
            _add(
                achados, "gold_semana_tem_7_dias", CRITICO,
                f"{fora_de_7} linha(s) cuja semana não tem exatamente 7 dias", n=fora_de_7,
            )

    # ---- clima: nunca negativo (missing continua sendo missing) ----
    for coluna in [c for c in df_gold.columns if "precipitacao" in c or "chuva" in c]:
        valores = pd.to_numeric(df_gold[coluna], errors="coerce")
        n_neg = int((valores < 0).sum())
        if n_neg:
            _add(achados, "clima_nao_negativo", CRITICO, f"{n_neg} valor(es) negativo(s) em {coluna}", coluna=coluna, n=n_neg)

    for coluna in [c for c in df_gold.columns if c.startswith("umidade_relativa")]:
        valores = pd.to_numeric(df_gold[coluna], errors="coerce")
        n_fora = int(((valores < 0) | (valores > 100)).sum())
        if n_fora:
            _add(achados, "umidade_intervalo", CRITICO, f"{n_fora} valor(es) fora de 0-100% em {coluna}", coluna=coluna, n=n_fora)

    # ---- integridade referencial com território ----
    if codigos_bairro_territorio is None:
        _add(achados, "gold_integridade_territorio", AVISO, "território não informado — portão de integridade referencial pulado")
    elif "codigo_bairro" in df_gold.columns:
        do_territorio = {str(c) for c in codigos_bairro_territorio}
        da_gold = {str(c) for c in df_gold["codigo_bairro"].unique()}
        sobrando = sorted(da_gold - do_territorio)
        faltando = sorted(do_territorio - da_gold)
        if sobrando:
            _add(
                achados, "gold_integridade_territorio", CRITICO,
                f"{len(sobrando)} bairro(s) na Gold sem correspondência no território", codigos=sobrando[:10],
            )
        if faltando:
            _add(
                achados, "gold_integridade_territorio", CRITICO,
                f"{len(faltando)} bairro(s) do território ausente(s) na Gold", codigos=faltando[:10],
            )

    return achados


def validar_dataset_publicavel(df: pd.DataFrame, colunas_proibidas: Iterable[str]) -> list[Achado]:
    """Portão de privacidade: nenhuma coluna potencialmente identificável
    pode chegar ao dataset publicado (ver `src/export_dashboard_dataset.py`
    para a lista e o porquê)."""
    achados: list[Achado] = []
    presentes = {c.lower() for c in df.columns}
    encontradas = sorted(presentes.intersection({c.lower() for c in colunas_proibidas}))
    if encontradas:
        _add(
            achados, "privacidade_sem_dado_individual", CRITICO,
            f"coluna(s) potencialmente identificável(is) no dataset publicável: {encontradas}",
            colunas=encontradas,
        )
    return achados


def separar_por_severidade(achados: list[Achado]) -> tuple[list[Achado], list[Achado]]:
    criticos = [a for a in achados if a.severidade == CRITICO]
    avisos = [a for a in achados if a.severidade == AVISO]
    return criticos, avisos


def exigir_aprovacao(achados: list[Achado], contexto: str) -> list[Achado]:
    """Registra todos os achados e levanta `QualityGateError` se houver
    qualquer crítico. Devolve a lista de avisos (não-bloqueantes)."""
    criticos, avisos = separar_por_severidade(achados)
    for achado in achados:
        (logger.error if achado.severidade == CRITICO else logger.warning)("%s | %s", contexto, achado)
    if criticos:
        raise QualityGateError(criticos)
    logger.info("%s | %d portão(ões) de qualidade aprovado(s), %d aviso(s)", contexto, len(achados) - len(avisos), len(avisos))
    return avisos


def achados_para_dict(achados: list[Achado]) -> list[dict[str, Any]]:
    return [
        {"portao": a.portao, "severidade": a.severidade, "mensagem": a.mensagem, "detalhe": a.detalhe}
        for a in achados
    ]
