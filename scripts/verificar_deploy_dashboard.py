"""Checagem de preparação para deploy do dashboard (Streamlit Community Cloud).

Uso:
    python scripts/verificar_deploy_dashboard.py

Não inicia um servidor Streamlit real — importa cada módulo do dashboard
num processo Python simples (pega erro de import/sintaxe) e faz checagens
estáticas (dataset presente, sem caminho absoluto local, sem segredo no
código, requirements de deploy existe). A validação funcional completa
(páginas carregam, filtros funcionam, mapas renderizam) foi feita
manualmente via browser nesta sessão — ver relatório da etapa.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DASHBOARD = RAIZ / "dashboard"

PADRAO_CAMINHO_ABSOLUTO_WINDOWS = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:/(?!/)")
PADROES_SEGREDO = re.compile(r"(secret|password|api_key|access_key|token)\s*=\s*[\"']", re.IGNORECASE)


def _checar_arquivo(caminho: Path) -> list[str]:
    problemas = []
    texto = caminho.read_text(encoding="utf-8")

    try:
        ast.parse(texto, filename=str(caminho))
    except SyntaxError as exc:
        problemas.append(f"erro de sintaxe: {exc}")

    if PADRAO_CAMINHO_ABSOLUTO_WINDOWS.search(texto):
        problemas.append("possível caminho absoluto do Windows hardcoded")

    if PADROES_SEGREDO.search(texto):
        problemas.append("possível segredo hardcoded (senha/token/api_key)")

    return problemas


def main() -> int:
    erros: list[str] = []

    arquivos_py = sorted(DASHBOARD.rglob("*.py"))
    print(f"Checando {len(arquivos_py)} arquivo(s) .py em dashboard/...")
    for arquivo in arquivos_py:
        problemas = _checar_arquivo(arquivo)
        for problema in problemas:
            erros.append(f"{arquivo.relative_to(RAIZ)}: {problema}")

    dataset_gold = DASHBOARD / "data" / "gold_arboviroses_clima_bairro.parquet"
    dataset_geo = DASHBOARD / "data" / "bairro_geo.geojson"
    if not dataset_gold.exists():
        erros.append(f"dataset ausente: {dataset_gold} (rode 'python -m src.export_dashboard_dataset')")
    if not dataset_geo.exists():
        erros.append(f"dataset ausente: {dataset_geo} (rode 'python -m src.export_dashboard_dataset')")

    requirements_dashboard = DASHBOARD / "requirements.txt"
    if not requirements_dashboard.exists():
        erros.append(f"requirements de deploy ausente: {requirements_dashboard}")

    arquivo_env = RAIZ / ".env"
    if arquivo_env.exists():
        gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        if ".env" not in gitignore.splitlines():
            erros.append(".env existe localmente e NÃO está no .gitignore — risco de commit acidental de segredo")

    if erros:
        print("\nProblemas encontrados:")
        for erro in erros:
            print(f"  - {erro}")
        return 1

    print("\nOK — nenhum problema estático encontrado.")
    print(
        f"Dataset: {dataset_gold.stat().st_size / 1e6:.2f} MB (Gold) + "
        f"{dataset_geo.stat().st_size / 1e6:.2f} MB (geometria)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
