# Integração CEMADEN — resultados reais

> Execução real, 2026-08-20, contra dados reais (CKAN/INMET/APAC/CEMADEN),
> usando `moto.server` como stub do MinIO (ver CLAUDE.md §9). Segue as
> investigações anteriores:
> `reports/climate_source_analysis/apac_freshness_investigation.md`,
> `reports/climate_source_analysis/alternative_sources_analysis.md` e
> `reports/climate_source_analysis/cemaden_precipitation_endpoint_investigation.md`.

## Objetivo desta etapa

Implementar oficialmente o CEMADEN na arquitetura Bronze → Silver → Estratégia
A → bairro, mantendo APAC e INMET intactos, sem relaxar
`LIMIAR_DIAS_ESTACAO_ATIVA=90`, e validar com dados reais se isso destrava a
cobertura que estava em `0/94` (APAC congelada).

## Endpoints utilizados

- **Cadastro** (WFS): `https://gsc.cemaden.gov.br/geoserver/cemaden_dev/wfs`,
  layer `cemaden_dev:view_pcds_pluviometrica_cemaden`, `CQL_FILTER=uf='PE'`
  — coordenadas reais, sem autenticação.
- **Status**: `https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=PE`
  — lista plana com `idestacao` (numérico) e `tipoestacao` (filtramos `==1`,
  pluviométrica — o endpoint mistura outros tipos de rede).
- **Série horária real**: `https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/{idEstacao}/{horas}`
  — mesmo endpoint que o painel público usa.

Nenhum dos três exige autenticação, CAPTCHA ou cookie/sessão (reconfirmado
nesta sessão).

## Módulos criados/alterados

**Criado**: `src/clients/cemaden_client.py` — `CemadenClient` com
`baixar_cadastro_estacoes`, `baixar_status_estacoes`, `baixar_serie_horaria`
(só HTTP, sem parsing semântico, igual aos outros clientes de clima).

**Alterados** (nenhuma arquitetura paralela — tudo reaproveita o desenho
Bronze/Silver/Estratégia A já existente):

- `src/config.py` / `.env.example`: `CEMADEN_WFS_URL`, `CEMADEN_STATUS_URL`,
  `CEMADEN_HORARIO_URL` (defaults = endpoints reais validados),
  `CEMADEN_HORAS_INGESTAO` (default 48h).
- `src/ingestion/climate_ingestion.py`: `executar_ingestao_cemaden` — baixa
  cadastro+status de PE inteira (2 chamadas baratas) e a série horária só
  das candidatas pluviométricas da **Grande Recife**
  (`MUNICIPIOS_GRANDE_RECIFE = RECIFE, OLINDA, JABOATÃO DOS GUARARAPES,
  CAMARAGIBE, SÃO LOURENÇO DA MATA, PAULISTA, ABREU E LIMA`) — recorte
  pragmático documentado para não gerar ~437 chamadas HTTP por execução;
  município é usado só para decidir *o que vale a pena consultar*, nunca
  para decidir associação bairro-estação (isso continua sendo um join
  geométrico real, ver abaixo).
- `src/silver/schema_climate.py`: `FONTES_CLIMA` agora inclui `"CEMADEN"`;
  novo campo `horas_validas_dia` (nullable) em `COLUNAS_SILVER_CLIMA_DIARIO`
  — quantas leituras horárias válidas formaram o valor diário (permite
  distinguir "24h de zero real" de "cobertura parcial" sem redesenhar o
  schema; populado também para INMET/APAC, não só CEMADEN).
- `src/silver/climate.py`: `transformar_estacoes_cemaden` (junta cadastro +
  status pelo nome normalizado da estação),
  `extrair_observacoes_horarias_cemaden` (parsing robusto da matriz
  `datas`×`horarios`→`acumulados`, tolerante a arrays incompatíveis/nulos),
  `agregar_diario_cemaden` (soma horária→diária, `min_count=1`),
  `transformar_diario_cemaden` (conveniência ponta a ponta).
