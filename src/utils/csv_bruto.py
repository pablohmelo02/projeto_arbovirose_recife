"""Leitura tolerante de CSVs brutos da Bronze.

Os arquivos publicados pela prefeitura têm inconsistências reais entre anos:
delimitador (`;` na maioria dos recursos, mas `,` em Dengue 2015 e 2019) e
encoding (`utf-8` na maioria, com `latin-1` como alternativa). Esta função
concentra a lógica de detectar essas variações, para não duplicá-la entre o
profiling e a Silver.

Tudo é lido como texto (`dtype=str`): a Bronze preserva os dados como vieram
da fonte, e deixar o pandas inferir tipo automaticamente corromperia códigos
com zeros à esquerda (ex.: `ID_UNIDADE="0004774"` viraria `4774`).
"""
from __future__ import annotations

import io

import pandas as pd

ENCODINGS_TENTATIVAS = ("utf-8", "latin-1")
DELIMITADORES_CANDIDATOS = (";", ",")


class CsvBrutoError(Exception):
    """Erro ao decodificar ou parsear um CSV bruto da Bronze."""


def decodificar(conteudo: bytes) -> tuple[str, str]:
    """Decodifica bytes tentando utf-8 e depois latin-1."""
    for encoding in ENCODINGS_TENTATIVAS:
        try:
            return conteudo.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise CsvBrutoError(
        f"não foi possível decodificar o conteúdo ({'/'.join(ENCODINGS_TENTATIVAS)})"
    )


def detectar_delimitador(primeira_linha: str) -> str:
    """Escolhe, entre `;` e `,`, o delimitador com mais ocorrências no cabeçalho."""
    contagens = {delim: primeira_linha.count(delim) for delim in DELIMITADORES_CANDIDATOS}
    if max(contagens.values()) == 0:
        return ";"
    return max(contagens, key=contagens.get)


def ler_csv_bruto(conteudo: bytes) -> pd.DataFrame:
    """Lê um CSV bruto da Bronze como DataFrame de strings.

    Detecta delimitador e encoding automaticamente. Não infere tipos, não
    remove nulos, não renomeia colunas — apenas torna o conteúdo bruto
    manipulável em memória.
    """
    if not conteudo:
        raise CsvBrutoError("conteúdo vazio (0 bytes)")

    texto, _ = decodificar(conteudo)
    linhas = texto.splitlines()
    if not linhas:
        raise CsvBrutoError("conteúdo sem linhas")

    delimitador = detectar_delimitador(linhas[0])

    try:
        return pd.read_csv(
            io.StringIO(texto),
            sep=delimitador,
            dtype=str,
            engine="python",
            on_bad_lines="warn",
            keep_default_na=False,
            na_values=[""],
        )
    except pd.errors.ParserError as exc:
        raise CsvBrutoError(f"falha ao parsear CSV: {exc}") from exc
