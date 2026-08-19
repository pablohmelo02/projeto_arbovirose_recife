"""Contrato canônico do mapeamento Silver bairro -> estação climática
(`silver_bairro_estacao_climatica`).

Implementa a **Estratégia A** (estação elegível mais próxima), decisão
registrada em `README.md` (seção 26): as estratégias B/C/D (múltiplas
estações, IDW, kriging) exigem profundidade histórica que a APAC ainda não
tem no nosso Data Lake — não são implementadas aqui.

Duas relações que NUNCA devem ser confundidas (ver docstring de
`climate_bairro.py`):

- **localização física**: a estação está dentro do polígono do bairro X —
  responsabilidade de `src/silver/climate_spatial.py::estacoes_dentro_do_recife`
  (já existente, reutilizado aqui, não duplicado).
- **representatividade**: a estação Y foi escolhida para representar
  climaticamente o bairro X — é o que este módulo produz. Uma estação pode
  estar fisicamente em um bairro e representar vários bairros vizinhos.

Restrito a estações **APAC**: é a fonte com cobertura espacial suficiente
dentro do Recife para esta estratégia (o INMET não tem nenhuma estação ativa
em Recife — ver README, seções 5 e 27). Isso não é uma limitação nova desta
etapa, é a mesma decisão de fonte já tomada para o domínio clima.
"""
from __future__ import annotations

FONTE_ELEGIVEL = "APAC"

METODO_ASSOCIACAO = "nearest_station"
VERSAO_ESTRATEGIA = "A.1"

# Uma estação PCD da APAC reporta em tempo real (janelas de 15min a 24h, ver
# reports/climate_source_analysis/source_analysis.md). Estações "mortas" há
# anos (achado real e documentado: última leitura em 2018) não podem
# representar o clima atual de um bairro só porque estão geometricamente
# perto. 90 dias dá margem para instabilidade temporária de telemetria
# (queda de sinal, manutenção) sem aceitar estações efetivamente offline.
# Constante nomeada e documentada de propósito — nunca um número escondido
# dentro de uma função (ver instrução da sessão que criou este módulo).
LIMIAR_DIAS_ESTACAO_ATIVA = 90

COLUNAS_SILVER_BAIRRO_ESTACAO = (
    "codigo_bairro",
    "nome_bairro",
    "codigo_estacao",
    "nome_estacao",
    "fonte",
    "latitude_estacao",
    "longitude_estacao",
    "distancia_km",
    "estacao_dentro_do_bairro",
    "metodo_ponto_representativo_bairro",
    "metodo_associacao",
    "versao_estrategia",
    "_gerado_em",
)
