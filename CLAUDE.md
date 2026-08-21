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

- `README.md` — **documento de produto** (público misto: problema, solução,
  resultados, limitações). Desde 2026-08-21 não é mais o documento técnico.
- `docs/arquitetura_e_pipeline.md` — **o antigo README** (35 seções, nada
  removido): camadas, contratos, decisões de fonte, resultados de execução.
  Sempre validar contra ele antes de assumir algo sobre arquitetura.
- `reports/product/` — documentação para gestão desta etapa: visão do
  produto, atualidade dos dados, segurança/privacidade, confiabilidade,
  módulo experimental, runbook e o relatório de hardening (ver §19).
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
  visualizações e a cobertura climática real, atualizada após o backfill
  (ver §12 e §13).
- `reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`
  — investigação de profundidade histórica do CEMADEN e o backfill
  implementado (ver §13).
- `reports/eda/README.md` — EDA reproduzível (histórica 2013-2025 +
  integrada com clima 2024-2025) e o dashboard Streamlit que a consome
  (ver §14).
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
python -m src.backfill_climate_cemaden --dias 730      # backfill historico CEMADEN (ver CLAUDE.md §13)
python -m src.analyze_climate_coverage        # cobertura espacial (diagnóstico)
python -m src.transform_climate_bairro        # mapeamento bairro→estação (Silver, Estratégia A)
python -m src.analyze_climate_neighborhood_mapping   # relatório do mapeamento

python -m src.main && python -m src.transform         # arboviroses (Bronze → Silver)
python -m src.transform_gold_arboviroses_clima        # Gold: bairro × semana epi × agravo
python -m src.analyze_gold                            # profiling + visualizações da Gold

python -m src.validate_dengue_onset_ranking_evidence  # validação estatística do candidato (§18)
python -m src.plot_evidence_validation                # figuras A-I da validação (§18)
streamlit run tools/model_validation_app.py           # visualização técnica experimental (§18)

