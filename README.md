# AlertaDengue Recife — Bronze, Profiling e Silver

## 1. Objetivo do projeto

Construir, em etapas, uma plataforma de inteligência territorial e previsão de
risco de arboviroses (Dengue, Zika e Chikungunya) para a cidade do Recife, a
partir de dados públicos: casos epidemiológicos, território (bairros) e clima.

## 2. Status das fases

```text
Fase 1 — Epidemiologia
✅ Bronze Arboviroses
✅ Profiling
✅ Silver Arboviroses
✅ Data Quality

Fase 2 — Território
✅ Bronze GeoJSON (bairros do Recife)
✅ Profiling geográfico
✅ Silver bairro_geo
✅ Data Quality espacial

Fase 3 — Clima
✅ Análise APAC/INMET (fontes reais testadas, não só documentação)
✅ Bronze (INMET: ZIP histórico; APAC: instantâneo de telemetria)
✅ Profiling (schema, cobertura temporal, achados de qualidade)
✅ Silver (silver_estacao_climatica + silver_clima_diario)
✅ Data Quality
✅ Análise espacial das estações (cobertura + distância a bairro)

Fase 4 — Gold
⬜ Dimensões
⬜ Fatos semanais

Fase 5 — ML
⬜ Feature engineering
⬜ Modelo
⬜ Backtesting

Fase 6 — Produto
⬜ API
⬜ Dashboard
⬜ Mapa de risco
```

## 3. Arquitetura Medalhão

```text
                          FONTES

      ┌───────────────────┼────────────────────┐
      │                    │                    │
      ▼                    ▼                    ▼

 CKAN ARBOVIROSES     APAC + INMET        GEOJSON RECIFE
 (implementado)       (implementado)       (implementado)

      │                    │                    │
      ▼                    ▼                    ▼

   BRONZE               BRONZE               BRONZE
 arboviroses             clima              territorio
  (CSV original)    (ZIP INMET + JSON APAC)  (GeoJSON original)

      │                    │                    │
      ▼                    ▼                    ▼

   SILVER               SILVER               SILVER
 arboviroses         estacoes + diario       bairro_geo
  (Parquet)              (Parquet)          (GeoParquet)

      │                    │                    │
      └────────────────────┼────────────────────┘
                            ▼
                          GOLD  (fora do escopo atual)
                bairro + semana epidemiológica
                            │
                            ▼
                  FEATURE ENGINEERING (fora do escopo)
                            │
                            ▼
                  MACHINE LEARNING (fora do escopo)
                            │
                            ▼
                RISCO FUTURO POR BAIRRO (fora do escopo)
```

Bronze/Silver de arboviroses, território e clima são **domínios
independentes** nesta etapa — nenhum join entre eles acontece ainda (isso é
responsabilidade da Gold, não implementada). A única ponte que já existe é
diagnóstica: a análise espacial da seção 26 relaciona estações climáticas a
bairros, sem criar uma tabela unificada.

## 4. Escopo desta etapa

Este repositório implementa:

- **Bronze de arboviroses**: ingestão e armazenamento do dado bruto de
  Dengue/Zika/Chikungunya.
- **Profiling e Silver de arboviroses**: contrato canônico
  `silver_arboviroses`, tipagem real, deduplicação, regras de qualidade.
- **Bronze/Profiling/Silver de território**: GeoJSON de bairros do Recife,
  `silver_bairro_geo`, CRS documentado, área/centroide em projeção métrica.
- **Bronze de clima**: INMET (ZIP histórico anual, estações de Pernambuco) e
  APAC (instantâneo da rede de telemetria pluviométrica).
- **Profiling de clima**: schema, cobertura temporal, estações, achados de
  qualidade (valores negativos, coordenadas ausentes, gaps de sensor).
- **Silver de clima**: `silver_estacao_climatica` (as duas fontes) e
  `silver_clima_diario` (agregação horário→diário do INMET com regras
  explícitas; granularidade nativa do instantâneo da APAC).
- **Análise espacial de cobertura climática**: quais estações caem dentro do
  Recife, quais bairros têm estação, distância ao vizinho mais próximo — sem
  atribuir clima a bairro como regra definitiva.

Não implementa: Gold, star schema, Machine Learning, dashboards, FastAPI,
PostGIS, Airflow, dbt ou Power BI. Nenhum dos três domínios é unido (join)
nesta etapa.

## 5. Fontes dos dados

