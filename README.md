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
✅ Análise APAC/INMET/CEMADEN/ANA (fontes reais testadas, não só documentação)
✅ Bronze (INMET: ZIP histórico; APAC: instantâneo; CEMADEN: cadastro/status/série horária)
✅ Profiling (schema, cobertura temporal, achados de qualidade)
✅ Silver (silver_estacao_climatica + silver_clima_diario)
✅ Data Quality
✅ Análise espacial das estações (cobertura + distância a bairro)
✅ Estratégia A: bairro → estação elegível mais próxima (94/94 bairros)

Fase 4 — Gold
✅ Gold analítica integrada (arboviroses + território + clima), grão
   bairro × semana epidemiológica × agravo — 191.478 linhas, 2013-2025
✅ Profiling + visualizações de validação
⬜ Modelo dimensional (star schema, surrogate keys) — não iniciado

Fase 5 — ML
✅ Formalização do problema + target de "surto" + baselines + 1º modelo
   (DENGUE, horizonte t+1) — ver seção 32 e `reports/ml/`
✅ Otimização controlada (diagnóstico de 2023, features de histórico
   local, tuning pequeno, threshold operacional, ranking, calibração) —
   ver seção 33. Classificação ainda B: melhorou, mas não pronto para o
   dashboard.
✅ Reformulação para onset (início de episódio) + ranking territorial
   preventivo — ver seção 34. Classificação ainda B: valor real mas
   concentrado em Top-5/10, disparidade regional (RPA 6) não resolvida.
⬜ Investigação territorial dedicada (RPA 6/IPSEP), ensemble/deep
   learning (fora de escopo por decisão do projeto) — não iniciado

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
  endpoint existe mas devolveu tabelas vazias nos testes). **Congelada desde
  2024-04-09** (investigação real em
  `reports/climate_source_analysis/apac_freshness_investigation.md`): o
  endpoint continua no ar e é o mesmo referenciado pelo painel público
  atual, mas não recebe telemetria nova — não é bug do projeto, é a rede
  real. A ingestão continua rodando (não foi removida), só não gera mais
  estações elegíveis na Estratégia A (ver seção 26).
- **CEMADEN** — mesma rede física de pluviômetros que a APAC monitora em
  Recife, mas com um sinal de atividade e valores de precipitação
  genuinamente atuais (investigação real em
  `reports/climate_source_analysis/cemaden_precipitation_endpoint_investigation.md`
  e `reports/climate_source_analysis/cemaden_integration_results.md`). Três
  endpoints sem autenticação: cadastro geoespacial (WFS/GeoServer), status
  atual de todas as estações de uma UF, e série horária real de
  precipitação por estação (`MapaInterativoWS/resources/horario/{id}/{horas}`
  — o mesmo endpoint que o painel público usa para desenhar seu gráfico).
  O histórico "oficial" em lote (formulário de download) é bloqueado por
  CAPTCHA, mas o endpoint de série horária já foi validado até 365 dias
  numa única chamada, sem CAPTCHA nem limite — é essa a via usada.

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
| responses       | Mock de chamadas HTTP (INMET/APAC/CEMADEN), só em testes       |

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
│   ├── config.py                     # Variáveis de ambiente (CKAN x2, INMET_ANOS, CEMADEN_*)
│   ├── main.py / validate.py / profile.py / transform.py       # Arboviroses
│   ├── ingest_territorio.py / profile_territorio.py / transform_territorio.py
│   ├── ingest_climate.py             # Bronze clima (INMET + APAC + CEMADEN)
│   ├── profile_climate.py            # Profiling clima
│   ├── transform_climate.py          # Silver clima
│   ├── analyze_climate_coverage.py   # Cobertura espacial estações x bairro (diagnóstico)
│   ├── transform_climate_bairro.py   # Estratégia A: bairro -> estação elegível mais próxima
│   ├── analyze_climate_neighborhood_mapping.py   # Relatório do mapeamento bairro-estação
│   │
│   ├── clients/
│   │   ├── ckan_client.py            # Genérico: arboviroses + território
│   │   ├── minio_client.py           # Genérico: todos os domínios
│   │   ├── inmet_client.py           # Download ZIP anual + filtro por UF
│   │   ├── apac_client.py            # Instantâneo da rede PCD
│   │   └── cemaden_client.py         # Cadastro (WFS) + status + série horária real
│   │
│   ├── ingestion/
│   │   ├── classifier.py / bronze_ingestion.py / bronze_validation.py   # Arboviroses
│   │   ├── territory_classifier.py / territory_ingestion.py             # Território
│   │   └── climate_ingestion.py      # Bronze clima (3 fontes, 3 manifests)
│   │
│   ├── profiling/
│   │   ├── bronze_profiler.py        # Arboviroses
│   │   ├── territory_profiler.py     # Território + cross-check bairro
│   │   └── climate_profiler.py       # Clima (INMET/CEMADEN-cadastro dedup / APAC+CEMADEN-serie todos os snapshots)
│   │
│   ├── silver/
│   │   ├── schema.py / quality.py / arboviroses.py / dimensoes.py / pipeline.py   # Arboviroses
│   │   ├── schema_territorio.py / territorio.py / pipeline_territorio.py         # Território
│   │   ├── schema_climate.py         # Contrato estacao/diario + CRS/limiares
│   │   ├── climate.py                # Transformações (agregação horária, DQ)
│   │   ├── climate_spatial.py        # Spatial join estação x bairro (diagnóstico)
│   │   ├── pipeline_climate.py       # Orquestra Silver clima
│   │   ├── schema_climate_bairro.py  # Contrato do mapeamento bairro-estação (Estratégia A)
│   │   ├── climate_bairro.py         # Elegibilidade + estação mais próxima por bairro
│   │   └── pipeline_climate_bairro.py   # Orquestra a Silver do mapeamento bairro-estação
│   │
│   └── utils/
│       ├── text.py / csv_bruto.py    # Arboviroses
│       └── inmet_csv.py              # Parsing do CSV de estação do INMET
│
│   # Adições de sessões posteriores (ver seções 12, 13, 29-31 para o detalhe):
│   ├── gold/                         # Gold analítica (arboviroses+território+clima)
│   ├── eda/                         # EDA reutilizável, pura pandas (dashboard + relatório)
│   ├── ingestion/cemaden_backfill.py
│   ├── backfill_climate_cemaden.py
│   ├── export_dashboard_dataset.py
│   └── generate_eda_report.py
│
├── dashboard/                        # Streamlit — ver seção 31
│   ├── app.py / _bootstrap.py / pages/ / components/ / utils/ / data/
│
├── scripts/
│   ├── preview_bronze.py
│   ├── exportar_historico_local.py
│   └── verificar_deploy_dashboard.py
│
├── reports/
│   ├── bronze_profile/
│   ├── territory_profile/
│   ├── climate_source_analysis/      # APAC x INMET x CEMADEN + backfill CEMADEN (seções 5, 30)
│   ├── climate_profile/
│   ├── climate_spatial/              # Cobertura, distâncias (ver seção 26)
│   ├── climate_neighborhood_mapping/ # Resultado real da Estratégia A (bairro -> estação)
│   ├── gold_analysis/                # Gold analítica (seção 29)
│   └── eda/                          # EDA reproduzível (seção 31)
│
└── tests/  (256 testes — ver seções 29-31 para os novos de EDA/dashboard)
```

(Esta árvore documenta a estrutura de alto nível; para a lista completa e
atualizada de arquivos, veja o próprio repositório — algumas pastas
antigas listadas acima podem já ter crescido além do que está detalhado
aqui.)

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
CEMADEN_HORAS_INGESTAO=48
```