# --- etapa de produto (§19) ---
python -m src.update_recife_alerta                    # orquestra a atualizacao (NUNCA treina)
python -m src.update_recife_alerta --sem-rede         # recalcula so com o que esta em disco
python -m src.update_recife_alerta --com-datalake     # inclui a cadeia canonica no MinIO
python -m src.build_climate_grade --destino local     # reanalise -> Silver em grade
python -m src.enrich_gold_clima_grade --origem local  # Gold 1.0 -> 1.1 (bloco em grade)
python -m src.generate_freshness                      # metadados de atualidade
python -m src.train_priority_model                    # treina/congela o modelo (operacao SEPARADA)
python -m src.generate_priority_artifacts             # backtest + status (sem treinar)
python -m src.healthcheck                             # PASS/WARN/FAIL
python -m src.investigate_gridded_climate             # investigacao de fonte em grade (§19.1)
python -m src.experiment_dengue_ranking_clima         # experimento A x B de clima (§19.2)
python scripts/verificar_deploy_dashboard.py          # aptidao para publicacao
python scripts/testar_dashboard_navegador.py --todos-os-perfis   # 9 paginas x 3 larguras
```

## 8. Estado do desenvolvimento (ver `docs/arquitetura_e_pipeline.md` §2 para detalhe por fase)

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

Decisão herdada da análise anterior (`docs/arquitetura_e_pipeline.md` §26): B/C/D (múltiplas estações,
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
- Não afirmar ganho do modelo sobre rankings simples em **Top-10, Top-15 ou
  Top-20** — validado em 2026-08-20: só **Top-5** tem IC que não cruza zero
  (§18). Em Top-20 o baseline é significativamente melhor.
- Não integrar o ranking preditivo às 7 páginas do dashboard público
  (*Recife Alerta*) — a visualização técnica vive em
  `tools/model_validation_app.py`, separada de propósito (§18).
- Não alterar modelo/feature/target/hiperparâmetro de
  `dengue_onset_ranking_candidate_v1` e reaproveitar os números da §18:
  qualquer mudança cria **nova versão** e exige nova validação.
- Não treinar modelo nem gerar previsão futura dentro de qualquer app
  Streamlit — as páginas só leem artefatos já calculados.
- Não incorporar clima ao modelo do produto: o experimento controlado (§19.2)
  mostrou ganho nulo em Top-5 (a faixa de claim), com IC cruzando zero nos
  três esquemas de reamostragem e sinal negativo em 2024. O ganho em Top-10 é
  um achado **registrado**, não um resultado — usá-lo exigiria uma versão v2
  com o protocolo completo de validação.
- Não descrever a reanálise em grade como "estação meteorológica do bairro":
  são **2 células** de precipitação para os 94 bairros (§19.1). Sempre
  "estimativa climática em grade/reanálise", com resolução declarada.
- Não gerar `latest_priority.parquet` quando o portão de atualidade estiver
  fechado (§19.3) — e nunca deixar um arquivo antigo sobreviver ao bloqueio.
  O healthcheck trata essa incoerência como `FAIL`, não aviso.
- Não publicar probabilidade do modelo em nenhum artefato ou página. Só
  posição no ranking e `score_prioridade` (posto relativo, calculado por
  ordenação — nunca probabilidade reescalada).
- Não escrever data literal em texto de UI ou de relatório: toda data vem de
  `dashboard/data/_freshness.json` (§19.3).
- Não publicar artefato sem passar pelos portões de qualidade
  (`src/quality_gates.py`) nem gravar sem `src/utils/io_atomico.py`.
- Não reaproveitar os ~79% de detecção em epidemias grandes (formulação
  binária, §15) para o módulo de ranking: sob ranking o valor real é 30,4%
  em Top-10 — **pior** que a média.
- Não adicionar dependência ao `dashboard/requirements.txt` (superfície
  publicada, 5 pacotes) nem importar `boto3`/`geopandas`/`sklearn`/
  `matplotlib`/`requests` em `dashboard/` ou `src/eda/` — o script de
  verificação de deploy falha se isso acontecer.

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

**Limitação original (resolvida parcialmente em 2026-08-20, ver §13)**:
nesta execução original, **0% das linhas tinham clima real** — a
interseção temporal entre casos (2013-2025) e clima com leitura real
(CEMADEN: 2026-08-18 a 2026-08-20) era vazia. Depois do backfill histórico
(§13), a Gold foi reconstruída e a cobertura real subiu para 6,11%
(2024-2025). **Não** foi implementada mistura de fontes (INMET regional
como proxy) — decisão arquitetural que continua exigindo autorização, não
mudou.

**Próximo passo (decisão do usuário)**: EDA. Com o backfill (§13), agora
existem duas janelas possíveis — (1) EDA clima×arboviroses restrita a
2024-2025 (dado real, 90/94 e 65/94 bairros cobertos); ou (2) EDA completa
da dimensão epidemiológica+territorial (13 anos, sem clima). Para
2013-2023, EDA integrada com clima real continua impossível — nenhuma fonte
investigada resolve esse trecho (ver §13, seção "próxima fonte" do
relatório de backfill).

## 13. Backfill histórico do CEMADEN e reconstrução da Gold (sessão de 2026-08-20)

Investigação e execução completas em
`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`
(ver também `reports/gold_analysis/README.md`, seção "Atualização"). Resumo
operacional:

- **Profundidade histórica real do CEMADEN**: validada tecnicamente até
  **1825 dias (5 anos)** por estação via `horario/{id}/{horas}` (Porto:
  2021-08-21 → 2026-08-20, 400 MB, 200 OK, sem CAPTCHA/login). O endpoint
  só aceita "últimas N horas a partir de agora" — **não existe parâmetro
  de data inicial**, logo não há chunking real por intervalo (a
  profundidade é a maior requisição bem-sucedida por estação, não a soma
  de várias). Achado operacional: janelas ≥ ~2 anos podem exceder 60s na
  1ª requisição a uma estação ("cold start" reproduzível — a mesma
  requisição repetida responde em segundos), por isso o backfill usa
  timeout alto (180s) + retentativa, nunca chunking por data.
- **Backfill implementado**: sim.
  `src/ingestion/cemaden_backfill.py` (`executar_backfill_cemaden`,
  `estacoes_com_backfill_suficiente` para checkpoint/retomada) +
  `python -m src.backfill_climate_cemaden --dias N`. Grava em
  `bronze/recife/clima/cemaden/horario_backfill/...` (prefixo distinto do
  operacional `.../horario/...`). **Nenhuma mudança em
  `pipeline_climate.py`**: a Silver já acumulava/deduplicava qualquer
  entrada `tipo="horario"` de qualquer manifest CEMADEN, operacional ou
  backfill — confirmado com teste de integração dedicado.
- **Intervalo obtido nesta execução**: 730 dias (2 anos, 2024-08-20 →
  2026-08-20) — não os 1825 dias validados tecnicamente, por limitação de
  memória do ambiente local (`moto` em memória, sem MinIO/Docker real,
  ~1,9-2,3 GB livres observados nesta sessão). Documentado como decisão de
  ambiente, não limite do CEMADEN — `--dias 1825` funcionaria sem mudança
  de código num ambiente com MinIO real.
- **Estações**: as 16 que a Estratégia A já usa (`silver_bairro_estacao`),
  não as 407 de PE nem as 35 candidatas da Grande Recife — partiu do
  mapeamento espacial atual, conforme decidido. 16/16 sucesso, 0 erros.
  Achado real: a estação `6532` só tem leitura real desde 2026-04-14
  (começou a operar no meio da janela de 730 dias pedida) — tratado
  corretamente pelo mecanismo existente (`horas_validas_dia`,
  `missing ≠ 0`), sem mudança de código.
- **Estratégia A não precisou de versão temporal** (bairro+período →
  estação elegível naquele período): a elegibilidade depende só da leitura
  mais recente (invariante a backfill), e `transform_climate_bairro` deu o
  mesmo mapeamento 94/94 antes e depois do backfill.
- **Cobertura dos bairros**: 2024 = 90/94 (95,74%), 2025 = 65/94 (69,15%);
  2013-2023 seguem 0/94 (fora da janela de 730 dias a partir de
  2026-08-20).
- **Percentual da Gold com clima real**: 0% → **6,1151%** (11.709/191.478
  linhas), 8.210 casos reais em semanas com clima real, os 3 agravos
  representados, 0 leakage (reconfirmado), 0 duplicatas (inalterado).
- **Limitações**: 2013-2023 continuam sem clima real (nenhuma fonte
  investigada resolve); profundidade aplicada (730d) é menor que a
  validada tecnicamente (1825d) só por causa do ambiente local; payload do
  endpoint cresce ao quadrado da janela (documentado), o que tornaria 10+
  anos caro mesmo com MinIO real.
- **Classificação: B — histórico parcial útil.**
- **Próximo passo (decisão do usuário, nada iniciado)**: EDA
  clima×arboviroses restrita a 2024-2025; ou rodar o backfill com
  `--dias 1825` num ambiente com MinIO real para estender a janela a
  2021-2025 antes da EDA; ou investigar ANA/Hidroweb ou produtos de
  precipitação em grade para 2013-2023 (não iniciado, não autorizado).
  Suíte: **226/226 passando** (baseline era 217).

## 14. Dashboard Streamlit + EDA reproduzível (sessão de 2026-08-20)

**Dashboard criado.** Tecnologia: **Streamlit** (1.62, `st.navigation`/
`st.Page`) + **Plotly** (única lib de gráfico/mapa — sem Folium/PyDeck em
paralelo, decisão registrada). Produto analítico principal do projeto a
partir desta etapa (não descartável).

**Estrutura**: `dashboard/{app.py, _bootstrap.py, pages/, components/,
utils/, data/, requirements.txt}` + `.streamlit/config.toml`. Lógica
analítica reutilizável em `src/eda/` (`filtros.py`, `epidemiologia.py`,
`clima.py`, `correlacao.py`, `relatorio.py`) — puro pandas, sem Streamlit,
usada tanto pelo dashboard quanto por `reports/eda/`
(`python -m src.generate_eda_report`). **Nenhuma lógica da Gold foi
reimplementada** (dashboard só consome, nunca recalcula join/Estratégia A/
agregação epidemiológica).

**Páginas** (7): Visão Geral, Epidemiologia (2013-2025), Mapa
Epidemiológico, Ranking de Bairros, Clima (CEMADEN), Clima × Arboviroses
(2024-2025, restrita automaticamente a linhas com clima real), Qualidade
dos Dados.

**Comandos**:
```bash
python -m src.export_dashboard_dataset   # gera dashboard/data/
streamlit run dashboard/app.py
python -m src.generate_eda_report        # gera reports/eda/
python scripts/verificar_deploy_dashboard.py
```

**Dataset usado**: `dashboard/data/gold_arboviroses_clima_bairro.parquet`
(0,34 MB, 191.478 linhas) + `bairro_geo.geojson` (2,16 MB, 94 bairros) —
exportados uma vez do Data Lake (MinIO/moto), nunca lidos em tempo real
pelo dashboard (permite deploy sem infraestrutura local). Seguro por
construção (Gold já agregada, sem dado individual do SINAN); o script de
exportação levanta erro se aparecer coluna potencialmente identificável.

**Achados principais da EDA** (`reports/eda/README.md`, todos com N de
observações reportado):
- Ano com mais casos de arboviroses (2013-2025): **2015**. Pico de Zika em
  2016, onda de chikungunya em 2021, alta de dengue 2024-2025.
- Sazonalidade real: pico médio na **semana epidemiológica 11**
  (fev/mar), platô elevado entre semanas ~8-25.
- Maior carga histórica: **COHAB, IBURA, VÁRZEA, ÁGUA FRIA** (contagem
  absoluta — sem incidência, sem dado de população por bairro).
- EDA integrada (só 2024-2025, n=3.903-4.137 observações por agravo):
  correlação exploratória (Pearson) casos×chuva **cresce com o lag**
  (28d > 21d > 14d > 7d) nos 3 agravos, mas é **fraca** em todos os casos
  (< 0,12) — Dengue tem a maior correlação exploratória entre os três.
  **Não é causalidade, não é generalizável a 2013-2023.**

**Status de deploy**: preparado, **não publicado nesta sessão** (nenhuma
credencial do Streamlit Community Cloud disponível/configurada neste
ambiente). `dashboard/requirements.txt` (mínimo, sem geopandas/boto3/moto),
`.streamlit/config.toml`, sem caminho absoluto local, sem segredo no
código — verificado por `scripts/verificar_deploy_dashboard.py`. Testado
localmente via `streamlit run` + browser real: as 7 páginas carregam,
filtros (agravo/ano/RPA/bairro) funcionam, mapa renderiza, sem erro de
console.

**Testes**: 30 novos (`test_eda.py` 25, `test_eda_relatorio.py` 3,
`test_export_dashboard_dataset.py` 2) — camada analítica (filtros,
agregação, ranking, correlação, cobertura, **DataFrame vazio** [achou e
corrigiu um bug real em `cobertura_por_ano`/`cobertura_por_bairro`],
bairro sem clima, rejeição de dado identificável na exportação). Suíte
total: **256/256 passando** (baseline era 226, 0 regressões).

**Próximo passo (decisão do usuário, nada iniciado)**: publicar no
Streamlit Community Cloud (credenciais/repositório GitHub pendentes do
usuário); ou avançar para feature engineering/Machine Learning a partir
dos achados da EDA — **iniciado na sessão seguinte, ver §15**.

## 15. Machine Learning: alerta antecipado de dengue por bairro (sessão de 2026-08-20, continuação)

Relatório completo em `reports/ml/dengue_early_warning_baseline.md`
(formalização, target, features, split, baselines, modelos, métricas
técnicas/operacionais, lead time, comparação com clima, limitações,
decisão). Resumo operacional — ver também `docs/arquitetura_e_pipeline.md` §32:

- **DENGUE é o agravo preditivo principal a partir de agora.** Zika/
  Chikungunya seguem só para EDA/comparação.
- **Pacote novo `src/ml/`** (`target.py`, `features.py`, `dataset.py`,
  `split.py`, `baselines.py`, `models.py`, `evaluation.py`,
  `alert_metrics.py`) + entry point
  `python -m src.evaluate_dengue_alert_baseline`. Consome
  `dashboard/data/gold_arboviroses_clima_bairro.parquet` — nenhum
  join/agregação da Gold é reimplementado.
- **Definição de "risco elevado"** (`target.py`): `casos > percentil 90`
  da distribuição histórica do MESMO bairro numa janela de `±2` semanas em
  torno da semana alvo, usando só anos anteriores (fallback para
  distribuição geral do bairro se amostra sazonal < 15; indefinido se nem
  isso, nunca forçado a 0/1). Não é um corte absoluto (`casos > N`) —
  justificado pela variação de escala entre bairros (COHAB 6.817 casos
  acumulados vs. PAU FERRO 1, em 13 anos) e pela ausência de dado de
  população por bairro no projeto.
- **Horizonte principal: t+1 semana** (t+2 avaliado à parte, PR-AUC menor:
  0,250 vs 0,292). **Target ≠ previsão de contagem** — é estado de risco
  elevado em t+1 (Saída B/alerta), distinto da previsão quantitativa
  (Saída A, `casos_t+1`), que existe só como baseline de apoio.
  Split temporal: treino 2013-2019, validação 2020-2022, teste 2023-2025
  (nunca aleatório); threshold de decisão escolhido por F1 na validação,
  nunca no teste.
- **Resultado real** (teste 2023-2025, 14.664 linhas, 58.750 linhas no
  dataset supervisionado completo, 12,03% positivo): HistGradientBoosting
  PR-AUC 0,292 / Logistic Regression PR-AUC 0,278 — ambos superam
  claramente os 3 baselines (persistência PR-AUC 0,156, crescimento
  recente 0,094, sazonal simples 0,140). Episódios detectados: 39,3%
  geral, **79,3% nas epidemias grandes** (top 10% por casos). Lead time
  mediano nos episódios detectados: **3 semanas** (81,5% das detecções são
  antecipadas, não simultâneas/tardias). Walk-forward por ano mostra
  **forte instabilidade** (PR-AUC de 0,074 em 2023 a 0,652 em 2021) — não
  generaliza uniformemente entre ciclos epidêmicos. Vários bairros com
  histórico suficiente têm 0% de detecção — heterogeneidade espacial real,
  não ruído disperso.
- **Comparação BASE × BASE+CLIMA** (2024→2025, mesmas linhas, mesmo split,
  só o modelo de árvore por aceitar `NaN` nativamente): ganho de PR-AUC
  **+0,025**, pequeno e estatisticamente frágil (treino de só 1.305 linhas
  de um único ano). **Clima não foi incorporado ao modelo principal** —
  regra explícita de não forçar clima sem ganho robusto.
- **Classificação: B — existe sinal, mas precisa melhorar.** **Decisão:
  SIM**, avançar para uma etapa de otimização (não para produção) — ver
  ressalvas específicas no relatório (investigar falha de 2023, elevar
  taxa de detecção geral, heterogeneidade por bairro, calibração de
  probabilidade antes de qualquer exibição de "risco: X%").
- **Testes**: 29 novos, incluindo leakage adversarial (injeção de
  `casos=99999` no futuro confirmando que features/limiares passados não
  mudam) em target/features/dataset, e testes de episódio/lead time/split.
  Suíte total: **285/285 passando** (baseline era 256, 0 regressões).
- **Dependência nova**: `scikit-learn` (`requirements.txt`) — única
  adição, usada por `LogisticRegression`/`HistGradientBoostingClassifier`.
- **Não alterado**: Bronze, Silver, Gold, dashboard, dados climáticos.
  Nenhum tuning extensivo, ensemble, deep learning, calibração avançada,
  categorias verde/amarelo/vermelho ou deploy — conforme regra de parada
  explícita desta etapa.
- **Próximo passo (decisão do usuário)**: otimização do sistema de alerta
  — **executada na sessão seguinte, ver §16**.

## 16. Machine Learning: otimização e diagnóstico de robustez (sessão de 2026-08-20, continuação)

Relatório completo em `reports/ml/dengue_early_warning_optimization.md`
(ver também `docs/arquitetura_e_pipeline.md` §33). Resumo operacional:

- **Diagnóstico de 2023** (pior ano da etapa anterior, PR-AUC 0,074):
  NÃO é falha de feature/target/modelo. Evidência: prevalência do target
  2,6% (5-6x menor que anos "normais" como 2019/2021/2024/2025);
  episódios mais curtos (1,08 semana vs 1,5-2,4 nos outros anos), mais
  fracos (pico mediano 2 casos) e mais restritos espacialmente (56/94
  bairros vs 91-92/94); drift de features (KS test) **menor** em 2023 que
  em 2024/2025 (que têm melhor desempenho absoluto) — descarta drift como
  causa. `lift_pr_auc = PR-AUC/prevalência` (`src/ml/diagnostics.py`)
  mostra que, corrigindo por prevalência, 2023 (2,80x) não é o pior ano —
  2024 é (2,44x). **Confirmação decisiva**: mesmo após todas as
  melhorias desta etapa (features + tuning), o PR-AUC de 2023 não mudou
  (0,0738 → 0,0738) — é um limite estrutural do ano epidemiológico, não
  do pipeline.
- **Features novas** (`src/ml/features.py`): histórico local
  (`razao_limiar_historico = casos_t/(limiar_historico_local+1)`,
  `z_score_historico_local`, `razao_media_recente`, suavização de Laplace
  `+1` para nunca gerar `inf`/`NaN` por divisão por zero) e momentum
  (`delta_1s/2s`, `aceleracao_1s`, `taxa_crescimento_suavizada`,
  `n_semanas_consecutivas_crescimento`). Ablation cumulativo
  (`ablation_features.csv`): sazonal é o grupo com maior ganho isolado
  (+0,024 PR-AUC), histórico local o segundo (+0,009) — e
  `razao_limiar_historico` acaba sendo a feature MAIS importante do
  modelo em TODOS os 7 folds do walk-forward (permutation importance).
  Território e momentum têm ganho marginal (+0,003 cada), mantidos por
  não piorarem nada.
- **Target alternativo** (`calcular_estado_alto_risco_v2_experimental`,
  anomalia sazonal + crescimento em 2 semanas): comparado, **não
  adotado** — concordância baixa com o oficial (Jaccard 0,08-0,18,
  pior ainda no ano de epidemia grande 2015: 50,2% de concordância) e
  risco de target auto-realizável se combinado com features de momentum
  (seção 12 do pedido da etapa). Target oficial (`estado_alto_risco`,
  P90 histórico-sazonal) **mantido sem alteração**.
- **Tuning controlado**: grade pequena (4 combinações), avaliada por
  MEDIANA do PR-AUC no walk-forward completo (generalização, não só
  validação isolada) — as 4 combinações tiveram desempenho
  estatisticamente indistinguível; escolhida a mais simples
  (`max_depth=4`, `max_iter=150`) por parcimônia.
- **Resultado real** (teste 2023-2025, mesmo split da etapa anterior):
  PR-AUC 0,292 → **0,308**; episódios detectados 39,3% → **45,9%**;
  bairros com 0% de detecção 12 → **7** (IPSEP — bairro de volume
  substancial, 1.629 casos acumulados — continua em 0%, achado
  específico a investigar); epidemias grandes seguem em ~78-79%
  (estável); Brier Score calibrado (isotonic, fit só na validação,
  `sklearn.frozen.FrozenEstimator`) **0,116 → 0,073** (-37%).
- **Threshold operacional** (`threshold_operacional.csv`): tabela
  completa 0,3-0,7 com Precision/Recall/episódios detectados/lead
  time/falsos alertas por semana/bairros alertados por semana — não um
  único limiar escondido. Threshold 0,6 (escolhido por F1 na validação):
  mediana de 7 bairros alertados/semana (máximo observado numa semana:
  53); sequências de falsos alertas consecutivos no mesmo bairro: média
  1,5 semana, máxima 5 (a maioria isolada, não persistente).
- **Ranking territorial** (`src/ml/ranking.py`, novo): Recall@20 semanal
  41-46% (~2x o acaso); em 52,7% dos episódios reais o bairro já estava
  no Top-20 de risco da cidade em algum momento das 4 semanas antes do
  início (mais informativo que Recall@K semanal isolado, mas ainda
  modesto).
- **Instabilidade entre anos persiste**: desvio-padrão do PR-AUC entre os
  7 folds do walk-forward = 0,201 (min 0,074 em 2023, max 0,664 em 2021)
  — não resolvida pela otimização, é estrutural.
- **2025 não é mais holdout puro** — já usado como teste na etapa
  anterior; documentado explicitamente, não escondido.
- **Classificação: B — melhorou, mas ainda apresenta fragilidades
  relevantes. Decisão explícita: NÃO integrar ao dashboard nesta etapa.**
  Se/quando integrado no futuro, mostrar score/ranking de risco, não
  probabilidade calibrada como número de confiança absoluto (mesmo com o
  Brier Score melhorado, a instabilidade entre anos e a heterogeneidade
  territorial tornam arriscado comunicar "82% de chance" como medida
  uniformemente confiável).
- **Testes**: 21 novos (features de histórico local/momentum sem
  leakage e sem `inf`/`NaN` por divisão por zero; diagnóstico de
  drift/lift; ranking sem olhar o futuro do próprio episódio; calibração
  determinística; métricas operacionais semanais). Suíte total:
  **306/306 passando** (baseline era 285, 0 regressões).
- **Dependência nova**: nenhuma — reutiliza `scikit-learn`
  (`CalibratedClassifierCV`/`FrozenEstimator`, `permutation_importance`,
  já disponíveis na versão já instalada).
- **Não alterado**: Bronze, Silver, Gold, dashboard, dados climáticos,
  definição oficial do target (`estado_alto_risco`),
  `src/ml/baselines.py` (baselines da etapa anterior preservados sem
  mudança). Nenhum deploy, nenhuma integração ao Streamlit, nenhum
  ensemble/deep learning/AutoML, clima mantido fora do modelo principal
  (não revisitado nesta etapa, por instrução explícita).
- **Próximo passo (decisão do usuário)**: investigar bairros com 0% de
  detecção; explorar onset + ranking — **executado na sessão seguinte,
  ver §17**.

## 17. Machine Learning: onset + ranking territorial preventivo (sessão de 2026-08-20, continuação)

Relatório completo em `reports/ml/dengue_onset_ranking_analysis.md` (ver
também `docs/arquitetura_e_pipeline.md` §34). Resumo operacional:

- **Reformulação**: Formulação A (`estado_alto_risco` em t+1, já
  existente, preservada sem alteração) vs **Formulação B** (`src/ml/onset.py`,
  novo): "um novo episódio vai COMEÇAR entre t+1 e t+3?" — só a PRIMEIRA
  semana de cada episódio conta como positivo (reaproveita
  `alert_metrics.construir_episodios`, não reimplementado). Produto
  tratado como **ranking territorial semanal** (Top-K bairros), não
  classificação binária isolada.
- **Onset ≠ continuação**: testado explicitamente
  (`test_onset_nao_marca_semanas_de_continuacao_mesmo_com_horizonte_maior`)
  — se o bairro já está ativo em `t`, isso nunca "descobre" um onset novo
  automaticamente ao continuar em `t+1` (só conta se o episódio atual
  terminar e um novo genuinamente começar, com gap).
- **Horizonte h=3 escolhido sobre h=1**: PR-AUC walk-forward médio 0,314
  (h=3) vs 0,197 (h=1) — mais valor preventivo E melhor sinal bruto.
- **Resultado real** (teste 2023-2025, mesmo split/features/hiperparâmetros
  das etapas anteriores, sem clima): walk-forward do onset h=3 é **mais
  estável** que a Formulação A (desvio-padrão de PR-AUC 0,147 vs 0,201;
  piso 0,108 vs 0,074) — 2022 (não 2023) passa a ser o pior ano (menor
  número de episódios da série). Recall@10 "por episódio" (bairro no
  Top-10 em algum momento das 4 semanas antes do início real): **38,4%**
  (Formulação B) vs 33,2% (Formulação A). Bairros com 0% de detecção:
  7 → **2** (Poço, Ponto de Parada).
- **Achado honesto (não escondido)**: comparado a 3 baselines de ranking
  sem modelo (`casos_t`, `taxa_crescimento_suavizada`,
  `razao_limiar_historico`), o modelo só vence claramente em **Top-5**
  (25,8% vs melhor baseline 19,8%) e **Top-10** (38,4% vs 35,8%) — em
  **Top-15/20 os baselines simples empatam ou SUPERAM o modelo**
  (Recall@20: baseline "crescimento recente" 63,2% vs modelo 57,6%). O
  valor de ML se concentra no cenário operacional mais restritivo
  (poucos bairros priorizáveis por semana).
- **Achado novo — disparidade regional**: Recall@20 por RPA varia de
  **74,1% (RPA 5) a 33,8% (RPA 6)** — não investigado a fundo. IPSEP
  (RPA 6, bairro de volume substancial já flagado nas etapas anteriores)
  melhora de 0% para 16,7% de detecção, mas continua entre os piores
  (posição mediana 39ª de ~94).
- **Achado crítico para o desafio**: separando episódios que ocorrem
  logo após atividade recente ("recaída") dos que ocorrem após período
  de baixa ("antecipação genuína") — **antecipação genuína é o cenário
  mais comum (762/920 episódios, 82,8%) E o mais difícil** (Recall@20
  53,8% vs 76,0% em recaídas). É exatamente o cenário mais relevante
  para o objetivo do desafio (detectar o INÍCIO de algo novo).
- **Persistência do sinal é fraca**: só 8,3% dos episódios têm 2+ semanas
  CONSECUTIVAS de destaque no Top-10 antes do início — a maioria é um
  sinal de 1 semana isolada. Estabilidade do ranking semana a semana
  (Jaccard): 0,23 (Top-5) a 0,40 (Top-20) — lista muda de forma
  substancial semana a semana.
- **Grandes episódios têm desempenho PIOR sob ranking competitivo**
  (Recall@20 51,1% vs 57,6% geral) — ao contrário do achado da etapa
  anterior sob classificação binária (79% de detecção). Explicação:
  ranking é relativo entre os 94 bairros na mesma semana; epidemias
  grandes tendem a elevar vários bairros simultaneamente, "competindo"
  entre si pelo Top-K.
- **Classificação: B — existe valor, mas as limitações ainda são fortes.
  Decisão preservada: NÃO integrar ao dashboard.** Se/quando integrado,
  mostrar score/ranking, não probabilidade (mesmo com a calibração já
  melhorada na etapa anterior) — a instabilidade semanal do ranking e a
  fraqueza no cenário de antecipação genuína tornam mais honesto
  comunicar posição relativa que uma % de confiança.
- **Bug real corrigido**: `alert_metrics.construir_episodios` devolvia
  um DataFrame SEM NENHUMA COLUNA quando não havia episódios (histórico
  totalmente indefinido) — `pd.DataFrame([])` sem `columns=` explícito.
  Corrigido com lista de colunas fixa, encontrado ao testar onset com
  histórico curto antes de afetar qualquer resultado real.
- **Testes**: 17 novos (definição de onset — só 1ª semana conta, episódio
  já ativo não vira onset novo, gap conta como novo evento, leakage
  adversarial, dois bairros não se misturam; Precision@K, estabilidade
  de ranking Jaccard 0/1, persistência consecutiva no Top-K). Suíte
  total: **317/317 passando** (baseline era 306, 0 regressões).
- **Dependência nova**: nenhuma.
- **Não alterado**: Bronze, Silver, Gold, dashboard, dados climáticos,
  Formulação A completa (`src/ml/target.py`, `dataset.py::montar_dataset`
  — preservada intacta como referência comparativa, conforme instrução
  explícita), `src/ml/baselines.py`. Nenhum deploy, nenhuma integração ao
  Streamlit, nenhuma categoria de risco (verde/amarelo/vermelho), clima
  não revisitado.
- **Próximo passo (decisão do usuário, nada iniciado)**: investigar a
  disparidade regional (RPA 6/IPSEP); investigar por que "antecipação
  genuína" é tão mais difícil que "recaída"; considerar um ranking
  híbrido modelo+`razao_limiar_historico` para robustecer Top-15/20. Só
  depois disso, reconsiderar página experimental no dashboard.

## 18. Validação estatística da evidência do ranking (sessão de 2026-08-20, continuação)

Relatório completo em `reports/ml/dengue_ranking_evidence_validation.md`
(ver também `docs/arquitetura_e_pipeline.md` §35). **Etapa de avaliação, não de melhoria**: nenhum
retreino exploratório, feature, algoritmo, tuning, target ou hiperparâmetro
foi alterado. **A pesquisa de ML desta versão está encerrada aqui.**

- **Candidato congelado `dengue_onset_ranking_candidate_v1`**: onset h=3,
  38 features (sem clima), `HistGradientBoostingClassifier`
  (`max_depth=4`, `lr=0.1`, `max_iter=150`), seeds 42, split 2013-2019 /
  2020-2022 / **teste 2023-2025 (14.476 linhas)**, 920 episódios reais em
  93 bairros. **Reprodutibilidade verificada**: duas execuções na mesma
  sessão devolveram resultado idêntico campo a campo.
- **Metodologia**: bootstrap percentil (2.000 reamostragens, seed 42) com
  unidade de reamostragem = **episódio** (nunca linha semanal — semanas do
  mesmo episódio não são independentes); delta modelo × baseline sempre
  **pareado** (mesmos índices reamostrados nos dois lados, mesmo conjunto
  de episódios); sensibilidade por **cluster `bairro`** e por
  **cluster `bairro × ano`** (reamostra clusters inteiros).
- **Resultado central (restringe a leitura da etapa anterior)**: o ganho
  do modelo é estatisticamente defensável **só em K=5** (+5,98 pp, IC
  [+2,83; +9,13], e IC>0 também nos dois esquemas de cluster). Em **K=10 o
  IC cruza zero** (+2,61 pp, IC [−0,76; +5,98]) — o "38,4% vs 35,8%" da
  etapa anterior **não se sustenta como diferença**. Em **K=20 o modelo é
  significativamente PIOR** que o baseline `crescimento_recente` (−5,54
  pp, IC [−10,11; −1,30]).
- **Por ano**: Δ@5 positivo nos 3 anos (+1,7 / +5,7 / +7,6 pp) — ganho
  consistente em sinal. Δ@10 **negativo em 2023 e 2024, positivo só em
  2025**; o leave-one-year-out confirma: excluir 2025 **inverte o sinal**
  de Δ@10 (−1,72 pp), enquanto Δ@5 permanece +4,8 a +6,6 pp excluindo
  qualquer ano. **K=10 depende de um único ano; K=5 não.**
- **Territorial**: RPA 5 Recall@10 59,4% (n=197) × RPA 6 22,97% (n=74).
  Zero detecção em Top-20: **2 bairros** (POÇO n=8, PONTO DE PARADA n=3);
  em Top-10: 16 bairros (98 episódios). **Amostra pequena está
  praticamente descartada como explicação**: 93/94 bairros têm episódio,
  só 1 tem N ≤ 2 (mediana 9). IPSEP: 6 episódios, **0 em Top-10**, melhor
  posição mediana **39ª de ~94** → limitação sistemática, não ruído.
- **Grandes episódios (top 10%, n=92)**: Recall@10 30,4% — **pior** que a
  média (38,4%), o inverso do que a classificação binária sugeria (~79%).
  Ranking é relativo: numa epidemia grande vários bairros competem pelo
  mesmo Top-K.
- **Antecipação genuína (762/920 = 82,8%) × recaída (158)**: Recall@10
  33,5% vs 62,0%, **ICs sem sobreposição em nenhum K**; posição mediana
  18,5ª vs 6ª. O cenário mais relevante para a Prefeitura é o pior.
- **Lead time (353 episódios detectados @10)**: mediana 2 semanas (IC
  [2,3]), média 2,39, p25/p75 1/3, ≥2 semanas 69,1%, ≥3 semanas 45,6%.
  `% ≥1 semana = 100%` **por construção** (janela `[inicio-4, inicio-1]`
  — destaque na própria semana de início nunca conta).
- **Carga operacional** (unidades separadas — episódio × priorização):
  Top-5 antecipa 237/920 episódios com 770 priorizações, das quais
  **65,5% não precedem episódio**; Top-10 antecipa 353/920 com 70,1% de
  priorizações sem episódio futuro. **Estabilidade do Top-10**: Jaccard
  médio 0,294 (mediano 0,25) em 153 pares consecutivos — só ~2-4 dos 10
  bairros permanecem de uma semana para a seguinte.
- **Claims**: "prevê surtos" e "reduz incidência" = **NÃO PERMITIDOS**.
  "Ganho sobre regras simples em Top-10" = **NÃO PERMITIDO** (IC cruza
  zero) — só vale reescrito para **Top-5**. "Identifica antecipadamente
  bairros prioritários" e "pode apoiar priorização preventiva" =
  **permitidos com ressalva** (período, K, taxa real e limitações
  explícitas). Nunca usar "previsão oficial", "probabilidade real de
  surto", "% de chance", categorias verde/amarelo/vermelho — exibir
  **posição/ranking**, nunca probabilidade como confiança absoluta.
- **Classificação: B — evidência sugestiva, mas ainda incerta.**
- **Decisão de produto: SIM como funcionalidade experimental, FORA do
  dashboard público.** A decisão preservada continua valendo: as 7 páginas
  do *Recife Alerta* seguem intactas. A visualização técnica é um **app
  separado** — `streamlit run tools/model_validation_app.py` — escolhido
  em vez de `dashboard/pages/8_*.py` porque é a alternativa com menor
  risco de confusão entre material técnico e produto operacional. A página
  abre com "Validação experimental — não representa ferramenta operacional
  de previsão", **só lê artefatos de backtest** (`reports/ml/evidence_*`),
  nunca treina, nunca prevê futuro, nunca mostra probabilidade
  operacional.
- **Módulos**: `src/ml/evidence_validation.py` (bootstrap por episódio/
  cluster, delta pareado, agregação por grupo, leave-one-group-out, carga
  de priorização, série de Jaccard), `src/validate_dengue_onset_ranking_evidence.py`
  (entry point estatístico), `src/plot_evidence_validation.py` (9 figuras
  A-I, matplotlib `Agg`, separado da análise), `tools/model_validation_app.py`.
- **Testes**: 25 no total para esta etapa (11 novos nesta sessão: carga de
  priorização incluindo alvo indefinido nunca forçado a 0, Jaccard
  idêntico/disjunto/lacuna e coerência com `estabilidade_ranking`,
  contrato do dataset da visualização técnica, geração das 9 figuras sobre
  artefatos sintéticos). Suíte total: **342/342 passando** (baseline era
  331, 0 regressões).
- **Dependência nova**: nenhuma.
- **Não alterado**: Bronze, Silver, Gold, clima, dashboard público
  (7 páginas), target, features, modelo, hiperparâmetros,
  `src/ml/baselines.py`. Nenhum deploy, nenhuma previsão futura, nenhuma
  categoria de risco.
- **Comandos**:
  ```bash
  python -m src.validate_dengue_onset_ranking_evidence   # estatistica (seed 42)
  python -m src.plot_evidence_validation                 # figuras A-I
  streamlit run tools/model_validation_app.py            # visualizacao tecnica
  ```
- **Próximo passo (decisão do usuário)**: se o caminho for produto/
  submissão — página experimental de priorização retrospectiva, publicar o
  Streamlit e preparar material para a Prefeitura, usando **apenas** os
  claims permitidos e a frase da seção 13 do relatório. Qualquer mudança
  de modelo/feature/target cria **nova versão** e exige nova validação.

## 19. Etapa de produto: Recife Alerta robusto e demonstrável (sessão de 2026-08-21)

Documentação para gestão em `reports/product/` (7 arquivos). Relatório de
auditoria: `reports/product/product_hardening_report.md`. O antigo
`README.md` (1118 linhas técnicas) virou `docs/arquitetura_e_pipeline.md`;
o `README.md` novo é documento de produto.

**Auditoria inicial** (commit `b6c7b92`, working tree limpo): a máquina
**não tinha nenhuma dependência do projeto instalada** — nem `pytest`. Foi
criado `.venv` e instalado `requirements.txt` antes de qualquer alteração;
linha de base confirmada em **342/342 testes**. Suíte final: **532/532**.

### 19.1 Clima em grade 2013-2025 (investigação + incorporação)

Relatório: `reports/climate_source_analysis/gridded_climate_investigation.md`.
A investigação ERA5/CHIRPS **não existia** antes desta sessão (só uma
recomendação em §13). Quatro candidatas testadas por HTTP real:

- **ERA5/ERA5-Land via Open-Meteo Archive**: escolhida. Público, sem chave,
  2013-2025 completo, ~2 s por requisição multi-ponto.
- **CDS/Copernicus direto**: exige credencial, indisponível aqui.
- **CHIRPS (0,05°)**: diretório acessível, descartada por custo de ingestão
  (GeoTIFF global diário + GDAL/rasterio).
- **NASA POWER**: funciona, descartada por resolução (0,5° × 0,625°).

**Achado de provenância medido**: o provedor **não serve precipitação para
o modelo `era5_land`** (nulo em toda a janela). Logo precipitação vem de
`era5` (0,25°) e temperatura/umidade de `era5_land` (0,10°) — duas grades,
modeladas explicitamente (`grade` é parte da chave). O modelo "seamless"
**não é usado** (misturaria as duas sob um rótulo único).

**Limitação central, medida**: os centroides dos 94 bairros ocupam 0,1774°
de latitude por 0,1080° de longitude. Resultado: **2 células ERA5** e **3
células ERA5-Land** para os 94 bairros; **mediana de 2 valores distintos de
precipitação por semana entre todos os bairros**; distância mediana
centroide-para-centro-da-célula 8,06 km (máx. 17,29 km), contra 1,431 km da
Estratégia A com estações. **A grade informa *quando* chove, não *onde*
dentro do Recife.**

**Validação contra o CEMADEN** (3.903 linhas bairro x semana com as duas
fontes): Pearson 0,6084 · Spearman 0,5507 · MAE 17,6 mm · viés -5,68 mm ·
razão dos totais 0,7144 (subestima ~29%) · recall de semana chuvosa
(>=20 mm) 64,21%. Agregado da cidade: Pearson 0,7787 · Spearman 0,8626
(n=72 semanas). Por bairro: Pearson mediano 0,7123 (mín. -0,0022, n=71).
**Classificação: B — utilizável com limitações.**

**Módulos**: `src/clients/gridded_climate_client.py`,
`src/silver/schema_climate_grade.py`, `src/silver/climate_grade.py`,
`src/silver/pipeline_climate_grade.py`,
`src/ingestion/gridded_climate_ingestion.py`, `src/gold/clima_grade.py`,
`src/build_climate_grade.py`, `src/enrich_gold_clima_grade.py`,
`src/investigate_gridded_climate.py`, `src/eda/clima_grade.py`.

**Gold 1.0 para 1.1**: 191.478 linhas (inalteradas), 31 para 46 colunas.
Cobertura climática **6,1151% para 100%** das linhas, 2013-2025. Verificado
programaticamente que **todas as 31 colunas pré-existentes ficaram
idênticas valor a valor** (só `versao_schema_gold` mudou). Idempotência
verificada: duas execuções seguidas produzem tabela idêntica, exceto os dois
metadados de execução.

**Por que o enriquecimento é uma transformação da Gold sobre a Gold, e não
um pipeline paralelo**: a Silver anterior só existiu dentro de um `moto`
efêmero de outra sessão. Reconstruir a cadeia hoje mudaria a janela do
backfill CEMADEN (sempre "últimos N dias a partir de agora"), alterando as
colunas de estação e **invalidando todos os números de ML já validados**.
A rota canônica (Bronze/Silver/Gold no MinIO) está implementada e
disponível com `--com-datalake` / `--destino minio`.

Silver em grade versionada localmente em `data/silver/clima_grade/`
(23.765 linhas, 5 células, 2012-12-30 a 2026-01-03, 128 KB) — é o que
permite reconstruir a Gold sem infraestrutura.

### 19.2 Experimento controlado de clima no ML (resultado negativo, publicado)

Relatório: `reports/ml/dengue_ranking_clima_experiment.md`.
`python -m src.experiment_dengue_ranking_clima`.

A x B: mesmas 58.562 linhas, mesmo split, mesmo algoritmo, mesmos
hiperparâmetros; única diferença = 8 features climáticas em grade (38 para 46).
**Critério declarado antes de rodar**: incorporar só se Recall@5 tiver IC
que não cruza zero E sinal positivo em todos os anos.

| K | Delta B-A | IC episódio | IC cluster bairro | IC cluster bairro x ano |
|---|---|---|---|---|
| 5 | **-0,11 pp** | [-2,28; +2,07] | [-2,46; +2,23] | [-2,47; +2,37] |
| 10 | +2,83 pp | [+0,43; +5,33] | [+0,21; +5,34] | [+0,40; +5,29] |
| 15 | +3,37 pp | [+0,98; +5,87] | [+0,74; +5,92] | — |
| 20 | +1,96 pp | [-0,11; +4,24] | [-0,44; +4,22] | — |

Por ano em K=5: 2023 +1,71 · 2024 **-1,48** · 2025 +0,76 pp.
**Decisão: NÃO incorporar** (as duas condições do critério falharam).

**Verificação valiosa**: o modelo A reproduziu o candidato congelado **campo
a campo** sobre a Gold 1.1 (delta@5 = +0,059783, ICs idênticos aos de §18) —
prova de que o enriquecimento climático não alterou a evidência validada.

**Achado secundário registrado, não usado**: em K=10 o delta B-A é positivo
com IC acima de zero nos três esquemas e em todos os anos; e com clima o
modelo passa a vencer o baseline também em K=10 (+5,43 pp, IC [+1,96;
+9,02]). Hipótese: a grade não diferencia bairros, mas diferencia
**semanas**. Candidato a `..._candidate_v2`, exigiria validação completa.

### 19.3 Freshness, portões, atomicidade, healthcheck, orquestração

- `src/freshness.py` — metadados por conjunto (`dataset`, `fonte`,
  `ultima_atualizacao_fonte`, `data_maxima_evento`, `semana_epi_maxima`,
  `pipeline_executado_em`, `atraso_dias`, `status`). **Nada é `ATUAL` por
  omissão.** Limiares: epidemiologia 120 d (a fonte declara `trimestral`),
  território 1095 d, clima 30 d.
- **Portão da projeção atual**: `LIMIAR_SEMANAS_PROJECAO_ATUAL = 4`
  (horizonte 3 + 1 de folga). Estado real: `current_projection_available =
  false`, `reason = epidemiological_data_stale`, 32 semanas de atraso.
  `latest_priority.parquet` **não é gerado** e é **removido** se existir.
- `src/quality_gates.py` — 14 portões críticos + severidade `AVISO`.
  Crítico bloqueia a publicação e preserva o artefato anterior.
  Testado que **precipitação toda nula não é erro** (`missing != 0`).
- `src/utils/io_atomico.py` — temporário no mesmo diretório, validar,
  `os.replace`. Cobre Parquet/JSON/CSV/texto.
- `src/healthcheck.py` — `PASS`/`WARN`/`FAIL`, saída 1 só em `FAIL`.
  Estado atual: **13 PASS · 1 WARN · 0 FAIL** (o WARN é o atraso da fonte).
  Verificação-chave: `latest_priority.parquet` presente com portão fechado
  (ou ausente com portão aberto) é **`FAIL`**.
- `src/logging_config.py` — log estruturado (JSON com
  `RECIFE_ALERTA_LOG_JSON=1`), `FiltroRedacao` que redige chaves sensíveis,
  credencial em URL, CPF e CNS **na mensagem já formatada** (cobre valor
  vindo de argumento de formatação), `registrar_resultado_fonte` e `etapa`
  (duração). `configurar_logging` é idempotente (vários entry points no
  mesmo processo não duplicam handler).
- `src/update_recife_alerta.py` — orquestra ingestão, validação,
  transformação, exportação e healthcheck. **Nunca treina.** ~23 s.
  Flags `--sem-rede` e `--com-datalake`. Grava
  `dashboard/data/_ultima_atualizacao.json`.
- `src/ml/artifacts.py` — metadados obrigatórios (`model_version`,
  `feature_schema_version`, `feature_names`, `trained_until`,
  `target_definition`, `horizon`, `git_commit`, `created_at`,
  `data_cutoff`, `cutoff_epi_*`, `sklearn_version`, `gold_schema_version`).
  Carregar **valida** assinatura de features (detecta feature nova E
  reordenação), schema da Gold e major.minor do sklearn — incompatível
  levanta exceção. `caminho_artefato` valida contra `^[a-z0-9_]+$` **e**
  lista permitida (defesa contra path traversal, com testes).
- `src/train_priority_model.py` (separado) e
  `src/generate_priority_artifacts.py` (não treina; gera backtest de
  14.476 linhas / 154 semanas + `_priority_status.json` +
  `_evidence_summary.json`).
- `artifacts/models/**/*.joblib` **não versionado** (pickle executa código;
  e não é portável entre versões maiores do sklearn). `metadata.json` é
  versionado.

### 19.4 Dashboard modernizado (9 páginas)

`dashboard/app.py` com `st.navigation` em **4 grupos** ("Situação
observada", "Apoio à decisão", "Contexto climático", "Transparência"), para
que a natureza do conteúdo seja óbvia antes da leitura.

Páginas: `1_inicio`, `2_situacao_epidemiologica`, `3_mapa_territorial`,
`4_bairros_prioritarios`, `5_evolucao_historica`, `6_clima`,
`7_clima_dengue`, `8_priorizacao_experimental`, `9_qualidade_limitacoes`.
As 7 páginas antigas foram **substituídas** (não coexistem).

Novos componentes: `tema.py` (CSS institucional, cartões, formatação
pt-BR), `atualizacao.py` (faixa de freshness), `pagina.py` (preâmbulo
comum — garante que **nenhuma página esqueça a faixa de atualização**),
`erros.py` (fronteira de erro por seção), `graficos_produto.py` (13
gráficos novos). Nova camada analítica: `src/eda/prioridade_observada.py`
(volume recente, aceleração, razão contra o próprio histórico — sazonal, só
anos anteriores) e `src/eda/clima_grade.py`.
Validação de entrada: `dashboard/utils/validacao.py` (domínio **real** do
dataset carregado, nunca lista fixa no código).

**Decisões de UI que não devem ser revertidas**:

- Sem escala verde-amarelo-vermelho em nenhum lugar — cor de semáforo
  comunicaria categoria de risco, que a validação não sustenta. Teste
  automatizado verifica que a paleta não tem verde de semáforo.
- "Conclusivo x inconclusivo" no gráfico de delta é marcado por **padrão de
  preenchimento e rótulo textual**, não só por cor (acessibilidade).
- A página experimental publica as 4 faixas de K com a leitura correta de
  cada uma, **inclusive a faixa em que a regra simples é melhor**.
- O backtest mostra uma tabela dedicada de **episódios perdidos** — mostrar
  só acertos daria leitura falsa.

**Bug real encontrado pelo teste de navegador**: conflito de assinatura do
Plotly (`title` em `LAYOUT_PADRAO` mais `title` na chamada) fazia 6
gráficos falharem, e a fronteira de erro os transformava em mensagem
amigável — ou seja, **o painel "funcionava" com gráficos faltando**.
Corrigido (`title_font` no layout, `title_text` nas chamadas de
`update_layout`, `title` nas de `plotly.express`) e coberto por
`tests/test_dashboard_graficos.py`, que exercita **os 23 construtores de
gráfico**.

### 19.5 Segurança e verificação

- Auditoria de segredos: **nada versionado, nada no histórico do Git**.
- Corrigidos: `.env.example` com `admin`/`admin123` para placeholders;
  `docker-compose.yml` de `${VAR:-admin}` para `${VAR:?}` (aborta sem
  credencial); MinIO restrito a `127.0.0.1`; `.gitignore` reescrito.
- `pip-audit`: `pytest 8.4.2` com `PYSEC-2026-1845`, elevado para
  `>=9.0.3,<10`. **Zero vulnerabilidades** nos dois arquivos de requisitos.
  `dashboard/requirements.txt` permanece com 5 pacotes.
- `bandit` (18.419 linhas): 6 achados para **3**, todos LOW, todos
  investigados. Corrigidos: B113 (timeout obrigatório no `InmetClient`),
  B101 (`assert` para `raise`), B607 (`shutil.which` + caminho absoluto).
  Remanescentes documentados como falso positivo / aceitos.
- `scripts/verificar_deploy_dashboard.py` reescrito: sintaxe, **imports
  proibidos em runtime**, caminhos absolutos, segredos, artefatos,
  tamanho, `.gitignore` e **privacidade de todos os artefatos publicados**
  (19 nomes de coluna). Resultado: **APTO**, 0 bloqueios, 3,72 MB.
- `scripts/testar_dashboard_navegador.py` (Selenium; `selenium` **não** vai
  para `requirements.txt`): 9 páginas x 3 larguras = 27 cargas, 0 exceções,
  0 seções degradadas, 0 overflow horizontal. Carregamento inicial ~285 ms /
  11 KB; troca de página 0,93 a 3,82 s.

### 19.6 Respostas explícitas

- **Há dados de 2026?** **NÃO.** CKAN consultado ao vivo: 49 recursos, os
  mais recentes de casos são de 2025. `SEM_NOT` vai até `202553`;
  `metadata_modified` = 2026-05-20; periodicidade declarada `trimestral`.
  Nenhuma ingestão foi feita porque não há nada novo. Achado extra:
  `SEM_PRI` tem valores impossíveis em 2025 (`195002`, `196834`) — o
  projeto usa `SEM_NOT`, não afetado; e há **revisão retroativa**
  (chikungunya 2021 alterado depois de criado).
- **Há dado atual suficiente para priorização do período atual?** **NÃO**
  (32 semanas de atraso contra o limite de 4). Só backtest.
- **Clima histórico 2013-2025 defensável?** **PARCIAL** — reanálise
  ERA5/ERA5-Land, 100% de cobertura temporal, mas quase nenhuma resolução
  espacial (2 células) e subestimação de ~29%.
- **Dashboard tecnicamente apto a deploy público?** **SIM**. **Deploy
  realizado?** **NÃO** — falta conta do Streamlit Community Cloud e
  repositório GitHub (pendência humana).
- **Classificação: produto B** (demonstrável com pendências pequenas, ambas
  externas ao código) · **módulo ML A** (experimental demonstrável).

### 19.7 Próximos passos (decisão do usuário, nada iniciado)

1. Publicar no Streamlit Community Cloud (credencial/repositório pendentes).
2. Investigar a disparidade da RPA 6 / IPSEP (limitação quantificada, causa
   não investigada).
3. Considerar `dengue_onset_ranking_candidate_v2` com clima em Top-10 —
   **só** com o protocolo completo de validação.
4. CHIRPS (0,05°, ~11 células) se houver infraestrutura para ingestão raster.
5. Reexecutar `pip-audit` periodicamente.

> Nota: entre §19 e esta seção houve sessões não documentadas aqui (V2 de
> incidência, reconstrução populacional Gold 1.2, exportação Power BI) —
> working tree não commitado no início desta etapa. Ver
> `reports/population/`, `reports/ml/incidence_based_v2_*` e
> `powerbi/README.md` para o que já existia antes desta sessão.

## 20. Versão final de demonstração: filtros, clima×arboviroses, projeção 2026, apoio à decisão, Figma, Power BI (sessão de 2026-08-21, continuação)

Etapa de produto pedida explicitamente com regra de parada e proibições
(não reabrir tuning V1/V2, não misturar projeção com priorização
territorial, não afirmar causalidade climática, não aplicar ML de dengue a
Zika/Chikungunya, não prever por bairro sem validação). **Todas
respeitadas — nem `src/ml/` nem os artefatos/relatórios do candidato
`dengue_onset_ranking_candidate_v1` foram tocados**, verificado por dois
testes de isolamento dedicados (`tests/test_ml_incidence_v2_v1_intacto.py`,
pré-existente, e `tests/test_forecast_v1_intacto.py`, novo).

**Baseline inicial**: 629/629 testes (o repositório real do projeto vive em
`projeto_arbovirose_recife/`, subpasta com git próprio — não a raiz do
repo externo). **Suíte final: 737/737**, 0 regressões.

### 20.1 Verificações ao vivo (item 10/13 do pedido)

- **Casos 2026**: CKAN (`dados.recife.pe.gov.br`) reconsultado — 58
  recursos, todos rotulados até 2025; metadado do dataset tocado em
  2026-05-20 mas nenhum recurso 2026 existe. Existe um boletim estadual
  (SES-PE) com números de 2026 para Pernambuco inteiro, fonte diferente
  (estadual, sem bairro), fora de escopo. **Confirma §19.6: sem observado
  2026.**
- **População municipal 2026**: estimativas IBGE mais recentes têm
  referência 01/07/2025; nenhuma estimativa oficial municipal 2026
  encontrada. **Projeção 2026 é sempre em casos, nunca em incidência.**

### 20.2 Filtro global de agravo

A maior parte já existia (`src/eda/filtros.py::aplicar_filtros`,
`dashboard/components/filtros_sidebar.py::renderizar_filtros`). Adicionado:
`renderizar_filtros(..., permitir_todas: bool = True)` — quando `False`,
remove a opção "Todas as arboviroses" do seletor (clima e projeção 2026,
onde somar os 3 agravos não tem interpretação válida). `total_arboviroses`
passou a calcular também `incidencia_100k_combinada` (uma única divisão
sobre os agregados, nunca soma de taxas). Página 1 (Início) ganhou filtro
de agravo real (antes fixo em DENGUE) e cartão de incidência da cidade.
Página 8 (Priorização experimental) ganhou o aviso fixo **"Priorização
experimental atualmente validada apenas para dengue."** — ela não tem
seletor de agravo, então o aviso é incondicional.

### 20.3 Clima × Arboviroses — defasagem real (`src/eda/associacao_climatica.py`)

Módulo novo, Recife total apenas (a grade ERA5/ERA5-Land só resolve 2-3
células para os 94 bairros — nenhuma função aceita bairro/RPA). Defasagem
**deslocada de verdade** (`alvo[t]` × `clima[t-k]`, `.shift(k)`, k=0..12,
Spearman + p-valor + n), diferente da janela cumulativa já publicada
(`src/eda/correlacao.py`/`clima_grade.correlacoes_lag_grade`, preservada
intacta). Dessazonalização (resíduo vs. média histórica da mesma semana
epi) compara correlação bruta vs. ajustada. `resumo_textual` escolhe o lag
de maior `|Spearman|` **entre os confiáveis (n≥30)**, nunca por p-valor, e
nunca afirma causalidade. Casos e incidência calculados e reportados
separadamente. Página `7_clima_dengue.py` (nav: "Clima × Arboviroses")
reorganizada em 3 abas (janelas cumulativas / defasagem real / bruta vs.
ajustada), filtro com `permitir_todas=False`. Relatório:
`reports/analysis/climate_arbovirus_association.md` (gerado por
`python -m src.generate_climate_arbovirus_report`, números reais).

**Achado real (Dengue × Precipitação)**: melhor lag = 2 semanas
(Spearman≈0,17 casos / 0,18 incidência), cai para perto de zero (até
negativo) após dessazonalizar — sugere que a associação bruta é
majoritariamente sazonalidade compartilhada, não um sinal que sobreviva à
remoção da sazonalidade.

### 20.4 Forecast 2026 (`src/forecast/`, isolado de `src/ml/`)

Pacote novo: `dataset.py` (série semanal Recife-total por agravo, com
guarda `garantir_sem_observado_futuro` — recusa qualquer
`ano_epidemiologico` além de `ULTIMO_ANO_HISTORICO_VALIDADO=2025`),
`baselines.py` (seasonal naive, média histórica da semana, tendência +
sazonalidade), `modelos.py` (ETS/Holt-Winters via `statsmodels`, único
método adicional — decisão do usuário, sem SARIMA/deep learning/AutoML),
`intervalos.py` (banda 80%/95%, empírica ou simulação nativa do ETS),
`backtest.py` (walk-forward 2022→23/2023→24/2024→25; MAE, RMSE, MASE vs.
seasonal naive, erro de pico e de timing, cobertura de intervalo),
`selecao_modelo.py` (mediana do MASE, desempate por timing — nunca olhando
2026), `projecao_2026.py` (orquestrador).

Entry point `python -m src.generate_forecast_artifacts` escreve
`dashboard/data/_forecast_2026.parquet` +
`_forecast_2026_metadata.json` — a página Streamlit (`10_projecao_2026.py`,
nova) só lê, nunca treina em tempo real (mesma convenção da página
experimental). `python -m src.generate_forecast_report` gera
`reports/forecast/arbovirus_2026_projection.md`.

**Resultado real**: modelo vencedor por agravo — Dengue: `média histórica
da semana` (MASE mediano 0,613); Zika e Chikungunya: `seasonal naive`
(MASE 1,0 — nenhum modelo mais complexo superou o baseline mais simples
nesses dois agravos). **Achado honesto**: no backtest de 2025, o erro de
timing do pico foi de 22 (dengue/zika) a 30 semanas (chikungunya) — anos
com padrão sazonal atípico, documentado no relatório, não escondido.
Nenhuma incidência 2026 é publicada (sem população 2026 oficial).

**Cobertura de intervalo** (`backtest.py::cobertura_leave_one_fold_out` —
adicionada após o primeiro rascunho do relatório, quando notei que o item
14 do pedido explicitamente pedia essa métrica e ela só existia testada
isoladamente, nunca calculada no pipeline real): cada dobra é avaliada com
a banda construída a partir dos erros das OUTRAS dobras (nunca da própria,
para não inflar a cobertura artificialmente). Resultado real 2023: Dengue
54%/58% (80%/95%) — banda subestima a incerteza real nesse ano; Zika
92%/100%; Chikungunya 79%/100%. Com só 3 dobras é uma leitura aproximada,
documentada como tal no relatório e na página.

### 20.5 Apoio à decisão

Página nova `11_da_informacao_a_acao.py` ("Da informação à ação"):
9 perguntas → indicador → decisão apoiada (item 21 do pedido), aviso fixo
"apoia/prioriza/informa/contextualiza — nunca ordena/substitui/garante/
diagnostica". Relatório equivalente:
`reports/product/prefeitura_decision_support.md`.

### 20.6 Modernização visual (item 26 — todas as 9 páginas + 2 novas)

Auditoria confirmou que o sistema de design (`dashboard/components/tema.py`)
já era consistente na maior parte do painel (sessões anteriores já tinham
aplicado bem os primitivos de cartão/cabeçalho). Correções reais: 2 usos
remanescentes de `st.metric` substituídos por `linha_de_cartoes`; página 9
(`9_qualidade_limitacoes.py`) tinha uma afirmação obsoleta ("incidência não
é calculada em nenhuma página" — falsa desde a Gold 1.2) corrigida, com
`tipo_populacao`/MAPE explicados; tabela de afirmações permitidas da página
9 ganhou linhas sobre associação climática e projeção 2026. Nova tag visual
`etiqueta="projecao"` em `tema.py::cabecalho_pagina` (cor própria, roxa,
nunca confundida com a tag "experimental" — projeção estatística sazonal e
priorização territorial são coisas diferentes, marcadas diferente de
propósito).

### 20.7 Power BI (item 28 — extensão, não documentação-só)

Duas fact tables novas em `src/export_powerbi_dataset.py`:
`fact_associacao_climatica` (agravo×variável×lag×tipo de série×ajustada,
recalculada de verdade a partir de `src/eda/associacao_climatica.py`,
**sem** chave de bairro/tempo — sempre incluída, só depende da Gold) e
`fact_projecao_2026` (agravo×semana, observado+projetado, **opcional**:
degrada graciosamente se `_forecast_2026.parquet` não existir, diferente
do "fail closed" das 3 fontes originais). `dim_tempo` estendida para
cobrir as semanas de 2026 quando a projeção está presente.
`validar_star_schema` ganhou checagens para as duas tabelas novas
(FK, chave duplicada, `lag_semanas` em 0-12, sem coluna de
probabilidade/risco). **Execução real**: 9 tabelas, `fact_associacao_climatica`
780 linhas, `fact_projecao_2026` 2.193 linhas, `dim_tempo` 679→731 semanas,
`integridade_referencial: "ok"`. `powerbi/README.md` atualizado. Nenhum
`.pbix` gerado (explicitamente fora de escopo).

### 20.8 Especificação Figma (item 23-24, 27 — documentação pura)

`reports/product/figma_specification.md` (≈590 linhas): 8 telas (Home,
Situação Epidemiológica, Mapa Territorial, Histórico, Clima ×
Arboviroses, Projeção 2026, Priorização Experimental, Qualidade e
Transparência), cada uma com objetivo/KPIs/gráficos/filtros/textos/estados
vazios/avisos/interação, mapeadas explicitamente às 11 páginas Streamlit
reais. Seção "Figma ≠ Streamlit" explícita; paleta semente = tokens reais
de `tema.py`, não uma identidade nova; nenhuma identidade visual oficial
da Prefeitura usada. Elementos propostos sem código real por trás
marcados `[conceito — não implementado]` (ex.: hero dinâmico na Home,
drill-down por clique no mapa, toggle casos/incidência na projeção).

### 20.9 Testes e arquivos (visão geral desta etapa)

Novos/estendidos: `src/eda/associacao_climatica.py`,
`src/generate_climate_arbovirus_report.py`, `src/forecast/` (7 módulos),
`src/generate_forecast_artifacts.py`, `src/generate_forecast_report.py`,
extensões em `src/export_powerbi_dataset.py`,
`dashboard/pages/10_projecao_2026.py`,
`dashboard/pages/11_da_informacao_a_acao.py`, extensões em
`dashboard/pages/1_*.py`, `2_*.py`, `7_*.py`, `8_*.py`, `9_*.py`,
`dashboard/app.py`, `dashboard/components/{tema,filtros_sidebar,
graficos_produto}.py`, `dashboard/utils/data_loader.py`. Relatórios novos:
`reports/analysis/climate_arbovirus_association.md`,
`reports/forecast/arbovirus_2026_projection.md`,
`reports/product/prefeitura_decision_support.md`,
`reports/product/figma_specification.md`. ~15 arquivos de teste novos
(forecast, associação climática, Power BI, filtros, rotulagem
observado/projetado). Suíte final: **737/737**.

**Não alterado**: `src/ml/` (V1 completo), `src/ml/*_incidencia.py` (V2),
`artifacts/models/dengue_onset_ranking_candidate_v1/`, qualquer arquivo em
`reports/ml/`, hiperparâmetros/target/features do candidato congelado.

**Próximo passo (decisão do usuário, nada iniciado)**: publicar no
Streamlit Community Cloud; considerar levar `fact_associacao_climatica`/
`fact_projecao_2026` para medidas DAX dedicadas (`powerbi/medidas_dax.md`
ainda não foi estendido para as 2 tabelas novas); reavaliar o forecast
quando houver caso observado de 2026 real (backtest atual usa só
2023-2025).
