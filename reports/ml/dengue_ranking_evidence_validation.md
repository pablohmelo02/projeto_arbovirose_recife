# Validação estatística da evidência — ranking territorial preventivo de dengue

**Candidato avaliado:** `dengue_onset_ranking_candidate_v1`
**Data da execução:** 2026-08-20
**Commit de partida:** `c3933b4` (Gold analítica integrada)
**Suíte de testes na entrada desta etapa:** 331/331 passando
**Escopo desta etapa:** validar a evidência já existente. Nenhum retreino
exploratório, nenhuma feature nova, nenhum algoritmo novo, nenhum tuning,
nenhuma mudança de target ou de hiperparâmetro. Tudo o que segue é
reamostragem/agregação de um resultado de backtest **já obtido**.

> **Decisão preservada das etapas anteriores:** o ranking **não** foi
> integrado como funcionalidade operacional do dashboard público
> *Recife Alerta*. Esta etapa não reabre essa decisão; ela decide apenas se
> o componente pode ser apresentado como **prova de conceito experimental**.

---

## 1. Configuração congelada

Registrada em `reports/ml/resultado_evidence_validation_completo.json`
(seção `configuracao`) e reproduzida integralmente por
`python -m src.validate_dengue_onset_ranking_evidence`.

| Item | Valor congelado |
| --- | --- |
| Identificador | `dengue_onset_ranking_candidate_v1` |
| Agravo | DENGUE (único; Zika/Chikungunya não entram) |
| Unidade | bairro × semana epidemiológica (94 bairros do Recife) |
| Target | **onset**: "um novo episódio começa entre `t+1` e `t+3`?" (`src/ml/onset.py::construir_target_onset`, apenas a 1ª semana de cada episódio é positiva) |
| Horizonte | 3 semanas (`h=3`, escolhido na etapa anterior sobre `h=1`) |
| Features | 38 features: epidemiológica básica + sazonal + território + histórico local + momentum. **Sem clima** |
| Modelo | `HistGradientBoostingClassifier` (`max_depth=4`, `learning_rate=0.1`, `max_iter=150`) |
| Seeds | `random_state=42` (modelo) e `seed=42` (bootstrap) |
| Split temporal | treino 2013–2019 (29.328 linhas) · validação 2020–2022 · **teste 2023–2025 (14.476 linhas)** |
| Método de ranking | `construir_ranking_semanal`: posição 1 = maior score entre os bairros com previsão disponível naquela semana |
| Critério de episódio | `alert_metrics.construir_episodios` — semanas consecutivas com `estado_alto_risco=1` no mesmo bairro |
| Janela de avaliação | 4 semanas **estritamente anteriores** ao início real (`inicio-4` … `inicio-1`) |
| Episódios avaliados | **920** episódios reais em 2023–2025, distribuídos em 93 bairros |
| Reamostragens | 2.000 por intervalo |

**Reprodutibilidade verificada:** o pipeline foi executado duas vezes nesta
sessão; todas as seções de resultado pré-existentes saíram **idênticas**
(comparação campo a campo do JSON). O candidato é determinístico dadas as
seeds.

`candidato congelado` ≠ `modelo de produção`. É a versão que foi avaliada,
e é a única sobre a qual as afirmações da seção 12 se aplicam.

---

## 2. Metodologia estatística

**Unidade de reamostragem = episódio.** Semanas de um mesmo episódio não são
observações independentes; tratar cada linha semanal como i.i.d. estreitaria
artificialmente os intervalos. Cada linha do arquivo mestre
(`evidence_master_episodios.csv`, 920 linhas × 35 colunas) é **um episódio
real**, com uma coluna de detecção por método × K.

**Bootstrap percentil, 2.000 reamostragens, seed 42, IC 95%.** Três esquemas
de reamostragem foram usados:

1. **Por episódio** (principal): reamostra os 920 episódios com reposição.
2. **Por cluster `bairro`** (sensibilidade): reamostra bairros inteiros com
   reposição — preserva a correlação entre episódios do mesmo território
   (um bairro "difícil de rankear" tende a ser difícil em todos os seus
   episódios). Produz intervalos mais largos.
