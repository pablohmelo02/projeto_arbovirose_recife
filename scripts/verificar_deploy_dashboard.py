"""Checagem de aptidão para deploy público do Recife Alerta.

Uso:
    python scripts/verificar_deploy_dashboard.py

Verificação **estática**, sem subir servidor: sintaxe, dependências
proibidas em runtime, caminhos absolutos, segredos, artefatos necessários,
tamanho publicado e — a checagem mais importante — **privacidade do dataset
publicado**. A verificação funcional (páginas, filtros, mapas, larguras)
é `scripts/testar_dashboard_navegador.py`, que precisa de navegador.

Código de saída: 0 se apto, 1 se houver bloqueio.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

DASHBOARD = RAIZ / "dashboard"
DADOS = DASHBOARD / "data"

PADRAO_CAMINHO_ABSOLUTO = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:/(?!/)|/home/[a-z]|/Users/")
PADRAO_SEGREDO = re.compile(
    r"(secret|password|senha|api_key|access_key|token)\s*=\s*[\"'][^\"']{4,}", re.IGNORECASE
)

#: Módulos que o dashboard publicado NÃO pode importar: exigem
#: infraestrutura (MinIO/moto), binários pesados (GDAL do geopandas) ou
#: capacidade de treinar modelo em tempo de renderização.
IMPORTS_PROIBIDOS_NO_DASHBOARD = {
    "boto3", "botocore", "moto", "geopandas", "shapely", "pyproj",
    "sklearn", "joblib", "matplotlib", "requests",
}

#: Colunas que, se aparecessem em qualquer artefato publicado, indicariam
#: vazamento de dado individual. Lista defensiva — não é o que a Gold tem.
COLUNAS_PROIBIDAS = (
    "id_notificacao", "nu_notific", "nome", "nome_paciente", "cpf", "cns",
    "data_nascimento", "dt_nasc", "endereco", "logradouro", "numero_casa",
    "telefone", "email", "prontuario", "latitude_paciente", "longitude_paciente",
)

ARTEFATOS_OBRIGATORIOS = ("gold_arboviroses_clima_bairro.parquet", "bairro_geo.geojson")

#: Limite prático do Streamlit Community Cloud para um repositório
#: confortável. Não é um limite rígido da plataforma, é uma folga saudável.
LIMITE_TOTAL_MB = 200.0


def _modulos_importados(arvore: ast.Module) -> set[str]:
    modulos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(alias.name.split(".")[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            modulos.add(no.module.split(".")[0])
    return modulos


def _checar_codigo() -> list[str]:
    problemas: list[str] = []
    arquivos = sorted(DASHBOARD.rglob("*.py"))
    print(f"[1/5] Analisando {len(arquivos)} arquivo(s) .py do dashboard...")
    for arquivo in arquivos:
        relativo = arquivo.relative_to(RAIZ)
        texto = arquivo.read_text(encoding="utf-8")
        try:
            arvore = ast.parse(texto, filename=str(arquivo))
        except SyntaxError as exc:
            problemas.append(f"{relativo}: erro de sintaxe: {exc}")
            continue

        proibidos = _modulos_importados(arvore) & IMPORTS_PROIBIDOS_NO_DASHBOARD
        if proibidos:
            problemas.append(
                f"{relativo}: importa módulo não disponível/indesejado em runtime: {sorted(proibidos)}"
            )
        if PADRAO_CAMINHO_ABSOLUTO.search(texto):
            problemas.append(f"{relativo}: possível caminho absoluto de máquina local")
        if PADRAO_SEGREDO.search(texto):
            problemas.append(f"{relativo}: possível segredo literal no código")
    return problemas


def _checar_dependencias_transitivas() -> list[str]:
    """`src/eda/*` e `src/freshness.py` são importados pelo dashboard: eles
    também não podem puxar dependência de infraestrutura."""
    problemas: list[str] = []
    modulos_consumidos = sorted((RAIZ / "src" / "eda").glob("*.py"))
    print(f"[2/5] Analisando {len(modulos_consumidos)} módulo(s) de src/eda/ consumido(s)...")
    for arquivo in modulos_consumidos:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        proibidos = _modulos_importados(arvore) & IMPORTS_PROIBIDOS_NO_DASHBOARD
        if proibidos:
            problemas.append(
                f"{arquivo.relative_to(RAIZ)}: importa {sorted(proibidos)} — quebraria o deploy mínimo"
            )
    return problemas


def _checar_artefatos() -> tuple[list[str], float]:
    problemas: list[str] = []
    print("[3/5] Verificando artefatos publicados...")
    total_bytes = 0
    for nome in ARTEFATOS_OBRIGATORIOS:
        caminho = DADOS / nome
        if not caminho.exists():
            problemas.append(
                f"artefato obrigatório ausente: {nome} (rode 'python -m src.update_recife_alerta')"
            )
        elif caminho.stat().st_size == 0:
            problemas.append(f"artefato obrigatório vazio: {nome}")
    for caminho in DADOS.glob("*"):
        if caminho.is_file():
            total_bytes += caminho.stat().st_size

    if not (DASHBOARD / "requirements.txt").exists():
        problemas.append("dashboard/requirements.txt ausente — o Cloud não saberia o que instalar")
    if not (RAIZ / ".streamlit" / "config.toml").exists():
        problemas.append(".streamlit/config.toml ausente")

    total_mb = total_bytes / 1e6
    if total_mb > LIMITE_TOTAL_MB:
        problemas.append(f"dados publicados somam {total_mb:.1f} MB (acima de {LIMITE_TOTAL_MB} MB)")
    return problemas, total_mb


def _checar_privacidade() -> list[str]:
    """A checagem que não pode falhar: nenhum artefato publicado contém
    coluna potencialmente identificável."""
    import pandas as pd

    from src.quality_gates import validar_dataset_publicavel

    problemas: list[str] = []
    parquets = sorted(DADOS.glob("*.parquet"))
    print(f"[4/5] Verificando privacidade de {len(parquets)} arquivo(s) Parquet publicado(s)...")
    for caminho in parquets:
        try:
            colunas = pd.read_parquet(caminho).columns
        except Exception as exc:  # noqa: BLE001 - artefato ilegível também é bloqueio
            problemas.append(f"{caminho.name}: ilegível ({exc})")
            continue
        achados = validar_dataset_publicavel(pd.DataFrame(columns=colunas), COLUNAS_PROIBIDAS)
        problemas.extend(f"{caminho.name}: {a.mensagem}" for a in achados)

    geo = DADOS / "bairro_geo.geojson"
    if geo.exists():
        conteudo = json.loads(geo.read_text(encoding="utf-8"))
        propriedades = set()
        for feature in conteudo.get("features", []):
            propriedades.update((feature.get("properties") or {}).keys())
        suspeitas = {p for p in propriedades if p.lower() in COLUNAS_PROIBIDAS}
        if suspeitas:
            problemas.append(f"bairro_geo.geojson: propriedade identificável {sorted(suspeitas)}")
    return problemas


def _checar_segredos_no_repositorio() -> list[str]:
    problemas: list[str] = []
    print("[5/5] Verificando segredos e .gitignore...")
    gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    obrigatorios = (".env", ".streamlit/secrets.toml", "*.pem", "*.key")
    for padrao in obrigatorios:
        if padrao not in gitignore:
            problemas.append(f".gitignore não cobre {padrao!r}")

    for nome in (".env", ".streamlit/secrets.toml"):
        if (RAIZ / nome).exists():
            print(f"      nota: {nome} existe localmente (coberto pelo .gitignore)")
    return problemas


def main() -> int:
    print("Recife Alerta — verificação de aptidão para deploy\n" + "=" * 68)
    problemas: list[str] = []
    problemas += _checar_codigo()
    problemas += _checar_dependencias_transitivas()
    problemas_artefatos, total_mb = _checar_artefatos()
    problemas += problemas_artefatos
    problemas += _checar_privacidade()
    problemas += _checar_segredos_no_repositorio()

    print("=" * 68)
    if problemas:
        print(f"NÃO APTO — {len(problemas)} bloqueio(s):")
        for problema in problemas:
            print(f"  - {problema}")
        return 1

    print(f"APTO — nenhum bloqueio. Dados publicados: {total_mb:.2f} MB em dashboard/data/.")
    print("Lembrete: 'tecnicamente apto' não é 'publicado'. A publicação exige a conta do")
    print("Streamlit Community Cloud e é uma decisão humana.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
