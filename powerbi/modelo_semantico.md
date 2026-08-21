# Modelo semântico — esquema estrela

## Diagrama de relacionamentos

```
dim_bairro (94)                dim_tempo (679)              dim_agravo (3)
codigo_bairro (PK)             id_semana_epi (PK)           agravo (PK)
     |  1                           |  1                          |  1
     |                              |                              |
     *                              *                              *
     +-------- fact_epidemiologia_semanal (codigo_bairro, id_semana_epi, agravo) FKs
     |
     *                              *
     +-------- fact_clima_semanal (codigo_bairro, id_semana_epi) FKs
     |
     *                              *
     +-------- fact_priorizacao_backtest (codigo_bairro, id_semana_epi) FKs

data_freshness -- tabela solta, sem relacionamento (metadados de atualidade)
```

Todos os relacionamentos são **1 (dimensão) para * (fato)**, filtro num
único sentido (dimensão → fato) — nenhum many-to-many. `fact_clima_semanal`
não se relaciona com `dim_agravo` porque clima não depende de agravo (ver
"Por que 3 fatos, não 1" abaixo).

## Tabelas

### `dim_bairro` (94 linhas, chave `codigo_bairro`)

| coluna | tipo | descrição |
|---|---|---|
| `codigo_bairro` | texto | código interno do território (PK) — não é o código IBGE |
| `nome_bairro` | texto | nome normalizado (maiúsculo, sem acento) |
| `codigo_rpa` | texto | Região Político-Administrativa (1-6) |
| `codigo_microrregiao` | texto | microrregião dentro da RPA |
| `area_km2` | decimal | área do bairro |
| `centroide_lat` / `centroide_lon` | decimal | centroide (EPSG:4326) — útil para mapa se não usar o GeoJSON |

### `dim_tempo` (679 linhas, chave `id_semana_epi`)

| coluna | tipo | descrição |
|---|---|---|
| `id_semana_epi` | inteiro | `ano_epidemiologico * 100 + semana_epidemiologica` (ex.: `202401` = SE 01/2024) |
| `ano_epidemiologico` | inteiro | ano da semana epidemiológica (convenção SVS/CDC, não ISO) |
| `semana_epidemiologica` | inteiro | 1-53 |
| `semana_epi_data_inicio` / `semana_epi_data_fim` | data | intervalo de datas da semana |

Marque esta tabela como **Tabela de Datas** no Power BI usando
`semana_epi_data_inicio` (Modelagem → Marcar como Tabela de Datas) se
quiser usar funções de inteligência de tempo do DAX — com a ressalva de
que a granularidade é semanal, não diária.

### `dim_agravo` (3 linhas, chave `agravo`)

Só a coluna `agravo` (`DENGUE`, `ZIKA`, `CHIKUNGUNYA`).

### `fact_epidemiologia_semanal` (191.478 linhas)

Grão: bairro × semana epidemiológica × agravo. Chave composta
`(id_semana_epi, codigo_bairro, agravo)`.

| coluna | tipo | descrição |
|---|---|---|
| `casos` | inteiro | contagem absoluta (`0` é valor real, não ausência) |
| `populacao_bairro_ano` | inteiro | população do bairro naquele ano (ver `tipo_populacao`) |
| `tipo_populacao` | texto | `CENSO_OBSERVADO` / `ESTIMATIVA_INTERCENSITARIA` / `PROJECAO_POS_CENSO` |
| `densidade_populacional_hab_km2` | decimal | `populacao_bairro_ano / area_km2` |
| `incidencia_100k` | decimal | casos da própria semana / população × 100.000 (`null` se população ausente) |
| `incidencia_4s_100k` / `8s` / `12s` | decimal | janela móvel de N semanas (soma de casos ÷ população × 100.000) |
| `incidencia_anual_100k` | decimal | janela móvel de 52 semanas (não é "ano civil completo" — ver `src/gold/populacao.py`) |

### `fact_clima_semanal` (63.826 linhas)

Grão: bairro × semana epidemiológica (**sem agravo** — o clima é o mesmo
para as 3 doenças na mesma semana/bairro; manter em grão de agravo
triplicaria a tabela sem motivo). Duas famílias de colunas, nunca
misturadas:

- **Estação** (CEMADEN, real só a partir de 2024): `precipitacao_total_semana_mm`,
  `chuva_7d_mm`...`chuva_28d_mm`, `dias_com_dado_valido_semana`, etc.
- **Grade/reanálise** (ERA5/ERA5-Land, 2013-2025, resolução baixa — ~2-3
  células para os 94 bairros): colunas com sufixo `_grade`.

### `fact_priorizacao_backtest` (14.476 linhas, só 2023-2025)

Backtest do candidato **congelado** `dengue_onset_ranking_candidate_v1`
(ver `reports/ml/dengue_ranking_evidence_validation.md`). `ranking` e
`score_prioridade` são posição/score relativo — nunca probabilidade.
`cutoff_epi_year`/`cutoff_epi_week` identificam a semana em que a
priorização foi calculada (pode ser semanas antes de `id_semana_epi`, que
é a semana-alvo) — mantidos como colunas simples, sem relacionamento
próprio com `dim_tempo`, para não exigir uma segunda relação ativa/inativa
na mesma tabela.

### `data_freshness`

Uma linha por dataset monitorado (`epidemiologia`, `território`, `clima`),
com `status` (`ATUAL`/`ATRASADO`) e `atraso_dias`. Sem relacionamento —
consumir via cartão/tabela solta, não via slicer cruzado com os fatos.

## Por que 3 fatos, não 1

Uma única fato larga (grão bairro×semana×agravo com as colunas de clima
replicadas 3× e o backtest só existindo para 3 dos 13 anos, cheio de nulo
fora de 2023-2025) violaria a prática de esquema estrela de não misturar
grãos diferentes numa mesma tabela — o Power BI otimiza agregação por
tabela de fato de grão único, e medidas ficam mais simples sem precisar de
`DISTINCT`/deduplicação dentro do DAX.

## Convenções

- Chaves são sempre **texto ou inteiro simples** (nunca chave composta
  concatenada em runtime) — `id_semana_epi` é a única surrogate key deste
  modelo, criada porque `(ano, semana)` são duas colunas e o Power BI só
  relaciona por uma.
- Nenhuma coluna de fato duplica uma coluna de dimensão (ex.: `nome_bairro`
  não aparece em nenhum fato — sempre via relacionamento).