3. **Por cluster `bairro × ano`** (sensibilidade): unidade intermediária
   entre as duas anteriores.

**Comparação pareada.** O delta modelo × baseline usa **os mesmos índices
reamostrados nos dois lados** em cada repetição, sobre o **mesmo conjunto de
920 episódios**. Nunca se comparam amostras diferentes, e nunca se
reamostram os dois métodos de forma independente (o que infla a variância do
delta e pode inverter o sinal por acaso).

**Baselines comparados** (mesmos episódios, mesmas semanas, mesmo método de
ranking — só a coluna de score muda):

| Baseline | Score usado |
| --- | --- |
| `casos_atuais` | `casos_t` |
| `crescimento_recente` | `taxa_crescimento_suavizada` |
| `razao_historica_local` | `razao_limiar_historico` |

**Definição de detecção (Recall@K por episódio).** Um episódio é "capturado
antecipadamente em Top-K" se o bairro apareceu na posição ≤ K em **alguma**
das 4 semanas anteriores ao início real. Um destaque na **própria semana de
início nunca conta** — por construção da janela `[inicio-4, inicio-1]`.

---

## 3. Recall@K: modelo × baselines, com IC 95%

Fonte: `evidence_recall_ic.csv` · figura `evidence_a_recall_modelo_vs_baselines.png`
N = 920 episódios em todas as linhas.

| K | Modelo | `casos_atuais` | `crescimento_recente` | `razao_historica_local` |
| --- | --- | --- | --- | --- |
| **5** | **25,76%** [22,93–28,59] | 11,41% [9,46–13,48] | 18,37% [15,98–20,98] | 19,78% [17,28–22,39] |
| **10** | **38,37%** [35,22–41,52] | 20,43% [17,93–23,15] | 34,67% [31,52–37,83] | 35,76% [32,72–38,91] |
| **15** | 48,15% [44,89–51,52] | 29,78% [26,74–32,72] | **48,80%** [45,54–52,17] | 48,70% [45,54–51,96] |
| **20** | 57,61% [54,24–60,87] | 37,72% [34,56–40,87] | **63,15%** [60,00–66,30] | 57,93% [54,78–61,09] |

O melhor baseline **muda com K**: `razao_historica_local` em K=5 e K=10,
`crescimento_recente` em K=15 e K=20 — o comparativo sempre usa o melhor
baseline observado naquele K (o mais exigente possível para o modelo).

---

## 4. Ganho sobre o melhor baseline (métrica central desta etapa)

Fonte: `evidence_delta_vs_baseline.csv` · figura `evidence_b_delta_vs_baseline_ic.png`
`delta Recall@K = Recall@K(modelo) − Recall@K(melhor baseline naquele K)`.

| K | Melhor baseline | Delta observado | IC 95% (episódio) | IC 95% (cluster bairro) | IC 95% (cluster bairro×ano) | Leitura |
| --- | --- | --- | --- | --- | --- | --- |
| **5** | `razao_historica_local` | **+5,98 pp** | **[+2,83, +9,13]** | **[+1,89, +10,17]** | **[+2,40, +9,60]** | **Ganho defensável** — IC não cruza zero em nenhum dos 3 esquemas |
| **10** | `razao_historica_local` | +2,61 pp | [−0,76, +5,98] | [−1,82, +6,85] | [−1,14, +6,50] | **Inconclusivo** — IC cruza zero nos 3 esquemas |
| **15** | `crescimento_recente` | −0,65 pp | [−5,22, +3,91] | [−6,54, +4,95] | [−5,98, +4,68] | Empate estatístico |
| **20** | `crescimento_recente` | **−5,54 pp** | **[−10,11, −1,30]** | [−10,70, −0,32] | [−10,57, −0,53] | **Modelo estatisticamente PIOR** que a regra simples |

Este é o resultado mais importante da etapa, e ele **restringe** a conclusão
otimista da etapa anterior:

- O ganho do modelo é **estatisticamente defensável apenas em K=5**, e
  sobrevive às três formas de reamostragem (inclusive a mais conservadora,
  por bairro inteiro).
- Em **K=10** o ganho observado (+2,6 pp) é **compatível com zero** — a
  etapa anterior o descreveu como vantagem ("38,4% vs 35,8%"); com IC, ele
  não se sustenta como diferença.
- Em **K=20** o baseline `crescimento_recente` é **significativamente
  melhor** que o modelo. Resultado negativo, reportado sem atenuação.

---

## 5. Análise por ano (não escondida em média global)

Fonte: `evidence_por_ano.csv` · figura `evidence_c_por_ano.png`

| Ano de início | N episódios | Recall@5 modelo | Recall@5 baseline | Δ@5 | Recall@10 modelo | Recall@10 baseline | Δ@10 | Lead time mediano |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023 | 117 | 30,77% | 29,06% | +1,71 pp | 42,74% | 47,01% | **−4,27 pp** | 3 sem. |
| 2024 | 406 | 25,86% | 20,20% | +5,67 pp | 37,19% | 38,18% | **−0,99 pp** | 2 sem. |
| 2025 | 397 | 24,18% | 16,62% | **+7,56 pp** | 38,29% | 29,97% | **+8,31 pp** | 2 sem. |

**Achado central:** o ganho em **K=5 é positivo nos três anos** (+1,7 / +5,7
/ +7,6 pp) — consistente em sinal, variável em magnitude. Já o ganho em
**K=10 é negativo em 2023 e 2024 e positivo apenas em 2025**: o "+2,6 pp"
agregado de K=10 é essencialmente **um efeito de 2025**, não um ganho
consistente. Isso é exatamente a distinção que a seção 7 do pedido exigia, e
ela desqualifica K=10 como base para uma afirmação forte.

### Leave-one-year-out (sensibilidade, sem retreino)

Fonte: `evidence_leave_one_year_out.csv`. Só reavalia excluindo um ano do
conjunto de episódios — nenhum modelo é retreinado.

| Ano excluído | N episódios restantes | Recall@5 modelo | Recall@5 baseline | Δ@5 | Recall@10 modelo | Recall@10 baseline | Δ@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sem 2023 | 803 | 25,03% | 18,43% | +6,60 pp | 37,73% | 34,12% | +3,61 pp |
| sem 2024 | 514 | 25,68% | 19,46% | +6,23 pp | 39,30% | 33,85% | +5,45 pp |
| sem 2025 | 523 | 26,96% | 22,18% | +4,78 pp | 38,43% | 40,15% | **−1,72 pp** |

**Conclusão da sensibilidade temporal:** a superioridade em **K=5 não
depende de nenhum ano isolado** — removendo qualquer um dos três anos, o
delta permanece entre +4,8 e +6,6 pp. Em **K=10, remover 2025 inverte o
sinal** do delta (−1,7 pp), confirmando a leitura da tabela anual: o ganho
em K=10 é dependente de um único ano.

---

## 6. Análise territorial por RPA

Fonte: `evidence_por_rpa.csv` · figura `evidence_d_por_rpa.png`
Nenhum percentual sem o N que o sustenta.

| RPA | N episódios | Recall@5 | Recall@10 | Recall@20 |
| --- | --- | --- | --- | --- |
| 1 | 129 | 20,16% | 31,01% | 50,39% |
| 2 | 146 | 22,60% | 39,73% | 63,70% |
| 3 | 277 | 21,66% | 31,41% | 53,79% |
| 4 | 97 | 25,77% | 35,05% | 53,61% |
| **5** | 197 | **41,62%** | **59,39%** | **74,11%** |
| **6** | 74 | **14,86%** | **22,97%** | **33,78%** |

