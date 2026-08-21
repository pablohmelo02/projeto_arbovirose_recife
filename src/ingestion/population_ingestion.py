"""Ingestão Bronze do domínio População (`data/bronze/populacao/`).

## O que é automatizável, e o que não é (investigado nesta sessão)

- **IBGE Censo 2022 "Agregados por Bairro"**: automatizável. Arquivo público
  no FTP do IBGE, ~700 KB, sem autenticação. `baixar_censo2022_bairro_recife`
  baixa o ZIP nacional e filtra para `CD_MUN=2611606` (Recife).
- **IBGE Estimativas de População (SIDRA, tabela 6579) + Censos (tabelas
  202 e 9514)**: automatizável. API pública sem chave.
  `baixar_estimativas_municipais` busca as três tabelas.
- **Secretaria de Saúde do Recife/CIEVS, "População 2010 a 2017"**: **não
  automatizável de forma confiável**. É um PDF de 33 páginas sem estrutura
  de tabela consistente (`pdfplumber.extract_tables` não reconhece a tabela
  de bairros — foi extraída por regex sobre o texto bruto, numa sessão
  manual, com verificação de integridade: soma dos 94 bairros bate com o
  Total publicado em todos os 8 anos, diferença <= 4 pessoas, atribuída a
  arredondamento da própria fonte). Este módulo **não tenta reparsear o
  PDF automaticamente** — o resultado já verificado está versionado em
  `cievs_populacao_bairro_2010_2017.json`, com a proveniência completa
  (metodologia, URL, verificação de integridade) no próprio arquivo. Se o
  documento precisar ser reprocessado (ex.: erro encontrado depois), o
  procedimento fica documentado no relatório
  `reports/population/population_source_inventory.md`, não neste módulo.

Nenhuma função aqui é chamada automaticamente pelo pipeline Silver
(`src/silver/pipeline_population.py`) — ele lê os arquivos já em
`data/bronze/populacao/`. Rodar as funções deste módulo só é necessário para
**atualizar** o Bronze (nova estimativa anual do IBGE, por exemplo), nunca
para reconstruir a Silver do zero.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_BRONZE_POPULACAO = RAIZ / "data" / "bronze" / "populacao"

CODIGO_MUNICIPIO_RECIFE = "2611606"

URL_CENSO2022_BAIRROS_ZIP = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
    "Agregados_por_Bairro_csv/Agregados_por_bairros_basico_BR_20260520.zip"
)
URL_SIDRA_TABELA_202 = "https://apisidra.ibge.gov.br/values/t/202/n6/{municipio}/v/allxp/p/{ano}"
URL_SIDRA_TABELA_6579 = "https://apisidra.ibge.gov.br/values/t/6579/n6/{municipio}/v/allxp/p/all"
URL_SIDRA_TABELA_9514 = "https://apisidra.ibge.gov.br/values/t/9514/n6/{municipio}/v/allxp/p/all"

TIMEOUT_SEGUNDOS = 30


def _normalizar_nome_bairro(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


def baixar_censo2022_bairro_recife(destino: Path = PASTA_BRONZE_POPULACAO) -> dict[str, Any]:
    """Baixa o produto oficial do Censo 2022 e filtra para os bairros do Recife.

    Sobrescreve `censo2022_ibge_bairro_recife.csv` e seu manifest — só rodar
    se uma nova versão do produto do IBGE precisar ser incorporada.
    """
    resposta = requests.get(URL_CENSO2022_BAIRROS_ZIP, timeout=TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resposta.content)) as zf:
        nome_csv = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        conteudo = zf.read(nome_csv).decode("latin1")

    linhas_recife = []
    leitor = csv.DictReader(io.StringIO(conteudo), delimiter=";")
    for linha in leitor:
        if linha.get("CD_MUN") == CODIGO_MUNICIPIO_RECIFE:
            linhas_recife.append(linha)

    if len(linhas_recife) != 94:
        raise ValueError(
            f"esperado 94 bairros para Recife (CD_MUN={CODIGO_MUNICIPIO_RECIFE}), "
            f"encontrado {len(linhas_recife)} — produto do IBGE pode ter mudado de formato"
        )

    fieldnames_out = [
        "CD_BAIRRO", "NM_BAIRRO", "nome_bairro_normalizado", "NM_NU",
        "AREA_KM2", "v0001", "v0002", "v0003", "v0004",
    ]
    caminho_csv = destino / "censo2022_ibge_bairro_recife.csv"
    with open(caminho_csv, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=fieldnames_out)
        escritor.writeheader()
        for linha in linhas_recife:
            escritor.writerow(
                {
                    "CD_BAIRRO": linha["CD_BAIRRO"],
                    "NM_BAIRRO": linha["NM_BAIRRO"],
                    "nome_bairro_normalizado": _normalizar_nome_bairro(linha["NM_BAIRRO"]),
                    "NM_NU": linha["NM_NU"],
                    "AREA_KM2": linha["AREA_KM2"],
                    "v0001": linha["v0001"],
                    "v0002": linha["v0002"],
                    "v0003": linha["v0003"],
                    "v0004": linha["v0004"],
                }
            )

    total_populacao = sum(int(linha["v0001"]) for linha in linhas_recife)
    logger.info("Censo 2022: %d bairros, populacao total %d", len(linhas_recife), total_populacao)
    return {"n_bairros": len(linhas_recife), "populacao_total": total_populacao, "arquivo": str(caminho_csv)}


def baixar_estimativas_municipais(
    municipio: str = CODIGO_MUNICIPIO_RECIFE, destino: Path = PASTA_BRONZE_POPULACAO
) -> dict[str, Any]:
    """Busca a série de estimativas anuais (SIDRA 6579) e os totais dos dois
    Censos (tabelas 202 e 9514) para o município e atualiza
    `estimativas_municipais_ibge.json`, preservando o formato/documentação
    já existente no arquivo."""
    caminho = destino / "estimativas_municipais_ibge.json"
    with open(caminho, encoding="utf-8") as f:
        atual = json.load(f)

    resp_6579 = requests.get(URL_SIDRA_TABELA_6579.format(municipio=municipio), timeout=TIMEOUT_SEGUNDOS)
    resp_6579.raise_for_status()
    for registro in resp_6579.json()[1:]:
        ano = registro["D3N"]
        if ano in atual["series"]:
            atual["series"][ano]["valor"] = int(registro["V"])

    resp_202 = requests.get(
        URL_SIDRA_TABELA_202.format(municipio=municipio, ano=2010), timeout=TIMEOUT_SEGUNDOS
    )
    resp_202.raise_for_status()
    valor_2010 = int(resp_202.json()[1]["V"])
    atual["series"]["2010"]["valor"] = valor_2010

    resp_9514 = requests.get(URL_SIDRA_TABELA_9514.format(municipio=municipio), timeout=TIMEOUT_SEGUNDOS)
    resp_9514.raise_for_status()
    valor_2022 = int(resp_9514.json()[1]["V"])
    atual["series"]["2022"]["valor"] = valor_2022

    atual["data_extracao"] = datetime.now(timezone.utc).isoformat()

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=2)

    logger.info("Estimativas municipais IBGE atualizadas: 2010=%d, 2022=%d", valor_2010, valor_2022)
    return {"valor_2010": valor_2010, "valor_2022": valor_2022, "arquivo": str(caminho)}


__all__ = ["baixar_censo2022_bairro_recife", "baixar_estimativas_municipais"]
