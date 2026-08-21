"""Versionamento, gravação e carregamento **validado** de artefatos de ML.

## Regra de ouro: falhar fechado

Um recurso preditivo nunca deve exibir um ranking aparentemente válido a
partir de um artefato ausente, incompatível ou desatualizado. Toda
incompatibilidade detectada aqui vira exceção (`ArtefatoIncompativelError`),
e quem consome deve transformar isso numa mensagem honesta de
indisponibilidade — nunca num resultado silenciosamente errado.

## Metadados obrigatórios

Todo artefato carrega, no mesmo diretório, um `metadata.json` com:

| campo | por que é obrigatório |
|---|---|
| `model_version` | identidade do candidato; qualquer mudança de modelo/feature/target cria uma versão nova |
| `feature_schema_version` | assinatura do conjunto de features; se mudar, o modelo salvo não pode ser aplicado |
| `feature_names` | ordem e nomes exatos das colunas de `X` no treino |
| `trained_until` | último ano epidemiológico presente no treino |
| `target_definition` | descrição textual do alvo (não é decorativo: impede confundir onset com estado) |
| `horizon` | horizonte em semanas |
| `git_commit` | commit do código que gerou o artefato |
| `created_at` | quando foi gerado |
| `data_cutoff` | data-limite dos dados usados (nada posterior entra em feature) |
| `cutoff_epi_year` / `cutoff_epi_week` | o mesmo corte em semana epidemiológica |
| `sklearn_version` | pickle de modelo sklearn não é portável entre versões maiores |
| `gold_schema_version` | versão da Gold que originou as features |

## Sobre desserialização

O artefato é um pickle (`joblib`) gerado **pelo próprio pipeline deste
repositório**. Carregar pickle executa código, portanto:

- o caminho do artefato **nunca** vem de entrada de usuário (ver
  `caminho_artefato`, que só compõe caminhos sob `artifacts/models/` a
  partir de um `model_version` validado contra uma lista permitida);
- o dashboard público **não** carrega modelo nenhum: ele lê apenas os
  Parquet/JSON já calculados. Assim nenhuma superfície pública desserializa
  objeto arbitrário.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_ARTEFATOS_MODELOS = RAIZ / "artifacts" / "models"

NOME_ARQUIVO_MODELO = "model.joblib"
NOME_ARQUIVO_METADADOS = "metadata.json"

#: Versões de modelo que este código sabe produzir e consumir. Serve como
#: lista permitida para nunca compor caminho de arquivo a partir de texto
#: arbitrário.
VERSOES_CONHECIDAS = ("dengue_onset_ranking_candidate_v1",)

PADRAO_VERSAO = re.compile(r"^[a-z0-9_]+$")


class ArtefatoIncompativelError(RuntimeError):
    """Artefato existe mas não pode ser usado com segurança."""


class ArtefatoAusenteError(FileNotFoundError):
    """Artefato de modelo não encontrado."""


@dataclass
class MetadadosModelo:
    model_version: str
    feature_schema_version: str
    feature_names: list[str]
    trained_until: int
    target_definition: str
    horizon: int
    git_commit: str
    created_at: str
    data_cutoff: str
    cutoff_epi_year: int
    cutoff_epi_week: int
    sklearn_version: str
    gold_schema_version: str
    hyperparameters: dict[str, Any]
    seed: int
    n_treino: int
    observacoes: str = ""

    @property
    def cutoff_epi_week_formatada(self) -> str:
        return f"{self.cutoff_epi_year}-{self.cutoff_epi_week:02d}"

    def como_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["cutoff_epi_week_formatada"] = self.cutoff_epi_week_formatada
        return dados


def commit_atual() -> str:
    """Commit do código que gerou o artefato. Em ambiente sem git ou fora de
    repositório, devolve `"desconhecido"` — nunca inventa um hash.

    O executável é resolvido com `shutil.which` e invocado pelo caminho
    absoluto, com `shell=False` e lista de argumentos fixa: nenhum dado de
    usuário entra na chamada, e um `git` plantado mais cedo no `PATH` não é
    escolhido por acidente (achado da análise estática — B603/B607).
    """
    executavel = shutil.which("git")
    if not executavel:  # pragma: no cover - ambiente sem git
        return "desconhecido"
    try:
        saida = subprocess.run(  # noqa: S603 - argumentos fixos, sem entrada de usuário
            [executavel, "rev-parse", "HEAD"],
            cwd=RAIZ, capture_output=True, text=True, timeout=15, check=False, shell=False,
        )
        if saida.returncode == 0 and saida.stdout.strip():
            return saida.stdout.strip()
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - falha do git
        pass
    return "desconhecido"


def assinatura_features(feature_names: Sequence[str]) -> str:
    """Assinatura estável do conjunto de features: contagem + hash curto dos
    nomes em ordem. Detecta tanto feature nova quanto reordenação (que
    quebraria um modelo sklearn treinado sobre a ordem antiga)."""
    import hashlib

    bruto = "|".join(feature_names).encode("utf-8")
    return f"{len(feature_names)}-{hashlib.sha256(bruto).hexdigest()[:12]}"


def caminho_artefato(model_version: str, base: Optional[Path] = None) -> Path:
    """Diretório do artefato. Valida `model_version` contra a lista
    permitida e contra um padrão restrito — nunca compõe caminho a partir de
    texto livre (defesa contra *path traversal*)."""
    if not PADRAO_VERSAO.match(model_version):
        raise ValueError(f"model_version inválida: {model_version!r}")
    if model_version not in VERSOES_CONHECIDAS:
        raise ValueError(
            f"model_version {model_version!r} não está em VERSOES_CONHECIDAS={VERSOES_CONHECIDAS}"
        )
    return (base or PASTA_ARTEFATOS_MODELOS) / model_version


def salvar_artefato_modelo(
    modelo,
    metadados: MetadadosModelo,
    base: Optional[Path] = None,
) -> Path:
    """Grava modelo + metadados atomicamente no diretório da versão."""
    import joblib

    from src.utils.io_atomico import caminho_temporario, escrever_json_atomico

    destino = caminho_artefato(metadados.model_version, base)
    destino.mkdir(parents=True, exist_ok=True)

    with caminho_temporario(destino / NOME_ARQUIVO_MODELO) as temporario:
        joblib.dump(modelo, temporario)
    escrever_json_atomico(destino / NOME_ARQUIVO_METADADOS, metadados.como_dict())
    logger.info("Artefato de modelo gravado em %s", destino)
    return destino


def carregar_metadados(model_version: str, base: Optional[Path] = None) -> dict[str, Any]:
    caminho = caminho_artefato(model_version, base) / NOME_ARQUIVO_METADADOS
    if not caminho.exists():
        raise ArtefatoAusenteError(
            f"metadados do modelo não encontrados em {caminho}. "
            "Rode 'python -m src.train_priority_model' primeiro."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def carregar_artefato_modelo(
    model_version: str,
    feature_names_esperadas: Optional[Sequence[str]] = None,
    gold_schema_version_esperada: Optional[str] = None,
    base: Optional[Path] = None,
) -> tuple[Any, dict[str, Any]]:
    """Carrega modelo + metadados **validando compatibilidade**.

    Levanta `ArtefatoAusenteError` se não existir e
    `ArtefatoIncompativelError` se:

    - a assinatura de features do artefato não bater com
      `feature_names_esperadas` (nome, quantidade ou ordem);
    - a versão de schema da Gold não bater com a esperada;
    - a versão instalada do scikit-learn tiver *major.minor* diferente da
      que gerou o pickle.
    """
    import joblib
    import sklearn

    diretorio = caminho_artefato(model_version, base)
    caminho_modelo = diretorio / NOME_ARQUIVO_MODELO
    if not caminho_modelo.exists():
        raise ArtefatoAusenteError(
            f"modelo não encontrado em {caminho_modelo}. "
            "Rode 'python -m src.train_priority_model' primeiro."
        )
    metadados = carregar_metadados(model_version, base)

    if feature_names_esperadas is not None:
        esperada = assinatura_features(list(feature_names_esperadas))
        if esperada != metadados.get("feature_schema_version"):
            raise ArtefatoIncompativelError(
                "assinatura de features incompatível: artefato="
                f"{metadados.get('feature_schema_version')!r} vs atual={esperada!r}. "
                "O conjunto de features mudou — treine uma nova versão em vez de reusar esta."
            )

    if gold_schema_version_esperada is not None:
        if metadados.get("gold_schema_version") != gold_schema_version_esperada:
            raise ArtefatoIncompativelError(
                "versão de schema da Gold incompatível: artefato="
                f"{metadados.get('gold_schema_version')!r} vs atual={gold_schema_version_esperada!r}"
            )

    minor_artefato = ".".join(str(metadados.get("sklearn_version", "")).split(".")[:2])
    minor_atual = ".".join(sklearn.__version__.split(".")[:2])
    if minor_artefato and minor_artefato != minor_atual:
        raise ArtefatoIncompativelError(
            f"scikit-learn do artefato ({metadados.get('sklearn_version')}) difere do instalado "
            f"({sklearn.__version__}) — pickle de modelo não é portável entre versões maiores"
        )

    modelo = joblib.load(caminho_modelo)
    logger.info(
        "Artefato carregado: %s (treinado até %s, commit %s)",
        metadados.get("model_version"), metadados.get("trained_until"),
        str(metadados.get("git_commit"))[:8],
    )
    return modelo, metadados


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