`INMET_ANOS` aceita uma lista separada por vírgula (ex.: `2020,2021,2022`).
Cada ano baixa um ZIP de ~100MB (todo o Brasil, filtrado para PE) — comece
com 1 ano para validar antes de baixar vários.

`CEMADEN_HORAS_INGESTAO` é a janela (em horas) de série horária buscada por
execução — 48h por padrão, dá folga sobre o intervalo entre execuções
sucessivas. `CEMADEN_WFS_URL`/`CEMADEN_STATUS_URL`/`CEMADEN_HORARIO_URL`
existem para permitir override, mas os defaults já são os endpoints reais
validados (ver seção 5) — normalmente não precisam ser definidos.

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
python -m src.ingest_climate               # Bronze: INMET (ZIP) + APAC (instantâneo) + CEMADEN (cadastro/status/série horária)
python -m src.profile_climate               # Profiling: schema, cobertura, achados
python -m src.transform_climate              # Silver: estacoes + clima_diario
python -m src.analyze_climate_coverage       # Cobertura espacial x silver_bairro_geo (diagnóstico)
python -m src.transform_climate_bairro       # Estratégia A: bairro -> estação elegível mais próxima
python -m src.analyze_climate_neighborhood_mapping   # Relatório do mapeamento bairro-estação
```

`analyze_climate_coverage` e `transform_climate_bairro` dependem da Silver
de território e de clima já existirem no MinIO (roda os comandos das
seções 13 e 14 primeiro). O comando `ingest_climate` deve ser **executado
periodicamente** (cron, agendador) — tanto a APAC quanto o CEMADEN
acumulam histórico próprio ao longo de execuções sucessivas (cada execução
é uma janela recente, não uma correção da anterior — ver seção 20).

## 14.1 Pipeline Gold (arboviroses + território + clima)

```bash
python -m src.transform_gold_arboviroses_clima   # Gold: bairro x semana epi x agravo
python -m src.analyze_gold                        # Profiling + visualizações de validação
```

Depende das Silver dos três domínios já existirem no MinIO (seções 12-14).
Grão, decisões e limitações: seção 29 abaixo e
`reports/gold_analysis/README.md` (resultados reais).

## 15. Rodando os testes

```bash
pytest
```

**217 testes**, todos passando: arboviroses + território inalterados, mais
os de clima (parsing do CSV do INMET, clientes HTTP com mock via
`responses` para INMET/APAC/CEMADEN, ingestão com lineage, profiling com
seleção de última versão válida por fonte, agregação horário→diário com
regras de unidade/missing, Data Quality, spatial join e distância
estação-bairro, pipeline ponta a ponta via `moto`), os da **Gold** (grão e
chave única, conservação de casos, ausência de many-to-many, `missing ≠ 0`,
**leakage temporal**, reprodutibilidade/idempotência, calendário
epidemiológico) e os da Estratégia A
`bairro → estação elegível mais próxima` (elegibilidade multi-fonte,
deduplicação de execuções sobrepostas do CEMADEN, colisão de chave composta
`fonte`+`codigo_estacao`, e o caso real "estação cadastrada sem série
utilizável não fica elegível").

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
│           ├── apac/pcd/ingestion=<run_id>/pcds.json
│           │   └── _controle/manifest_<run_id>.json
│           └── cemaden/
│               ├── cadastro/ingestion=<run_id>/cadastro.json
│               ├── status/ingestion=<run_id>/status.json
│               ├── horario/ingestion=<run_id>/<idEstacao>.json
│               └── _controle/manifest_<run_id>.json
│
└── silver/
    └── recife/
        ├── arboviroses/...
        ├── territorio/bairro_geo/bairros.parquet
        │
        └── clima/
            ├── estacoes/estacoes.parquet             (INMET + APAC + CEMADEN combinadas)
            ├── diario/ano=<ano>/clima_diario_<ano>.parquet
            ├── bairro_estacao/bairro_estacao.parquet  (Estratégia A: bairro -> estação elegível mais próxima)
            │   └── _controle/manifest_silver_clima_bairro_<run_id>.json
            ├── _rejected/rejeitados_<run_id>.csv
            └── _controle/manifest_silver_clima_<run_id>.json

gold/
└── recife/
    └── arboviroses_clima/
        ├── gold_arboviroses_clima_bairro.parquet   (bairro x semana epi x agravo)
        └── _controle/manifest_gold_arboviroses_clima_<run_id>.json
```

