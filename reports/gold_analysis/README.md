# Gold analítica: `gold_arboviroses_clima_bairro` — resultados reais

> Execução real, 2026-08-20, contra os dados reais já ingeridos (CKAN
> arboviroses/território, INMET, APAC, CEMADEN), usando `moto.server` como
> stub do MinIO (ver CLAUDE.md §9). Todos os números abaixo vêm do manifest
> desta execução (`gold/recife/arboviroses_clima/_controle/`) e de
> `profiling.json` nesta pasta — nenhum é estimativa.

## Objetivo

Primeira camada Gold analítica integrando os três domínios Silver
(arboviroses + território + clima) num dataset pronto para EDA/modelagem
futura. **Nenhum modelo foi treinado nesta etapa.**

## Grão escolhido: `bairro × semana epidemiológica × agravo`

**Opção A (semana epidemiológica) escolhida sobre a Opção B (mês)**, com
base na inspeção real dos dados, não em preferência:

- `semana_notificacao` (formato `AAAASS`) **já existe no SINAN**, nativo, com
  apenas **72 nulos em 162.534 linhas (0,04%)** — os casos já têm resolução
  semanal confiável.
- Usar mês descartaria precisão que os dados já sustentam, sem nenhum ganho.
- O join climático é feito agregando `silver_clima_diario` (diário) **para**
  o intervalo semanal — nunca distribuindo casos semanais em dias (nenhuma
  falsa precisão criada).

**Semana epidemiológica não foi recalculada** para os casos: o campo do
SINAN é usado como está. O que foi implementado (`src/gold/epidemiologia.py`)
é o mapeamento inverso, necessário para o clima: dado (ano, semana), qual o
intervalo de datas (domingo→sábado, semana 1 = a que contém 4 de janeiro —
convenção SVS/CDC, **não** `isocalendar()`, que é ISO segunda→domingo).
Essa regra foi **validada empiricamente contra 5.000 pares reais**
(`data_notificacao`, `semana_notificacao`) da Silver antes de ser usada:
5000/5000 bateram.

**Agravos em linhas, não colunas** (`agravo` como valor): mantém o formato
já usado em toda a Silver, não exige inventar convenção de nome de coluna
por doença, e continua pivotável sob demanda.

## Chave analítica

```text
codigo_bairro + agravo + ano_epidemiologico + semana_epidemiologica
```

Verificado nesta execução: **0 duplicatas de chave** em 191.478 linhas.

## Números reais desta execução

| Métrica | Valor real |
|---|---|
| Linhas Gold | **191.478** |
| Bairros | **94** |
| Agravos | 3 (DENGUE, ZIKA, CHIKUNGUNYA) |
| Períodos (ano_epi, semana_epi) distintos | **679** |
| Intervalo epidemiológico | **2013 → 2025** |
| Intervalo de datas coberto | 2012-12-30 → 2026-01-03 |
| Casos totais preservados | **156.504** |
| Linhas com ≥1 caso | 42.498 (22,19%) |
| Linhas com 0 casos | 148.980 |
| Casos por agravo | DENGUE 109.792 · CHIKUNGUNYA 39.552 · ZIKA 7.160 |
| Casos negativos | 0 |
| **Linhas com clima real** | **0 (0,0000%)** ⚠️ |

## Cardinalidade dos joins (antes → depois, nada silencioso)

| Etapa | Antes | Depois | Perda | Motivo |
|---|---|---|---|---|
| Duplicatas exatas | 162.537 | 162.534 | 3 | linhas 100% idênticas em todas as colunas de negócio |
| Período epidemiológico | 162.534 | 162.462 | 72 | `semana_notificacao` nula/não parseável |
| Join bairro oficial | 162.462 | 156.504 | 5.958 | 5.833 sem `nome_bairro` + 125 com nome fora dos 94 oficiais |
| **Aproveitamento total** | — | — | — | **96,33%** dos casos entram no grão espacial |
| Agregação → grão | 156.504 casos | 42.498 linhas com caso | 0 casos | agregação, não perda (total conferido: 156.504 = 156.504) |
| Materialização do grão completo | 42.498 | 191.478 | — | produto cartesiano 94 × 3 × 679, `casos=0` onde não há notificação |
| Join território | 191.478 | 191.478 | 0 | many-to-one, validado em código (levanta erro se mudar) |
| Join bairro→estação | 191.478 | 191.478 | 0 | many-to-one (1 estação por bairro) |

