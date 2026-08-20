# EDA — Arboviroses × Território × Clima (Recife)

> Relatório reproduzível, gerado por `python -m src.generate_eda_report`
> (`src/eda/relatorio.py`), a partir do mesmo dataset estático que alimenta
> o dashboard Streamlit (`dashboard/data/gold_arboviroses_clima_bairro.parquet`,
> ver `src/export_dashboard_dataset.py`). Todos os números abaixo vêm de
> `resumo.json` e dos CSVs nesta pasta — nenhum é estimado à mão.

## Escopo e período

Duas janelas de análise, deliberadamente não misturadas (ver
`src/eda/schema_eda.py::ANO_INICIO_COBERTURA_CLIMATICA_REAL`):

| Janela | Período | Domínios | Linhas Gold |
|---|---|---|---:|
| **EDA histórica** | 2013–2025 (679 semanas epidemiológicas) | Epidemiologia + território | 191.478 |
| **EDA integrada** | 2024–2025 | Epidemiologia + território + clima real | 11.709 (6,12% do total) |

**2013–2023 nunca têm clima real** — nenhum gráfico ou achado desta etapa
atribui clima a esses anos.

## Cobertura climática real por ano

| Ano | Linhas | Linhas com clima real | % linhas | Bairros com clima real | % bairros |
|---:|---:|---:|---:|---:|---:|
| 2013–2023 | 14.664–14.946/ano | 0 | 0,00% | 0/94 | 0,00% |
| **2024** | 14.664 | 3.915 | **26,70%** | **90/94** | **95,74%** |
| **2025** | 14.946 | 7.794 | **52,15%** | **65/94** | **69,15%** |

Ver `cobertura_climatica_por_ano.csv` e
`reports/climate_source_analysis/cemaden_historical_backfill_analysis.md`
para a investigação completa de profundidade histórica do CEMADEN.

## Estatísticas gerais (2013-2025)

- **156.504 casos** de arboviroses preservados na Gold (94 bairros, 3 agravos, 679 semanas).
- Por agravo: **DENGUE 109.792** · **CHIKUNGUNYA 39.552** · **ZIKA 7.160**.
- 94/94 bairros com pelo menos 1 caso notificado no período completo.
- 90/94 bairros têm clima real em algum período (só 2024-2025; ver limitação abaixo).

## Padrões observados (2013-2025)

### 1. Quais são os principais padrões epidemiológicos?

- Série claramente não estacionária, com picos concentrados por doença
  (ver `comparacao_agravos.csv` e o painel "Epidemiologia" do dashboard):
  epidemia de dengue em 2015-2016, pico de Zika em 2016 (coincidente com a
  introdução do vírus no Brasil), onda de chikungunya em 2021, e nova
  alta de dengue em 2024-2025.
- **Ano com mais casos de arboviroses no total: 2015.**

### 2. Quais bairros apresentam maior carga?

Top bairros por casos totais (2013-2025, todos os agravos —
`ranking_bairros_geral.csv`): **COHAB (8.836)**, **IBURA (8.408)**,
**VÁRZEA (6.334)**, **ÁGUA FRIA (5.667)**, seguidos por Iputinga,
Imbiribeira, Boa Viagem, Nova Descoberta, Campo Grande e Afogados —
bairros densamente povoados e/ou de urbanização mais antiga da zona
oeste/norte do Recife. **Sem incidência por 100 mil** (nenhuma fonte do
projeto tem população por bairro) — este ranking é de volume absoluto, não
de taxa.

### 3. Como os três agravos diferem temporalmente?

- **Dengue**: presença quase contínua, com picos muito mais altos que os
  outros dois agravos (escala de milhares de casos/semana no auge de 2015).
- **Zika**: concentrado quase inteiramente em 2016 (ano de introdução/
  epidemia), depois cai para um nível residual baixo.
- **Chikungunya**: onda tardia e concentrada, com pico claro em 2021 —
  padrão temporal distinto dos outros dois.

### 4. Existe sazonalidade visível?

Sim — a semana epidemiológica com maior número médio de casos (agregando
os 13 anos) é a **semana 11** (~fevereiro/março, 356,5 casos/ano em média),
com um platô elevado aproximadamente entre as semanas 8 e 25 (verão/outono
no hemisfério sul, período mais chuvoso no Recife) e queda pronunciada no
segundo semestre. **Descrição do padrão observado, não inferência causal
sobre chuva** (a EDA integrada com clima real só cobre 2024-2025, ver
seção seguinte).

## EDA integrada (2024-2025): clima real × arboviroses

### 5. Qual a cobertura climática real em 2024 e 2025?

