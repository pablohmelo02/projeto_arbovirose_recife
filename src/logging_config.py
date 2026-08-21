"""Configuração central de log estruturado do pipeline.

## O que o log precisa responder

Depois de uma execução, o log tem de deixar claro, sem consultar código:

- o pipeline começou e terminou (ou onde parou);
- qual fonte foi acessada;
- quantos registros foram obtidos e quantos foram rejeitados, por motivo;
- qual a data máxima do dado processado;
- quais avisos apareceram;
- quanto tempo cada etapa levou.

## O que o log nunca contém

- **Segredo**: chaves do MinIO, tokens, `Authorization`, senha em URL. Um
  filtro de redação (`FiltroRedacao`) atua sobre a mensagem já formatada, de
  modo que mesmo um `logger.info(f"...{config}")` descuidado não vaza.
- **Dado pessoal**: o pipeline trabalha em grão agregado (bairro × semana),
  mas a Bronze contém registro individual do SINAN. Nenhum log deste projeto
  imprime linha de Bronze; para reduzir o risco de alguém introduzir isso, a
  redação também mascara sequências com formato de CPF e de CNS.

## Formato

Texto legível por padrão (é o que um operador lê no terminal) e JSON por
linha com `RECIFE_ALERTA_LOG_JSON=1` (é o que uma ferramenta de coleta
consome). A escolha é de ambiente, não de código de chamada.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

VARIAVEL_LOG_JSON = "RECIFE_ALERTA_LOG_JSON"
VARIAVEL_LOG_NIVEL = "RECIFE_ALERTA_LOG_NIVEL"

TEXTO_REDIGIDO = "***REDIGIDO***"

#: Chaves cujo VALOR nunca deve aparecer no log, em qualquer formato de
#: atribuição (`chave=valor`, `"chave": "valor"`, `chave: valor`).
CHAVES_SENSIVEIS = (
    "minio_secret_key", "minio_access_key", "secret_key", "access_key",
    "aws_secret_access_key", "aws_access_key_id", "password", "passwd",
    "senha", "token", "authorization", "api_key", "apikey", "secret",
)

_PADROES_REDACAO: tuple[tuple[re.Pattern[str], str], ...] = (
    # chave=valor / "chave": "valor" / chave: valor
    (
        re.compile(
            r"(?i)\b(" + "|".join(CHAVES_SENSIVEIS) + r")\b(\"?\s*[:=]\s*\"?)([^\s,;}\"']+)"
        ),
        r"\1\2" + TEXTO_REDIGIDO,
    ),
    # credencial embutida em URL: scheme://usuario:senha@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@"), r"\1" + TEXTO_REDIGIDO + "@"),
    # CPF (com ou sem pontuação) — nenhum log deste projeto deveria ter isto
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), TEXTO_REDIGIDO),
    # CNS (cartão nacional de saúde): 15 dígitos
    (re.compile(r"\b\d{15}\b"), TEXTO_REDIGIDO),
)


def redigir(texto: str) -> str:
    """Aplica todas as regras de redação a um texto já formatado."""
    for padrao, substituicao in _PADROES_REDACAO:
        texto = padrao.sub(substituicao, texto)
    return texto


class FiltroRedacao(logging.Filter):
    """Redige a mensagem **já formatada**.

    Atua em `record.getMessage()` (não só em `record.msg`), para cobrir
    também os casos em que o valor sensível veio de um argumento de
    formatação — que é justamente como um vazamento acidental acontece.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - API do logging
        try:
            mensagem = record.getMessage()
        except Exception:  # pragma: no cover - formatação inválida não deve derrubar o log
            return True
        limpa = redigir(mensagem)
        if limpa != mensagem:
            record.msg = limpa
            record.args = ()
        return True


class FormatadorJson(logging.Formatter):
    """Uma linha JSON por registro — para coleta automatizada."""

    def format(self, record: logging.LogRecord) -> str:
        bloco: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "nivel": record.levelname,
            "modulo": record.name,
            "mensagem": redigir(record.getMessage()),
        }
        if record.exc_info:
            bloco["excecao"] = self.formatException(record.exc_info)
        for chave, valor in getattr(record, "contexto", {}).items():
            bloco[chave] = valor
        return json.dumps(bloco, ensure_ascii=False, default=str)


def configurar_logging(
    nivel: Optional[str] = None, formato_json: Optional[bool] = None
) -> logging.Logger:
    """Configura o logger raiz de forma idempotente e devolve-o.

    Chamar duas vezes não duplica *handlers* (um problema real quando vários
    entry points são orquestrados no mesmo processo, como em
    `src/update_recife_alerta.py`).
    """
    nivel_efetivo = (nivel or os.getenv(VARIAVEL_LOG_NIVEL) or "INFO").upper()
    usar_json = formato_json if formato_json is not None else os.getenv(VARIAVEL_LOG_JSON) == "1"

    raiz = logging.getLogger()
    for handler in list(raiz.handlers):
        if getattr(handler, "_recife_alerta", False):
            raiz.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        FormatadorJson()
        if usar_json
        else logging.Formatter("[%(levelname)s] %(asctime)s %(name)s | %(message)s", "%H:%M:%S")
    )
    handler.addFilter(FiltroRedacao())
    handler._recife_alerta = True  # type: ignore[attr-defined]

    raiz.addHandler(handler)
    raiz.setLevel(nivel_efetivo)
    return raiz


def registrar_resultado_fonte(
    logger: logging.Logger,
    fonte: str,
    obtidos: int,
    rejeitados: int = 0,
    motivos_rejeicao: Optional[dict[str, int]] = None,
    data_maxima: Optional[str] = None,
    duracao_s: Optional[float] = None,
) -> None:
    """Linha de log padronizada por fonte — os campos que o §45 exige.

    Rejeição sempre aparece **por motivo**: "37 rejeitados" sem o porquê é
    um número que ninguém consegue investigar depois."""
    partes = [f"fonte={fonte}", f"registros_obtidos={obtidos}", f"registros_rejeitados={rejeitados}"]
    if data_maxima:
        partes.append(f"data_maxima={data_maxima}")
    if duracao_s is not None:
        partes.append(f"duracao_s={duracao_s:.2f}")
    logger.info(" | ".join(partes))
    for motivo, quantidade in (motivos_rejeicao or {}).items():
        logger.warning("fonte=%s | rejeicao=%r | quantidade=%d", fonte, motivo, quantidade)


@contextmanager
def etapa(logger: logging.Logger, nome: str) -> Iterator[dict[str, Any]]:
    """Registra início, fim e duração de uma etapa; em exceção, registra a
    falha (com *traceback*) e propaga — nunca engole o erro.

    O dicionário cedido pode receber contexto (`{"linhas": 123}`) que entra
    na linha final."""
    logger.info("etapa=%s | status=iniciou", nome)
    inicio = time.monotonic()
    contexto: dict[str, Any] = {}
    try:
        yield contexto
    except Exception:
        logger.exception(
            "etapa=%s | status=falhou | duracao_s=%.2f", nome, time.monotonic() - inicio
        )
        raise
    extras = "".join(f" | {k}={v}" for k, v in contexto.items())
    logger.info(
        "etapa=%s | status=concluiu | duracao_s=%.2f%s", nome, time.monotonic() - inicio, extras
    )