## 18. Manifests e relatórios

Cada domínio segue o mesmo padrão: manifest de execução com `run_id`,
lineage, status/erro por recurso, e relatórios de profiling pequenos
(versionados no git, ao contrário de `preview/`/`historico/`). O clima tem
**três manifests Bronze** (`inmet`, `apac` e `cemaden`), porque as fontes
têm semânticas de execução diferentes — ver seção 20.

## 19. Contrato de dados: `silver_arboviroses`

Sem mudanças nesta etapa — ver `src/silver/schema.py` para o contrato
completo (campos por alias, `tipo_arbovirose` vindo do metadado da Bronze).

## 20. Seleção de "última versão válida": INMET x APAC x CEMADEN

Arboviroses e território reaproveitam a mesma regra ("para cada recurso,
pega a entrada SUCCESS mais recente entre todos os manifests"). Clima
**não pode** seguir essa regra igual para as três fontes:

- **INMET**: cada arquivo de estação é estável (um ano completo, uma vez
  publicado não muda) — aplica a mesma regra de dedup por nome de arquivo.
- **APAC**: cada execução grava um **instantâneo novo**, não uma correção do
  anterior. Pegar só "o mais recente" jogaria fora todo o histórico que o
  pipeline vem acumulando. Por isso `climate_profiler.listar_todos_snapshots_apac`
  mantém **todos** os instantâneos já coletados — cada um vira 1 linha por
  estação em `silver_clima_diario`, na data do "último dado" daquela
  estação especificamente (não na data da execução do pipeline).
- **CEMADEN**: dois padrões diferentes no mesmo domínio, porque os recursos
  têm naturezas diferentes:
  - Cadastro + status (metadado de estação): quase-estático, segue o
    padrão do INMET — `selecionar_cadastro_status_cemaden_mais_recentes`
    usa só a execução mais recente com os dois com sucesso.
  - Série horária real: cada execução cobre uma **janela recente** (padrão
    48h) que se sobrepõe com a anterior — segue o padrão da APAC
    (`listar_todas_series_horarias_cemaden` acumula todas as execuções),
    mas com um passo extra que a APAC não precisa: deduplicação por
    (`codigo_estacao`, `data`, `hora`) antes de agregar para diário, para
    não contar duas vezes a mesma hora que apareceu em janelas sobrepostas
    de execuções diferentes (a mais recente vence em caso de conflito).

## 21. Contrato de dados: `silver_estacao_climatica` e `silver_clima_diario`

Definido depois do profiling real de ambos os CSVs/JSON (ver
`src/silver/schema_climate.py`).

**`silver_estacao_climatica`**: `codigo_estacao`, `nome_estacao`, `fonte`,
`latitude`, `longitude`, `altitude`, `municipio`, `uf`, `data_inicio`,
`data_fim`, `_source`, `_processed_at`. INMET não tem `municipio`/`data_fim`
no CSV (ficam nulos, não inventados); APAC/CEMADEN não têm
`altitude`/`data_inicio` (idem). **Chave natural: (`fonte`, `codigo_estacao`)
— nunca só `codigo_estacao`**, que não é único entre fontes (bug real
corrigido ao adicionar o CEMADEN: `codigo_estacao` pode colidir
textualmente entre APAC e CEMADEN sem serem a mesma estação física; todo
merge/índice na Estratégia A usa a chave composta).

**`silver_clima_diario`**: `data`, `codigo_estacao`, `fonte`,
`precipitacao_mm`, `horas_validas_dia`, `temperatura_min/max/media_c`,
`umidade_min/max/media_pct`, `_source_resource`, `_ingestion_run_id`,
`_processed_at`. Granularidade: estação + dia (não agrega por semana nem
por bairro — isso é Gold). `horas_validas_dia` (novo, adicionado com o
CEMADEN, populado também para INMET/APAC) registra quantas leituras
horárias válidas formaram o valor diário — distingue "24h de zero real" de
"dia com cobertura parcial" sem precisar de um schema à parte.

**Regra de agregação horário→diário do INMET** (documentada, nunca aplicada
às cegas):
- `precipitacao_mm` = soma das leituras horárias válidas do dia. Se
  **nenhuma** hora tiver leitura, o resultado é `None`, nunca `0` — "sem
  dado" e "não choveu" são coisas diferentes.
- `temperatura_min/max/media_c` = mínimo/máximo/média das leituras horárias
  de bulbo seco (não usamos os campos auxiliares "hora anterior" do INMET,
  que têm semântica de janela deslizante, não de dia calendário).
- `umidade_min/max/media_pct` = idem, a partir da umidade relativa horária.

**APAC e CEMADEN não geram temperatura/umidade** (ambas são redes só de
pluviômetros) — ficam sempre nulos, documentado, não inventado. A data de
cada linha da APAC vem do campo "Data último dado" da própria estação —
estações offline há tempo aparecem com data antiga (achado de qualidade,
não bug; ver `reports/climate_source_analysis/apac_freshness_investigation.md`
para o caso extremo: a rede inteira está nessa situação desde 2024-04-09).

**Regra de agregação horário→diário do CEMADEN** (mesmo princípio do
INMET, granularidade diferente na origem): a fonte já entrega uma matriz
horária diretamente (`datas`×`horarios`→`acumulados`, endpoint
`horario/{id}/{horas}`) — `precipitacao_mm` = soma das horas válidas do
dia (`min_count=1`, nunca `0` por ausência total), `horas_validas_dia` =
contagem de horas realmente somadas. Séries de execuções sucessivas se
sobrepõem (mesma hora relatada mais de uma vez); a Silver deduplica por
(`codigo_estacao`, `data`, `hora`) antes de somar — sem isso, uma hora
apareceria em dobro no total diário.

**Unidades**: já nascem padronizadas na fonte (mm, °C, %) — a única
conversão feita é de notação numérica: INMET usa vírgula decimal brasileira
("25,5"), APAC/CEMADEN usam ponto decimal padrão ("0.62") — **são funções
diferentes** (`converter_decimal_brasileiro` vs `converter_float` em
`quality.py`); usar a errada silenciosamente corrompe coordenadas (bug real
encontrado e corrigido durante o desenvolvimento: `converter_decimal_brasileiro`
aplicada a uma coordenada da APAC como "-8.340000000000000" virava
"-8340000000000000" ao remover os pontos como se fossem separador de
milhar).

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
- APAC: 299 estações, 1 instantâneo por execução (congelada desde
  2024-04-09 — ver seção 27).
- **CEMADEN** (adicionado em 2026-08-20): 407 estações válidas em
  `silver_estacao_climatica` (de 437 no cadastro de PE), 35 candidatas
  pluviométricas da Grande Recife com série horária buscada, 24 com ao
  menos 1 dia real de precipitação (as demais existem no cadastro mas sem
  série utilizável — mesmo achado de qualidade documentado para a APAC:
  cadastro ≠ dado real). Dados reais cobrindo 2026-08-18 a 2026-08-20 (data
  do sistema nesta execução: 2026-08-20).
- Silver combinada (execução mais recente, com CEMADEN): **718 estações**,
  **5.057 linhas diárias válidas**, **0 rejeitadas** nesta execução. Ver
  `reports/climate_source_analysis/cemaden_integration_results.md` para o
  detalhamento completo.

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

**Estratégia A foi implementada** (`src/silver/climate_bairro.py`,
`python -m src.transform_climate_bairro`) — B/C/D continuam não
implementadas, pela mesma razão (profundidade histórica insuficiente,
ver seção 20). Elegibilidade de estação exige leitura real recente em
`silver_clima_diario` (`LIMIAR_DIAS_ESTACAO_ATIVA=90` dias) — nunca
metadado de cadastro (`tempo_inatividade` da APAC/CEMADEN não é usado como
critério).

**Resultado real mais recente** (2026-08-20, com CEMADEN — ver
`reports/climate_source_analysis/cemaden_integration_results.md`):

```text
94/94 bairros associados (100%)
16 estações distintas usadas (todas CEMADEN — APAC congelada desde 2024-04-09
não gerou nenhuma estação elegível)
distância mediana: 1,431 km | máxima: 4,632 km
```

A cobertura ficou em `0/94` até o CEMADEN ser adicionado (a APAC sozinha
está sem leitura real desde 2024-04-09 — ver
`reports/climate_source_analysis/apac_freshness_investigation.md`). Não há
prioridade explícita entre fontes no código: a estação mais próxima **entre
as elegíveis** já implementa a regra correta — se a APAC voltar a ter
leitura real, volta a competir por atividade sem precisar mudar código.

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
  profundidade histórica.** O INMET tem histórico robusto mas nenhuma
  estação ativa em Recife (a única fechou em 2020); as mais próximas ficam
  a ~90 km.
- **APAC está congelada desde 2024-04-09** (confirmado com evidência direta
  — reconsulta ao vivo idêntica byte a byte ao Bronze já armazenado, ver
  `reports/climate_source_analysis/apac_freshness_investigation.md`): o
  endpoint continua no ar e é o mesmo referenciado pelo painel oficial
  atual, mas não recebe telemetria nova. A ingestão continua rodando (não
  removida), só não gera mais estações elegíveis.
- **CEMADEN monitora fisicamente a mesma rede de pluviômetros que a APAC em
  Recife**, mas com sinal de atividade e valores genuinamente atuais —
  adicionado em 2026-08-20 para destravar a Estratégia A (ver seção 26).
  Limitação conhecida: a busca de série horária é restrita a um recorte
  "Grande Recife" (município textual, `MUNICIPIOS_GRANDE_RECIFE` em
  `climate_ingestion.py`) para não gerar uma chamada HTTP por estação de PE
  a cada execução (437 estações) — decisão pragmática documentada, não uma
  garantia matemática de que nenhuma estação relevante fique de fora.
  Histórico: um backfill (`src/ingestion/cemaden_backfill.py`, ver §30)
  recuperou até 730 dias reais para as 16 estações usadas pela Estratégia
  A (tecnicamente validado até 1825 dias/estação) — 2013-2023 continuam
  sem clima real; nenhuma fonte investigada resolve esse trecho.
- A rede convencional (manual) da APAC responde ao endpoint de consulta
  histórica, mas devolveu tabelas **vazias** em todos os testes (RMR,
  jan/2025 e ago/2026) — não foi usada. O histórico "oficial" em lote do
  CEMADEN (formulário de download) é bloqueado por CAPTCHA — não usado; a
  série horária real (`horario/{id}/{horas}`, validada até 365 dias numa
  única chamada) é o caminho usado no lugar.
- `apitempo.inmet.gov.br` (API não-documentada, usada por muitos projetos
  da comunidade) respondeu erro 500/502 de forma reproduzível — não foi
  usada; preferiu-se o ZIP histórico oficial, estático e funcional.

**Ambiente sem Docker** (todos os domínios): todo o pipeline foi validado
ponta a ponta contra as APIs/arquivos reais (CKAN, INMET, APAC) com `moto`
simulando o MinIO — não contra um MinIO de verdade. Quando você tiver
Docker disponível, rode `docker compose up -d` e os comandos das seções
12-14 para confirmar contra o MinIO real.

## 28. Próximos passos

- estratégia de atribuição clima→bairro **implementada** (Estratégia A, ver
  seção 26);
- agregação de arboviroses + clima por bairro + semana epidemiológica
  **implementada** (Gold, ver seção 29);
- **EDA completa** da Gold (próximo passo recomendado — ver seção 29 para a
  ressalva sobre a dimensão climática);
- modelo dimensional (star schema, surrogate keys — a Silver e a Gold atual
  propositalmente não criam nenhuma);
- features para Machine Learning;
- dashboards / API de consulta / mapa de risco.

## 29. Gold analítica: `gold_arboviroses_clima_bairro`

Primeira camada Gold, integrando os três domínios. Resultados reais
completos (números, cardinalidade de cada join, profiling, visualizações,
limitações) em **`reports/gold_analysis/README.md`** — abaixo só o resumo.

**Grão**: `bairro × semana epidemiológica × agravo`. Chave analítica:
`codigo_bairro + agravo + ano_epidemiologico + semana_epidemiologica`
(0 duplicatas em 191.478 linhas).

Escolhido sobre `bairro + mês` porque `semana_notificacao` (`AAAASS`) **já
existe no SINAN** com 0,04% de nulos — os casos já têm resolução semanal, e
usar mês descartaria precisão real. O clima é **agregado** do diário para a
semana, nunca o contrário (nenhum caso é distribuído artificialmente em
dias).

**Semana epidemiológica não é recalculada** para os casos (usa o campo do
SINAN). `src/gold/epidemiologia.py` implementa o mapeamento inverso
(ano+semana → intervalo de datas) na convenção SVS/CDC (domingo→sábado,
semana 1 contém 4 de janeiro), **não** `isocalendar()` — validado
empiricamente contra 5.000 pares reais da Silver (5000/5000).

**Join arboviroses × território é por `nome_bairro` normalizado, não por
código**: verificado que o `codigo_bairro` do SINAN não é o mesmo espaço de
códigos de `silver_bairro_geo` (só 21/94 coincidem); por nome bate 94/94.
Aproveitamento real: 96,33% dos casos entram no grão espacial; as perdas
(5.833 sem nome + 125 com nome fora dos 94 oficiais + 72 sem semana válida)
são contadas no manifest, nunca silenciosas.

**`casos = 0` é materializado** (produto cartesiano completo 94 × 3 × 679
semanas): notificação de arbovirose é compulsória, então ausência de
registro é `0` real, não desconhecimento — necessário para modelagem de
série temporal. Isso é deliberadamente **diferente** da regra do clima,
onde ausência de leitura é `None` (`missing ≠ 0 mm`, nunca `fillna(0)`).

**Sem `incidencia_por_100k`**: nenhuma fonte do projeto tem população por
bairro (`silver_bairro_geo` tem área, não população). Não foi inventada.

**Leakage temporal**: toda feature climática usa somente dias com
`data <= semana_epi_data_fim` da própria linha; janelas retrospectivas
(`chuva_7d/14d/21d/28d_mm`) terminam nessa data. Teste dedicado injeta
chuva futura e confirma que nenhuma feature muda.

**Cobertura climática real (após o backfill histórico do CEMADEN, ver
§30)**: a interseção temporal real entre casos (2013-2025) e clima com
leitura real passou de **0 linhas (0,0000%)** para **11.709 linhas
(6,1151%)**, concentradas em 2024-2025 (90/94 e 65/94 bairros
respectivamente — ver §30 para a tabela completa por ano). 2013-2023
seguem em 0% real: nenhuma fonte investigada tem histórico automatizável
para esse período. Não foi implementada mistura de fontes (INMET regional
a ~90 km como proxy de clima de bairro) para preencher isso — seria
exatamente a falsa precisão que o projeto evita. Ver
`reports/gold_analysis/README.md` para o detalhamento e
`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`
para a investigação de profundidade/backfill.

## 30. Backfill histórico do CEMADEN e reconstrução da Gold

Investigação e execução completas em
`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`.
Resumo:

- O endpoint `horario/{id}/{horas}` (mesmo usado pela ingestão operacional,
  §14) só aceita "últimas N horas a partir de agora" — sem parâmetro de
  data inicial, portanto **sem chunking por intervalo real**: a
  profundidade alcançável é a maior requisição bem-sucedida por estação,
  não a soma de várias. Validado tecnicamente até **1825 dias (5 anos)**
  por estação (Porto: 2021-08-21 → 2026-08-20, 400 MB, 200 OK).
- Achado operacional: para janelas ≥ ~2 anos, a 1ª requisição a uma estação
  pode exceder 60s ("cold start" reproduzível), mas a mesma requisição
  repetida responde em segundos — por isso o backfill usa timeout alto
  (180s) e retentativa, não chunking por data.
- **Módulo novo**: `src/ingestion/cemaden_backfill.py` +
  `python -m src.backfill_climate_cemaden --dias N`. Grava em
  `bronze/recife/clima/cemaden/horario_backfill/...` (prefixo distinto do
  operacional), com checkpoint/retomada (estação já com backfill
  suficiente não é rebuscada). **Nenhuma mudança** foi necessária em
  `pipeline_climate.py`: a Silver já acumulava e deduplicava todas as
  entradas `tipo="horario"` de qualquer manifest CEMADEN, operacional ou
  backfill.
- **Backfill efetivamente aplicado nesta execução**: 730 dias (2 anos),
  para as 16 estações que a Estratégia A já usa (partiu do mapeamento
  espacial atual, não das 407 estações de PE) — não os 1825 dias validados
  tecnicamente, por limitação de memória do ambiente local sem MinIO/Docker
  real (stub `moto` em memória, ~2 GB livres nesta sessão). Documentado
  como decisão de ambiente, não limite do CEMADEN.
- **Estratégia A não precisou de versão temporal** (bairro+período →
  estação elegível naquele período): a elegibilidade já depende só da
  leitura mais recente (não muda com backfill), e as 16 estações usadas
  têm série real cobrindo a maior parte da janela de 730 dias pedida —
  confirmado rodando `transform_climate_bairro` antes e depois do backfill
  (mesmo mapeamento 94/94 nas duas vezes).
- **Resultado real**: Gold reconstruída, mesmo grão e chave, 0 leakage
  (reconfirmado), 0 duplicatas; cobertura climática real subiu de 0% para
  6,1151% da Gold total (96%/69% dos bairros em 2024/2025 respectivamente).
- **Classificação: B — histórico parcial útil.** Suficiente para uma EDA
  integrada clima×arboviroses restrita a 2024-2025; não resolve
  2013-2023. Testes: 226/226 (9 novos, 0 regressões).

## 31. Dashboard

Aplicação web interativa (**Streamlit**) que consome a Gold pronta — é o
produto analítico principal do projeto a partir desta etapa, não um
artefato descartável. Objetivo: EDA reproduzível (2013-2025 epidemiológico
+ território; 2024-2025 integrado com clima real) exposta em um dashboard
que continuará em uso nas etapas futuras (feature engineering, modelagem).

### Objetivo e arquitetura

```text
dashboard/
├── app.py                  # entrypoint (st.navigation / st.Page)
├── _bootstrap.py           # garante `src` importável (ver docstring)
├── pages/                  # 7 páginas, uma por arquivo
├── components/             # filtros de sidebar, KPIs, gráficos Plotly
├── utils/data_loader.py    # leitura cacheada do dataset estático
├── data/                   # dataset publicado (Parquet + GeoJSON)
└── requirements.txt        # requirements mínimos SÓ do dashboard (deploy)
```

**Nenhuma lógica da Gold é reimplementada no dashboard** — `src/eda/`
(módulo novo, puro pandas, sem Streamlit) contém toda a EDA reutilizável
(`epidemiologia.py`, `clima.py`, `correlacao.py`, `filtros.py`,
`relatorio.py`); o dashboard e `reports/eda/` (gerado por
`python -m src.generate_eda_report`) consomem exatamente as mesmas funções,
nunca calculam a mesma métrica de duas formas diferentes.

### Páginas

1. **Visão Geral** — KPIs do recorte selecionado.
2. **Epidemiologia (2013-2025)** — série semanal, sazonalidade, comparação
   entre agravos (não depende de clima).
3. **Mapa Epidemiológico** — coroplético Plotly sobre a geometria real dos
   94 bairros (sem token de mapbox); só "Casos" (sem incidência — nenhuma
   fonte do projeto tem população por bairro).
4. **Ranking de Bairros** — Top 10/20/todos, por casos.
5. **Clima (CEMADEN)** — cobertura por ano, heatmap ano×semana,
   precipitação real — sempre com o aviso de que a cobertura real começa
   em 2024.
6. **Clima × Arboviroses (2024-2025)** — restrita automaticamente a linhas
   com clima real; correlação exploratória por janela de lag (7/14/21/28
   dias), scatter, sempre com N de observações visível.
7. **Qualidade dos Dados** — antes×depois do backfill, matriz de
   correlação exploratória, proveniência do dataset publicado, avisos de
   viés de disponibilidade.

### Dataset consumido

`python -m src.export_dashboard_dataset` lê `gold_arboviroses_clima_bairro`
+ `silver_bairro_geo` do Data Lake e grava versões estáticas em
`dashboard/data/`: `gold_arboviroses_clima_bairro.parquet` (0,34 MB,
191.478 linhas) + `bairro_geo.geojson` (2,16 MB, 94 bairros) —
o dashboard **nunca** lê o MinIO/Data Lake diretamente, o que permite
funcionar também no Streamlit Community Cloud sem infraestrutura
adicional. Seguro por construção: a Gold já é agregada por
`bairro × semana × agravo` (sem `id_notificacao`, sem dado individual do
SINAN); o script rejeita a exportação (levanta erro) se qualquer coluna
potencialmente identificável aparecer.

### Executando localmente

```bash
python -m src.export_dashboard_dataset   # gera dashboard/data/ (uma vez, ou após novo backfill/Gold)
streamlit run dashboard/app.py
```

### Deploy no Streamlit Community Cloud

- `dashboard/requirements.txt` (mínimo: streamlit, plotly, statsmodels,
  pandas, pyarrow — sem geopandas/boto3/moto, que só o pipeline usa) é o
  arquivo lido pelo Cloud quando o app apontado é `dashboard/app.py`.
- `.streamlit/config.toml` define o tema (sem segredo nenhum).
- Nenhum caminho absoluto local, nenhuma variável de ambiente obrigatória,
  nenhum segredo no código — verificado por
  `python scripts/verificar_deploy_dashboard.py`.
- `.env` permanece fora do Git (`.gitignore`) — o dashboard não depende
  dele (só lê arquivos estáticos).

### Limitações climáticas (herdadas, sempre visíveis na UI)

Clima real só em 2024-2025 (ver §30) — toda página que usa clima mostra o
N de observações, bairros e período considerados, e a página "Clima ×
Arboviroses" nunca deixa isso implícito.

### Testes

`tests/test_eda.py` (25), `tests/test_eda_relatorio.py` (3),
`tests/test_export_dashboard_dataset.py` (2) — camada analítica (filtros,
agregações, ranking, correlação, cobertura, DataFrame vazio, bairro sem
clima, rejeição de dado identificável), não pixels do dashboard.

## 32. Machine Learning: alerta antecipado de dengue por bairro (sessão de 2026-08-20)

Relatório completo (formalização do problema, definição de "surto",
target, features, split temporal, baselines, modelos, métricas técnicas e
operacionais, lead time, comparação com clima, limitações, decisão) em
**`reports/ml/dengue_early_warning_baseline.md`**. Resumo operacional:

- **Agravo preditivo principal a partir desta etapa: DENGUE** (Zika/
  Chikungunya seguem disponíveis para EDA/comparação).
- **Módulos criados** (`src/ml/`, pacote novo, consome a Gold sem
  reimplementar nenhum join/agregação dela): `target.py` (definição de
  "risco elevado" — percentil 90 histórico-sazonal local por bairro, sem
  leakage entre anos), `features.py` (lags/rolling/sazonalidade/
  território), `dataset.py` (monta `X`/`y` com target em t+horizonte),
  `split.py` (split temporal + walk-forward), `baselines.py`
  (persistência/crescimento/sazonal/contagem), `models.py` (Logistic
  Regression + HistGradientBoostingClassifier), `evaluation.py` (métricas
  de classificação), `alert_metrics.py` (episódios, lead time, falsos
  alertas). Entry point: `python -m src.evaluate_dengue_alert_baseline`.
- **Horizonte principal: t+1 semana** (t+2 avaliado à parte, PR-AUC
  menor). **Target**: estado de risco elevado em t+1, não contagem de
  casos — evita confundir previsão quantitativa com alerta.
- **Resultado real**: modelos (PR-AUC 0,278-0,292) superam claramente os 3
  baselines (melhor: persistência, PR-AUC 0,156); detecção de episódios
  39,3% geral, **79,3% nos grandes surtos**; lead time mediano de 3
  semanas nos episódios detectados; desempenho instável entre anos
  (walk-forward PR-AUC 0,074 em 2023 a 0,652 em 2021); comparação
  BASE×BASE+CLIMA (2024→2025, mesmas linhas) mostra ganho pequeno e
  estatisticamente frágil (+0,025 PR-AUC) — clima não foi forçado no
  modelo principal.
- **Classificação: B — existe sinal, mas precisa melhorar** antes de
  qualquer uso operacional (taxa de detecção geral modesta, heterogeneidade
  por bairro, calibração de probabilidade ruim).
- **Decisão**: **SIM**, os resultados justificam avançar para uma etapa de
  otimização (tuning, investigar falha de 2023, modelo hierárquico por
  bairro, calibração) — não para deploy/produção nesta mesma etapa.
- Testes: **29 novos** (leakage adversarial de target/features/dataset,
  episódios, lead time, split). Suíte total: **285/285 passando** (baseline
  era 256, 0 regressões).
- **Não alterado nesta etapa**: Bronze, Silver, Gold, dashboard, dados
  climáticos. Nenhum tuning extensivo, ensemble, deep learning ou deploy —
  conforme regra de parada.

## 33. Machine Learning: otimização e diagnóstico de robustez (sessão de 2026-08-20, continuação)

Relatório completo em **`reports/ml/dengue_early_warning_optimization.md`**.
Resumo operacional:

- **Diagnóstico de 2023** (pior ano da etapa anterior): não é uma falha
  de feature/target/modelo — é um ano epidemiologicamente diferente
  (prevalência do target 5-6x menor, episódios mais curtos/fracos/restritos
  espacialmente que o normal) somado a um artefato de métrica (PR-AUC é
  mecanicamente deprimido por baixa prevalência; corrigindo por
  "lift" — PR-AUC/prevalência — 2023 não é mais o pior ano, 2024 é).
  Confirmado pela otimização: mesmo com features novas e tuning, o PR-AUC
  de 2023 **não se moveu** (0,074 → 0,074).
- **Features novas** (`razao_limiar_historico`, `z_score_historico_local`,
  `razao_media_recente`, momentum): `razao_limiar_historico` (casos
  relativos ao próprio limiar histórico do bairro) é a feature mais
  importante do modelo em TODOS os 7 folds de walk-forward — contexto
  histórico local supera casos absolutos como sinal.
- **Resultado real** (teste 2023-2025): PR-AUC 0,292 → **0,308**;
  episódios detectados 39,3% → **45,9%**; bairros com 0% de detecção
  12 → **7** (mas IPSEP, um bairro de volume substancial, continua em 0%);
  Brier Score calibrado (isotonic, só na validação): **0,116 → 0,073**
  (-37%). Epidemias grandes seguem bem detectadas (~78-79%, estável).
- **Ranking territorial**: Recall@20 (semanal) de 41-46% (~2x o acaso);
  em 52,7% dos episódios reais o bairro já estava no Top-20 de risco da
  cidade em algum momento das 4 semanas antes do início — ranking mais
  útil que o cutoff binário isolado, mas ainda modesto.
- **Instabilidade entre anos persiste** mesmo após otimização (PR-AUC
  desvio-padrão 0,201 no walk-forward) — não é um problema de engenharia
  corrigível, é um limite estrutural dado o histórico disponível.
- **Classificação: B — melhorou, mas ainda apresenta fragilidades
  relevantes. Decisão: NÃO integrar ao dashboard nesta etapa** — se/quando
  integrado no futuro, mostrar score/ranking de risco, não probabilidade
  calibrada como número de confiança absoluto.
- **Testes**: 21 novos (features sem leakage/divisão por zero,
  diagnóstico, ranking sem olhar o futuro do episódio, calibração
  determinística). Suíte total: **306/306 passando** (baseline era 285,
  0 regressões).
- **Não alterado**: Bronze, Silver, Gold, dashboard, dados climáticos,
  definição oficial do target, `baselines.py`. Nenhum deploy, nenhuma
  integração ao Streamlit, clima mantido fora do modelo principal.

## 34. Machine Learning: onset + ranking territorial preventivo (sessão de 2026-08-20, continuação)

Relatório completo em **`reports/ml/dengue_onset_ranking_analysis.md`**.
Resumo operacional:

- **Reformulação do problema**: em vez de "o bairro estará em estado de
  risco elevado em t+1?" (Formulação A, inclui continuação de surto já
  ativo), esta etapa testa "um novo episódio de risco vai COMEÇAR entre
  t+1 e t+3?" (Formulação B, `src/ml/onset.py`) e trata o produto
  principal como **ranking territorial semanal** (Top-K bairros), não
  classificação binária isolada.