**Arboviroses** — CKAN do Recife, dataset `casos-de-dengue-zika-e-chikungunya`.

**Território** — mesmo CKAN, dataset `mapas-de-limites-e-divisoes-territoriais`,
recurso "Limites dos Bairros - 2023" (GeoJSON).

**Clima** — nenhuma das duas é CKAN (ver `reports/climate_source_analysis/source_analysis.md`
para a investigação técnica completa, com testes HTTP reais, não só leitura
de documentação):

- **INMET** — `portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip`: download
  estático anual, funcional, com CSV horário por estação (todo o Brasil; o
  cliente filtra só Pernambuco). A API não-documentada `apitempo.inmet.gov.br`,
  amplamente citada pela comunidade, respondeu **erro 500/502** em todos os
  testes — por isso não foi usada.
- **APAC** — `barramento.apac.pe.gov.br/.../ServicoMonitoramentoPCDs.php`:
  API JSON pública (sem autenticação) por trás do painel de monitoramento,
  com o instantâneo atual de ~300 pluviômetros em Pernambuco, 21-22 deles
  dentro do Recife. Não há mecanismo de histórico em lote que funcione (o
  endpoint existe mas devolveu tabelas vazias nos testes).

## 6. Tecnologias utilizadas

| Tecnologia      | Uso                                                       |
|-----------------|------------------------------------------------------------|
| Python 3.11+    | Linguagem de todo o pipeline                                |
| requests        | Chamadas HTTP (CKAN, INMET, APAC)                            |
| boto3           | Cliente S3 para o MinIO                                     |
| python-dotenv   | Configuração via `.env`                                      |
| pandas          | Profiling e transformação Silver tabular                    |
| pyarrow         | Escrita/leitura Parquet                                      |
| geopandas       | GeoJSON, GeoDataFrame, GeoParquet, spatial join               |
| shapely         | Validação de geometria, distância métrica                    |
| pyproj          | Reprojeção de CRS (via geopandas)                             |
| MinIO           | Data Lake local (S3 compatível)                              |
| Docker Compose  | Provisionamento do MinIO                                     |
| pytest          | Testes unitários e de integração                             |
| moto            | Servidor S3 simulado, só em testes                            |
| responses       | Mock de chamadas HTTP (INMET/APAC), só em testes              |

Nenhuma dependência nova entrou "por precaução" — cada uma só foi adicionada
quando o profiling ou a implementação confirmaram a necessidade real (ex.:
`geopandas` só quando território exigiu geometria; `responses` só quando os
testes de cliente HTTP de clima precisaram simular erro sem depender da rede).

## 7. Estrutura de pastas

```text
Projeto Dengue/
│
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── README.md
│
├── src/
│   ├── config.py                     # Variáveis de ambiente (CKAN x2, INMET_ANOS)
│   ├── main.py / validate.py / profile.py / transform.py       # Arboviroses
│   ├── ingest_territorio.py / profile_territorio.py / transform_territorio.py
│   ├── ingest_climate.py             # Bronze clima (INMET + APAC)
│   ├── profile_climate.py            # Profiling clima
│   ├── transform_climate.py          # Silver clima
│   ├── analyze_climate_coverage.py   # Cobertura espacial estações x bairro
│   │
│   ├── clients/
│   │   ├── ckan_client.py            # Genérico: arboviroses + território
│   │   ├── minio_client.py           # Genérico: todos os domínios
│   │   ├── inmet_client.py           # Download ZIP anual + filtro por UF
│   │   └── apac_client.py            # Instantâneo da rede PCD
│   │
│   ├── ingestion/
│   │   ├── classifier.py / bronze_ingestion.py / bronze_validation.py   # Arboviroses
│   │   ├── territory_classifier.py / territory_ingestion.py             # Território
│   │   └── climate_ingestion.py      # Bronze clima (2 fontes, 2 manifests)
│   │
│   ├── profiling/
│   │   ├── bronze_profiler.py        # Arboviroses
│   │   ├── territory_profiler.py     # Território + cross-check bairro
│   │   └── climate_profiler.py       # Clima (INMET dedup / APAC todos os snapshots)
│   │
│   ├── silver/
│   │   ├── schema.py / quality.py / arboviroses.py / dimensoes.py / pipeline.py   # Arboviroses
│   │   ├── schema_territorio.py / territorio.py / pipeline_territorio.py         # Território
│   │   ├── schema_climate.py         # Contrato estacao/diario + CRS/limiares
│   │   ├── climate.py                # Transformações (agregação horária, DQ)
│   │   ├── climate_spatial.py        # Spatial join estação x bairro
│   │   └── pipeline_climate.py       # Orquestra Silver clima
│   │
│   └── utils/
│       ├── text.py / csv_bruto.py    # Arboviroses
│       └── inmet_csv.py              # Parsing do CSV de estação do INMET
│
├── scripts/
│   ├── preview_bronze.py
│   └── exportar_historico_local.py
│
├── reports/
│   ├── bronze_profile/
│   ├── territory_profile/
│   ├── climate_source_analysis/      # Comparação APAC x INMET (ver seção 5)
│   ├── climate_profile/
│   └── climate_spatial/              # Cobertura, distâncias (ver seção 26)
│
└── tests/  (137 testes)
    ├── (33 de arboviroses, inalterados)
    ├── (25 de território, inalterados)
    └── clima (35 novos):
        test_inmet_csv.py, test_clients_climate.py, test_climate_ingestion.py,
        test_climate_profiler.py, test_climate_silver.py, test_climate_spatial.py,
        test_climate_pipeline.py
```

