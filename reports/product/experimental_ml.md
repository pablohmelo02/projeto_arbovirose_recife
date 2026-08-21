# Módulo experimental de priorização — o que ele é e o que ele não é

**Documento para gestão.** A análise técnica completa está em
`reports/ml/dengue_ranking_evidence_validation.md` (validação estatística) e
`reports/ml/dengue_ranking_clima_experiment.md` (experimento climático).

> **Módulo experimental.** Resultados retrospectivos e sinais de priorização
> não substituem avaliação epidemiológica nem representam previsão oficial
> da Prefeitura do Recife.

---

## 1. O que o modelo faz

Para cada bairro, em cada semana, ele responde a **uma** pergunta:

> *Considerando tudo o que se sabe até o fim desta semana, qual a chance
> relativa de um novo episódio de risco elevado de dengue começar nas
> próximas três semanas neste bairro — comparada aos outros 93 bairros?*

O resultado é uma **ordem de prioridade** entre os bairros da mesma semana.
Não é um número de risco absoluto, não é uma contagem prevista de casos, e
não é uma classificação de "bairro perigoso".

---

## 2. Como ele é apresentado — e por quê

| Publicado | Não publicado | Motivo |
|---|---|---|
| Posição no ranking (1º, 2º, …) | Probabilidade do modelo | A validação mostrou que a probabilidade não deve ser comunicada como grau de confiança: o desempenho varia muito entre anos e entre territórios. |
| Score de prioridade 0–100 | "83 % de chance de surto" | O score é **posto relativo normalizado dentro da semana** (100 = topo daquela semana), calculado por ordenação, não por reescala de probabilidade — justamente para não poder ser lido como percentual de chance. |
| Faixas Top-5 / 10 / 15 / 20 | Uma faixa única "recomendada" | A capacidade operacional é do gestor, e o desempenho **muda** com ela. |
| — | Categoria verde/amarelo/vermelho | Categorizar risco exigiria uma validação que não existe. A paleta do produto não tem sequer as cores de semáforo. |

---

## 3. Ficha técnica do candidato congelado

| Campo | Valor |
|---|---|
| Identificador | `dengue_onset_ranking_candidate_v1` |
| Alvo | início de novo episódio de risco elevado em `t+1` a `t+3` |
| Definição de "risco elevado" | casos acima do percentil 90 do histórico do **próprio bairro** na mesma época do ano, usando só anos anteriores |
| Features | 38, **sem clima** |
| Algoritmo | `HistGradientBoostingClassifier` (`max_depth=4`, `lr=0.1`, `max_iter=150`, semente 42) |
| Treino | 2013–2019 (29.328 linhas) |
| Validação | 2020–2022 |
| Teste | 2023–2025 (14.476 linhas, 920 episódios reais em 93 bairros) |
| Corte do treino | SE 52 / 2019 |
| Reprodutibilidade | verificada: duas execuções, resultado idêntico campo a campo — e reconfirmada após o enriquecimento climático da Gold |

**Congelado** significa: nenhum retreino exploratório, nenhuma mudança de
alvo, feature, algoritmo ou hiperparâmetro. Qualquer mudança cria uma
**versão nova** e exige validação própria — os números abaixo não podem ser
reaproveitados.

---

## 4. O resultado central, sem arredondar para cima

Métrica: *em quantos episódios reais o bairro apareceu entre os K primeiros
do ranking em alguma das 4 semanas anteriores ao início observado?*
Bootstrap ao nível de **episódio** (2.000 reamostragens, semente 42), porque
semanas do mesmo episódio não são independentes.

| K | Modelo | Melhor regra simples | Diferença | IC 95 % | Leitura |
|---|---|---|---|---|---|
| **5** | **25,76 %** | 19,78 % | **+5,98 pp** | **[+2,83; +9,13]** | **Ganho robusto** — IC não cruza zero, e também não cruza nos dois esquemas de cluster |
| 10 | 38,37 % | 35,76 % | +2,61 pp | [−0,76; +5,98] | **Inconclusivo** — IC cruza zero |
| 15 | 48,15 % | 48,80 % | −0,65 pp | [−5,22; +3,91] | **Empate** — regra simples é competitiva |
| 20 | 57,61 % | 63,15 % | **−5,54 pp** | **[−10,11; −1,30]** | **Regra simples é melhor** de forma detectável |