Nenhum join many-to-many acidental: `juntar_bairro_oficial` e
`juntar_atributos_territorio` **levantam exceção** se a cardinalidade
aumentar, e `materializar_grao_completo` levanta se o total de casos mudar.

## Join arboviroses × território: por nome, não por código

Achado real que definiu a decisão (verificado antes de implementar):

- O `codigo_bairro` da Silver de arboviroses (`ID_BAIRRO`/`CO_BAIRRO_RESIDENCIA`
  do SINAN) **não é o mesmo espaço de códigos** de `silver_bairro_geo`: só
  **21 de 94** códigos coincidem, e **93 dos 94** bairros oficiais têm mais
  de um `codigo_bairro` distinto associado nos casos. Usar código como chave
  primária produziria um join massivamente errado.
- `nome_bairro` normalizado (`limpar_texto`, já existente na Silver) bate
  **94/94**. É a chave usada.

## Features

**Epidemiológica**: `casos` (contagem absoluta de notificações).

**`incidencia_por_100k` NÃO existe** — verificado: **nenhuma fonte deste
projeto tem população por bairro** (`silver_bairro_geo` tem `area_km2`, não
população/densidade). Calcular incidência exigiria nova fonte (IBGE/Censo),
fora do escopo autorizado. Não foi inventado nem aproximado.

**Territoriais**: `area_km2`, `codigo_rpa`, `codigo_microrregiao`,
`centroide_lat`, `centroide_lon`.

**Climáticas (própria semana)**: `precipitacao_total_semana_mm`,
`precipitacao_media_diaria_mm`, `precipitacao_maxima_diaria_mm`,
`dias_com_chuva`, `dias_com_dado_valido_semana`,
`completude_climatica_semana`.

**Climáticas retrospectivas**: `chuva_7d_mm`, `chuva_14d_mm`,
`chuva_21d_mm`, `chuva_28d_mm`, `dias_com_dado_valido_7d`,
`dias_com_dado_valido_28d`.

**Rastreabilidade de fonte climática** (nunca uma série "homogênea"
escondendo troca de rede): `fonte_clima`, `codigo_estacao_clima`,
`distancia_estacao_km`, `metodo_associacao_clima`, mais
`versao_schema_gold` e `_processed_at`.

## Regra de leakage temporal

**Regra única, testável**: toda feature climática de uma linha usa somente
dias com `data <= semana_epi_data_fim` **dessa própria linha**.

| Feature | Data de referência | Janela | Último instante permitido |
|---|---|---|---|
| `precipitacao_*_semana*`, `dias_com_chuva`, `dias_com_dado_valido_semana` | `semana_epi_data_fim` | 7 dias (a própria semana) | `semana_epi_data_fim` |
| `chuva_7d/14d/21d/28d_mm` | `semana_epi_data_fim` | 7/14/21/28 dias terminando nela | `semana_epi_data_fim` |
| `dias_com_dado_valido_7d/28d` | `semana_epi_data_fim` | idem | `semana_epi_data_fim` |

As janelas **incluem** a própria semana-alvo (a chuva da semana em que os
casos foram notificados não é informação do futuro em relação a eles), mas
**nunca** um dia posterior. Implementação: as janelas móveis são calculadas
por estação **antes** do merge, e o merge busca o valor exatamente em
`semana_epi_data_fim`.

Teste dedicado (`test_features_climaticas_nunca_usa_dado_posterior_ao_fim_da_semana`):
injeta 999 mm de chuva em dias posteriores ao fim da semana e confirma que
**nenhuma** feature muda de valor.

