"""Diagnóstico do produto: `PASS` / `WARN` / `FAIL` por verificação.

Uso:
    python -m src.healthcheck            # texto legível
    python -m src.healthcheck --json     # saída JSON (uso em automação)

Responde, sem depender de infraestrutura e sem acessar a rede, às quatro
perguntas operacionais:

1. **O pipeline está saudável?** — os artefatos que o dashboard consome
   existem, são legíveis e passam nos portões de qualidade.
2. **Os dados estão atualizados?** — o artefato de freshness existe e diz
   até quando cada conjunto vai.
3. **Os artefatos preditivos são compatíveis?** — metadados presentes,
   assinatura de features batendo, estado do portão de projeção coerente com
   a existência (ou não) de `latest_priority.parquet`.
4. **O dashboard tem os arquivos necessários?** — inclusive os opcionais,
   que devem degradar para `WARN` (o painel funciona sem o módulo
   experimental) e não para `FAIL`.

Código de saída: `0` se nenhuma verificação falhou (`WARN` não falha), `1`
se houver qualquer `FAIL`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.logging_config import configurar_logging

logger = logging.getLogger(__name__)

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dashboard" / "data"

#: Artefatos sem os quais o dashboard **não funciona** — ausência é `FAIL`.
ARTEFATOS_OBRIGATORIOS = {
    "gold_arboviroses_clima_bairro.parquet": "tabela analítica principal",
    "bairro_geo.geojson": "geometria dos 94 bairros",
}

#: Artefatos que habilitam módulos específicos — ausência é `WARN` (modo
#: degradado: o painel histórico continua funcionando sem eles).
ARTEFATOS_OPCIONAIS = {
    "_freshness.json": "metadados de atualidade",
    "_priority_status.json": "estado do módulo experimental de priorização",
    "historical_priority_backtest.parquet": "backtest navegável do módulo experimental",
    "_evidence_summary.json": "resumo da validação estatística do modelo",
    "_gold_clima_grade.json": "manifest do bloco climático em grade",
    "_profiling_export.json": "proveniência da exportação",
}

@dataclass
class Verificacao:
    nome: str
    status: str
    mensagem: str
    detalhe: dict[str, Any] | None = None

    def como_dict(self) -> dict[str, Any]:
        return {
            "verificacao": self.nome,
            "status": self.status,
            "mensagem": self.mensagem,
            "detalhe": self.detalhe or {},
        }

def _verificar_arquivos(pasta: Path) -> list[Verificacao]:
    resultados: list[Verificacao] = []
    for nome, descricao in ARTEFATOS_OBRIGATORIOS.items():
        caminho = pasta / nome
        if not caminho.exists():
            resultados.append(
                Verificacao(f"arquivo:{nome}", FAIL, f"{descricao} ausente — o dashboard não abre sem isto")
            )
        elif caminho.stat().st_size == 0:
            resultados.append(Verificacao(f"arquivo:{nome}", FAIL, f"{descricao} está vazio (0 bytes)"))
        else:
            resultados.append(
                Verificacao(
                    f"arquivo:{nome}", PASS, f"{descricao} presente",
                    {"tamanho_mb": round(caminho.stat().st_size / 1e6, 3)},
                )
            )
    for nome, descricao in ARTEFATOS_OPCIONAIS.items():
        caminho = pasta / nome
        if not caminho.exists():
            resultados.append(
                Verificacao(f"arquivo:{nome}", WARN, f"{descricao} ausente — módulo correspondente fica indisponível")
            )
        else:
            resultados.append(
                Verificacao(
                    f"arquivo:{nome}", PASS, f"{descricao} presente",
                    {"tamanho_mb": round(caminho.stat().st_size / 1e6, 3)},
                )
            )
    return resultados

def _verificar_gold(pasta: Path) -> list[Verificacao]:
    import pandas as pd

    from src.quality_gates import CRITICO, validar_gold

    caminho = pasta / "gold_arboviroses_clima_bairro.parquet"
    if not caminho.exists():
        return [Verificacao("gold:legivel", FAIL, "Gold ausente — portões não executados")]
    try:
        df = pd.read_parquet(caminho)
    except Exception as exc:  # noqa: BLE001 - parquet corrompido pode levantar vários tipos
        return [Verificacao("gold:legivel", FAIL, f"Gold ilegível/corrompida: {exc}")]

    resultados = [
        Verificacao(
            "gold:legivel", PASS, "Gold lida com sucesso",
            {"linhas": int(len(df)), "colunas": int(df.shape[1])},
        )
    ]
    achados = validar_gold(df)
    criticos = [a for a in achados if a.severidade == CRITICO]
    avisos = [a for a in achados if a.severidade != CRITICO]
    if criticos:
        resultados.append(
            Verificacao(
                "gold:portoes_qualidade", FAIL,
                f"{len(criticos)} portão(ões) crítico(s) falharam",
                {"achados": [a.mensagem for a in criticos]},
            )
        )
    else:
        resultados.append(
            Verificacao(
                "gold:portoes_qualidade", PASS,
                "todos os portões críticos aprovados",
                {"avisos": [a.mensagem for a in avisos]},
            )
        )
    return resultados

def _verificar_freshness(pasta: Path) -> list[Verificacao]:
    caminho = pasta / "_freshness.json"
    if not caminho.exists():
        return [
            Verificacao(
                "freshness:presente", WARN,
                "sem metadados de atualidade — rode 'python -m src.generate_freshness'",
            )
        ]
    try:
        artefato = json.loads(caminho.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [Verificacao("freshness:presente", FAIL, f"_freshness.json inválido: {exc}")]

    resultados = []
    epi = (artefato.get("datasets") or {}).get("epidemiologia") or {}
    status_epi = epi.get("status")
    if status_epi == "ATUAL":
        resultados.append(
            Verificacao(
                "freshness:epidemiologia", PASS,
                f"dados epidemiológicos até {epi.get('semana_epi_maxima')} (dentro do limiar)",
            )
        )
    elif status_epi == "ATRASADO":
        # Atraso de fonte oficial trimestral não é falha do sistema — é o
        # estado real do dado, e a UI é obrigada a declará-lo.
        resultados.append(
            Verificacao(
                "freshness:epidemiologia", WARN,
                f"dados epidemiológicos até {epi.get('semana_epi_maxima')} "
                f"({epi.get('atraso_dias')} dias de atraso; limiar {epi.get('limiar_atraso_dias')})",
                {"periodicidade_declarada": (epi.get("detalhe") or {}).get("periodicidade_declarada_pela_fonte")},
            )
        )
    else:
        resultados.append(
            Verificacao("freshness:epidemiologia", WARN, "atualidade epidemiológica indeterminada")
        )
    return resultados

def _verificar_modelo(pasta: Path) -> list[Verificacao]:
    caminho_status = pasta / "_priority_status.json"
    if not caminho_status.exists():
        return [
            Verificacao(
                "modelo:status", WARN,
                "módulo experimental sem status — rode 'python -m src.generate_priority_artifacts'",
            )
        ]
    try:
        status = json.loads(caminho_status.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [Verificacao("modelo:status", FAIL, f"_priority_status.json inválido: {exc}")]

    resultados: list[Verificacao] = []
    if status.get("backtest_available"):
        periodo = status.get("backtest_periodo") or {}
        resultados.append(
            Verificacao(
                "modelo:backtest", PASS,
                f"backtest disponível ({periodo.get('semanas')} semanas, "
                f"{periodo.get('ano_inicio')}-{periodo.get('ano_fim')})",
                {"model_version": status.get("model_version")},
            )
        )
    else:
        resultados.append(
            Verificacao(
                "modelo:backtest", WARN,
                f"backtest indisponível ({status.get('reason')}) — módulo experimental desabilitado",
            )
        )

    caminho_latest = pasta / "latest_priority.parquet"
    disponivel = bool(status.get("current_projection_available"))
    if disponivel and not caminho_latest.exists():
        resultados.append(
            Verificacao(
                "modelo:coerencia_projecao", FAIL,
                "status diz que a projeção atual está disponível, mas latest_priority.parquet não existe",
            )
        )
    elif not disponivel and caminho_latest.exists():
        resultados.append(
            Verificacao(
                "modelo:coerencia_projecao", FAIL,
                "latest_priority.parquet existe apesar de a projeção atual estar bloqueada "
                "— artefato potencialmente enganoso",
            )
        )
    else:
        resultados.append(
            Verificacao(
                "modelo:coerencia_projecao", PASS,
                (
                    "projeção do período atual disponível e materializada"
                    if disponivel
                    else f"projeção do período atual corretamente bloqueada ({status.get('reason')})"
                ),
            )
        )

    from src.ml.artifacts import ArtefatoAusenteError, carregar_metadados
    from src.train_priority_model import MODEL_VERSION

    try:
        metadados = carregar_metadados(MODEL_VERSION)
    except (ArtefatoAusenteError, ValueError):
        resultados.append(
            Verificacao(
                "modelo:artefato_treinado", WARN,
                "modelo treinado ausente localmente — o dashboard não precisa dele "
                "(consome só os Parquet já gerados), mas regenerar artefatos exige treinar",
            )
        )
    else:
        if metadados.get("feature_schema_version") != status.get("feature_schema_version"):
            resultados.append(
                Verificacao(
                    "modelo:artefato_treinado", FAIL,
                    "assinatura de features do modelo treinado difere da usada nos artefatos publicados",
                    {
                        "modelo": metadados.get("feature_schema_version"),
                        "artefatos": status.get("feature_schema_version"),
                    },
                )
            )
        else:
            resultados.append(
                Verificacao(
                    "modelo:artefato_treinado", PASS,
                    f"modelo {metadados.get('model_version')} compatível com os artefatos publicados",
                    {"git_commit": str(metadados.get("git_commit"))[:8]},
                )
            )
    return resultados

def executar_healthcheck(pasta: Optional[Path] = None) -> dict[str, Any]:
    pasta = pasta or PASTA_DADOS
    verificacoes: list[Verificacao] = []
    verificacoes += _verificar_arquivos(pasta)
    verificacoes += _verificar_gold(pasta)
    verificacoes += _verificar_freshness(pasta)
    verificacoes += _verificar_modelo(pasta)

    contagem = {
        PASS: sum(1 for v in verificacoes if v.status == PASS),
        WARN: sum(1 for v in verificacoes if v.status == WARN),
        FAIL: sum(1 for v in verificacoes if v.status == FAIL),
    }
    return {
        "status_geral": FAIL if contagem[FAIL] else (WARN if contagem[WARN] else PASS),
        "contagem": contagem,
        "verificacoes": [v.como_dict() for v in verificacoes],
    }

def main(argv: list[str] | None = None) -> int:
    configurar_logging(nivel="WARNING")
    parser = argparse.ArgumentParser(description="Diagnóstico do produto Recife Alerta.")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    args = parser.parse_args(argv)

    resultado = executar_healthcheck()

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        largura = max(len(v["verificacao"]) for v in resultado["verificacoes"]) + 2
        print("Recife Alerta — healthcheck\n" + "=" * 72)
        for v in resultado["verificacoes"]:
            print(f"{v['status']:<5} {v['verificacao']:<{largura}} {v['mensagem']}")
        print("=" * 72)
        c = resultado["contagem"]
        print(f"{resultado['status_geral']}  ({c[PASS]} PASS · {c[WARN]} WARN · {c[FAIL]} FAIL)")

    return 1 if resultado["contagem"][FAIL] else 0

if __name__ == "__main__":
    sys.exit(main())