- **Onset** = primeira semana de um episódio (reaproveita
  `alert_metrics.construir_episodios`); continuação nunca conta como
  onset novo (testado). Horizonte principal: **t+1 a t+3** (mais valor
  preventivo e melhor PR-AUC que t+1 puro: 0,314 vs 0,197 no
  walk-forward).
- **Resultado real** (teste 2023-2025): PR-AUC walk-forward mais
  **estável** que a Formulação A (desvio 0,147 vs 0,201; piso 0,108 vs
  0,074) — ganho real na fragilidade mais citada nas etapas anteriores.
  Recall@10 "por episódio" (bairro no Top-10 antes do início):
  **38,4%** (vs 33,2% da Formulação A). Zero-detecção caiu de 7 para
  **2 bairros**.
- **Achado honesto**: o modelo só supera claramente baselines simples
  (crescimento recente, razão histórica) em **Top-5/Top-10** — em
  Top-15/20 os baselines empatam ou vencem (Recall@20: baseline
  crescimento 63,2% vs modelo 57,6%). O valor de ML se concentra no
  cenário operacional mais restritivo.
- **Achado novo**: disparidade regional real (RPA 5: 74,1% Recall@20 vs
  **RPA 6: 33,8%**) — não investigada a fundo. IPSEP (RPA 6) melhora de
  0% para 16,7% de detecção, mas continua fraco.