## Tratamento de missing

**Clima (`None ≠ 0 mm`)** — regra inegociável do projeto, preservada:
semana sem leitura tem `precipitacao_* = None`, nunca `0`. Zero real
informado pela fonte permanece `0`. Nenhuma imputação. As **contagens de
dias** (`dias_com_dado_valido_*`, `dias_com_chuva`) são preenchidas com `0`
apenas quando o bairro **tem** estação associada (0 leituras válidas é uma
contagem real); ficam `None` se o bairro não tiver nenhuma estação elegível.
Verificado nesta execução: **0 bairros sem estação associada**.

**Epidemiologia (`ausência = 0 casos`, decisão explícita e justificada)**:
notificação de arbovirose é **compulsória** e a ingestão de cada ano foi
100% bem-sucedida — a ausência de notificação para (bairro, semana, agravo)
significa genuinamente "nenhum caso notificado", não "não sei". Por isso o
grão completo é materializado com `casos=0` (necessário para qualquer
modelagem de série temporal: sem isso, o modelo só veria semanas com caso).
Semântica **diferente** da do clima de propósito: falha de telemetria é
desconhecimento, ausência de notificação compulsória é informação.

## ⚠️ Cobertura temporal — limitação crítica desta execução

A interseção real dos três domínios é **essencialmente vazia hoje**:

| Domínio | Cobertura real |
|---|---|
| Arboviroses | 2013 → 2025 (679 semanas epidemiológicas) |
| Território | atemporal (limites de 2023, aplicados a todo o período) |
| Clima — CEMADEN | **2026-08-18 → 2026-08-20** (3 dias) |
| Clima — APAC | 2015-01-23 → 2024-04-09, mas só **98 datas distintas** (instantâneos esparsos, rede congelada) |
| Clima — INMET | 2024 completo, mas **nenhuma estação em Recife** (mais próxima ~90 km) |
| **Interseção Gold (casos + clima real)** | **0 linhas (0,0000%)** |

Causa: o CEMADEN — hoje a fonte de 100% das associações bairro→estação
(Estratégia A) — só começou a acumular série no momento em que foi
integrado (2026-08), **depois** do fim da série epidemiológica disponível
(2025). Não é bug: é o estado real das fontes. As colunas climáticas
existem, o mecanismo está correto e testado (validado com dado sintético e
com o teste de leakage), mas ficam `None` em 100% das linhas históricas.

