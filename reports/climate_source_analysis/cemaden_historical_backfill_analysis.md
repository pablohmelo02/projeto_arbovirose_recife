# Backfill histórico do CEMADEN — profundidade real e impacto na Gold

> Investigação e execução real, 2026-08-20, contra o endpoint de produção
> do CEMADEN (`mapservices.cemaden.gov.br`) e contra os dados reais já
> ingeridos (CKAN arboviroses/território, INMET, APAC, CEMADEN), usando
> `moto.server` como stub do MinIO (ver `CLAUDE.md` §9). Segue
> `reports/climate_source_analysis/cemaden_integration_results.md` e
> `reports/climate_source_analysis/cemaden_precipitation_endpoint_investigation.md`,
> que haviam deixado a profundidade histórica real como pergunta aberta.

## 0. Estado antes desta etapa

- Baseline preservado: commit `c3933b4` ("Adiciona Gold analítica integrada"),
  branch `main`, working tree limpo antes de qualquer alteração.
- Suíte completa confirmada **217/217 passando** antes de qualquer mudança
  (baseline idêntico ao registrado em `CLAUDE.md`).
- Gold existente (`gold_arboviroses_clima_bairro`, 191.478 linhas, 2013-2025)
  preservada intacta como referência de "antes": **0% das linhas com clima
  real** (a interseção entre casos 2013-2025 e CEMADEN 2026-08-18→2026-08-20
  era vazia).
- Nenhuma alteração em Bronze/Silver existentes, na Estratégia A,
  em `LIMIAR_DIAS_ESTACAO_ATIVA` (permanece 90), na APAC ou no INMET.

## 1. Objetivo

Responder: **é possível recuperar histórico real do CEMADEN suficiente para
criar interseção temporal útil com os casos de arboviroses (2013-2025)?**
Se sim, implementar o backfill, reconstruir Silver e Gold, e medir a
interseção real — sem fabricar clima nem usar uma estação distante como
proxy de bairro.

## 2. Semântica do endpoint `horario/{id}/{horas}`

Testada experimentalmente (não suposta), com requisições HTTP reais e
controladas (sequenciais, com pausas, sem concorrência):

- **`{horas}` significa "as últimas N horas a partir de agora"** — não
  aceita data inicial/final. Confirmado inspecionando os campos `datas`
  retornados: para qualquer `horas` testado, o **último** dia retornado é
  sempre a data da requisição; o **primeiro** dia é sempre
  `hoje − horas/24` dias. **Não existe parâmetro de offset.**
- **Consequência arquitetural importante**: como não há offset, **não é
  possível "paginar" blocos de datas diferentes** (ex.: pedir "2015" e depois
  "2016"). A única forma de alcançar mais profundidade é aumentar `horas`,
  e cada requisição maior sempre reinclui tudo que uma requisição menor já
  trazia. Portanto **a profundidade máxima alcançável é o tamanho da MAIOR
  requisição bem-sucedida por estação — não a soma de várias.** O
  "chunking" pedido na etapa (seção 9) não se aplica no sentido clássico de
  paginação por intervalo; foi reinterpretado como "uma única requisição por
  estação, de tamanho generoso", ver seção 5.
- **O backend realmente consulta dados antigos** (não é truncamento
  silencioso disfarçado de sucesso): os valores não-nulos aumentam de forma
  monotônica e aproximadamente linear com o tamanho da janela (ver tabela na
  seção 4) — evidência de série real, não de eco/cache de um mesmo bloco
  pequeno.
- **Existe timeout para janelas grandes, mas não é um limite rígido da
  fonte** — ver achado central na seção 5.
- **Não há paginação.** Não há campo explícito indicando "período
  efetivamente coberto" — quem chama precisa inspecionar `datas`/`acumulados`
  para descobrir o que realmente veio (o `horas` solicitado é sempre
  ecoado no tamanho do array, mesmo quando quase tudo vem `null`).