- `src/profiling/climate_profiler.py`:
  `selecionar_cadastro_status_cemaden_mais_recentes` (cadastro/status:
  padrão "última execução com sucesso", como o INMET — é metadado
  quase-estático) e `listar_todas_series_horarias_cemaden` (série horária:
  padrão "acumula todas as execuções", como a APAC — cada execução cobre
  uma janela recente que se sobrepõe com a anterior).
- `src/silver/pipeline_climate.py`: `_processar_cemaden` — acumula **todas**
  as séries horárias já coletadas, deduplica por (`codigo_estacao`, `data`,
  `hora`) mantendo a leitura da execução mais recente em caso de conflito, e
  só então agrega para diário (dedup por hora, não por dia — evitar isso
  subcontaria dias parcialmente cobertos por execuções diferentes).
- `src/silver/schema_climate_bairro.py` / `src/silver/climate_bairro.py`:
  `FONTE_ELEGIVEL` (uma fonte) virou `FONTES_ELEGIVEIS = ("APAC", "CEMADEN")`.
  **Dois bugs de correção corrigidos como parte desta generalização** (só
  se manifestavam com 2+ fontes, nunca antes): o merge de última leitura e
  o índice de localização física usavam só `codigo_estacao` como chave —
  `codigo_estacao` não é único entre fontes, só dentro de cada uma. Ambos
  agora usam a chave composta `(fonte, codigo_estacao)`. Cobertos por dois
  testes novos de regressão
  (`test_codigo_estacao_colidindo_entre_fontes_nao_contamina_elegibilidade`,
  `test_join_fisico_nao_colide_entre_fontes_com_mesmo_codigo_estacao`).
- `src/ingest_climate.py`: chama `executar_ingestao_cemaden` depois de
  INMET/APAC.

**Nenhuma prioridade explícita entre APAC e CEMADEN foi adicionada** — e
isso é proposital, não uma omissão. `filtrar_estacoes_elegiveis` já exige
leitura real recente em `silver_clima_diario`, nunca metadado de cadastro.
Uma estação "congelada" nunca entra no pool de elegíveis; "escolher a mais
próxima entre as elegíveis" já implementa a regra desejada. Hoje isso
significa CEMADEN na prática (confirmado abaixo, 94/94 bairros usam
CEMADEN), mas se a APAC voltar a ter leitura real, ela volta a competir por
atividade real automaticamente — sem mudar nenhum código. Uma prioridade
hardcoded destruiria essa propriedade. Um teste de regressão prova isso
explicitamente
(`test_estrategia_a_prefere_estacao_ativa_mesmo_com_outra_fonte_mais_perto_porem_inativa`).

## Resultado real da execução (não estimativa — rodado nesta sessão)

### Ingestão Bronze

- INMET: 12 estações de PE (ano 2024), 0 erros (inalterado).
- APAC: instantâneo capturado, 0 erros (continua rodando — não removida).
- **CEMADEN**: cadastro (437 registros PE) + status (531 registros PE,
  todos os tipos de rede) baixados com sucesso. **35 estações
  pluviométricas candidatas na Grande Recife** identificadas
  (`tipoestacao==1` + município na lista) — série horária (48h) buscada
  para as 35, **35/35 com sucesso, 0 erros**.

### Silver — estações

- Cadastro×status: 435 casamentos por nome (de 437 features do cadastro; 2
  sem correspondência pluviométrica no status). **407 válidas, 28
  rejeitadas** — motivo: `codigo_estacao duplicado (mesma fonte)` (duas
  features do cadastro compartilhando o mesmo nome normalizado colidiram no
  mesmo `idEstacao` do status; contabilizado, não descartado
  silenciosamente).
- `silver_estacao_climatica` total: **718 linhas** (12 INMET + 299 APAC +
  407 CEMADEN).

### Silver — clima diário (CEMADEN)

- Das 35 candidatas com série horária buscada, **24 estações produziram ao
  menos 1 dia válido** em `silver_clima_diario` (as demais — como o caso
  "Dois Unidos" já identificado na investigação anterior — não têm nenhuma
  leitura real utilizável apesar de aparecerem no cadastro/status).
