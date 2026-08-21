"""Gera `reports/forecast/arbovirus_2026_projection.md` a partir do
artefato já calculado por `python -m src.generate_forecast_artifacts`
(nunca recalcula nada — só formata o que já está em
`dashboard/data/_forecast_2026_metadata.json`).

Uso:
    python -m src.generate_forecast_report
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src.eda.schema_eda import AGRAVOS
from src.logging_config import configurar_logging
from src.utils.io_atomico import escrever_texto_atomico

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_RELATORIO = RAIZ / "reports" / "forecast" / "arbovirus_2026_projection.md"
CAMINHO_METADATA = RAIZ / "dashboard" / "data" / "_forecast_2026_metadata.json"


def _carregar_metadados() -> Optional[dict[str, Any]]:
    """Lê o JSON de metadados diretamente (sem depender de
    `dashboard.utils.data_loader`, que é código de app Streamlit — `src/`
    nunca importa `dashboard/`, só o inverso)."""
    if not CAMINHO_METADATA.exists():
        return None
    return json.loads(CAMINHO_METADATA.read_text(encoding="utf-8"))

AVISO_PERMANENTE = (
    "Projeção estatística baseada nos dados históricos disponíveis até 2025. "
    "Não representa casos observados em 2026 nem previsão oficial da Prefeitura do Recife."
)


def _tabela_backtest(dobras: list[dict]) -> str:
    linhas = [
        "| Ano-alvo | MAE | RMSE | MASE | Pico observado (SE) | Pico previsto (SE) | Erro de timing (semanas) | Erro de magnitude do pico |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in dobras:
        linhas.append(
            f"| {d['ano_alvo']} | {d['mae']:.1f} | {d['rmse']:.1f} | {d['mase']:.3f} | "
            f"{d['semana_pico_observada']} | {d['semana_pico_prevista']} | {d['erro_timing_semanas']:+d} | "
            f"{d['erro_magnitude_pico']:+.1f} |"
        )
    return "\n".join(linhas)


def _fmt_cobertura(valor) -> str:
    return "—" if valor is None else f"{valor * 100:.0f}%"


def _tabela_cobertura(por_dobra: list[dict]) -> str:
    linhas = ["| Ano-alvo | Cobertura 80% | Cobertura 95% |", "|---|---|---|"]
    for d in por_dobra:
        linhas.append(
            f"| {d['ano_alvo']} | {_fmt_cobertura(d.get('cobertura_80'))} | "
            f"{_fmt_cobertura(d.get('cobertura_95'))} |"
        )
    return "\n".join(linhas)


def _tabela_modelos(resumo: list[dict]) -> str:
    linhas = [
        "| Modelo | Dobras válidas | MASE mediano | Erro de timing absoluto mediano (semanas) |",
        "|---|---|---|---|",
    ]
    for r in resumo:
        mase = f"{r['mase_mediano']:.3f}" if r["mase_mediano"] is not None else "—"
        timing = f"{r['erro_timing_absoluto_mediano']:.1f}" if r["erro_timing_absoluto_mediano"] is not None else "—"
        linhas.append(f"| {r['modelo']} | {r['n_dobras_validas']} | {mase} | {timing} |")
    return "\n".join(linhas)


def _secao_agravo(agravo: str, dados: dict) -> str:
    if not dados.get("disponivel"):
        return f"## {agravo}\n\nIndisponível: {dados.get('motivo')}\n"

    pico = dados["pico_projetado"]
    media_hist = dados["media_semanal_historica_comparavel"]
    razao = pico["casos_esperados"] / media_hist if media_hist else None
    razao_txt = f"{razao:.1f}×" if razao is not None else "—"

    achados_extra = ""
    for dobra in dados["backtest_por_dobra_do_modelo_escolhido"]:
        if abs(dobra["erro_timing_semanas"]) >= 10:
            achados_extra += (
                f"\n> **Achado honesto**: no backtest de {dobra['ano_alvo']}, o modelo escolhido errou o "
                f"timing do pico por {abs(dobra['erro_timing_semanas'])} semanas (previu SE "
                f"{dobra['semana_pico_prevista']}, real foi SE {dobra['semana_pico_observada']}) — "
                "um ano com padrão sazonal atípico frente à média histórica usada pelo modelo.\n"
            )

    return f"""## {agravo}

**Modelo escolhido**: `{dados['modelo_escolhido']}` (banda de incerteza: {dados['metodo_banda']}), entre 3
baselines obrigatórios e 1 método adicional (ETS/Holt-Winters), escolhido pela mediana do MASE nas 3
dobras do backtest walk-forward — nunca olhando 2026.

### Comparação de modelos no backtest

{_tabela_modelos(dados['resumo_backtest_por_modelo'])}

### Desempenho do modelo escolhido, por dobra

{_tabela_backtest(dados['backtest_por_dobra_do_modelo_escolhido'])}
{achados_extra}
### Cobertura das bandas de previsão (leave-one-fold-out)

A banda de cada dobra do backtest usa os erros das OUTRAS dobras (nunca os
da própria, o que inflaria a cobertura artificialmente):
{_tabela_cobertura(dados['cobertura_intervalo_por_dobra'])}

