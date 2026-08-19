"""Parsing dos CSVs históricos de estação do INMET.

Cada arquivo tem 8 linhas de metadados (`CHAVE:;valor`), uma linha de
cabeçalho (`Data;Hora UTC;...`) e depois a série horária. Encoding
`latin-1`, delimitador `;`, decimal `,` (formato brasileiro) — verificado
contra arquivos reais baixados do ZIP oficial (ver
`reports/climate_source_analysis/source_analysis.md`).
"""
from __future__ import annotations

import io

import pandas as pd

CAMPOS_METADADOS = (
    "REGIAO", "UF", "ESTACAO", "CODIGO (WMO)", "LATITUDE", "LONGITUDE", "ALTITUDE",
    "DATA DE FUNDACAO",
)


class InmetCsvError(Exception):
    """Erro ao parsear um CSV de estação do INMET."""


def ler_estacao_inmet(conteudo: bytes) -> tuple[dict[str, str], pd.DataFrame]:
    """Lê um CSV de estação do INMET, retornando (metadados, série horária)."""
    try:
        texto = conteudo.decode("latin-1")
    except UnicodeDecodeError as exc:
        raise InmetCsvError(f"Falha ao decodificar CSV do INMET: {exc}") from exc

    linhas = texto.splitlines()
    metadados: dict[str, str] = {}
    indice_cabecalho = None

    for i, linha in enumerate(linhas[:20]):
        partes = linha.split(";")
        chave = partes[0].strip().rstrip(":").upper()
        if chave in CAMPOS_METADADOS:
            metadados[chave] = partes[1].strip() if len(partes) > 1 else ""
        if linha.startswith("Data;"):
            indice_cabecalho = i
            break

    if indice_cabecalho is None:
        raise InmetCsvError("Cabeçalho de dados ('Data;...') não encontrado")

    corpo = "\n".join(linhas[indice_cabecalho:])
    try:
        df = pd.read_csv(
            io.StringIO(corpo),
            sep=";",
            decimal=",",
            dtype=str,
            engine="python",
            on_bad_lines="warn",
            keep_default_na=False,
            na_values=[""],
        )
    except pd.errors.ParserError as exc:
        raise InmetCsvError(f"Falha ao parsear série horária: {exc}") from exc

    # O cabeçalho real termina com ';' sobrando, o que cria uma coluna
    # "Unnamed: N" vazia no final — descartada, não carrega dado nem nome.
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]

    return metadados, df