- **67 linhas diárias válidas** no total, cobrindo **2026-08-18 a
  2026-08-20** — dados genuinamente atuais (a data do sistema nesta sessão
  é 2026-08-20).
- `horas_validas_dia`: média 14,4, mediana 21, mínimo 2, máximo 24 — reflete
  corretamente dias parciais (bordas da janela de 48h e o dia corrente
  ainda em andamento), sem nunca virar `0`/imputado.

### Elegibilidade (Estratégia A, `LIMIAR_DIAS_ESTACAO_ATIVA=90`, inalterado)

- Candidatas totais (APAC+CEMADEN): **706** (299 + 407).
- **Elegíveis: 24** — todas CEMADEN. As 299 candidatas APAC: 100% excluídas
  por `"ultima leitura ha mais de 90 dias"` (congelada desde 2024-04-09,
  confirmado de novo). Das 407 candidatas CEMADEN: 383 excluídas por
  `"sem leitura em silver_clima_diario"` (a maioria são as ~372 estações de
  PE fora do escopo de busca horária da Grande Recife, mais as poucas
  dentro do escopo sem série real, como "Dois Unidos").

### Estratégia A — resultado final

```
94/94 bairros associados (100.00%)
```

- **Fonte de 100% das associações: CEMADEN** (0 bairros usando APAC —
  resultado emergente do filtro de atividade real, não de uma regra de
  prioridade escrita).
- Estações distintas utilizadas: **16** (de 24 elegíveis).
- Distância: média **1,656 km** | mediana **1,431 km** | p90 **2,848 km** |
  p95 **3,680 km** | máxima **4,632 km** (bairro Tótó) | mínima 0,109 km.
- Bairros com estação própria (fisicamente dentro do bairro): **14/94**.
- Bairros com estação de bairro vizinho: **80/94**.
- Top 3 bairros mais distantes: Tótó (4,632 km, estação 6532 "Ibura"),
  Guabiraba (4,386 km, estação 6529 "Guabiraba" — a própria estação do
  bairro ficou inelegível, sendo substituída pela mais próxima seguinte),
  Coqueiral (4,125 km, estação 6532).
- Estações mais utilizadas: 6536 "San Martin" (18 bairros), 6530 "Morro da
  Conceição" (13), 6535 "Torreão" (12).

Caso ilustrativo real (não hipotético): o bairro **Dois Unidos** (código
396) — mesmo tendo uma estação CEMADEN com esse exato nome fisicamente ali
— foi associado à estação **Nova Descoberta** (0,836 km), porque a série
real da estação "Dois Unidos" não retornou nenhuma leitura utilizável nesta
execução. Isso é a prova em produção de que a decisão de não confiar no
metadado de atividade (`tempo_inatividade`) e validar contra a série real
estava correta — exatamente o comportamento previsto na investigação
anterior.

## Regra de agregação horária → diária

`precipitacao_mm` = soma das leituras horárias válidas do dia
(`min_count=1` — nenhuma leitura válida vira `None`, nunca `0`).
`horas_validas_dia` registra quantas leituras horárias reais formaram esse
total, sem bloquear o pipeline nem inventar uma regra de "cobertura
mínima" — fica disponível para quem consumir a tabela decidir o que fazer
com um dia de cobertura parcial (ex.: Gold, fora de escopo desta etapa).

## Tratamento de missing

Idêntico ao resto do projeto: ausência de leitura horária não participa da
soma (`min_count=1`); zero informado pela fonte permanece `0`. Nenhum
`fillna(0)` foi usado em nenhum ponto do código novo.

## Idempotência e deduplicação

