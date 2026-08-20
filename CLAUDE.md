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
- `reports/climate_source_analysis/apac_freshness_investigation.md` —
  investigação real de por que a rede APAC (PCDs) não tem leituras após
  2024-04-09 (ver §10 para o resumo).
- `reports/climate_source_analysis/alternative_sources_analysis.md` —
  comparação real (HTTP) de CEMADEN e ANA/Hidroweb como fontes climáticas
  alternativas à APAC (ver §10.2 para o resumo e a próxima fonte
  recomendada).
- `reports/climate_source_analysis/cemaden_precipitation_endpoint_investigation.md`
  — endpoint real de precipitação por estação do CEMADEN, encontrado e
  validado (ver §10.3).
- `reports/climate_source_analysis/cemaden_integration_results.md` —
  implementação oficial do CEMADEN (cliente, Bronze, Silver, elegibilidade,
  Estratégia A) com resultado real: 94/94 bairros associados (ver §10.4).
- `reports/gold_analysis/README.md` — **Gold analítica** (arboviroses +
  território + clima): grão, joins, cardinalidade, leakage, profiling,
  visualizações e a limitação crítica de cobertura climática (ver §12).
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
python -m src.ingest_climate && python -m src.transform_climate   # agora INMET + APAC + CEMADEN
python -m src.analyze_climate_coverage        # cobertura espacial (diagnóstico)
python -m src.transform_climate_bairro        # mapeamento bairro→estação (Silver, Estratégia A)
python -m src.analyze_climate_neighborhood_mapping   # relatório do mapeamento