Cobertura média — 80%: {_fmt_cobertura(dados['cobertura_intervalo_media'].get('cobertura_80_media'))} ·
95%: {_fmt_cobertura(dados['cobertura_intervalo_media'].get('cobertura_95_media'))}.
Com só 3 dobras, a cobertura média é uma leitura aproximada, não uma
estimativa estatisticamente precisa da taxa de cobertura real.

### Projeção 2026

- **Semana de maior valor esperado**: SE {pico['semana_epidemiologica']}/2026 (início em
  {pico['data_inicio']}).
- **Casos esperados no pico**: {pico['casos_esperados']}.
- **Média sazonal histórica das mesmas semanas**: {media_hist:.1f} casos/semana.
- **Pico projetado vs. média histórica**: {razao_txt}.
- **Incidência 2026**: não calculada — {dados['motivo_incidencia_2026_indisponivel']}.

A série semanal completa (observado 2013-{dados['ultimo_ano_historico']} + projeção 2026 com bandas
80%/95%) está em `dashboard/data/_forecast_2026.parquet`, coluna `is_observado` distingue as duas
partes.
"""


def gerar_relatorio() -> str:
    metadados = _carregar_metadados()
    if metadados is None:
        raise RuntimeError(
            "dashboard/data/_forecast_2026_metadata.json não encontrado — rode "
            "'python -m src.generate_forecast_artifacts' antes deste relatório."
        )

    secoes = [_secao_agravo(agravo, metadados["por_agravo"].get(agravo, {"disponivel": False})) for agravo in AGRAVOS]

    return f"""# Projeção epidemiológica sazonal 2026 (casos, por agravo)

Gerado por `python -m src.generate_forecast_report` a partir de
`dashboard/data/_forecast_2026_metadata.json` (produzido por
`python -m src.generate_forecast_artifacts`, que por sua vez usa
`src/forecast/`). Todos os números abaixo são reais.

> **{AVISO_PERMANENTE}**

## Fonte de casos 2026 — verificação ao vivo (2026-08-21)

O Portal de Dados Abertos do Recife (`dados.recife.pe.gov.br`, dataset "Casos de Dengue, Zika e
Chikungunya") foi consultado ao vivo nesta sessão: 58 recursos, todos rotulados até 2025; o
metadado do dataset foi tocado em 2026-05-20, mas nenhum recurso 2026 existe. **Não há caso
observado de 2026 nesta fonte.** Existe um boletim estadual (SES-PE, Boletim Epidemiológico de
Arboviroses) com números de 2026 para Pernambuco inteiro, mas é uma fonte diferente — estadual,
sem granularidade de bairro — e integrá-la ao pipeline está fora do escopo desta etapa.

## População municipal 2026 — verificação ao vivo (2026-08-21)

As estimativas municipais mais recentes do IBGE têm data de referência 01/07/2025; nenhuma
estimativa oficial municipal de 2026 foi encontrada. Por isso a projeção é sempre em número de
casos — nunca em incidência por 100 mil habitantes para 2026 (`reports/population/` também para em
2025, e estender essa metodologia exigiria um total municipal 2026 que igualmente não existe).

## Metodologia

- **Granularidade**: Recife total × agravo × semana. Nenhuma projeção por bairro/RPA é publicada
  (instabilidade alta demais numa série semanal por bairro para ser defensável).
- **Baselines obrigatórios**: seasonal naive (repete a mesma semana do último ano), média
  histórica da mesma semana epidemiológica, tendência linear + sazonalidade média.
- **Método adicional**: ETS/Holt-Winters (`statsmodels`), único, sem SARIMA/deep learning/AutoML.
- **Seleção do modelo**: mediana do MASE (erro relativo ao seasonal naive) nas 3 dobras do backtest
  walk-forward (treina ≤2022→prevê 2023; ≤2023→2024; ≤2024→2025), desempate pelo menor erro de
  timing do pico absoluto mediano — nunca escolhido olhando 2026.
- **Intervalos**: 80% e 95%, via quantis empíricos dos erros do próprio backtest (ou simulação
  nativa do ETS quando é o modelo escolhido) — nunca uma única linha.

{chr(10).join(secoes)}

## Limitações gerais

- Nenhuma das três séries (dengue, zika, chikungunya) tem caso observado em 2026 — toda a seção
  "Projeção 2026" é, por definição, extrapolação estatística do padrão 2013-2025.
- O backtest mostra que o erro de timing do pico pode ser grande num ano atípico (ver achados
  honestos por agravo acima) — a banda de 95% existe para comunicar essa incerteza, a projeção
  central não deve ser lida como data exata.
- Projeção completamente separada da Priorização Territorial Experimental (V1/V2): nenhuma usa a
  outra como insumo, nenhuma foi ajustada para concordar com a outra.
"""


def main() -> int:
    configurar_logging()
    try:
        conteudo = gerar_relatorio()
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1
    escrever_texto_atomico(CAMINHO_RELATORIO, conteudo)
    logger.info("Relatório de projeção 2026 gerado em %s", CAMINHO_RELATORIO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