A disparidade regional apontada na etapa anterior **se confirma e é ampla**:
RPA 5 tem Recall@10 de 59,4% (n=197) contra 23,0% na RPA 6 (n=74) — 2,6x. As
demais RPAs ficam entre 31% e 40%. A RPA 6 é simultaneamente a de menor N
(74 episódios) e a de pior desempenho em todos os K. **Causa não
investigada** nesta etapa (seria trabalho de modelagem, fora do escopo).

---

## 7. Bairros críticos: limitação sistemática × amostra pequena

Fonte: `evidence_por_bairro.csv` · figura `evidence_i_por_bairro.png`

Dos 94 bairros, **93 tiveram ao menos um episódio** no teste. A distribuição
de episódios por bairro é confortável (mínimo 2, mediana 9, máximo 22), e
**apenas 1 bairro tem N ≤ 2** (COELHOS, n=2, Recall@20 = 50%). Ou seja: nesta
avaliação **quase não existe o artefato "percentual extremo por amostra
minúscula"** — os zeros observados são sobre amostras de tamanho utilizável,
o que os torna evidência de limitação sistemática, não ruído.

- **Zero detecção em Top-10: 16 bairros**, somando 98 episódios.
- **Zero detecção em Top-20: 2 bairros** — POÇO (n=8) e PONTO DE PARADA
  (n=3). Coincide com os dois bairros já identificados na etapa anterior.

Diagnóstico dos casos mais relevantes (posição = melhor colocação alcançada
na janela de 4 semanas antes do início):

| Bairro | N episódios | Detectados @10 | Detectados @20 | Melhor posição (mediana) | Faixa de posições | P(≤ detectados @20 \| Recall@20 global = 57,6%) |
| --- | --- | --- | --- | --- | --- | --- |
| **POÇO** | 8 | 0 | 0 | 44ª | 25ª – 66ª | 0,0010 |
| **IPSEP** | 6 | 0 | 1 | 39ª | 17ª – 65ª | 0,0531 |
| HIPÓDROMO | 10 | 0 | 1 | 35ª | 11ª – 63ª | 0,0027 |
| ILHA DO RETIRO | 9 | 0 | 1 | 26ª | 17ª – 68ª | 0,0058 |
| PONTO DE PARADA | 3 | 0 | 0 | 69ª | 52ª – 84ª | 0,0762 |

A última coluna é a probabilidade binomial de observar tão poucas detecções
se o bairro se comportasse como a média da cidade. É uma estatística de
**apoio, não um teste formal** — episódios do mesmo bairro não são
independentes, o que a torna otimista demais; ainda assim, para POÇO
(p≈0,001), HIPÓDROMO (p≈0,003) e ILHA DO RETIRO (p≈0,006) o padrão é
claramente sistemático, não sorte.

**IPSEP** (bairro de volume substancial, 1.629 casos acumulados, já flagado
nas duas etapas anteriores): 6 episódios, **nenhum** capturado em Top-10, um
único em Top-20, e a melhor posição mediana é a **39ª de ~94**. Não é efeito
de amostra pequena nem de percentual instável — o modelo simplesmente **não
coloca o IPSEP perto do topo** antes de seus episódios. É uma limitação
sistemática, e nesta etapa ela permanece sem explicação.

**PONTO DE PARADA** é o único caso em que a amostra (n=3) realmente impede
conclusão: p≈0,08 é compatível com azar.

---

## 8. Grandes episódios

Fonte: seção `grandes_episodios` do JSON · figura `evidence_f_grandes_episodios.png`
Definição já existente e documentada: **top 10% dos episódios por
`casos_totais_episodio`** → n = 92.

| Métrica | Grandes episódios (n=92) | Todos (n=920) |
| --- | --- | --- |
| Recall@5 | **18,48%** [10,87–27,17] | 25,76% [22,93–28,59] |
| Recall@10 | **30,43%** [20,65–40,22] | 38,37% [35,22–41,52] |
| Lead time mediano | 2 semanas | 2 semanas |

Os grandes episódios têm desempenho **pior** que a média em ambos os K (17
de 92 em Top-5; 28 de 92 em Top-10). Os ICs se sobrepõem parcialmente aos de
"todos", então a diferença não é conclusiva com n=92 — mas em nenhum cenário
os dados sustentam a leitura inversa (de que grandes episódios seriam mais
fáceis).