- **Achado crítico para o desafio**: separando episódios "recaída"
  (após atividade recente) de "antecipação genuína" (após período de
  baixa) — **antecipação genuína é o cenário mais comum (762/920
  episódios) e o mais difícil** (Recall@20 53,8% vs 76,0% em recaídas).
  É exatamente o cenário que a Prefeitura mais precisa que o sistema
  acerte.
- **Classificação: B — existe valor, mas as limitações ainda são fortes.
  Decisão preservada: NÃO integrar ao dashboard.**
- **Testes**: 17 novos (definição de onset, leakage, Precision@K,
  estabilidade de ranking, persistência). Suíte total: **317/317
  passando** (baseline era 306, 0 regressões). Bug real corrigido:
  `alert_metrics.construir_episodios` perdia as colunas quando não havia
  nenhum episódio (histórico totalmente indefinido) — corrigido antes de
  afetar qualquer resultado.
- **Não alterado**: Bronze, Silver, Gold, dashboard, dados climáticos,
  modelo/target da Formulação A (preservado como referência
  comparativa), `baselines.py`.

## 35. Validação estatística da evidência do ranking (sessão de 2026-08-20, continuação)

Relatório completo: `reports/ml/dengue_ranking_evidence_validation.md`.
Etapa de **avaliação final** do candidato congelado
`dengue_onset_ranking_candidate_v1` — sem retreino exploratório, sem
feature nova, sem tuning, sem mudança de target. Encerra a pesquisa de ML
desta versão.

