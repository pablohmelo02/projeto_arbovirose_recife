# CLAUDE.md — Memória operacional do projeto

> Gerado em 2026-08-19 após reconstrução de contexto em nova máquina. Fonte
> da verdade é o repositório (`README.md`, `reports/`, código, testes) — este
> arquivo é um resumo operacional, não um substituto do README.

## 1. Objetivo

Plataforma de inteligência territorial e previsão de risco de arboviroses
(Dengue, Zika, Chikungunya) para o Recife, a partir de dados públicos: casos
epidemiológicos (CKAN), território/bairros (CKAN GeoJSON) e clima (INMET +
APAC). Arquitetura em camadas Bronze → Silver → Gold (Gold ainda não
implementada).

## 2. Onde ler primeiro

- `README.md` — documento canônico e extenso (28 seções). Sempre validar
  contra ele antes de assumir algo sobre arquitetura/decisões.
- `reports/climate_source_analysis/source_analysis.md` — investigação real
  (HTTP) de APAC x INMET.
- `reports/climate_spatial/summary.json` — cobertura espacial estação x
  bairro (baseline: 311 estações, 22 dentro do Recife, 20/94 bairros com
  estação própria).
- `src/silver/schema_climate.py`, `src/silver/schema_territorio.py` —
  contratos de dados com o *porquê* de cada decisão no docstring.

## 3. Arquitetura Bronze/Silver (Gold fora do escopo)

Três domínios **independentes** (nenhum join entre eles ainda):

- **Arboviroses**: CKAN → Bronze CSV → Silver Parquet (`silver_arboviroses`).
- **Território**: CKAN GeoJSON (bairros do Recife, 94 features) → Bronze →
  Silver GeoParquet (`silver_bairro_geo`), CRS original `EPSG:4326`,
  área/centroide calculados em `EPSG:31985` (SIRGAS2000/UTM 25S), nunca em
  graus.
- **Clima**: INMET (ZIP histórico anual, `portal.inmet.gov.br`) + APAC
  (instantâneo JSON de telemetria, `barramento.apac.pe.gov.br/.../
  ServicoMonitoramentoPCDs.php`) → Bronze → Silver
  (`silver_estacao_climatica` + `silver_clima_diario`).

## 4. Decisão de fontes climáticas (não reabrir sem novo achado)

- **INMET = fonte histórica primária** (ZIP anual funciona; API
  `apitempo.inmet.gov.br` responde 500/502, não usada). Nenhuma estação ativa
  dentro do Recife (a única, RECIFE/CURADO 82900, fechou em 2020-09-01).
- **APAC = fonte complementar de alta resolução espacial** para precipitação
  no Recife (~299 estações em PE, 21-22 dentro do Recife). Sem mecanismo de
  histórico em lote funcional — histórico é construído **prospectivamente**
  rodando `ingest_climate` periodicamente. Só fornece precipitação (rede é só
  de pluviômetros).
- Divergência 21 vs 22 estações dentro do Recife: 21 = cross-check por
  `município` da própria API; 22 = spatial join geométrico real — reportado,
  não "corrigido" para bater.

## 5. Regra de qualidade inegociável

`precipitacao_mm` ausente **≠** `0`. Ausência de leitura → `None`; zero
informado pela fonte → `0`. **Nunca usar `fillna(0)` em precipitação.**

Conversores numéricos são **por fonte, não intercambiáveis**:
`converter_decimal_brasileiro` (INMET, vírgula decimal) vs `converter_float`
(APAC, ponto decimal) — em `src/silver/quality.py`. Usar o errado corrompe
coordenadas silenciosamente (bug real já corrigido).

## 6. Estrutura principal