Isso **contrasta com a etapa de classificação binária**, onde epidemias
grandes tinham ~79% de detecção. A explicação já registrada permanece: o
ranking é **relativo entre os 94 bairros na mesma semana**; em epidemias
grandes vários bairros sobem juntos e competem pelo mesmo Top-K. Para o
desafio da Prefeitura este é um ponto desconfortável e não deve ser omitido:
**o cenário de maior impacto sanitário é onde a priorização por ranking
rende menos.**

---

## 9. Antecipação genuína × recaída

Fonte: seção `genuino_vs_recaida` do JSON · figura `evidence_g_genuino_vs_recaida.png`
Critério (já existente): um episódio é **recaída** se o bairro já estava em
`estado_alto_risco=1` no início da janela de 4 semanas; caso contrário é
**antecipação genuína**.

| K | Antecipação genuína (n=762) | Recaída (n=158) |
| --- | --- | --- |
| Recall@5 | **20,997%** [18,11–24,02] | 48,73% [41,14–56,33] |
| Recall@10 | **33,46%** [30,18–36,62] | 62,03% [54,43–69,62] |
| Recall@20 | **53,81%** [50,13–57,09] | 75,95% [68,99–82,28] |

O achado da etapa anterior se confirma com ICs que **não se sobrepõem em
nenhum K**: a antecipação genuína é o cenário **mais comum** (762/920 =
82,8%) e **claramente o mais difícil** — 33,5% vs 62,0% em Recall@10. A
posição mediana alcançada antes do início é **18,5ª** para episódios
genuínos contra **6ª** para recaídas.

Como o cenário prioritário do desafio é justamente detectar o início de algo
novo, **é sobre 33,5% (Top-10) / 21,0% (Top-5) que uma apresentação honesta
deve ser calibrada** — não sobre a média de 38,4% / 25,8%.

---

## 10. Lead time

Fonte: seção `lead_time_k10` do JSON · figura `evidence_e_lead_time.png`
Base: os **353 episódios detectados em Top-10**. A janela de avaliação é
`[inicio-4, inicio-1]`: **um destaque na própria semana de início nunca
conta como antecipação**, por isso `% ≥ 1 semana` é 100% por construção.

| Estatística | Valor |
| --- | --- |
| N (episódios detectados @10) | 353 |
| Média | 2,39 semanas |
| **Mediana** | **2 semanas** (IC 95% [2, 3]) |
| P25 / P75 | 1 / 3 semanas |
| Mínimo / Máximo | 1 / 4 semanas |
| % ≥ 1 semana | **100,0%** |
| % ≥ 2 semanas | **69,1%** |
| % ≥ 3 semanas | **45,6%** |

Por ano, a mediana é 3 semanas em 2023 e 2 semanas em 2024 e 2025. Entre
antecipação genuína e recaída a mediana é a mesma (2 semanas), com média
ligeiramente maior nos genuínos (2,53 vs 2,02) — quando o modelo acerta um
onset genuíno, a antecedência é comparável.

---

## 11. Carga operacional e estabilidade do Top-K

### Carga operacional

Fonte: `evidence_carga_operacional.csv`. Duas unidades distintas, nunca
misturadas: **episódio** (cobertura) e **priorização = bairro × semana**
(custo). Período: 154 semanas avaliadas.

| Cenário | Episódios antecipados | Episódios perdidos | Priorizações totais | Priorizações **sem** episódio futuro | % sem episódio futuro |
| --- | --- | --- | --- | --- | --- |
| **Top-5** (até 5 bairros/semana) | 237 / 920 (25,8%) | 683 | 770 | 504 | **65,5%** |
| **Top-10** | 353 / 920 (38,4%) | 567 | 1.540 | 1.080 | **70,1%** |
| Top-15 | 443 / 920 (48,2%) | 477 | 2.310 | 1.661 | 71,9% |
| Top-20 | 530 / 920 (57,6%) | 390 | 3.080 | 2.261 | 73,4% |