**Por ano (Top-5):** +1,71 pp (2023) · +5,67 pp (2024) · +7,56 pp (2025) —
positivo nos três.

**Por ano (Top-10):** −4,27 pp (2023) · −0,99 pp (2024) · +8,31 pp (2025) —
o resultado agregado depende de um único ano. Excluir 2025 **inverte o
sinal**. Excluir qualquer ano mantém o ganho de Top-5 entre +4,8 e +6,6 pp.

**Interpretação honesta:** o valor do modelo está concentrado no cenário
operacional mais restritivo. Se a Prefeitura tiver capacidade para priorizar
cinco bairros por semana, o modelo ajuda de forma mensurável. Se tiver
capacidade para vinte, uma regra simples de crescimento recente é melhor —
e o painel diz isso.

---

## 5. Antecipação

Medida em **Top-10**, período 2023–2025, sobre os 353 episódios detectados
nessa faixa:

| Métrica | Valor |
|---|---|
| Antecedência mediana | **2 semanas** (IC 95 %: 2–3) |
| Média | 2,39 semanas |
| P25 / P75 | 1 / 3 semanas |
| ≥ 2 semanas | 69,1 % |
| ≥ 3 semanas | 45,6 % |

A janela de avaliação vai de 4 a 1 semanas antes do início observado: um
destaque na própria semana de início **nunca** conta como antecipação. Por
isso "≥ 1 semana = 100 %" é verdade por construção e não é apresentado como
resultado.

**Esta medida é de Top-10 e não deve ser combinada com a afirmação de ganho
de Top-5** — são faixas diferentes.

---

## 6. Onde o modelo é fraco — com números

### 6.1 Disparidade territorial

| RPA | Episódios (N) | Top-10 |
|---|---|---|
| 5 | 197 | **59,4 %** |
| 2 | 146 | 39,7 % |
| 4 | 97 | 35,1 % |
| 3 | 277 | 31,4 % |
| 1 | 129 | 31,0 % |
| **6** | **74** | **23,0 %** |

Diferença de ~36 pontos percentuais entre a melhor e a pior RPA. **A causa
não foi investigada.**

Amostra pequena está praticamente descartada como explicação: 93 dos 94
bairros tiveram ao menos um episódio no período, e apenas 1 tem N ≤ 2
(mediana 9, máximo 22). Os zeros observados são sobre amostras utilizáveis —
evidência de limitação sistemática, não de percentual instável.

Caso concreto: **IPSEP** (RPA 6), bairro de volume substancial, teve 6
episódios no período e **0 % de detecção em Top-10**, com melhor posição
mediana **39ª de ~94**.

### 6.2 O cenário mais importante é o pior