- **Sem limite de registros detectado** até a maior janela testada (5 anos,
  ver seção 4) — o limite observado é de **tempo de resposta**, não de
  contagem.

## 3. Estações testadas

3 estações reais e funcionais da Estratégia A atual, como pedido (Porto,
Dois Irmãos, Imbiribeira):

| Estação | `idEstacao` | `codEstacao` (WFS) |
|---|---|---|
| Porto | 6846 | 261160620A |
| Dois Irmãos | 3006 | 261160603A |
| Imbiribeira | 3257 | 261160609A |

## 4. Teste de profundidade histórica (progressivo, sequencial, controlado)

Requisições reais, uma por vez, com pausa de 1,5s entre elas (nunca
concorrentes). Tabela completa (janela solicitada vs. período efetivamente
retornado, primeiro e último `data` no payload, observações não-nulas):

| Estação | Dias solicitados | Status | Tempo | Tamanho resposta | Primeiro dia retornado | Não-nulas |
|---|---:|---|---:|---:|---|---:|
| Porto | 1 | 200 | 0,44s | 972 B | 19/08/2026 | 22 |
| Porto | 7 | 200 | 0,42s | 8,3 KB | 13/08/2026 | 158 |
| Porto | 30 | 200 | 7,56s | 116 KB | 21/07/2026 | 663 |
| Porto | 90 | 200 | 18,48s | 997 KB | 22/05/2026 | 1.951 |
| Porto | 365 | 200 | 12,82s | 16,1 MB | 20/08/2025 | 2.889 |
| Porto | 730 | 200 | 28,56s | 64,1 MB | 20/08/2024 | 4.815 |
| Porto | **1825 (5 anos)** | **200** (na 2ª tentativa daquele exato `horas`, ver §5) | 13,34s | 400,2 MB | **21/08/2021** | 28.586 |
| Dois Irmãos | 1 → 365 | 200 (todas) | 0,3-16s | 1KB→16MB | 20/08/2025 | 3→1.506 |
| Dois Irmãos | 730 (1ª tentativa) | **timeout (60s)** | 60,18s | — | — | — |
| Dois Irmãos | 730 (repetição, timeout maior) | **200** | 2,48s | 64,1 MB | 20/08/2024 | 6.254 |
| Imbiribeira | 1 → 365 | 200 (todas) | 0,3-15s | 1KB→16MB | 20/08/2025 | 25→8.655 |
| Imbiribeira | 730 (1ª tentativa) | **timeout (60s)** | 60,16s | — | — | — |
| Imbiribeira | 730 (repetição, timeout maior) | **200** | 2,77s | 64,1 MB | 20/08/2024 | 17.274 |

Janelas adicionais testadas **só em Porto** (para não multiplicar carga em 3
estações — ver justificativa na seção 5): 900, 1095 (3 anos), 1460 (4 anos)
e 1825 dias (5 anos), todas com **200 OK** e valores não-nulos crescendo de
forma consistente (6.585 → 11.237 → 19.922 → 28.586). Janelas de 3.650 e
5.000+ dias foram tentadas (1ª tentativa) e **excederam 60s** — não foram
retentadas com timeout maior, por decisão de carga (seção 5.3).

**Comparação solicitado vs. retornado**: em todas as respostas 200 OK, o
array `datas` tem exatamente `horas/24 + 1` elementos e o `acumulados` é uma
matriz `len(datas) × len(horarios)` — ou seja, **a janela retornada bate
exatamente com a solicitada quando a requisição tem sucesso**; não há
truncamento silencioso disfarçado de sucesso. O que existe é a requisição
**falhar** (timeout) antes de completar — nesse caso não há corpo de
resposta para comparar, é um erro explícito de rede, não um 200 com dado
cortado.

## 5. Achados operacionais importantes (não previstos antes do teste)

### 5.1 A matriz de resposta cresce ao quadrado da janela, não linearmente