"Sem episódio futuro" usa o **target real de onset** da própria linha (não a
previsão): a fração das priorizações que, retrospectivamente, não
precederam nenhum início de episódio naquele bairro na janela `t+1..t+3`.
Nenhuma linha com alvo indefinido foi forçada a 0 (nesta execução houve 0
indefinidos). A leitura operacional é direta: **mesmo no cenário mais
restritivo (Top-5), cerca de 2 de cada 3 visitas priorizadas não são
seguidas por um início de episódio** — a priorização reduz o espaço de busca
de 94 para 5–10 bairros, mas não entrega uma lista "limpa".

### Estabilidade do Top-10

Fonte: seção `estabilidade_top10` + `evidence_estabilidade_top10_semanal.csv`
· figura `evidence_h_estabilidade_top10.png`

| Métrica | Valor |
| --- | --- |
| Pares de semanas consecutivas | 153 |
| Jaccard médio | **0,294** |
| Jaccard mediano | **0,250** |

Jaccard de 0,25–0,29 significa que, de uma semana para a seguinte,
tipicamente **apenas ~2 a 4 dos 10 bairros permanecem** na lista. Para
planejamento operacional isso é **volátil**: a lista serve para orientar a
semana corrente, não para montar um plano estável de várias semanas. A série
semanal mostra que a instabilidade é distribuída ao longo de todo o período,
não concentrada em um trecho.

---

## 12. Claims: o que os dados sustentam

| # | Afirmação | Avaliação | Justificativa |
| --- | --- | --- | --- |
| **A** | "O sistema prevê surtos de dengue." | **NÃO PERMITIDA** | O produto avaliado é um **ranking relativo** de bairros, não previsão de surto. Não há previsão de magnitude, data ou duração; grandes episódios têm desempenho pior (30,4% em Top-10); e o alvo é "início de episódio de risco elevado relativo ao próprio histórico do bairro", não "surto". |
| **B** | "O modelo identifica antecipadamente bairros prioritários." | **PERMITIDA COM RESSALVA** | Verdadeira apenas com: período (backtest 2023–2025), K explícito, taxa real (25,8% em Top-5 / 38,4% em Top-10 dos 920 episódios) e a ressalva de que **61,6% dos episódios não são capturados** em Top-10. Sem esses números, a frase sugere cobertura que não existe. |
| **C** | "Em backtest histórico, o modelo apresentou ganho sobre regras simples na priorização dos Top-10 bairros." | **NÃO PERMITIDA como está** | Em **K=10** o delta é +2,6 pp com IC [−0,8; +6,0] — **cruza zero**, e o sinal se inverte ao remover 2025. A frase só se torna **permitida com ressalva** se trocada para **Top-5**, onde o delta é +6,0 pp com IC [+2,8; +9,1], estável nos 3 anos e nos 3 esquemas de bootstrap. |
| **D** | "O sistema reduz a incidência da dengue." | **NÃO PERMITIDA** | Nenhum dado do projeto sustenta efeito causal sobre incidência. Não houve intervenção, grupo de controle ou avaliação de impacto — e o projeto **nem tem população por bairro** para calcular incidência. |
| **E** | "O sistema pode apoiar a priorização preventiva de recursos territoriais." | **PERMITIDA COM RESSALVA** | Sustentada como **hipótese de uso** com ganho medido em Top-5 e antecedência mediana de 2 semanas. Ressalvas obrigatórias: ~65% das priorizações não precedem episódio; lista instável entre semanas (Jaccard 0,29); forte disparidade territorial (RPA 5 vs RPA 6); pior desempenho justamente em antecipação genuína e em grandes episódios. |

### Proibições adicionais de linguagem

Não usar, em nenhum material: "previsão oficial", "probabilidade real de
surto", "X% de chance de surto", "sistema de alerta", "previsão de casos",
"reduz casos/óbitos", "acurácia de N%", categorias verde/amarelo/vermelho.
Ao exibir resultados, exibir **posição/ranking**, nunca probabilidade
calibrada como número de confiança absoluto.

