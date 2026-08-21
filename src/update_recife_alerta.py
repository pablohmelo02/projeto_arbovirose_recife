"""Orquestra a atualização do produto Recife Alerta.

Uso:
    python -m src.update_recife_alerta                  # atualização padrão (sem Data Lake)
    python -m src.update_recife_alerta --com-datalake    # inclui Bronze/Silver/Gold no MinIO
    python -m src.update_recife_alerta --sem-rede        # só recalcula com o que já está em disco

## Etapas — e o que esta rotina deliberadamente NÃO faz

    ingestão → validação → transformação → exportação → healthcheck

**Nunca treina modelo.** Treinar é `python -m src.train_priority_model`,
operação separada, controlada e com revisão humana do resultado — não um
efeito colateral de um refresh de dados. Um retreino silencioso mudaria os
números publicados sem que ninguém decidisse isso.

Também não recalcula a evidência estatística do candidato
(`src/validate_dengue_onset_ranking_evidence.py`) nem roda experimentos.

## Duas variantes

- **Padrão (sem `--com-datalake`)**: atualiza o que não depende de
  infraestrutura — clima em grade (rede), bloco climático da Gold,
  freshness, artefatos de priorização, healthcheck. É a variante usada no
  ambiente de desenvolvimento deste projeto, que não tem MinIO/Docker.
- **`--com-datalake`**: acrescenta, ANTES do resto, a cadeia canônica
  completa (CKAN/INMET/CEMADEN → Bronze → Silver → Gold → exportação do
  dataset do dashboard). Exige `.env` configurado e MinIO acessível.

Cada etapa é registrada com duração e resultado. Uma etapa que falha
**interrompe** a atualização (não há "continuar com dado parcial"), exceto
as marcadas como tolerantes, que apenas registram aviso.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.logging_config import configurar_logging

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent

@dataclass
class ResultadoEtapa:
    nome: str
    ok: bool
    duracao_s: float
    codigo_saida: Optional[int] = None
    erro: Optional[str] = None
    tolerante: bool = False
    detalhe: dict[str, Any] = field(default_factory=dict)

    def como_dict(self) -> dict[str, Any]:
        return {
            "etapa": self.nome,
            "ok": self.ok,
            "duracao_s": round(self.duracao_s, 2),
            "codigo_saida": self.codigo_saida,
            "erro": self.erro,
            "tolerante": self.tolerante,
            **({"detalhe": self.detalhe} if self.detalhe else {}),
        }

def _executar(nome: str, funcao: Callable[[], int], tolerante: bool = False) -> ResultadoEtapa:
    logger.info("--- %s ---", nome)
    inicio = time.monotonic()
    try:
        codigo = funcao()
    except Exception as exc:  # noqa: BLE001 - a etapa reporta, o orquestrador decide
        duracao = time.monotonic() - inicio
        logger.error("Etapa %r falhou: %s", nome, exc)
        return ResultadoEtapa(nome, False, duracao, erro=f"{type(exc).__name__}: {exc}", tolerante=tolerante)
    duracao = time.monotonic() - inicio
    ok = codigo == 0
    (logger.info if ok else logger.error)(
        "Etapa %r %s em %.1fs (codigo=%s)", nome, "concluída" if ok else "falhou", duracao, codigo
    )
    return ResultadoEtapa(nome, ok, duracao, codigo_saida=codigo, tolerante=tolerante)

def _etapas_datalake() -> list[tuple[str, Callable[[], int], bool]]:
    """Cadeia canônica completa — só com `--com-datalake`."""
    from src import (
        export_dashboard_dataset, ingest_climate, ingest_territorio, main as ingest_arboviroses,
        transform, transform_climate, transform_climate_bairro,
        transform_gold_arboviroses_clima, transform_territorio, validate,
    )

    return [
        ("ingestao: arboviroses (CKAN -> Bronze)", ingest_arboviroses.main, False),
        ("validacao: Bronze de arboviroses", validate.main, True),
        ("ingestao: territorio (CKAN -> Bronze)", ingest_territorio.main, False),
        ("transformacao: territorio (Bronze -> Silver)", transform_territorio.main, False),
        ("ingestao: clima INMET/APAC/CEMADEN (-> Bronze)", ingest_climate.main, False),
        ("transformacao: clima (Bronze -> Silver)", transform_climate.main, False),
        ("transformacao: bairro -> estacao (Estrategia A)", transform_climate_bairro.main, False),
        ("transformacao: arboviroses (Bronze -> Silver)", transform.main, False),
        ("transformacao: Gold arboviroses+clima", transform_gold_arboviroses_clima.main, False),
        ("exportacao: dataset do dashboard", export_dashboard_dataset.main, False),
    ]

def main(argv: list[str] | None = None) -> int:
    configurar_logging()
    parser = argparse.ArgumentParser(description="Atualiza o produto Recife Alerta.")
    parser.add_argument(
        "--com-datalake", action="store_true",
        help="inclui a cadeia canônica Bronze/Silver/Gold no MinIO (exige .env e MinIO no ar)",
    )
    parser.add_argument(
        "--sem-rede", action="store_true",
        help="não acessa a rede: recalcula apenas com o que já está em disco",
    )
    args = parser.parse_args(argv)

    from src import (
        build_climate_grade, enrich_gold_clima_grade, generate_freshness,
        generate_priority_artifacts, healthcheck,
    )

    etapas: list[ResultadoEtapa] = []
    inicio_total = time.monotonic()

    if args.com_datalake:
        if args.sem_rede:
            logger.error("--com-datalake e --sem-rede são incompatíveis (a cadeia canônica precisa de rede).")
            return 2
        for nome, funcao, tolerante in _etapas_datalake():
            resultado = _executar(nome, funcao, tolerante)
            etapas.append(resultado)
            if not resultado.ok and not resultado.tolerante:
                return _finalizar(etapas, inicio_total, interrompido_em=nome)

    if not args.sem_rede:
        resultado = _executar(
            "ingestao/Silver: clima em grade (reanalise)",
            lambda: build_climate_grade.main(["--destino", "local"]),
        )
        etapas.append(resultado)
        if not resultado.ok:
            return _finalizar(etapas, inicio_total, interrompido_em=resultado.nome)

    for nome, funcao, tolerante in (
        ("transformacao: Gold += clima em grade", lambda: enrich_gold_clima_grade.main(["--origem", "local"]), False),
        (
            "metadados: freshness",
            lambda: generate_freshness.main(["--offline"] if args.sem_rede else []),
            False,
        ),
        ("artefatos: priorizacao experimental (sem treinar)", generate_priority_artifacts.main, True),
    ):
        resultado = _executar(nome, funcao, tolerante)
        etapas.append(resultado)
        if not resultado.ok and not resultado.tolerante:
            return _finalizar(etapas, inicio_total, interrompido_em=nome)

    etapas.append(_executar("healthcheck", lambda: healthcheck.main([]), tolerante=True))
    return _finalizar(etapas, inicio_total)

def _finalizar(
    etapas: list[ResultadoEtapa], inicio_total: float, interrompido_em: Optional[str] = None
) -> int:
    from src.utils.io_atomico import escrever_json_atomico

    duracao = time.monotonic() - inicio_total
    falhas = [e for e in etapas if not e.ok and not e.tolerante]
    avisos = [e for e in etapas if not e.ok and e.tolerante]
    resumo = {
        "concluido": interrompido_em is None and not falhas,
        "interrompido_em": interrompido_em,
        "duracao_total_s": round(duracao, 2),
        "n_etapas": len(etapas),
        "n_falhas": len(falhas),
        "n_avisos": len(avisos),
        "etapas": [e.como_dict() for e in etapas],
    }
    escrever_json_atomico(RAIZ / "dashboard" / "data" / "_ultima_atualizacao.json", resumo)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    logger.info(
        "Atualização %s em %.1fs (%d etapa(s), %d falha(s), %d aviso(s))",
        "concluída" if resumo["concluido"] else "INTERROMPIDA", duracao, len(etapas), len(falhas), len(avisos),
    )
    return 0 if resumo["concluido"] else 1

if __name__ == "__main__":
    sys.exit(main())