O array `horarios` (rótulos de hora) **não tem 24 posições fixas** — tem
`horas + 1` posições, e a matriz `acumulados` é `dias × (horas+1)`, majoritariamente
`null` (só a diagonal-ish onde hora-do-array bate com a hora real daquele
dia tem valor). Isso explica por que o tamanho da resposta **não** dobra
quando a janela dobra: dobrar `dias` também dobra o número de colunas por
linha, então o payload cresce ~4× (365d→16MB, 730d→64MB, 1825d→400MB, todos
próximos de crescimento quadrático). Essa é a causa raiz de janelas muito
grandes serem caras — não é um limite de disponibilidade de dado, é uma
característica ineficiente do formato de resposta do próprio CEMADEN.

### 5.2 "Cold start" reproduzível: 1ª requisição de uma janela grande pode
exceder 60s; a repetição da mesma requisição responde em segundos

Achado direto, não hipotético: para **Dois Irmãos** e **Imbiribeira**, a
1ª requisição de 730 dias **excedeu um timeout de 60s** (3 tentativas
consecutivas, inclusive em janelas ainda maiores). Uma **repetição exata**
da mesma URL, minutos depois, com timeout maior (150s), respondeu em
**2,5-2,8 segundos** — 20× mais rápido, com o mesmo volume de dado real
(64 MB, mesmas datas). O mesmo padrão apareceu em Porto na janela de 5 anos
(1ª tentativa, isolada, não cronometrada por timeout curto, mas a mesma URL
exata respondeu em 13s numa consulta seguinte). Hipótese razoável (não
documentada pelo CEMADEN, não confirmada por nenhuma fonte oficial): o
backend monta a matriz de resposta sob demanda na primeira consulta de uma
janela grande para aquela estação, e algum tipo de cache (aplicação,
proxy, ou banco) acelera consultas subsequentes da mesma janela. **Isso não
é truncamento nem erro silencioso** — é uma questão de paciência do cliente,
não de disponibilidade do dado.