---

## 13. Frase recomendada para a Prefeitura

Sustentada pelos números reais, calibrada em **Top-5** (o único cenário com
ganho estatisticamente defensável):

> Em validação retrospectiva de 2023–2025 (920 episódios reais de dengue em
> 93 bairros), considerando capacidade para priorizar até **5 bairros por
> semana**, o modelo identificou antecipadamente **25,8%** dos episódios
> avaliados (IC 95%: 22,9–28,6%), contra **19,8%** do melhor ranking simples
> — um ganho de **6,0 pontos percentuais** (IC 95%: +2,8 a +9,1) — com
> antecedência mediana de **2 semanas**.

Se a apresentação precisar do cenário de 10 bairros por semana, a formulação
honesta é outra, e **não afirma ganho**:

> Ampliando a capacidade para 10 bairros por semana, a antecipação sobe para
> 38,4% dos episódios (IC 95%: 35,2–41,5%), mas nesse cenário o ganho sobre
> o melhor ranking simples deixa de ser estatisticamente distinguível de
> zero (+2,6 pp; IC 95%: −0,8 a +6,0).

---

## 14. Classificação final da evidência

### **B — Evidência sugestiva, mas ainda incerta**

Justificativa do enquadramento em B e não em A:

**A favor (o que sustentaria A):** o ganho em **Top-5** é positivo e
significativo no agregado, **consistente em sinal nos três anos**,
**robusto às três formas de reamostragem** (episódio, cluster por bairro,
cluster por bairro×ano) e **não depende de nenhum ano isolado**
(leave-one-year-out entre +4,8 e +6,6 pp). O lead time é operacionalmente
útil (mediana 2 semanas, 69% ≥ 2 semanas). Tudo é reprodutível e determinístico.

**Contra (o que impede A):**

1. O ganho existe **apenas em K=5**. Em K=10 é inconclusivo; em K=20 o
   modelo é **significativamente pior** que uma regra simples.
2. Em K=5, o ganho é de 6 pp sobre uma base baixa: **74% dos episódios
   continuam não capturados**.
3. O cenário prioritário do desafio — **antecipação genuína** — é o pior
   (Recall@10 33,5% vs 62,0% em recaída), e é 82,8% dos casos.
4. **Grandes episódios** vão pior que a média (Recall@10 30,4%), justamente
   onde o impacto sanitário é maior.
5. **Disparidade territorial forte e inexplicada** (RPA 5: 59,4% × RPA 6:
   23,0% em Top-10) e limitações sistemáticas em bairros de volume
   relevante (IPSEP: 0/6 em Top-10; POÇO: 0/8 em Top-20).
6. **Instabilidade semanal alta** (Jaccard 0,29) e **65–70% de priorizações
   sem episódio futuro**.
7. Avaliação em **um único split temporal**; 2025 já foi usado como teste em
   etapa anterior, portanto **não é holdout puro**.

Não é C ("ganho não robusto"): há um ganho real, reprodutível e robusto a
reamostragem em Top-5. Não é D ("baseline é suficiente"): em Top-5 o
baseline é mensuravelmente inferior — embora em Top-15/20 D seja de fato a
leitura correta, e isso precisa ser dito.

---

## 15. Decisão de produto

### **SIM — funcionalidade experimental, fora do dashboard público**

- O componente **pode** ser apresentado como **prova de conceito
  experimental** para a Prefeitura, usando exclusivamente a frase da seção
  13 e os claims permitidos da seção 12.
- A decisão preservada das etapas anteriores **permanece**: o ranking **não**
  entra como funcionalidade operacional das 7 páginas do *Recife Alerta*, que
  seguem inalteradas.