- **Método**: bootstrap percentil (2.000 reamostragens, seed 42) com
  unidade = **episódio** (920 episódios reais, 2023-2025, 93 bairros);
  delta modelo × baseline **pareado** sobre os mesmos episódios;
  sensibilidade por cluster `bairro` e `bairro × ano`. Execução
  determinística, reproduzida duas vezes com resultado idêntico.
- **Ganho defensável só em Top-5**: +5,98 pp sobre o melhor ranking
  simples (IC 95% [+2,83; +9,13], IC>0 também nos dois esquemas de
  cluster). Em **Top-10 o IC cruza zero** (+2,61 pp, IC [−0,76; +5,98]) e
  o sinal **depende de 2025** (excluir 2025 no leave-one-year-out inverte
  o delta). Em **Top-20 o modelo é significativamente pior** que a regra
  simples `crescimento_recente` (−5,54 pp, IC [−10,11; −1,30]).
  Resultados negativos reportados sem atenuação.
- **Recall@K do modelo** (920 episódios): 25,76% (K=5) · 38,37% (K=10) ·
  48,15% (K=15) · 57,61% (K=20).
- **Lead time**: mediana 2 semanas (IC [2,3]), 69,1% com ≥2 semanas,
  45,6% com ≥3. Alerta na própria semana de início **nunca** conta como
  antecipação.
