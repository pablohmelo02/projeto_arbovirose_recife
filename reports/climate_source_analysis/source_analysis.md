# Análise das fontes climáticas oficiais — APAC x INMET

Investigação técnica real, feita em 2026-08-19: chamadas HTTP diretas contra
os endpoints (não apenas leitura de documentação), para verificar o que de
fato está disponível e funcionando hoje — não o que a documentação promete.

## O que foi testado

| Ação | Resultado |
|---|---|
| `apitempo.inmet.gov.br/estacoes/T` (API de estações automáticas, não-documentada mas amplamente usada pela comunidade) | **HTTP 500**, erro interno (`TypeError: Cannot read property 'entries' of undefined`), reproduzido em 3 tentativas |
| `apitempo.inmet.gov.br/estacoes/M` (estações manuais) | **HTTP 502** Proxy Error |
| `tempo.inmet.gov.br` (painel visual de estações) | Protegido por bot-detection (script `TSbd`) + reCAPTCHA — não é scriptável de forma robusta |
| `portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip` (download histórico em massa) | **HTTP 200, funciona.** ZIP de ~100MB/ano com 1 CSV por estação automática, todo o Brasil |
| Catálogo oficial de estações convencionais (`Normal-Climatologica-ESTAÇÕES.xlsx`) | **Funciona.** Planilha oficial com código, nome, UF, lat/lon, período de operação, situação |
| `www.apac.pe.gov.br` — painel de monitoramento (mapa) | Página funciona; API real por trás (`barramento.apac.pe.gov.br/.../ServicoMonitoramentoPCDs.php`) **funciona e retorna JSON** |
| `geoportal.apac.pe.gov.br/portal/rest/services` (ArcGIS REST) | **HTTP 500** Internal Server Error |
| `old.apac.pe.gov.br/_lib/pluviometria.request.php` (consulta histórica de estações convencionais) | Responde HTTP 200 com uma tabela HTML bem estruturada (dia 1-31 por mês/estação), **mas todos os valores testados (RMR, jan/2025 e ago/2026) vieram vazios (`-`)** — a rede convencional parece não estar sendo alimentada/digitalizada nesse sistema atualmente |

## Comparação

| Critério | APAC | INMET |
|---|---|---|
| Fonte oficial | Sim (Governo de PE) | Sim (Governo Federal) |
| API | Sim, funcional (JSON, tempo real) para rede PCD; endpoint histórico de estações convencionais responde mas sem dados populados; ArcGIS REST fora do ar | API não-documentada (`apitempo`) fora do ar; download histórico em massa (ZIP anual) funcional |
| Histórico | **Não encontrado funcionando** (endpoint existe, mas retorna vazio nos testes) | **Funciona** — ZIPs anuais com dados horários, Brasil inteiro |
| Precipitação | Sim, tempo real, 21 estações **dentro do Recife** (bairro a bairro) | Sim, mas só em estações fora de Recife (mais próxima: Palmares, ~90 km) |
| Temperatura | Não encontrada nos endpoints testados (rede PCD parece ser só pluviômetros) | Sim, horária, nas estações automáticas |
| Umidade | Não encontrada | Sim, horária |
| Coordenadas | Sim, lat/lon por estação, no próprio JSON | Sim, no cabeçalho de cada CSV e no catálogo oficial |
| Frequência | Tempo real (janelas de 15min a 24h acumuladas) | Horária |
| Estações em Recife | **21** (rede PCD, nomeadas por bairro) | **0 ativas.** A única estação que já existiu em Recife foi a convencional "RECIFE (CURADO)" (código 82900), **fechada em 2020-09-01** |
| Autenticação | Não | Não |
| Facilidade de ingestão | Alta para tempo real (JSON limpo); histórico não disponível | Alta para histórico (ZIP/CSV bem estruturado); API de tempo real instável |

## Achado central (não uma escolha limpa)

Nenhuma das duas fontes, sozinha, resolve o problema todo:

- A **APAC** tem cobertura espacial excelente dentro do Recife (21 pluviômetros
  em bairros reais — Ibura, Dois Unidos, Guabiraba, Alto do Mandu etc., os
  mesmos nomes do nosso `silver_bairro_geo`), mas só entrega o valor **atual**
  — não achei nenhum mecanismo funcional de consulta histórica em lote. O
  endpoint que deveria servir isso (rede convencional) responde, mas sem
  dado nas amostras testadas.
- O **INMET** tem um mecanismo de download histórico robusto e funcional
  (ZIP anual, dados horários de pressão/temperatura/umidade/vento/radiação
  desde a fundação de cada estação), mas **nenhuma estação ativa em Recife
  hoje** — a única que existiu fechou em 2020, e a mais próxima em operação
  fica a ~90 km (Palmares).

## Recomendação

**Fonte primária: INMET.** Justificativa: é a única com um mecanismo de
histórico que realmente funciona hoje, essencial para correlacionar com o
histórico de casos de arboviroses (2013-2025) — sem histórico, não há o que
comparar. Usaremos a estação convencional fechada "RECIFE (CURADO)" (82900,
1961-2020) para o período em que ela existiu, e as estações automáticas mais
próximas (Palmares, Garanhuns, Caruaru — todas em PE) como aproximação
regional para além disso, **documentado explicitamente como aproximação, não
como dado hiperlocal de Recife**.

**Fonte complementar: APAC.** Justificativa: apesar de não ter histórico
acessível, sua densidade espacial dentro do Recife é exatamente o que o
projeto vai precisar no futuro (clima por bairro). A estratégia adotada é
**ingerir o instantâneo atual a cada execução da Bronze**, construindo um
histórico próprio a partir de agora — não um backfill retroativo (que não
existe). Isso é uma limitação real, documentada, não uma falha do pipeline.

## O que isso implica no desenho

- `silver_estacao_climatica` cobre estações de **ambas** as fontes (`fonte`
  distingue `INMET`/`APAC`), porque a granularidade espacial e a
  disponibilidade histórica são complementares, não substituíveis uma pela
  outra.
- `silver_clima_diario` do INMET é uma **agregação de horário para diário**,
  com regra explícita por variável (ver `src/silver/schema_clima.py`).
- `silver_clima_diario` da APAC, nesta etapa, terá no máximo 1 registro por
  estação por dia de execução — não terá profundidade histórica até que o
  pipeline rode repetidamente ao longo do tempo.
- Nenhuma estratégia de atribuição estação→bairro é definida nesta etapa
  (ver `reports/climate_spatial/`) — é só análise de cobertura, conforme
  solicitado.