Cada execução de ingestão cobre uma janela recente (48h por padrão) que se
sobrepõe com a anterior — a Silver acumula **todas** as séries horárias já
coletadas (mesmo padrão da APAC) e deduplica por (`codigo_estacao`, `data`,
`hora`) antes de agregar para diário, com a leitura mais recente vencendo em
caso de conflito. Rodar a transformação Silver duas vezes seguidas sobre o
mesmo Bronze produz o mesmo resultado (idempotente): a tabela é
regravada por inteiro a cada execução, nunca por append incremental.
Testado com um cenário de duas execuções sobrepostas com conflito
deliberado
(`test_executar_transformacao_silver_climate_cemaden_deduplica_execucoes_sobrepostas`).

## Por que não há chunking de histórico

O endpoint de série horária já foi validado (investigação anterior) até
365 dias numa única chamada, sem paginação nem limite. Não há evidência de
que uma janela maior precise ser fragmentada — implementar chunking sem
essa necessidade real seria complexidade não solicitada pelos dados. Se um
backfill de profundidade maior que a janela padrão for autorizado no
futuro, `executar_ingestao_cemaden(horas=...)` já aceita qualquer valor
maior sem mudança de código.

## Testes

- 29 testes novos (12 cliente, 22 Silver — alguns sobrepostos com os 19
  anteriores da Estratégia A —, 6 ingestão, 4 pipeline, 5 Estratégia A
  multi-fonte). Total real da suíte: **185/185 passando** (baseline era
  156). Nenhum teste antigo quebrou.
- Cobrem: sucesso/erro/timeout do cliente; parsing robusto (arrays
  incompatíveis, resposta vazia, rótulo de hora inválido, valor negativo);
  filtro de tipo de estação e recorte de município na ingestão; resiliência
  a falha parcial (uma estação falhando não derruba o lote); ponta a ponta
  Bronze→Silver com deduplicação real entre execuções sobrepostas; o caso
  "Dois Unidos" (estação cadastrada sem série real não gera diário nem
  fica elegível); as duas correções de colisão de chave composta
  (`fonte`, `codigo_estacao`); e a preferência emergente por estação ativa
  mesmo quando outra fonte está geometricamente mais perto porém inativa.

## Comparação APAC × CEMADEN (Recife, nesta execução real)

| Critério | APAC | CEMADEN |
|---|---|---|
| Candidatas | 299 | 407 (435 casamentos cadastro×status, 28 rejeitados por duplicidade) |
| Elegíveis (≤90 dias, dado real) | 0 | 24 |
| Bairros cobertos | 0 | 94/94 |
| Estações distintas usadas | — | 16 |
| Distância mediana | — | 1,431 km |
| Distância máxima | — | 4,632 km |
| Última leitura real | 2024-04-09 (congelada) | 2026-08-20 (mesma data do sistema) |

## Limitações conhecidas

- O recorte "Grande Recife" para busca de série horária é uma decisão
  pragmática, não uma regra descoberta nos dados — pode, em teoria, deixar
  de fora uma estação de município mais distante que fosse a mais próxima
  real de algum bairro de borda. Não há evidência de que isso tenha
  acontecido (todas as distâncias ficaram ≤4,632 km, bem dentro do raio
  coberto), mas é uma escolha de escopo documentada, não uma garantia
  matemática.
- Fuso horário da série CEMADEN continua não confirmado por campo explícito
  (mesma limitação já registrada na investigação anterior) — timestamps são
  armazenados exatamente como a fonte fornece.
- `diario/{id}/{dias}` (variante do mesmo endpoint) continua não funcional —
  não usado; agregação horária→diária é feita no próprio pipeline.
- 28 estações do cadastro CEMADEN de PE ficaram de fora por colisão de nome
  duplicado — não investigado a fundo qual das duas é a estação "certa"
  nesses casos (fora do escopo desta etapa; nenhuma delas caiu no recorte
  da Grande Recife nesta execução).

## Próximo passo

Critério de sucesso principal desta etapa foi atingido com dados reais:
CEMADEN → Bronze → Silver → estação elegível por observação real →
Estratégia A → 94/94 bairros. Não avançar para Gold, não implementar
modelos preditivos, não alterar threshold — aguardando autorização
explícita do usuário para os próximos passos.