python -m src.main && python -m src.transform         # arboviroses (Bronze → Silver)
python -m src.transform_gold_arboviroses_clima        # Gold: bairro × semana epi × agravo
python -m src.analyze_gold                            # profiling + visualizações da Gold
```

## 8. Estado do desenvolvimento (ver README §2 para detalhe por fase)

- Fase 1 (Arboviroses) e Fase 2 (Território): completas.
- Fase 3 (Clima): Bronze/Profiling/Silver/DQ/análise espacial completos.
- Mapeamento Silver `bairro → estação elegível mais próxima` (Estratégia A):
  **implementado, testado e validado com dados reais.** Histórico da
  investigação: a rede APAC ficou provada congelada desde 2024-04-09 (§10,
  §10.1) → CEMADEN identificado e recomendado como fonte alternativa
  (§10.2) → endpoint de valores de precipitação do CEMADEN encontrado e
  validado (§10.3) → **CEMADEN implementado oficialmente na arquitetura em
  2026-08-20 (§10.4) — resultado real: 94/94 bairros associados**, todos
  via CEMADEN (APAC permanece integrada mas inativa; nenhuma foi removida).
  Suíte: **185/185 passando** naquele momento.
- **Fase 4 (Gold analítica): implementada e validada em 2026-08-20** — ver
  §12. `gold_arboviroses_clima_bairro`, grão `bairro × semana epidemiológica
  × agravo`, 191.478 linhas reais (2013-2025), chave única, sem leakage,
  com profiling e 6 visualizações de validação. Suíte: **217/217 passando**.
  **Modelo dimensional (star schema) NÃO foi implementado** — não faz parte
  desta Gold.
- Fase 5 (ML) em diante: não iniciada. **Não avançar sem autorização.**

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

**Atualização**: a dúvida sobre rede real vs. relógio do ambiente, levantada
logo abaixo, foi **resolvida na investigação seguinte (§10.1): é a rede
real** (confirmado por reconsulta ao vivo idêntica ao Bronze). Ver §10.1 e
§10.2 para o estado atual completo.

### 10.1 Investigação de atualidade da APAC (sessão de 2026-08-19, continuação)

Investigação completa em
`reports/climate_source_analysis/apac_freshness_investigation.md`. Resumo:

- **Confirmado**: a resposta ao vivo do endpoint (reconsultado diretamente,
  fora do Bronze) é **idêntica, byte a byte**, ao que já estava armazenado
  — o endpoint serve um conjunto de dados congelado, não telemetria real.
- **Confirmado**: `ServicoMonitoramentoPCDs.php` (usado por `apac_client.py`)
  **é o mesmo endpoint que o painel público atual da APAC** referencia como
  fonte oficial de "Coleta de Dados (PCDs)" (`ServicoMapa.php?mapeamento=1/`
  do módulo `mod_painel_mapa`, atual, baseado em OpenLayers). **Não é
  endpoint legado.**
- **Confirmado**: parsing 100% correto (299/299, formato `DD-MM-AAAA`
  inequívoco, sem inversão dia/mês) e campo `"Data último dado"` significa
  literalmente última transmissão recebida — não é bug nosso nem campo
  com semântica diferente.
- **Achado**: 157/299 estações (52,5%) pararam de transmitir no mesmo dia
  (`2024-04-09`, horários distintos e plausíveis), mais 18 em `2024-04-08`
  — um evento concentrado, não apenas morte gradual e independente por
  estação. Causa raiz exata não confirmada (hipótese em aberto).
- **Classificação: A — rede real desatualizada** (não B/C/D). Ver relatório
  para descarte detalhado de cada hipótese alternativa.
- **Diagnóstico isolado (não persistido em Silver)**: ignorando só a idade
  da estação, a Estratégia A cobre **94/94 bairros**, com 27 estações
  distintas, distância mediana 1,1 km e máxima 3,6 km — a cobertura
  geométrica é excelente; o único problema é atualidade temporal.
- **Recomendação**: manter `LIMIAR_DIAS_ESTACAO_ATIVA=90` e o resultado
  0/94 como correto. Não implementar fonte alternativa nem relaxar o
  threshold sem essa decisão vir do usuário primeiro.

### 10.2 Investigação de fontes alternativas: CEMADEN e ANA/Hidroweb (sessão de 2026-08-19, continuação)

Investigação completa em
`reports/climate_source_analysis/alternative_sources_analysis.md`
(metodologia: requisições HTTP reais, spatial join geométrico real contra
`silver_bairro_geo`, diagnóstico da Estratégia A só em memória — nada
persistido em Silver, nenhum cliente definitivo criado). Resumo:

- **CEMADEN**: 437 estações pluviométricas cadastradas em PE, **19
  fisicamente dentro do Recife** (spatial join real), **15/19 elegíveis**
  pelo limiar de 90 dias do projeto (campo nativo `tempo_inatividade`, real
  e atualizado). Mesmos nomes/coordenadas da rede PCD da APAC — é
  provavelmente o mesmo hardware físico, mas com sinal de atividade mais
  confiável que o endpoint atual da APAC. Diagnóstico da Estratégia A:
  **94/94 bairros**, 18 estações distintas (só elegíveis), distância
  mediana 1,41 km, máxima 5,37 km. **Gap conhecido**: não foi encontrado
  ainda um endpoint com os *valores* de precipitação por estação (só
  cadastro + status de atividade); o único layer de valores achado no
  GeoServer (`precipitacao_bacia_24`) é agregado por bacia hidrográfica e
  está congelado desde 2017. Histórico mensal existe (2011-2026) mas é
  bloqueado por CAPTCHA.
- **ANA/Hidroweb**: 85 estações cadastradas em PE (43 pluviométricas + 42
  telemétricas), só **1 dentro do Recife** (Afogados). API REST nova exige
  login (401 sem token, nenhum modo anônimo); SOAP legado morto (timeout);
  serviço de telemetria com service definition vazia. Nenhum dado real
  obtido. Diagnóstico da Estratégia A (só cadastro): 94/94 "cobertos" mas
  com apenas 2 estações distintas, distância mediana 5,45 km, máxima 11,19
  km — muito pior que APAC/CEMADEN.
- **Classificação**: INMET = PRIMÁRIA (mantida). APAC = **rebaixada de
  complementar para RESERVA** (feed atual congelado, mas pipeline pronto
  para reusar se a rede voltar). CEMADEN = **COMPLEMENTAR (condicional)** —
  candidata mais forte, mas faltava confirmar o endpoint de valores (ver
  §10.3 — **confirmado**). ANA = RESERVA (autenticação obrigatória,
  baixíssima densidade em Recife).
- **Recomendação explícita**: **CEMADEN é a próxima fonte a implementar.**

### 10.3 Endpoint de valores de precipitação do CEMADEN (sessão de 2026-08-20, continuação)

Investigação completa em
`reports/climate_source_analysis/cemaden_precipitation_endpoint_investigation.md`.
Resumo:

- **Encontrado e confirmado**: `GET
  https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/{idEstacao}/{horas}`
  — série horária real de precipitação (mm) por estação, sem
  autenticação, sem CAPTCHA, sem cookie/sessão. Descoberto inspecionando o
  JS do painel público (`grafico_pcds.php`, carregado a partir de
  `resources_url = https://resources.cemaden.gov.br`, um domínio não
  testado nas investigações anteriores).