- A visualização técnica foi implementada como **app separado**
  (`tools/model_validation_app.py`, executado com
  `streamlit run tools/model_validation_app.py`), **não** como oitava página
  do dashboard público. Motivo: é a alternativa com menor risco de confusão
  entre "material técnico de validação" e "produto operacional" — um usuário
  do painel público não encontra a página preditiva por navegação acidental.
  A página abre com o aviso *"Validação experimental — não representa
  ferramenta operacional de previsão"*, lê **apenas artefatos de backtest já
  calculados**, e nunca treina modelo, gera previsão futura ou exibe
  probabilidade operacional.
- Se, numa etapa futura de produto, o ranking for integrado ao dashboard,
  ele deve entrar rotulado como **"Priorização Experimental"**, exibindo
  **posição/ranking retrospectivo**, com K explícito e as ressalvas da seção
  12 visíveis na própria página.

---

## 16. Limitações desta validação

- **Não é validação prospectiva.** Todo o resultado é retrospectivo, sobre
  dados já conhecidos, num único split temporal (2023–2025). 2025 já havia
  sido usado como teste antes: **não é holdout puro**.
- **O bootstrap quantifica incerteza amostral, não erro de especificação.**
  Não cobre mudança de regime epidemiológico, mudança de notificação, nem
  drift futuro.
- **A estatística binomial da seção 7 é de apoio**, não um teste formal:
  assume independência entre episódios do mesmo bairro, o que não vale.
- **O target é relativo ao histórico do próprio bairro** (P90
  histórico-sazonal). "Episódio de risco elevado" ≠ "surto"; um bairro de
  baixo volume pode ter episódio com poucos casos absolutos.
- **Sem população por bairro**, logo sem incidência: todas as métricas são
  em contagem absoluta.
- **Clima permanece fora** do modelo avaliado (decisão da etapa de baseline,
  não revisitada aqui).
- **Nenhuma causa foi investigada** nesta etapa para a disparidade RPA
  5/RPA 6, para o caso IPSEP, nem para a dificuldade da antecipação genuína —
  são achados, não diagnósticos.

---

## 17. Artefatos

**Dados/resultados** (`reports/ml/`): `resultado_evidence_validation_completo.json`,
`evidence_master_episodios.csv` (920 episódios × 35 colunas — unidade de todo
o bootstrap), `evidence_recall_ic.csv`, `evidence_delta_vs_baseline.csv`,
`evidence_por_ano.csv`, `evidence_leave_one_year_out.csv`,
`evidence_por_rpa.csv`, `evidence_por_bairro.csv`,
`evidence_carga_operacional.csv`, `evidence_estabilidade_top10_semanal.csv`.

**Figuras** (`reports/ml/`, geradas por `python -m src.plot_evidence_validation`):

| Figura | Arquivo |
| --- | --- |
| A. Modelo × baselines (Recall@5/10/15/20, IC) | `evidence_a_recall_modelo_vs_baselines.png` |
| B. Delta modelo × baseline com IC | `evidence_b_delta_vs_baseline_ic.png` |
| C. Desempenho por ano | `evidence_c_por_ano.png` |
| D. Desempenho por RPA | `evidence_d_por_rpa.png` |
| E. Lead time | `evidence_e_lead_time.png` |
| F. Grandes episódios | `evidence_f_grandes_episodios.png` |
| G. Antecipação genuína × recaída | `evidence_g_genuino_vs_recaida.png` |
| H. Estabilidade do Top-10 | `evidence_h_estabilidade_top10.png` |
| I. Desempenho por bairro | `evidence_i_por_bairro.png` |

**Reprodução completa:**

```bash
python -m src.validate_dengue_onset_ranking_evidence   # estatística (determinístico, seed 42)
python -m src.plot_evidence_validation                 # figuras A-I
streamlit run tools/model_validation_app.py            # visualização técnica experimental
```

**Encerramento:** com esta etapa, a pesquisa de ML desta versão está
concluída. Qualquer alteração posterior de modelo, feature, target ou
hiperparâmetro cria uma **nova versão** e exige nova validação — os
resultados acima valem exclusivamente para
`dengue_onset_ranking_candidate_v1`.