Separando episódios que começam após um período sem atividade ("início
genuíno") dos que ocorrem logo após atividade recente ("recaída"):

| | N | Top-5 | Top-10 | Top-20 |
|---|---|---|---|---|
| Início genuíno | **762** (82,8 %) | 21,0 % | **33,5 %** | 53,8 % |
| Recaída | 158 | 48,7 % | **62,0 %** | 75,9 % |

Os intervalos de confiança **não se sobrepõem em nenhuma faixa**. O cenário
mais comum e mais relevante para a Prefeitura — detectar algo que está
**começando** — é justamente o mais difícil.

### 6.3 Grandes episódios têm desempenho pior

| K | Grandes episódios (N=92) | Todos (N=920) |
|---|---|---|
| 5 | 18,5 % | 25,8 % |
| 10 | **30,4 %** | **38,4 %** |

Sob **ranking**, um grande episódio é mais difícil, não mais fácil: numa
epidemia ampla vários bairros sobem ao mesmo tempo e competem pelas mesmas K
posições.

**Aviso explícito:** uma etapa anterior deste projeto, com formulação de
classificação binária, mediu ~79 % de detecção em epidemias grandes. **Esse
número não se aplica a este módulo** e não é reaproveitado em nenhum lugar
do painel ou da documentação. Cada métrica está vinculada à versão que a
produziu.

### 6.4 A lista muda muito de uma semana para a outra

Sobreposição (índice de Jaccard) do Top-10 entre semanas consecutivas, em
153 pares: **média 0,294 · mediana 0,25**. Na prática, apenas ~2 a 4 dos 10
bairros permanecem de uma semana para a seguinte.

### 6.5 O custo operacional é alto

| K | Episódios antecipados | Priorizações totais | Sem episódio na sequência |
|---|---|---|---|
| 5 | 237 de 920 (25,8 %) | 770 | **65,5 %** |
| 10 | 353 de 920 (38,4 %) | 1.540 | 70,1 % |
| 15 | 443 de 920 (48,2 %) | 2.310 | 71,9 % |
| 20 | 530 de 920 (57,6 %) | 3.080 | 73,4 % |

Duas unidades diferentes, de propósito: **episódio** (quantos surtos foram
antecipados) e **priorização** (quantas visitas bairro × semana o ranking
pede). A última coluna é o custo real.

---

## 7. O clima acrescenta valor? Experimento controlado

Comparação A × B: mesmas linhas, mesmo split, mesmo algoritmo, mesmos
hiperparâmetros — variando **apenas** a presença de 8 variáveis climáticas
em grade (precipitação semanal e acumulados de 2/3/4 semanas, temperatura
média/mínima/máxima, umidade relativa).

**Critério declarado antes de rodar:** incorporar o clima só se o ganho em
**Recall@5** tiver IC que não cruza zero **e** sinal positivo em todos os
anos do teste.

| K | Diferença B−A | IC 95 % (episódio) | IC (cluster bairro) | Positivo em todos os anos? |
|---|---|---|---|---|
| **5** | **−0,11 pp** | **[−2,28; +2,07]** | [−2,46; +2,23] | **Não** (2024 negativo) |
| 10 | +2,83 pp | [+0,43; +5,33] | [+0,21; +5,34] | Sim |
| 15 | +3,37 pp | [+0,98; +5,87] | [+0,74; +5,92] | — |
| 20 | +1,96 pp | [−0,11; +4,24] | [−0,44; +4,22] | — |

**Decisão: o clima NÃO foi incorporado ao modelo do produto.** As duas
condições do critério falharam em K=5.

**Achado secundário, reportado por transparência:** em K=10 o ganho é
consistente e o IC não cruza zero em nenhum dos três esquemas de
reamostragem — e, com clima, o modelo passa a superar a melhor regra simples
também nessa faixa (+5,43 pp, IC [+1,96; +9,02]). Hipótese plausível: o
clima em grade não diferencia bairros (produz no máximo **2 valores
distintos entre os 94 bairros na mesma semana**), mas diferencia **semanas** —
o que ajuda a decidir *quando* elevar vários bairros, não *qual* elevar.

Isso fica registrado como **candidata a uma versão futura**
(`..._candidate_v2`), que exigiria o protocolo completo de validação
(leave-one-year-out, análise territorial, lead time, estabilidade, carga
operacional). **Não é resultado.** Mudar o critério depois de ver o número
seria racionalização *post hoc*.

O bloco climático **permanece na Gold**: ele é valioso para descrição e para
a página Clima × Dengue (que passou a cobrir 2013–2025 em vez de só
2024–2025), mesmo sem entrar no modelo.

---

## 8. Estado operacional atual

| Item | Situação |
|---|---|
| Backtest navegável (2023–2025, 154 semanas, 14.476 linhas) | **Disponível** |
| Priorização do período atual | **Indisponível** — dado oficial ~32 semanas atrás do presente, acima do limite de 4 semanas |
| Motivo registrado | `epidemiological_data_stale` |
| Comportamento do painel | oferece apenas a simulação histórica, com explicação do bloqueio |

---

## 9. Classificação e recomendação

**Classificação: B — evidência sugestiva, mas ainda incerta.**

**Recomendação:** manter como **funcionalidade experimental**, apresentada
com todas as limitações desta página, útil para:

- demonstrar que existe sinal antecipado real, mensurado, no cenário Top-5;
- apoiar a discussão sobre capacidade operacional (o desempenho muda com K);
- servir de linha de base para uma versão futura.

**Não recomendado** para: substituir avaliação epidemiológica, alimentar
decisão automatizada, comunicar risco ao público, ou embasar qualquer
afirmação sobre redução de casos ou internações.