- **Correspondência de identificadores confirmada**: o `idEstacao`
  numérico usado por essa API (ex.: `6846` = Porto) é a mesma estação que
  o `codigo_estacao` alfanumérico do WFS (`261160620A`) — o payload da API
  devolve o campo `codEstacao` batendo exatamente com o cadastro já usado.
- **Testado em 4 estações reais do Recife** (Porto, Dois Irmãos,
  Imbiribeira, Dois Unidos): 3/4 com série real e recente; Dois Unidos sem
  nenhum valor não-nulo na janela recente, apesar de `tempo_inatividade=2`
  dias no cadastro WFS — **achado de qualidade**: esse campo de metadado
  não deve ser usado sozinho como critério de elegibilidade numa futura
  integração, precisa validar contra a série de valores real.
- **Histórico automatizável, sem CAPTCHA**: o mesmo endpoint aceita janelas
  grandes — testado com sucesso até `horas=8760` (365 dias, ~16 MB, 200
  OK) para a estação Porto, com dado real desde ~1 ano atrás. O CAPTCHA do
  `download_form.php` (documentado em §10.2) protege só um mecanismo de
  exportação formatada — **não é a única via de histórico**.
- **Unidade e semântica**: mm por hora-calendário (não é acumulado
  corrido). Janelas complementares (`acc1hr`...`acc96hr`) disponíveis no
  endpoint de status atual (`getJson2.php`) — nomeadas explicitamente, não
  devem ser confundidas entre si.
- **Frequência de base**: ~10 minutos por transmissão (inferido, não
  confirmado por série minuto a minuto de uma única estação); a API expõe
  agregação horária.
- **Fuso horário**: não confirmado por campo explícito no payload;
  aritmética compatível com UTC (ver relatório para detalhe) — hipótese,
  não fato.
- **Classificação: A — endpoint funcional encontrado.**
- **Recomendação**: CEMADEN pode ser usado como fonte automatizada de
  precipitação, tanto atual quanto histórica, via este endpoint REST.
  Endpoint `diario/{id}/{dias}` da mesma família **não funcionou** em
  nenhum teste (retornou vazio) — não confiar nele; agregar diário a
  partir do horário, como já feito para o INMET, se uma integração for
  autorizada. **Nada foi implementado ainda** — nenhum cliente, schema ou
  pipeline oficial criado nesta sessão.

### 10.4 Integração oficial do CEMADEN (sessão de 2026-08-20)

Implementação completa em `reports/climate_source_analysis/cemaden_integration_results.md`.
Resumo:

**Módulos criados/alterados** (nenhuma arquitetura paralela — tudo
reaproveita Bronze/Silver/Estratégia A já existentes):

- `src/clients/cemaden_client.py` (novo): `CemadenClient` —
  `baixar_cadastro_estacoes` (WFS `view_pcds_pluviometrica_cemaden`,
  `CQL_FILTER=uf='PE'`), `baixar_status_estacoes` (`getJson2.php`),
  `baixar_serie_horaria` (`MapaInterativoWS/resources/horario/{id}/{horas}`).
  Sem autenticação/CAPTCHA/cookie em nenhum dos três.