Ver tabela acima — **26,70%/95,74%** (linhas/bairros) em 2024 e
**52,15%/69,15%** em 2025. A cobertura não é homogênea nem no tempo nem no
espaço (ver heatmap ano×semana e mapa de completude no dashboard, página
"Clima").

### 6-8. Qual janela de lag tem maior associação exploratória? É consistente entre agravos? Quantas observações sustentam isso?

Correlação de Pearson entre `casos` e `chuva_{7,14,21,28}d_mm`, só sobre
observações com clima real (`correlacoes_lag_*.csv`):

| Agravo | 7d | 14d | 21d | 28d | n (28d) |
|---|---:|---:|---:|---:|---:|
| DENGUE | 0,0513 | 0,0751 | 0,1019 | **0,1194** | 4.137 |
| CHIKUNGUNYA | 0,0288 | 0,0389 | 0,0506 | **0,0518** | 4.137 |
| ZIKA | 0,0071 | 0,0164 | 0,0235 | **0,0289** | 4.137 |

**Padrão consistente entre os 3 agravos**: a correlação cresce com a
janela de lag (28d > 21d > 14d > 7d) — mas em magnitude **fraca** em todos
os casos (todas < 0,12). Todas as janelas têm amostra "confiável" no
sentido definido aqui (**n ≥ 30**, na prática n > 3.900 em todas) — mas
"confiável" não é um teste de significância estatística formal, e a
magnitude fraca da correlação já limita qualquer conclusão por si só.

**Isso não implica causalidade** e não deve ser generalizado além de
2024-2025 — é a única janela com dado real disponível.

### 9. Quantas observações sustentam cada resultado?

Explicitamente reportado em cada tabela/gráfico (nunca omitido): a EDA
integrada usa entre **3.903 e 4.137 observações** (bairro×semana×agravo
com leitura climática real), de um total de 191.478 linhas na Gold — ou
seja, a EDA integrada usa ~2% do volume total da Gold histórica.

## Limitações

1. **Janela climática curta**: só 2024-2025 têm clima real (backfill de
   730 dias do CEMADEN) — 2013-2023 não têm nenhuma leitura real. Isso é
   uma limitação de disponibilidade de fonte, não um artefato de cálculo
   (ver relatório de backfill).
2. **Sem incidência por 100 mil**: nenhuma fonte do projeto tem população
   por bairro — todo ranking/mapa usa contagem absoluta.
3. **Viés de disponibilidade**: a cobertura climática não é uniforme entre
   bairros (14/94 têm estação própria, os demais usam a estação elegível
   mais próxima, distância mediana ~1,4 km) nem entre semanas — qualquer
   correlação observada pode refletir parcialmente onde/quando há sensor,
   não apenas o fenômeno físico.
4. **Correlação ≠ causalidade**: nenhum teste de significância formal,
   nenhum controle por sazonalidade ou autocorrelação temporal foi
   aplicado — são estatísticas descritivas exploratórias.
5. **N pequeno relativo ao todo**: a EDA integrada usa uma fração pequena
   (~2%) do volume total de casos da Gold.

## Hipóteses para modelagem futura (não implementadas nesta etapa)

- Lags mais longos (14-28 dias) mostraram correlação exploratória
  consistentemente maior que lags curtos (7 dias) para os 3 agravos —
  candidato a feature preditiva, a validar com mais dado histórico.
  Dengue foi o agravo com maior correlação exploratória entre os três.
- Sazonalidade forte e recorrente (pico ~semana 11) é candidata a feature
  de calendário (seno/cosseno de semana epidemiológica, ou variável
  categórica de "período do ano") independente do clima.
- Bairros de maior carga histórica (COHAB, Ibura, Várzea, Água Fria)
  poderiam receber peso/prior espacial numa futura modelagem territorial.
- Nenhuma seleção final de features foi feita aqui — isso é uma decisão de
  modelagem, fora do escopo desta etapa (ver regra de parada).

## Observação vs. hipótese

Esta EDA distingue explicitamente três tipos de achado (ver `resumo.json`,
campo `achados[].tipo`):

- **observação**: fato direto dos dados (ex.: "2015 foi o ano com mais
  casos").
- **hipótese**: padrão exploratório que sugere investigação futura, mas
  não é conclusivo (ex.: correlação lag×casos).
- **limitação**: restrição que impede uma conclusão mais forte.

Nenhuma "hipótese" desta lista deve ser lida como "achado confirmado".

## Arquivos deste relatório

`resumo.json` (KPIs + achados estruturados), `sazonalidade_semanal.csv`,
`comparacao_agravos.csv`, `ranking_bairros_geral.csv`,
`cobertura_climatica_por_ano.csv`, `correlacoes_lag_{dengue,zika,chikungunya}.csv`.
