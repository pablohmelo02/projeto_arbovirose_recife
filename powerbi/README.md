# Camada Power BI — Recife Alerta

Exportação da Gold publicada para um modelo dimensional (esquema estrela),
pronto para o Power BI Desktop consumir sem precisar da Gold larga inteira
nem de nenhuma lógica Python. Gerada por `python -m src.export_powerbi_dataset`,
que só reformata (projeta colunas, dedup, cria chaves surrogate) — nenhum
join/agregação/cálculo novo acontece aqui; tudo já existe em
`dashboard/data/gold_arboviroses_clima_bairro.parquet` e
`dashboard/data/historical_priority_backtest.parquet`.

## Arquivos

`powerbi/data/`, em Parquet (recomendado — mais rápido e tipado) e CSV
(compatibilidade):

| arquivo | grão | linhas (execução real) |
|---|---|---|
| `dim_bairro` | 1 por bairro | 94 |
| `dim_tempo` | 1 por semana epidemiológica | 679 |
| `dim_agravo` | 1 por agravo | 3 |
| `fact_epidemiologia_semanal` | bairro × semana × agravo | 191.478 |
| `fact_clima_semanal` | bairro × semana (sem agravo) | 63.826 |
| `fact_priorizacao_backtest` | bairro × semana-alvo (só 2023-2025, candidato congelado) | 14.476 |
| `fact_associacao_climatica` | agravo × variável climática × lag (0-12) × tipo de série (casos/incidência) × bruta-ou-ajustada — **sem bairro/tempo** | ver execução real abaixo |
| `fact_projecao_2026` | agravo × semana (observado 2013-2025 + projeção 2026) — **sem bairro** | ver execução real abaixo |
| `data_freshness` | 1 por dataset monitorado (sem relacionamento) | variável |

`fact_associacao_climatica` e `fact_projecao_2026` são adições desta etapa
(item 28 do pedido de produto). Nenhuma das duas tem chave de bairro — a
análise climática e a projeção são Recife total, pelo mesmo motivo já
documentado no restante desta camada e em `docs/arquitetura_e_pipeline.md`
§19.1 (a grade climática só resolve 2-3 células para os 94 bairros).
`fact_associacao_climatica` não se relaciona com `dim_tempo` (não é um
fato semanal, é um resumo de associação por defasagem); `fact_projecao_2026`
se relaciona com `dim_tempo` normalmente, e por isso `dim_tempo` passa a
incluir também as semanas de 2026 quando essa tabela está presente.
`fact_projecao_2026` é **opcional**: se `dashboard/data/_forecast_2026.parquet`
não existir no momento da exportação, ela simplesmente não é gerada — as
demais 7 tabelas continuam saindo normalmente (degradação graciosa,
diferente do "fail closed" das 3 fontes originais).

## Como importar

1. Power BI Desktop → **Obter Dados** → **Pasta** → apontar para
   `powerbi/data/` → filtrar só os `.parquet` (ou importar os `.csv` se o
   conector de Parquet não estiver disponível na sua versão).
2. Carregar as tabelas presentes (7 a 9, dependendo da disponibilidade do
   forecast).
3. Criar os relacionamentos descritos em `modelo_semantico.md` (o Power BI
   tenta autodetectar por nome de coluna — confira `id_semana_epi` e
   `codigo_bairro` em cada fato antes de aceitar a sugestão automática).
4. Colar as medidas de `medidas_dax.md` (uma tabela de medidas dedicada,
   sem coluna, é a prática recomendada — crie uma tabela vazia "Medidas"
   se preferir não anexar todas ao `fact_epidemiologia_semanal`).

## Atualização

Rodar `python -m src.export_powerbi_dataset` sempre que a Gold publicada
mudar (nova ingestão epidemiológica trimestral, novo enriquecimento
climático ou populacional). O script recusa gravar (mantém os arquivos
anteriores) se qualquer portão de qualidade do star schema falhar — ver
`src/export_powerbi_dataset.py::validar_star_schema`.

## O que NÃO está aqui, de propósito

- **Probabilidade do modelo**: `fact_priorizacao_backtest.score_prioridade`
  é uma posição relativa (rank), nunca uma probabilidade — mesma regra do
  dashboard (`CLAUDE.md` §11). Não crie uma medida DAX que a reescale como
  "% de chance".
- **Categoria de risco (verde/amarelo/vermelho)**: não existe no dado
  fonte e não deve ser criada em DAX — vale também para
  `fact_associacao_climatica` e `fact_projecao_2026` (`validar_star_schema`
  recusa explicitamente qualquer coluna de probabilidade/risco nessas duas
  tabelas).
- **Retreino ou novo cálculo do candidato de ML**: `fact_priorizacao_backtest`
  é uma cópia read-only do backtest já validado
  (`dengue_onset_ranking_candidate_v1`, congelado). Mudar esse modelo está
  fora do escopo desta camada.
- **Causalidade climática**: `fact_associacao_climatica` publica correlação
  de Spearman por defasagem, nunca uma afirmação de causa — não crie uma
  medida DAX que a apresente como "efeito da chuva sobre os casos".
- **Incidência 2026**: `fact_projecao_2026` só tem `casos` — não existe
  estimativa municipal oficial do IBGE para a população de 2026, então não
  crie uma medida DAX que divida a projeção de casos por uma população
  estimada informalmente.
- **`.pbix`**: esta camada entrega dados prontos para importar, não um
  arquivo `.pbix` — nenhum foi gerado nem deve ser gerado automaticamente.

## Limitações herdadas da Gold (repetidas aqui para quem só vir o Power BI)

- População 2011-2021 e 2023-2025 é reconstrução/projeção deste projeto,
  não Censo — ver `tipo_populacao` em `fact_epidemiologia_semanal` e
  `reports/population/population_incidence_integration.md`.
- Cobertura climática de estação (`fact_clima_semanal`, colunas sem
  `_grade`) é real só a partir de 2024; as colunas `_grade` (reanálise
  ERA5/ERA5-Land) cobrem 2013-2025 mas com resolução espacial baixa
  (2-3 células para os 94 bairros) — ver `docs/arquitetura_e_pipeline.md` §19.1.