- **Antecipação genuína** (82,8% dos episódios) tem Recall@10 33,5%
  contra 62,0% em recaídas — ICs sem sobreposição. **Grandes episódios**
  vão pior que a média (Recall@10 30,4%, n=92).
- **Territorial**: RPA 5 59,4% (n=197) × RPA 6 23,0% (n=74). IPSEP: 0 de
  6 episódios em Top-10, posição mediana 39ª de ~94 — limitação
  sistemática (só 1 dos 93 bairros avaliados tem N ≤ 2, então amostra
  pequena não explica).
- **Carga operacional**: Top-5 = 770 priorizações, 65,5% sem episódio
  futuro; Top-10 = 1.540, 70,1% sem episódio futuro. Estabilidade do
  Top-10: Jaccard médio 0,294 — lista volátil entre semanas.
- **Frase defensável para a Prefeitura** (Top-5): *"Em validação
  retrospectiva de 2023-2025 (920 episódios reais em 93 bairros),
  considerando capacidade para priorizar até 5 bairros por semana, o
  modelo identificou antecipadamente 25,8% dos episódios (IC 95%:
  22,9-28,6%), contra 19,8% do melhor ranking simples — ganho de 6,0 pp
  (IC 95%: +2,8 a +9,1) — com antecedência mediana de 2 semanas."*
- **Classificação: B — evidência sugestiva, mas ainda incerta.**
  **Decisão: SIM como prova de conceito experimental, FORA do dashboard
  público.** As 7 páginas do *Recife Alerta* permanecem inalteradas; a
  visualização técnica é um app separado
  (`streamlit run tools/model_validation_app.py`) que só lê artefatos de
  backtest e nunca treina modelo nem gera previsão.
- **Artefatos**: `evidence_*.csv` + `resultado_evidence_validation_completo.json`
  + 9 figuras (`evidence_a_*` … `evidence_i_*`) em `reports/ml/`.
- **Testes**: suíte total **342/342 passando** (baseline 331, 0
  regressões).