- `src/config.py` / `.env.example`: `CEMADEN_WFS_URL`, `CEMADEN_STATUS_URL`,
  `CEMADEN_HORARIO_URL` (defaults = endpoints reais), `CEMADEN_HORAS_INGESTAO`
  (default 48h).
- `src/ingestion/climate_ingestion.py`: `executar_ingestao_cemaden` — baixa
  cadastro+status de PE inteira, mas a série horária só das candidatas
  pluviométricas (`tipoestacao==1`) da **Grande Recife**
  (`MUNICIPIOS_GRANDE_RECIFE`: Recife, Olinda, Jaboatão dos Guararapes,
  Camaragibe, São Lourenço da Mata, Paulista, Abreu e Lima) — recorte
  pragmático para não gerar ~437 chamadas HTTP por execução; documentado
  como decisão de escopo, não garantia matemática de completude.
- `src/silver/schema_climate.py`: `FONTES_CLIMA` inclui `"CEMADEN"`; novo
  campo **`horas_validas_dia`** (nullable) em `COLUNAS_SILVER_CLIMA_DIARIO`
  — quantas leituras horárias válidas formaram o valor diário (populado
  também para INMET/APAC, não só CEMADEN).
- `src/silver/climate.py`: `transformar_estacoes_cemaden` (junta cadastro
  WFS + status `getJson2.php` pelo nome normalizado da estação — validado
  18/18 sem ambiguidade antes de implementar),
  `extrair_observacoes_horarias_cemaden` (parsing robusto da matriz
  `datas`×`horarios`→`acumulados`), `agregar_diario_cemaden`,
  `transformar_diario_cemaden`.