## 8. Configurando o `.env`

```bash
cp .env.example .env
```

```env
CKAN_BASE_URL=https://dados.recife.pe.gov.br
CKAN_DATASET=casos-de-dengue-zika-e-chikungunya
CKAN_TERRITORIO_DATASET=mapas-de-limites-e-divisoes-territoriais

MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=admin123
MINIO_BUCKET=datalake

HTTP_TIMEOUT=30
INMET_ANOS=2024
```

`INMET_ANOS` aceita uma lista separada por vírgula (ex.: `2020,2021,2022`).
Cada ano baixa um ZIP de ~100MB (todo o Brasil, filtrado para PE) — comece
com 1 ano para validar antes de baixar vários.

## 9. Subindo o MinIO

```bash
docker compose up -d
```

## 10. Instalando dependências

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 11. Prévia dos dados sem MinIO/Docker

```bash
python -m scripts.preview_bronze
python -m scripts.exportar_historico_local
```

## 12. Pipeline de arboviroses

```bash
python -m src.main
python -m src.validate
python -m src.profile
python -m src.transform
```

## 13. Pipeline de território

```bash
python -m src.ingest_territorio
python -m src.profile_territorio
python -m src.transform_territorio
```

## 14. Pipeline de clima

```bash
python -m src.ingest_climate               # Bronze: INMET (ZIP) + APAC (instantâneo)
python -m src.profile_climate               # Profiling: schema, cobertura, achados
python -m src.transform_climate              # Silver: estacoes + clima_diario
python -m src.analyze_climate_coverage       # Cobertura espacial x silver_bairro_geo
```

`analyze_climate_coverage` depende da Silver de território e de clima já
existirem no MinIO (roda os comandos das seções 13 e 14 primeiro). O comando
`ingest_climate` deve ser **executado periodicamente** (cron, agendador) para
a APAC acumular histórico próprio — cada execução é um novo ponto no tempo,
não uma correção do anterior (ver seção 20).

## 15. Rodando os testes

```bash
pytest
```

**137 testes**, todos passando: os 102 já existentes (arboviroses +
território) **inalterados** + 35 novos de clima (parsing do CSV do INMET,
clientes HTTP com mock via `responses`, ingestão com lineage, profiling com
seleção de última versão válida do INMET vs. todos os snapshots da APAC,
agregação horário→diário com regras de unidade/missing, Data Quality,
spatial join e distância estação-bairro, pipeline ponta a ponta via `moto`).

## 16. Visualizando os objetos no MinIO

Console web em `http://localhost:9001`, bucket `datalake`.

## 17. Estrutura criada no Data Lake

```text
datalake/
├── bronze/
│   └── recife/
│       ├── arboviroses/...
│       ├── territorio/bairro/ingestion=<run_id>/<resource_id>.geojson
│       │
│       └── clima/
│           ├── inmet/ano=<ano>/ingestion=<run_id>/INMET_NE_PE_<codigo>_<nome>_....CSV
│           │   └── _controle/manifest_<run_id>.json
│           └── apac/pcd/ingestion=<run_id>/pcds.json
│               └── _controle/manifest_<run_id>.json
│
└── silver/
    └── recife/
        ├── arboviroses/...
        ├── territorio/bairro_geo/bairros.parquet
        │
        └── clima/
            ├── estacoes/estacoes.parquet             (INMET + APAC combinadas)
            ├── diario/ano=<ano>/clima_diario_<ano>.parquet
            ├── _rejected/rejeitados_<run_id>.csv
            └── _controle/manifest_silver_clima_<run_id>.json
```