```text
src/
├── clients/           ckan_client, minio_client, inmet_client, apac_client
├── ingestion/          Bronze: classifiers, ingestion, validation por domínio
├── profiling/          bronze_profiler, territory_profiler, climate_profiler
├── silver/
│   ├── schema.py / schema_territorio.py / schema_climate.py   contratos
│   ├── arboviroses.py / territorio.py / climate.py            transformações
│   ├── climate_spatial.py   cobertura espacial estação↔bairro (diagnóstico)
│   ├── pipeline.py / pipeline_territorio.py / pipeline_climate.py
│   └── quality.py      parsers/normalizadores compartilhados
├── ingest_*.py / transform_*.py / profile_*.py   entry points (`python -m src.X`)
└── analyze_climate_coverage.py   cobertura espacial (reports/climate_spatial/)

tests/   137+ testes (pytest, moto para MinIO simulado, responses para HTTP mock)
reports/ bronze_profile, territory_profile, climate_profile, climate_source_analysis,
         climate_spatial (e, a partir desta sessão, climate_neighborhood_mapping/)
```

Data Lake (dentro do bucket MinIO, não em disco local):

```text
bronze/recife/{arboviroses,territorio,clima/{inmet,apac}}/...
silver/recife/{arboviroses,territorio/bairro_geo,clima/{estacoes,diario,bairro_estacao}}/...
```

## 7. Comandos importantes

```bash
cp .env.example .env          # preencher CKAN_*, MINIO_*, INMET_ANOS
docker compose up -d          # MinIO local (ou usar moto server como stub, ver §9)
pip install -r requirements.txt
pytest                        # roda toda a suíte

python -m src.ingest_territorio && python -m src.transform_territorio
python -m src.ingest_climate && python -m src.transform_climate
python -m src.analyze_climate_coverage        # cobertura espacial (diagnóstico)
python -m src.transform_climate_bairro        # NOVO: mapeamento bairro→estação (Silver)
```

## 8. Estado do desenvolvimento (ver README §2 para detalhe por fase)

- Fase 1 (Arboviroses) e Fase 2 (Território): completas.
- Fase 3 (Clima): Bronze/Profiling/Silver/DQ/análise espacial completos.
- **Sessão atual**: implementando associação Silver `bairro → estação APAC
  elegível mais próxima` (Estratégia A), item novo dentro da Fase 3 — ver
  §10 abaixo para o resultado real desta sessão.
- Fase 4 (Gold) em diante: não iniciada. **Não avançar sem autorização.**

## 9. Ambiente sem Docker

Não há Docker/MinIO real disponível nesta máquina. Para validar pipelines
ponta a ponta usa-se `moto.server` (S3 real emulado em processo Python, sem
Docker) como stub de MinIO — é o mesmo padrão já usado pelos testes
(`ThreadedMotoServer` em `test_climate_pipeline.py` etc.), só que como
processo de longa duração para rodar os `python -m src.X` reais contra rede
real (CKAN/INMET/APAC) e armazenamento simulado.

## 10. Estratégia de atribuição clima → bairro (Estratégia A)

Decisão herdada da análise anterior (README §26): B/C/D (múltiplas estações,
IDW, kriging) **não devem ser implementadas agora** — APAC ainda não tem
profundidade histórica suficiente para justificá-las. Usar apenas
**Estratégia A: estação elegível mais próxima**.

**Módulos criados** (Silver, todos reutilizando `climate_spatial.py`/
`schema_territorio.py` já existentes, sem duplicar CRS/join espacial):

- `src/silver/schema_climate_bairro.py` — contrato: `FONTE_ELEGIVEL="APAC"`,
  `METODO_ASSOCIACAO="nearest_station"`, `VERSAO_ESTRATEGIA="A.1"`,
  `LIMIAR_DIAS_ESTACAO_ATIVA=90` (dias desde a última leitura em
  `silver_clima_diario` para considerar a estação ativa), e
  `COLUNAS_SILVER_BAIRRO_ESTACAO` (inclui `estacao_dentro_do_bairro`,
  campo separado de "estação escolhida para representar o bairro", para não
  confundir localização física com representatividade).
- `src/silver/climate_bairro.py` — `filtrar_estacoes_elegiveis` (fonte +
  coordenada válida + atividade recente, nenhuma exclusão silenciosa:
  `metricas["motivos_exclusao"]` conta cada motivo),
  `construir_pontos_representativos_bairro` (usa `centroide_lat/lon` de
  `territorio.py` quando cai dentro do polígono; `representative_point()`
  em CRS métrico como fallback para bairros côncavos onde o centroide cai
  fora), `calcular_estacao_representativa_por_bairro` (distância em
  `EPSG:31985`, nunca em graus), `montar_mapeamento_bairro_estacao`
  (orquestra tudo + métricas de cobertura), `associar_clima_diario_a_bairro`
  (merge de conveniência com `silver_clima_diario`, não persiste tabela
  nova, nunca imputa `precipitacao_mm` ausente).