**Por que não misturamos INMET como proxy histórico**: seria necessário
atribuir a estações a ~90 km de Recife (Palmares, Garanhuns, Caruaru) o
papel de clima "do bairro", numa escala em que chuva convectiva é
localizada — exatamente o tipo de falsa precisão que este projeto evita.
Isso é uma decisão arquitetural relevante, não implementada sem
autorização explícita (conforme instrução da etapa: "não invente mistura de
fontes sem estratégia explícita"). A Gold foi produzida para o grão
epidemiológico completo, com a limitação climática registrada.

**Limitação adicional (associação retroativa)**: `silver_bairro_estacao`
representa a associação bairro→estação **de hoje** (estações ativas hoje) e
é aplicada a todos os anos. Se/quando houver histórico climático real
sobreposto aos casos, essa associação precisará ser reavaliada por período
— hoje não faz diferença prática (0% de sobreposição).

## Profiling

Completo em `profiling.json`. Destaques:

- `chave_gold_duplicadas`: **0**
- `casos.negativos`: **0**
- `clima.precipitacao_negativa`: **0**
- Missing 100% (todas as 191.478 linhas): as 7 colunas de valor de
  precipitação (consequência direta da limitação de cobertura acima).
- Missing 0%: todas as colunas de identificação, `casos`, território
  (`area_km2` etc.) e rastreabilidade de estação (`fonte_clima`,
  `codigo_estacao_clima`, `distancia_estacao_km`).

## Visualizações de validação

Geradas por `python -m src.analyze_gold` (matplotlib, backend `Agg` — só
PNG, sem janela nem dashboard):

| Arquivo | O que valida |
|---|---|
| `a_cobertura_temporal.png` | (A) Cobertura por domínio e a interseção — mostra visualmente o vazio climático |
| `b_casos_por_agravo.png` | (B) Série de casos por agravo — epidemiologicamente coerente: epidemia de dengue 2015-16, pico de Zika 2016, onda de chikungunya 2021 |
| `c_precipitacao.png` | (C) Precipitação no grão da Gold — sem dado real, informa isso explicitamente em vez de desenhar zeros |
| `d_casos_vs_precipitacao.png` | (D) Casos × precipitação (exploratório, não causal) |
| `e_mapa_casos_por_bairro.png` | (E) Coroplético com a geometria real de `silver_bairro_geo` |
| `f_completude.png` | (F) Completude das principais variáveis |

Dados tabulares de apoio: `cobertura_temporal.csv`, `metricas_por_bairro.csv`.

## Problemas encontrados durante a implementação

1. **Espaço de códigos de bairro incompatível** entre arboviroses e
   território (21/94) — resolvido usando nome normalizado; se não tivesse
   sido verificado, o join sairia silenciosamente errado.
2. **Bug de normalização no join** (encontrado por teste próprio antes de
   rodar em dados reais): o merge preservava o `nome_bairro` bruto da
   notificação, fazendo "Boa Viagem" e "boa viagem" contarem como bairros
   diferentes e quebrando a conservação de casos. Corrigido — o nome
   canônico é sempre o oficial.
3. **Feature de "dias com chuva" mascarava missing como zero**: comparação
   com `NaN` retorna `False`, então uma semana sem nenhuma leitura contaria
   "0 dias de chuva" em vez de "sem dado" — violaria a regra `missing ≠ 0`.
   Corrigido com máscara explícita por completude.
4. **Performance**: a primeira versão calculava as estatísticas da semana
   com um laço Python por linha (4min28s). Reconhecido que a "própria
   semana" é matematicamente idêntica à janela retrospectiva de 7 dias já
   vetorizada — reuso em vez de recálculo: **4min28s → ~5s**.

## Testes

**32 testes novos** (12 do calendário epidemiológico, 16 da transformação
Gold, 4 do pipeline ponta a ponta). Suíte total: **217/217 passando**
(baseline anterior era 185, nenhuma regressão).

Cobrem: chave única e granularidade; conservação de casos; ausência de
many-to-many; normalização de nome de bairro; exclusões contadas (nome
nulo/fora dos oficiais, semana inválida); `missing ≠ 0` e `zero real = 0`;
**leakage** (injeção de dado futuro); reprodutibilidade (mesma entrada →
mesma Gold); idempotência do pipeline (duas execuções, resultado idêntico);
Gold sem `bairro_estacao` (features climáticas todas nulas, casos
corretos); e as fronteiras do calendário epidemiológico (semanas de 7 dias,
contíguas, 52/53 semanas, virada de ano).

## Recomendação para a próxima etapa

A Gold está estruturalmente correta, com grão consistente, chave única, sem
leakage e reproduzível — **pronta para EDA**. Mas a dimensão climática está
factualmente vazia para o período epidemiológico, então uma EDA de
correlação clima↔casos **não é possível hoje** com dado real.

Duas frentes possíveis (decisão do usuário, nenhuma iniciada):

1. **EDA completa da dimensão epidemiológica + territorial** (que tem 13
   anos de dado real e denso): sazonalidade, distribuição espacial,
   comparação entre agravos, bairros de maior carga.
2. **Resolver a lacuna climática histórica** antes da EDA integrada —
   decisão arquitetural explícita sobre usar INMET regional como proxy
   documentado, buscar outra fonte com histórico local, ou aguardar o
   CEMADEN acumular série (o que levaria anos para cobrir o passado — na
   prática não resolve o histórico).