- `src/profiling/climate_profiler.py`:
  `selecionar_cadastro_status_cemaden_mais_recentes` (cadastro/status:
  padrão "última execução com sucesso", como o INMET) e
  `listar_todas_series_horarias_cemaden` (série horária: padrão "acumula
  todas as execuções", como a APAC).
- `src/silver/pipeline_climate.py`: `_processar_cemaden` — acumula todas as
  séries horárias já coletadas e **deduplica por (`codigo_estacao`, `data`,
  `hora`)** antes de agregar para diário (janelas de execuções sucessivas
  se sobrepõem; a mais recente vence em conflito). Idempotente: a Silver é
  regravada por inteiro a cada execução, nunca por append.
- `src/silver/schema_climate_bairro.py` / `src/silver/climate_bairro.py`:
  `FONTE_ELEGIVEL` (uma fonte) generalizado para
  **`FONTES_ELEGIVEIS = ("APAC", "CEMADEN")`**. **Sem prioridade explícita
  entre fontes** — proposital: elegibilidade já exige leitura real recente
  em `silver_clima_diario` (nunca metadado de cadastro), então "a mais
  próxima entre as elegíveis" já implementa a regra certa; se a APAC
  voltar a ter leitura real, compete de novo sem mudar código. **Dois bugs
  de chave corrigidos** como parte da generalização (só se manifestavam
  com 2+ fontes): merge de última leitura e índice de localização física
  usavam só `codigo_estacao` (não é único entre fontes) — ambos agora usam
  a chave composta `(fonte, codigo_estacao)`.

**Regra de atividade**: inalterada, `LIMIAR_DIAS_ESTACAO_ATIVA=90`,
aplicada da mesma forma a todas as fontes — nunca a partir de metadado de
cadastro (`tempo_inatividade` da APAC/CEMADEN nunca é usado como critério
de elegibilidade, só a leitura real em `silver_clima_diario`).

**Resultado real da execução (2026-08-20, não estimativa)**:

- Ingestão: 35 estações pluviométricas candidatas na Grande Recife, 35/35
  séries horárias obtidas com sucesso, 0 erros.
- Silver estações: 407 CEMADEN válidas (de 437 no cadastro de PE; 28
  rejeitadas por `codigo_estacao` duplicado — achado de qualidade real,
  não hipótese). Total combinado: **718 estações** (12 INMET + 299 APAC +
  407 CEMADEN).
- Silver clima diário: 24 das 35 candidatas produziram ao menos 1 dia real
  válido; **67 linhas diárias CEMADEN**, cobrindo 2026-08-18 a 2026-08-20
  (dado genuinamente atual — mesma data do sistema).
- Elegibilidade: 706 candidatas (APAC+CEMADEN), **24 elegíveis — todas
  CEMADEN** (as 299 da APAC continuam 100% excluídas por inatividade,
  confirmando de novo o achado de §10.1).
- **Estratégia A: 94/94 bairros associados (100%)**, 16 estações distintas
  usadas, distância mediana 1,431 km, máxima 4,632 km (bairro Tótó), 14/94
  bairros com estação própria. **Todas as 94 associações usam CEMADEN** —
  resultado emergente do filtro de atividade real, não de uma regra de
  prioridade escrita (comprovado com um teste de regressão dedicado).
- Caso real ilustrativo: o bairro "Dois Unidos" não usa a estação CEMADEN
  de mesmo nome (fisicamente ali) porque ela não tinha série real
  utilizável nesta execução — foi associado à estação "Nova Descoberta"
  (0,836 km) em vez disso. Prova em produção do motivo de nunca confiar em
  metadado de atividade sozinho.

**Testes**: 29 novos (cliente, parsing Silver, ingestão, pipeline
ponta-a-ponta com deduplicação de execuções sobrepostas, Estratégia A
multi-fonte). **Suíte total: 185/185 passando**, nenhuma regressão.

**Próximo passo (não iniciado, decisão do usuário)**: nada — o critério de
sucesso desta etapa (CEMADEN → Bronze → Silver → estação elegível por
observação real → Estratégia A → bairro, com dados reais) foi atingido.
Não avançar para Gold, não implementar modelos preditivos, não relaxar o
threshold, sem autorização explícita.

## 11. Coisas que NÃO fazer sem autorização explícita

- Não implementar modelo dimensional Gold (star schema, surrogate keys,
  dimensões/fatos separados) — a Gold atual é uma tabela analítica única
  (§12), não um star schema.
- Não implementar Machine Learning / feature engineering além das features
  já existentes na Gold / backtesting / tuning / seleção de algoritmo.
- Não construir dashboard interativo (as visualizações da §12 são PNG de
  validação, geradas por script, propositalmente não interativas).
- Não implementar IDW, Kriging ou interpolação espacial — só Estratégia A.
- Não usar `fillna(0)` em variáveis climáticas ausentes.
- Não preencher a lacuna climática histórica da Gold misturando fontes
  (ex.: INMET regional a ~90 km como proxy de clima de bairro) sem decisão
  arquitetural explícita — ver §12 e `reports/gold_analysis/README.md`.
- Não usar `codigo_bairro` do SINAN para join com território — espaços de
  código incompatíveis (21/94); usar `nome_bairro` normalizado (§12).
- Não "corrigir" geometria inválida automaticamente (`make_valid()`) sem
  reportar explicitamente.
- Não misturar `converter_decimal_brasileiro` e `converter_float` entre
  fontes.
- Não recriar `silver_estacao_climatica`/`silver_clima_diario` — reutilizar
  (agora com INMET + APAC + CEMADEN, mesmo schema).
- Não adicionar prioridade hardcoded entre fontes na Estratégia A (ex.:
  "CEMADEN sempre vence APAC") — a elegibilidade por atividade real já
  implementa a regra certa (ver §10.4); uma prioridade fixa destruiria a
  propriedade de a APAC voltar a competir sozinha se reativar.
- Não usar `codigo_estacao` sozinho como chave em merges/índices no domínio
  de clima — não é único entre fontes; sempre `(fonte, codigo_estacao)`.

## 12. Gold analítica `gold_arboviroses_clima_bairro` (sessão de 2026-08-20)

Relatório completo com todos os números reais:
`reports/gold_analysis/README.md`. Resumo operacional:

**Módulos criados** (`src/gold/`, pacote novo):

- `epidemiologia.py` — calendário de semana epidemiológica (convenção
  SVS/CDC: domingo→sábado, semana 1 contém 4 de janeiro). **Não é
  `isocalendar()`** (que é ISO, segunda→domingo) — a regra foi validada
  empiricamente contra 5.000 pares reais (`data_notificacao`,
  `semana_notificacao`) da Silver: 5000/5000. A semana dos **casos não é
  recalculada** — usa `semana_notificacao` do SINAN como está; este módulo
  resolve o inverso (ano+semana → intervalo de datas) para agregar o clima.
- `schema_gold_arboviroses_clima.py` — contrato: `VERSAO_SCHEMA_GOLD="1.0"`,
  `JANELAS_RETROSPECTIVAS_DIAS=(7,14,21,28)`, `COLUNAS_GOLD_*` e a
  justificativa de cada decisão no docstring.
- `arboviroses_clima.py` — transformação (dedup → período epidemiológico →
  join bairro oficial → agregação → grão completo → território → features
  climáticas). Cada etapa devolve métricas de cardinalidade; joins
  **levantam exceção** se multiplicarem linhas ou perderem casos.
- `pipeline_gold_arboviroses_clima.py` + `src/transform_gold_arboviroses_clima.py`
  — orquestração/I-O e entry point.
- `profiling_gold.py` + `src/analyze_gold.py` — profiling e 6 visualizações
  de validação (matplotlib, backend `Agg`, só PNG). Separado da
  transformação de propósito: nenhuma função de transformação importa
  matplotlib.

**Grão e chave**: `bairro × semana epidemiológica × agravo`; chave
`codigo_bairro + agravo + ano_epidemiologico + semana_epidemiologica`.
Escolhido sobre `bairro+mês` porque `semana_notificacao` já existe no SINAN
com 0,04% de nulos (não precisa inventar distribuição). Agravos em
**linhas**, não colunas.

**Decisões que NÃO devem ser revertidas sem motivo novo**:

- Join arboviroses × território por **`nome_bairro` normalizado**, nunca por
  `codigo_bairro`: verificado que o código do SINAN não é o mesmo espaço de
  códigos de `silver_bairro_geo` (só 21/94 coincidem; 93/94 bairros oficiais
  têm >1 código associado). Por nome bate 94/94.
- **`casos=0` é materializado** (grão cartesiano completo): notificação é
  compulsória, logo ausência = zero real. Isso é **deliberadamente
  diferente** do clima, onde ausência = `None` (`missing ≠ 0 mm`).
- **Sem `incidencia_por_100k`**: nenhuma fonte do projeto tem população por
  bairro. Não inventar — exigiria nova fonte (IBGE), não autorizada.
- **Leakage**: features climáticas usam somente `data <= semana_epi_data_fim`
  da própria linha; janelas retrospectivas terminam nessa data (incluem a
  própria semana, nunca dias posteriores). Teste dedicado injeta chuva
  futura e confirma que nenhuma feature muda.

**Resultado real (2026-08-20)**: 191.478 linhas · 94 bairros · 3 agravos ·
679 semanas (2013-2025) · 156.504 casos preservados (96,33% de
aproveitamento no join espacial; perdas contadas no manifest) · 0
duplicatas de chave · 0 casos negativos.

**⚠️ Limitação crítica**: **0% das linhas têm clima real**. A interseção
temporal entre casos (2013-2025) e clima com leitura real (CEMADEN:
2026-08-18 a 2026-08-20) é vazia — o CEMADEN só começou a acumular série
quando foi integrado, depois do fim da série epidemiológica. As colunas
climáticas existem e o mecanismo é correto/testado, mas ficam `None` no
histórico. **Não** foi implementada mistura de fontes (INMET regional como
proxy) — decisão arquitetural pendente de autorização.

**Próximo passo (decisão do usuário, nada iniciado)**: EDA completa. Duas
frentes possíveis — (1) EDA da dimensão epidemiológica+territorial, que tem
13 anos de dado real e denso; ou (2) resolver a lacuna climática histórica
antes de uma EDA integrada clima↔casos (que hoje é impossível com dado
real).