## 18. Manifests e relatórios

Cada domínio segue o mesmo padrão: manifest de execução com `run_id`,
lineage, status/erro por recurso, e relatórios de profiling pequenos
(versionados no git, ao contrário de `preview/`/`historico/`). O clima tem
**dois manifests Bronze** (`inmet` e `apac`), porque as fontes têm semânticas
de execução diferentes — ver seção 20.

## 19. Contrato de dados: `silver_arboviroses`

Sem mudanças nesta etapa — ver `src/silver/schema.py` para o contrato
completo (campos por alias, `tipo_arbovirose` vindo do metadado da Bronze).

## 20. Seleção de "última versão válida": INMET x APAC

Arboviroses e território reaproveitam a mesma regra ("para cada recurso,
pega a entrada SUCCESS mais recente entre todos os manifests"). Clima
**não pode** seguir essa regra igual para as duas fontes:

- **INMET**: cada arquivo de estação é estável (um ano completo, uma vez
  publicado não muda) — aplica a mesma regra de dedup por nome de arquivo.
- **APAC**: cada execução grava um **instantâneo novo**, não uma correção do
  anterior. Pegar só "o mais recente" jogaria fora todo o histórico que o
  pipeline vem acumulando. Por isso `climate_profiler.listar_todos_snapshots_apac`
  mantém **todos** os instantâneos já coletados — cada um vira 1 linha por
  estação em `silver_clima_diario`, na data do "último dado" daquela
  estação especificamente (não na data da execução do pipeline).

## 21. Contrato de dados: `silver_estacao_climatica` e `silver_clima_diario`

Definido depois do profiling real de ambos os CSVs/JSON (ver
`src/silver/schema_climate.py`).

**`silver_estacao_climatica`**: `codigo_estacao`, `nome_estacao`, `fonte`,
`latitude`, `longitude`, `altitude`, `municipio`, `uf`, `data_inicio`,
`data_fim`, `_source`, `_processed_at`. INMET não tem `municipio`/`data_fim`
no CSV (ficam nulos, não inventados); APAC não tem `altitude`/`data_inicio`
(idem). Chave natural: (`fonte`, `codigo_estacao`).

**`silver_clima_diario`**: `data`, `codigo_estacao`, `fonte`,
`precipitacao_mm`, `temperatura_min/max/media_c`, `umidade_min/max/media_pct`,
`_source_resource`, `_ingestion_run_id`, `_processed_at`. Granularidade:
estação + dia (não agrega por semana nem por bairro — isso é Gold).

**Regra de agregação horário→diário do INMET** (documentada, nunca aplicada
às cegas):
- `precipitacao_mm` = soma das leituras horárias válidas do dia. Se
  **nenhuma** hora tiver leitura, o resultado é `None`, nunca `0` — "sem
  dado" e "não choveu" são coisas diferentes.
- `temperatura_min/max/media_c` = mínimo/máximo/média das leituras horárias
  de bulbo seco (não usamos os campos auxiliares "hora anterior" do INMET,
  que têm semântica de janela deslizante, não de dia calendário).
- `umidade_min/max/media_pct` = idem, a partir da umidade relativa horária.

**APAC não gera temperatura/umidade** (rede é só de pluviômetros) — ficam
sempre nulos, documentado, não inventado. A data de cada linha vem do campo
"Data último dado" da própria estação — estações offline há tempo aparecem
com data antiga (achado de qualidade, não bug).

**Unidades**: já nascem padronizadas na fonte (mm, °C, %) — a única
conversão feita é de notação numérica: INMET usa vírgula decimal brasileira
("25,5"), APAC usa ponto decimal padrão ("0.62") — **são funções diferentes**
(`converter_decimal_brasileiro` vs `converter_float` em `quality.py`);
usar a errada silenciosamente corrompe coordenadas (bug real encontrado e
corrigido durante o desenvolvimento: `converter_decimal_brasileiro` aplicada
a uma coordenada da APAC como "-8.340000000000000" virava "-8340000000000000"
ao remover os pontos como se fossem separador de milhar).

## 22. Regras de qualidade — clima

Nenhuma linha é descartada silenciosamente; toda rejeição vai para
`_rejected/` com motivo explícito.

**Rejeição** (`silver_clima_diario`): `data` ausente/não-parseável;
`codigo_estacao` ausente; `precipitacao_mm` negativa; `umidade_*` fora de
0-100. **Rejeição** (`silver_estacao_climatica`): `codigo_estacao` ausente;
lat/lon fora de ±90/±180; `codigo_estacao` duplicado (mesma fonte).

**Aviso, não rejeição**: temperatura fora do intervalo plausível para o
Nordeste do Brasil (10°C-42°C, documentado em `schema_climate.py`) — vira
métrica no manifest Silver (`avisos_temperatura_implausivel`), a linha
continua válida. Extremos reais acontecem; a Silver não decide sozinha o
que é "impossível" fisicamente sem um motivo técnico claro.

**`fillna(0)` nunca é usado** em `precipitacao_mm` — ver seção 21.

## 23. Achados reais de qualidade — clima

Validado ponta a ponta contra a API real (INMET ano 2024, 12 estações de
PE; instantâneo real da APAC, 299 estações):

- **INMET/PE 2024 tem gaps de sensor generalizados, não é um problema
  isolado de uma estação.** Das 12 estações de Pernambuco, várias têm
  percentuais altíssimos de ausência em campos críticos: GARANHUNS **100%**
  de precipitação ausente no ano inteiro; IBIMIRIM **100%** de umidade
  ausente; SURUBIM 91,78% de umidade ausente; PALMARES 39,89% de
  precipitação ausente (em blocos de 24h completas — 146 dias inteiros sem
  nenhuma leitura, não ruído pontual); a maioria das demais estações fica
  entre 20% e 63% de ausência em pelo menos uma variável. Isso é achado
  automático de `reports/climate_profile/quality_findings.csv` (limiar de
  20%), não uma amostra escolhida a dedo — **usar o INMET/PE-2024 como fonte
  de treino para um modelo exige lidar com essas lacunas explicitamente**,
  não presumir que "baixar o ZIP oficial" implica dado completo.
- **APAC**: 0 estações sem coordenada, 0 valores de precipitação negativos
  no instantâneo testado — dado limpo no momento da validação.
- **Estações "desatualizadas"**: algumas estações PCD da APAC reportam
  "Data último dado" bem antiga (ex.: 2018) mesmo quando consultadas em
  2026 — sinal de estação offline há anos. Isso não é escondido: a data
  real da estação é usada em `silver_clima_diario`, não a data da execução.

## 24. Resultado real da ingestão de clima (validação ponta a ponta)

- INMET: 12 estações de Pernambuco (nenhuma dentro de Recife — a única que
  já existiu, "RECIFE (CURADO)"/82900, é convencional e fechou em
  2020-09-01), 366 dias cada (2024, ano bissexto), 100% de cobertura
  temporal (todo dia tem ao menos 1 registro).
- APAC: 299 estações, 1 instantâneo por execução.
- Silver combinada: **311 estações**, **4.691 linhas diárias válidas**,
  **0 rejeitadas** nesta execução.

## 25. Regras de qualidade e cálculo geoespacial — território

(Sem mudanças nesta etapa.) CRS original `EPSG:4326` (verificado, não
presumido — RFC 7946 + coordenadas reais + detecção do geopandas), cálculo
de área/centroide em `EPSG:31985` (SIRGAS 2000 / UTM 25S), nunca em graus.
Geometria inválida é rejeitada e reportada, nunca corrigida com
`make_valid()` silenciosamente. Detalhes completos em
`src/silver/schema_territorio.py` e `src/silver/territorio.py`.

## 26. Cobertura espacial: clima × território (`analyze_climate_coverage`)

Resultado real (`reports/climate_spatial/summary.json`), cruzando as 311
estações da Silver de clima com as 94 geometrias de `silver_bairro_geo`:

```text
estações com coordenada válida: 311
estações dentro do polígono do Recife: 22
estações fora do Recife: 289

bairros com pelo menos 1 estação dentro: 20 / 94
bairros sem nenhuma estação dentro: 74 / 94

distância do centroide de cada bairro à estação mais próxima:
  média: 1,23 km
  máxima: 3,64 km
  mínima: 0,11 km
```

(22 ≠ 21 da seção 5: o cross-check por `município` reportado pela própria
APAC deu 21; o `spatial join` geométrico contra o polígono real do Recife
deu 22 — uma estação cujo campo `município` aponta para um município vizinho
cai, na prática, dentro do polígono do Recife. Isso é reportado, não
"corrigido" para bater um valor com o outro.)

**Não atribuímos clima de estação a bairro como regra definitiva nesta
etapa** — só analisamos cobertura, conforme pedido.

### Estratégias futuras para clima por bairro (análise, não implementação)

| Estratégia | Como funciona | Avaliação com os dados reais de hoje |
|---|---|---|
| **A — Estação mais próxima** | Bairro usa o dado da estação mais próxima do seu centroide | Distância média de 1,23 km é boa; mas 74/94 bairros (79%) não têm estação própria, então "emprestam" de um vizinho até 3,64 km — razoável para chuva (espacialmente correlacionada nessa escala), mais arriscado para eventos convectivos muito localizados, comuns no clima tropical |
| **B — Média de N estações próximas** | Suaviza ruído de uma estação isolada | Dilui exatamente os eventos de chuva intensa localizada que mais importam para vigilância de arbovirose; com clusters desiguais de estações, a escolha de N já muda o resultado |
| **C — IDW (Inverse Distance Weighting)** | Interpola continuamente por peso de distância | Tecnicamente mais correto que A/B, mas exige malha bem distribuída; nossa cobertura é desigual (0,11 km a 3,64 km), o que pode gerar precisão aparente onde a densidade real é baixa |
| **D — Interpolação espaço-temporal (kriging etc.)** | Modela a superfície climática completa | Exige série histórica consistente por estação — a APAC (mais densa em Recife) **não tem histórico retroativo** ainda (só o que o pipeline acumular a partir de agora); prematuro |

**Recomendação técnica**: por ora, **Estratégia A** é a mais defensável — não
por simplicidade, mas porque B/C/D dependem de profundidade histórica que a
fonte com melhor cobertura espacial (APAC) ainda não tem (ver seção 20).
Reavaliar quando o `ingest_climate` tiver acumulado alguns meses/anos de
execuções.

## 27. Limitações e decisões conhecidas

**Arboviroses**: delimitador inconsistente, 3 formatos de data, Chikungunya
com 2 códigos CID por era, cabeçalho corrompido em Chikungunya 2017,
colunas vazias em Chikungunya 2024, Zika 2021 contaminado com dado de
Chikungunya (rejeitado integralmente), 7 registros de Dengue 2022 sem
`id_notificacao` — ver `src/silver/schema.py`.

**Território**: divergência de código do bairro "SANCHO" entre fontes (não
resolvida automaticamente); `TBAIRRULAT` descartado por semântica não
confirmada.

**Clima**:
- **Nenhuma estação ativa (INMET nem APAC-conventional) cobre Recife com
  profundidade histórica.** A APAC tem a melhor cobertura espacial (21-22
  estações dentro do Recife) mas só entrega o instantâneo atual — histórico
  real só existe a partir de quando o pipeline começar a rodar
  periodicamente. O INMET tem histórico robusto mas nenhuma estação ativa
  em Recife (a única fechou em 2020); as mais próximas ficam a ~90 km.
- A rede convencional (manual) da APAC responde ao endpoint de consulta
  histórica, mas devolveu tabelas **vazias** em todos os testes (RMR,
  jan/2025 e ago/2026) — não foi usada.
- `apitempo.inmet.gov.br` (API não-documentada, usada por muitos projetos
  da comunidade) respondeu erro 500/502 de forma reproduzível — não foi
  usada; preferiu-se o ZIP histórico oficial, estático e funcional.

**Ambiente sem Docker** (todos os domínios): todo o pipeline foi validado
ponta a ponta contra as APIs/arquivos reais (CKAN, INMET, APAC) com `moto`
simulando o MinIO — não contra um MinIO de verdade. Quando você tiver
Docker disponível, rode `docker compose up -d` e os comandos das seções
12-14 para confirmar contra o MinIO real.

## 28. Próximos passos (Gold — fora do escopo atual)

- decidir e implementar a estratégia de atribuição clima→bairro (seção 26);
- agregação de arboviroses + clima por bairro + semana epidemiológica;
- modelo dimensional (star schema, surrogate keys — a Silver propositalmente
  não cria nenhuma);
- features para Machine Learning;
- dashboards / API de consulta / mapa de risco.