Implementado no backfill (`src/ingestion/cemaden_backfill.py`): timeout alto
(180s) **e** até 2 tentativas com espera entre elas, exatamente por causa
deste achado — sem isso, o backfill reportaria falso-negativo ("sem
histórico") para estações que só precisavam de uma segunda tentativa.

### 5.3 Decisão de não empurrar além de 5 anos nos testes exploratórios

Dado o crescimento quadrático (§5.1), uma janela de 10 anos custaria
~4× o payload de 5 anos (~1,6 GB) e uma de 13,7 anos (5.000 dias, testada e
com timeout) ainda mais. Buscar essas janelas por HTTP puro, fora de
qualquer necessidade de produção, cruzaria de "teste controlado" para
"carga desproporcional a um servidor público" — indo contra a instrução
explícita de não fazer stress test. Por isso **1825 dias (5 anos) é o maior
valor efetivamente validado nesta investigação**, não um limite descoberto
do CEMADEN. Documentado como decisão, não como limite da fonte.

## 6. Estabilidade do identificador de estação

Reconfirmado (não reinvestigado a fundo, pois a investigação anterior já
havia validado isso e não há sinal de problema): em todas as respostas
`horario/{id}/{horas}` desta sessão, o campo `estacao.codEstacao` bateu
exatamente com o `codigo_estacao` do cadastro WFS usado pela Silver — para
as 16 estações usadas na Estratégia A, sem ambiguidade. Nenhum sinal de
troca de código, estação substituída ou coordenada mudando entre chamadas
foi observado nesta sessão.

**Achado real relevante encontrado durante a execução do backfill** (não
hipotético — ver `reports/climate_source_analysis/cemaden_backfill_profiling_por_estacao.csv`):
a estação `6532` (usada pelo bairro Tótó/Coqueiral na Estratégia A) só tem
leitura real a partir de **2026-04-14**, apesar de o backfill ter pedido
730 dias — ou seja, essa estação especificamente **começou a operar (ou a
transmitir de forma utilizável) no meio da janela solicitada**, não desde o
início. Isso é evidência real de que "profundidade da janela pedida" e
"profundidade real disponível por estação" são coisas diferentes, e reforça
por que o schema já preserva `horas_validas_dia`/contagens de dia por
estação em vez de assumir cobertura uniforme.

## 7. Histórico via formulário (CAPTCHA) — não usado, confirmado de novo

Reconfirmado sem tentar contornar: o mecanismo de exportação em lote
(`download_form.php`, protegido por CAPTCHA) não foi acessado nem
investigado além do que já constava em `cemaden_precipitation_endpoint_investigation.md`.
Todo o backfill desta etapa usa exclusivamente `horario/{id}/{horas}`
(sem autenticação, sem CAPTCHA, sem cookie/sessão — reconfirmado nas
requisições reais desta sessão).

## 8. Decisão de backfill: viável, com profundidade validada de 5 anos

Critério mínimo do usuário (sobreposição útil com 2013-2025, não
necessariamente os 13 anos completos) **superado**: 5 anos de profundidade
validada (2021-08-21 → 2026-08-20) cobrem uma fração relevante e recente da
série epidemiológica (2021-2025). **Decisão: implementar o backfill.**

## 9. Implementação do backfill

Módulo novo: `src/ingestion/cemaden_backfill.py` + entry point
`src/backfill_climate_cemaden.py` (`python -m src.backfill_climate_cemaden --dias N`).

- **Sem chunking por intervalo de data** (ver seção 2) — uma única
  requisição por estação, com `dias_profundidade` como parâmetro de
  tamanho. Documentado explicitamente no módulo para não ser "descoberto de
  novo" numa sessão futura.
- **Retentativa por cold-start** (ver §5.2): timeout 180s, até 2 tentativas
  por estação, com espera entre elas. Todas as tentativas ficam registradas
  no manifest (`entrada["tentativas"]`), nunca escondidas.
- **Bronze**: grava em `bronze/recife/clima/cemaden/horario_backfill/...`
  (prefixo **distinto** do operacional, `.../cemaden/horario/...` —
  nunca sobrescreve). Manifest com `dataset="pcd-pluviometrica-backfill-historico"`
  e `dias_profundidade` no nível da execução — permite distinguir "coleta
  atual" de "backfill histórico" só inspecionando o manifest.
- **Checkpoint/retomada**: `estacoes_com_backfill_suficiente` varre os
  manifests de backfill já existentes; uma estação com backfill `SUCCESS`
  e `dias_profundidade` já suficiente é pulada (nenhuma nova chamada HTTP).
  Testado explicitamente (`test_executar_backfill_pula_estacao_com_checkpoint_suficiente`).
- **Falha isolada não derruba o lote**: uma estação que falha todas as
  tentativas é registrada como `ERROR` e as demais continuam.
- **Nenhuma mudança na Silver** (`pipeline_climate.py::_processar_cemaden`)
  foi necessária: a função já acumulava **todas** as entradas `tipo="horario"`
  de **todos** os manifests CEMADEN (operacional + backfill, indistintamente
  quanto ao prefixo do objeto) e já deduplicava por `(codigo_estacao, data,
  hora)`. O backfill só precisou gerar entradas no formato que esse
  mecanismo já esperava — confirmado com um teste de integração dedicado
  (`test_executar_transformacao_silver_climate_combina_backfill_historico_com_operacional`).
- **Seleção de estações**: não as 407 de PE inteira, nem sequer as 35
  candidatas da Grande Recife — **as 16 estações CEMADEN que a Estratégia A
  atual já usa** para representar os 94 bairros (`silver_bairro_estacao`),
  conforme a instrução de partir do mapeamento espacial atual. Essas 16
  foram obtidas rodando o pipeline operacional uma vez e lendo
  `silver_bairro_estacao["codigo_estacao"].unique()`.

## 10. Estratégia A histórica: não foi necessário mudar

Verificado antes de decidir (seção 14/15 da instrução): a elegibilidade da
Estratégia A (`filtrar_estacoes_elegiveis`) depende só de **"a estação tem
leitura em `silver_clima_diario` nos últimos 90 dias a partir de hoje"** —
um critério que **não muda com backfill histórico**, porque backfill nunca
altera qual é a leitura mais recente de uma estação. Confirmado na prática:
`transform_climate_bairro` foi rodado antes e depois do backfill e produziu
**exatamente o mesmo mapeamento (94/94 bairros, mesmas 16 estações,
mesmas distâncias)** nas duas vezes. Por isso a Gold reconstruída usa a
**mesma** associação bairro→estação de sempre, só que agora aplicada a um
`silver_clima_diario` com mais profundidade temporal para essas 16
estações — exatamente o comportamento que `calcular_features_climaticas`
(`src/gold/arboviroses_clima.py`) já implementava sem precisar de nenhuma
mudança de código: ela busca a série histórica completa da estação
associada, não só a leitura mais recente.

**Não foi necessário implementar "Estratégia A temporal"** (bairro+período
→ estação elegível naquele período) nesta etapa: as 16 estações usadas hoje
já têm série real cobrindo profundidade suficiente do período pedido (ver
tabela da seção 12) — a única exceção real observada (`6532`, início em
2026-04-14, seção 6) já é tratada corretamente pelo mecanismo existente:
simplesmente não há dado antes dessa data para aquela estação, e as
semanas correspondentes ficam com clima `None`, sem inventar valor.

## 11. Backfill efetivamente aplicado nesta sessão: 730 dias (não os 1825 validados)

**Decisão documentada, não limitação da fonte.** Esta máquina de
desenvolvimento tem `MinIO`/Docker indisponível (ver `CLAUDE.md` §9): o
stub usado é `moto.server`, que mantém todos os objetos **em memória do
processo Python**, não em disco. A memória livre observada durante esta
sessão foi de **~1,9-2,3 GB** (medida via `Get-CimInstance
Win32_OperatingSystem`, não estimada). Uma janela de 1825 dias por estação
pesa ~400 MB (ver §5.1); para as 16 estações usadas pela Estratégia A, isso
seria **~6,4 GB só de Bronze CEMADEN em memória** — inviável neste ambiente
sem risco real de esgotar a memória e perder a sessão inteira.

Por isso o backfill foi executado em dois incrementos controlados,
monitorando memória livre entre eles:

1. **365 dias** (16 MB/estação × 16 = ~256 MB): sucesso, memória estável
   (~2,3 GB livres depois).
2. **730 dias** (64 MB/estação × 16 = ~1 GB, superando o checkpoint de 365
   dias): sucesso, 16/16 estações, 0 erros, memória ainda estável (~1,9 GB
   livres depois).

Um terceiro incremento (1095+ dias) **não foi tentado** nesta sessão — o
custo adicional projetado (~2,3 GB extras) ultrapassaria a margem seguro de
memória livre observada. **Isso é uma limitação do ambiente local desta
sessão (sem MinIO/Docker real), não do CEMADEN**: a investigação da seção 4
já comprovou que 5 anos são tecnicamente recuperáveis por estação. Um
ambiente com MinIO real (armazenamento em disco, não em memória do
processo) poderia rodar `python -m src.backfill_climate_cemaden --dias
1825` sem essa restrição.

## 12. Profiling do backfill (dados reais desta execução)

`silver_estacao_climatica`: 718 estações (12 INMET + 299 APAC + 407
CEMADEN) — inalterado, backfill não cria estações novas.

`silver_clima_diario`: **11.749 linhas válidas** no total (antes do
backfill, só com a ingestão operacional: 4.762) — **+6.987 dias-estação
reais** adicionados pelo backfill. Das 24 estações CEMADEN com pelo menos
um dia real (16 backfilled + 8 só com a janela operacional de 48h fora do
recorte do backfill), a tabela completa está em
`reports/climate_source_analysis/cemaden_backfill_profiling_por_estacao.csv`.
Destaques (estações backfilled):

| Estação | Primeiro dia real | Último dia real | Dias com leitura | Horas válidas/dia (média) |
|---|---|---|---:|---:|
| 3253 | 2024-08-20 | 2026-08-20 | 731 | 23,9 |
| 3257 | 2024-08-20 | 2026-08-20 | 731 | 23,6 |
| 6535 | 2024-08-20 | 2026-08-20 | 731 | 23,9 |
| 6534 | 2024-08-20 | 2026-08-20 | 731 | 23,9 |
| 6529 | 2024-08-20 | 2026-08-20 | 718 | 23,6 |
| 6531 | 2024-08-20 | 2026-08-20 | 670 | 22,6 |
| 6846 (Porto) | 2024-08-20 | 2026-08-20 | 620 | 7,8 |
| 6530 | 2024-08-21 | 2026-08-20 | 511 | 4,8 |
| 6473 | 2024-08-20 | 2026-08-20 | 412 | 10,6 |
| 3006 (Dois Irmãos) | 2024-08-20 | 2026-08-19 | 322 | 19,4 |
| 3258 | 2024-08-20 | 2026-08-20 | 185 | 23,2 |
| 6536 | 2024-08-20 | 2026-08-20 | 149 | 23,3 |
| 3010 | 2024-08-20 | 2026-08-20 | 147 | 16,3 |
| 6847 | 2024-08-20 | 2026-08-20 | 253 | 23,6 |
| 2999 | 2024-08-22 | 2026-08-20 | 52 | 20,8 |
| **6532** | **2026-04-14** | 2026-08-20 | 71 | 9,4 |

Nenhuma duplicidade nova, nenhuma precipitação negativa
(`precipitacao_mm < 0`: 0 em 7.058 linhas CEMADEN), máximo observado 458,1
mm em um dia (plausível para evento de chuva intensa tropical, não
filtrado/descartado — o projeto não trata outlier de precipitação como
erro automático). Nenhuma estação backfilled ficou sem nenhum dia real
(diferente do caso "Dois Unidos" documentado na integração anterior — as 16
usadas pela Estratégia A já eram, por definição, as que tinham leitura
recente real).

## 13. Cobertura temporal do Recife, por ano (Gold reconstruída)

Tabela real (`reports/gold_analysis/cobertura_climatica_por_ano.csv`),
usando `dias_com_dado_valido_semana > 0` como critério de "bairro com clima
utilizável" naquela semana:

| Ano epidemiológico | Linhas Gold | Linhas com clima real | % linhas com clima | Bairros com clima (de 94) | % bairros |
|---:|---:|---:|---:|---:|---:|
| 2013 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2014 | 14.946 | 0 | 0,00% | 0 | 0,00% |
| 2015 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2016 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2017 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2018 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2019 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2020 | 14.946 | 0 | 0,00% | 0 | 0,00% |
| 2021 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2022 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| 2023 | 14.664 | 0 | 0,00% | 0 | 0,00% |
| **2024** | 14.664 | **3.915** | **26,70%** | **90** | **95,74%** |
| **2025** | 14.946 | **7.794** | **52,15%** | **65** | **69,15%** |

**Não foi forçado 94/94 em nenhum ano** (conforme instrução explícita) — os
números acima são exatamente o que o backfill de 730 dias produziu, sem
completar artificialmente. 2013-2023 seguem genuinamente em 0% (fora da
janela de 730 dias a partir de 2026-08-20) — não é erro, é o limite real
desta execução (ver seção 11).

Visualização: `reports/climate_source_analysis/cemaden_backfill_cobertura_antes_depois.png`
(painel A) e `reports/gold_analysis/a_cobertura_temporal.png` (interseção
visual real, antes vazia, agora com uma faixa 2024-2026).

## 14. Gold: antes × depois (métrica principal)

| | Antes do backfill | Depois do backfill (730 dias) |
|---|---:|---:|
| Linhas Gold totais | 191.478 | 191.478 (inalterado — mesmo grão) |
| Linhas com clima real | 0 | **11.709** |
| % com clima real | **0,0000%** | **6,1151%** |
| Bairros com algum clima real (algum período) | 0/94 | **90/94** |
| Agravos afetados | — | DENGUE, ZIKA, CHIKUNGUNYA (os 3) |
| Casos reais em semanas com clima real | 0 | **8.210** |
| Semanas epidemiológicas distintas com clima real | 0 | **72** |
| Período com clima real na Gold | — | **2024-08-18 → 2026-01-03** |
| Fontes climáticas na Gold | — | CEMADEN (única, 16 estações) |
| Chave única / duplicatas | 0 | 0 (inalterado) |
| Casos negativos | 0 | 0 (inalterado) |
| Precipitação negativa | 0 | 0 |

`gold_arboviroses_clima_bairro` manteve o grão (`bairro × semana
epidemiológica × agravo`), a chave única, e **0 casos perdidos/inventados**
(156.504 preservados, idêntico a antes) — só as colunas climáticas
passaram a ter valor real numa fração maior do intervalo.

## 15. Leakage temporal — reconfirmado após a reconstrução

A suíte completa (`226 testes`, incluindo os 9 novos desta etapa) passou
depois da reconstrução real da Gold, incluindo
`test_features_climaticas_nunca_usa_dado_posterior_ao_fim_da_semana`
(`tests/test_gold_arboviroses_clima.py`) — o teste de leakage não depende
de quanto histórico existe, só da regra `data <= semana_epi_data_fim`, que
não foi alterada nesta etapa. Nenhuma linha da Gold usa um dia de clima
posterior ao fim da própria semana, mesmo com um `silver_clima_diario`
maior.

## 16. Testes novos (9, suíte total 226/226)

`tests/test_cemaden_backfill.py` (8 testes): backfill de sucesso simples;
retentativa após falha (2 tentativas registradas); estação falha em todas
as tentativas sem derrubar o lote; checkpoint pula estação já suficiente
sem nenhuma chamada HTTP nova; checkpoint não pula quando a profundidade
pedida é maior que a já alcançada; `pular_se_ja_existe=False` sempre
rebusca; `_baixar_com_retentativa` retorna `None` após esgotar tentativas.

`tests/test_climate_pipeline.py` (1 teste novo):
`test_executar_transformacao_silver_climate_combina_backfill_historico_com_operacional`
— confirma que a Silver acumula e deduplica corretamente entradas do
backfill (prefixo `horario_backfill/`) junto com entradas operacionais
(prefixo `horario/`) para a mesma estação, sem nenhuma mudança em
`pipeline_climate.py`.

Nenhum teste existente regrediu (217 → 226, todos passando).

## 17. Problemas encontrados

1. **"Cold start" do endpoint para janelas grandes** (§5.2) — resolvido com
   timeout alto + retentativa no backfill; documentado para não ser
   confundido com "sem histórico".
2. **Crescimento quadrático do payload** (§5.1) — limitou a profundidade
   testada a 5 anos (não um limite da fonte, decisão de carga) e a
   profundidade aplicada nesta execução a 2 anos (limitação de memória do
   ambiente local, não da fonte).
3. **Estação `6532` com início real em 2026-04-14** dentro de uma janela de
   730 dias solicitados — confirma na prática a preocupação da seção 14 da
   instrução (não assumir que toda estação cobre o período pedido
   igualmente); o mecanismo existente (`horas_validas_dia`, `missing ≠ 0`)
   já trata isso corretamente sem mudança de código.
4. Nenhum bug de dado (sem duplicidade nova, sem precipitação negativa, sem
   colisão de `codigo_estacao` entre fontes — a chave composta
   `(fonte, codigo_estacao)` já corrigida na integração anterior continuou
   correta).

## 18. Arquivos criados

- `src/ingestion/cemaden_backfill.py`
- `src/backfill_climate_cemaden.py`
- `tests/test_cemaden_backfill.py`
- `reports/climate_source_analysis/cemaden_historical_backfill_analysis.md` (este arquivo)
- `reports/climate_source_analysis/cemaden_backfill_cobertura_antes_depois.png`
- `reports/climate_source_analysis/cemaden_backfill_profiling_por_estacao.csv`
- `reports/gold_analysis/cobertura_climatica_por_ano.csv`

## 19. Arquivos alterados

- `src/ingestion/climate_ingestion.py` (renomeia `_candidatos_pluviometricos_grande_recife`
  → `candidatos_pluviometricos_grande_recife`, reutilizada pelo backfill;
  nenhuma mudança de comportamento)
- `tests/test_climate_pipeline.py` (1 teste novo de integração)
- `reports/gold_analysis/*.png`, `cobertura_temporal.csv`, `profiling.json`
  (regenerados pela Gold reconstruída — números reais, não estimados)
- `reports/gold_analysis/README.md`, `README.md`, `CLAUDE.md` (ver seções
  seguintes)

**Não alterados** (conforme instrução): Estratégia A (`climate_bairro.py`,
`schema_climate_bairro.py`), `LIMIAR_DIAS_ESTACAO_ATIVA`, cliente APAC,
cliente INMET, `pipeline_climate.py` (nenhuma linha mudou — só passou a
processar mais dados de entrada), schema/grão da Gold.

## 20. Classificação final

**B — Histórico parcial útil.** Não cobre 2013-2025 completo, mas criou
uma janela temporal real e significativa (2024-2025: 96% e 69% dos 94
bairros com clima real respectivamente, 8.210 casos reais em semanas com
clima real, os 3 agravos representados) — suficiente para iniciar uma EDA
integrada clima×arboviroses **restrita a 2024-2025**, não para o histórico
completo de 13 anos.

## 21. Decisão obrigatória

> **Temos agora dados climáticos históricos reais suficientes para iniciar
> uma EDA integrada clima × arboviroses?**

**SIM — parcialmente, com escopo explícito.** Existe interseção real,
mensurável e não fabricada entre clima (CEMADEN) e arboviroses para
**2024-2025** (6,12% da Gold total, mas 26,7%/52,1% desses dois anos
especificamente, cobrindo 90/94 e 65/94 bairros). Uma EDA integrada
**restrita a esses dois anos epidemiológicos** é hoje possível com dado
real. Uma EDA integrada para **2013-2023 continua impossível** com dado
real — não foi fabricada nem aproximada nenhuma leitura para esse período.

## 22. Recomendação técnica

1. Se uma EDA clima×arboviroses de 2024-2025 já é útil para o objetivo do
   usuário, ela pode começar agora, com a Gold reconstruída
   (`gold_arboviroses_clima_bairro`, filtrando `ano_epidemiologico >= 2024`
   ou usando `dias_com_dado_valido_semana > 0` como filtro de linhas
   utilizáveis).
2. Se profundidade maior (potencialmente até 5 anos, 2021-2025, já validada
   tecnicamente na seção 4) for necessária, rodar
   `python -m src.backfill_climate_cemaden --dias 1825` num ambiente com
   MinIO real (armazenamento em disco, não em memória) — o código já
   suporta isso sem alteração, só não foi executado nesta sessão por
   limitação de memória do ambiente local (seção 11).
3. Para 2013-2023, nenhuma fonte investigada neste projeto (INMET, APAC,
   CEMADEN) tem histórico real disponível de forma automatizável. Se essa
   janela for necessária, a próxima investigação recomendada é
   **ANA/Hidroweb** (já mapeada em `alternative_sources_analysis.md` como
   tendo baixíssima densidade em Recife, mas não testada quanto a
   profundidade histórica real) ou um produto de precipitação **em grade**
   (satélite/reanálise, ex. CHIRPS/MERGE-INPE) — que deve ser
   explicitamente diferenciado de medição de estação (ver seção 33 da
   instrução) e não foi implementado nem avaliado nesta etapa.
