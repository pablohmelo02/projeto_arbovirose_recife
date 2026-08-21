"""Escrita atômica de artefatos em disco.

Motivo (regra de confiabilidade do produto): um artefato consumido pelo
dashboard — Parquet da Gold, GeoJSON dos bairros, JSON de freshness — nunca
deve poder existir num estado parcialmente escrito. Se a máquina cair, o
processo for interrompido (Ctrl+C) ou a validação de qualidade falhar no
meio, o arquivo anterior (válido) tem de continuar intacto.

Padrão implementado: **escrever em temporário no MESMO diretório → validar
→ `os.replace`**. `os.replace` é atômico dentro do mesmo sistema de
arquivos em POSIX e no Windows (ao contrário de `shutil.move` entre
volumes, e ao contrário de escrever direto no destino). Escrever o
temporário no mesmo diretório do destino é o que garante "mesmo sistema de
arquivos" sem depender de configuração do ambiente.

Nunca "engolir" erro: se a validação falhar, o temporário é removido, o
destino permanece como estava e a exceção sobe.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

logger = logging.getLogger(__name__)

SUFIXO_TEMPORARIO = ".tmp-escrita"


class ValidacaoArtefatoError(RuntimeError):
    """Artefato recém-escrito não passou na validação — destino preservado."""


@contextmanager
def caminho_temporario(destino: Path) -> Iterator[Path]:
    """Cede um caminho temporário no mesmo diretório de `destino` e o
    promove atomicamente ao sair sem exceção. Em caso de exceção, remove o
    temporário e deixa o destino intacto."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + SUFIXO_TEMPORARIO)
    if temporario.exists():
        temporario.unlink()
    try:
        yield temporario
        if not temporario.exists():
            raise ValidacaoArtefatoError(
                f"nada foi escrito em {temporario} — destino {destino} preservado"
            )
        os.replace(temporario, destino)
        logger.info("Artefato publicado atomicamente: %s", destino)
    except BaseException:
        if temporario.exists():
            try:
                temporario.unlink()
            except OSError:  # pragma: no cover - limpeza best-effort
                logger.warning("Não foi possível remover o temporário %s", temporario)
        raise


def escrever_bytes_atomico(
    destino: Path,
    conteudo: bytes,
    validar: Optional[Callable[[Path], None]] = None,
) -> Path:
    """Grava `conteudo` em `destino` de forma atômica. `validar` recebe o
    caminho TEMPORÁRIO (antes da promoção) e deve levantar exceção se o
    conteúdo for inválido."""
    with caminho_temporario(destino) as temporario:
        temporario.write_bytes(conteudo)
        if validar is not None:
            validar(temporario)
    return Path(destino)


def escrever_json_atomico(
    destino: Path,
    dados: Any,
    validar: Optional[Callable[[Path], None]] = None,
) -> Path:
    """JSON UTF-8 indentado, escrito atomicamente. Sempre `ensure_ascii=False`
    (os dados do projeto são em português e vão para relatórios lidos por
    pessoas)."""
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    return escrever_bytes_atomico(destino, conteudo, validar=validar)


def escrever_parquet_atomico(
    destino: Path,
    df,
    validar: Optional[Callable[[Path], None]] = None,
) -> Path:
    """Parquet escrito atomicamente. `df` é um `pandas.DataFrame` (import
    local para este módulo não puxar pandas quando só o JSON é usado)."""
    with caminho_temporario(destino) as temporario:
        df.to_parquet(temporario, engine="pyarrow", index=False)
        if validar is not None:
            validar(temporario)
    return Path(destino)


def escrever_csv_atomico(destino: Path, df, **kwargs: Any) -> Path:
    """CSV escrito atomicamente (relatórios de `reports/`)."""
    with caminho_temporario(destino) as temporario:
        df.to_csv(temporario, index=False, **kwargs)
    return Path(destino)


def escrever_texto_atomico(destino: Path, texto: str) -> Path:
    """Arquivo de texto (Markdown de relatório) escrito atomicamente."""
    return escrever_bytes_atomico(destino, texto.encode("utf-8"))