- `src/silver/pipeline_climate_bairro.py` /
  `src/transform_climate_bairro.py` — lê `silver_bairro_geo` +
  `silver_estacao_climatica` + todas as partições de `silver_clima_diario`
  do MinIO, grava
  `silver/recife/clima/bairro_estacao/bairro_estacao.parquet` +
  manifest com métricas reais (nunca inventadas).
- `src/analyze_climate_neighborhood_mapping.py` — formata o mapeamento já
  persistido em `reports/climate_neighborhood_mapping/` (CSV + summary.json),
  sem recalcular nada.
- `tests/test_climate_bairro.py` — 19 testes (elegibilidade, ponto
  representativo com fallback, distância/proximidade, obsolescência,
  determinismo, separação localização-física vs representatividade,
  `None`/`0` preservados no merge). Suíte completa: 156/156 passando.

**Resultado real desta sessão (execução ponta a ponta, 2026-08-19)**: rodei
o pipeline completo contra dados reais (CKAN, INMET, APAC) usando
`moto.server` como stub do MinIO (ver §9) — `ingest_territorio` (94
bairros) → `transform_territorio` → `ingest_climate` (INMET: 12 estações
de PE, nenhuma em Recife, ano 2024; APAC: 299 estações via snapshot
`ServicoMonitoramentoPCDs.php`) → `transform_climate` (311 estações Silver,
4691 dias válidos) → `transform_climate_bairro`.

**Cobertura obtida: 0/94 bairros.** `filtrar_estacoes_elegiveis` excluiu as
299 estações APAC candidatas, todas pelo mesmo motivo: `"ultima leitura ha
mais de 90 dias (estacao considerada inativa)"`. A leitura mais recente em
todo o snapshot real da APAC, checada nesta sessão, é **2024-04-09** — a
rede inteira está sem telemetria recente frente à data do sistema
(2026-08-19), mais de 850 dias de defasagem. Isso não é um bug do filtro:
é exatamente o comportamento que `LIMIAR_DIAS_ESTACAO_ATIVA` foi desenhado
para pegar (ver docstring de `schema_climate_bairro.py` sobre estações
"mortas"). `montar_mapeamento_bairro_estacao` levanta `ValueError` nesse
cenário (comportamento correto e testado — ver
`test_montar_mapeamento_sem_estacao_elegivel_levanta_erro`) em vez de
persistir um mapeamento vazio silenciosamente; por isso não há
`reports/climate_neighborhood_mapping/` nem Parquet/manifest gravados nesta
execução.

**Próximo passo (não iniciado, decisão do usuário)**: investigar se a
defasagem é (a) a rede APAC real estar de fato sem manutenção/telemetria
ativa agora, ou (b) o relógio do ambiente onde o pipeline roda estar à
frente do tempo real — nenhuma das duas hipóteses foi confirmada. Enquanto
isso não for esclarecido, `LIMIAR_DIAS_ESTACAO_ATIVA=90` não deve ser
alterado nem contornado só para forçar cobertura.

## 11. Coisas que NÃO fazer sem autorização explícita

- Não implementar Gold (dimensões, fatos, star schema).
- Não implementar Machine Learning / feature engineering / backtesting.
- Não implementar IDW, Kriging ou interpolação espacial — só Estratégia A.
- Não fazer join entre os três domínios (arboviroses/território/clima) além
  do mapeamento clima→bairro descrito acima.
- Não usar `fillna(0)` em variáveis climáticas ausentes.
- Não "corrigir" geometria inválida automaticamente (`make_valid()`) sem
  reportar explicitamente.
- Não misturar `converter_decimal_brasileiro` e `converter_float` entre
  fontes.
- Não recriar `silver_estacao_climatica`/`silver_clima_diario` — reutilizar.
