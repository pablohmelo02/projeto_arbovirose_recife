# Experimento controlado: o clima em grade acrescenta valor ao ranking?

**Data:** 2026-08-21 · **Reprodução:** `python -m src.experiment_dengue_ranking_clima`
**Artefatos:** `resultado_clima_experimento.json`,
`clima_experimento_delta.csv`, `clima_experimento_recall_ic.csv`,
`clima_experimento_por_ano.csv`, `clima_experimento_master_episodios.csv`

## 1. Desenho — um experimento, nada além

| | **A** (referência) | **B** (com clima em grade) |
|---|---|---|
| Target | onset de novo episódio em t+1..t+3 | idêntico |
| Linhas avaliadas | 58.562 (treino 29.328 / teste 14.476) | **as mesmas** |
| Split | treino 2013-2019 · validação 2020-2022 · teste 2023-2025 | idêntico |
| Algoritmo | `HistGradientBoostingClassifier` | idêntico |
| Hiperparâmetros | `max_depth=4, learning_rate=0.1, max_iter=150`, seed 42 | idênticos |
| Features | **38** | **46** (38 + 8 de clima em grade) |
| Episódios reais avaliados | 920 | os mesmos 920 |

Único fator manipulado: as 8 colunas de clima em grade
(`precipitacao_semana_grade_mm`, acumulados de 2/3/4 semanas, temperatura
média/mínima/máxima, umidade relativa média). Nenhum tuning, nenhuma
seleção de features, nenhum algoritmo novo, nenhum target novo.

Verificado programaticamente que A e B avaliam exatamente o mesmo conjunto
de linhas (`mesmas_linhas_em_A_e_B: true`) — o clima em grade tem 100 % de
cobertura, então não exclui nenhuma linha por ausência.

### 1.1 Critério de decisão, declarado antes de rodar

> Incorporar o clima ao modelo do produto **somente se** o delta B−A em
> **Recall@5** tiver IC que não cruza zero **e** sinal positivo em todos os
> anos do teste.

Recall@5 é a faixa escolhida porque é a única em que o candidato congelado
tem ganho estatisticamente defensável sobre regras simples
(`reports/ml/dengue_ranking_evidence_validation.md`) e, por consequência, a
única faixa de claim do produto.

### 1.2 Expectativa a priori, também registrada antes

A investigação da fonte mediu que a grade produz no máximo **2 valores
distintos de precipitação entre os 94 bairros na mesma semana**. Como o
produto é um ranking **entre bairros dentro da mesma semana**, uma variável
quase constante entre as unidades comparadas quase não tem como
discriminá-las. Ganho esperado: nulo ou marginal.

## 2. Verificação prévia: o candidato congelado não mudou

Depois de enriquecer a Gold de 1.0 para 1.1 (15 colunas novas), o modelo A
reproduziu o candidato congelado **campo a campo**:

| Métrica | Artefato congelado (§18) | Modelo A neste experimento |
|---|---|---|
| Delta Recall@5 vs melhor baseline | +0,059783 | **+0,059783** |
| IC (episódio) | [+0,028261; +0,091304] | **[+0,028261; +0,091304]** |
| IC (cluster bairro) | [+0,018888; +0,101699] | **[+0,018888; +0,101699]** |
| IC (cluster bairro×ano) | [+0,024040; +0,096010] | **[+0,024040; +0,096010]** |

Isto é a prova de que o enriquecimento climático da Gold **não alterou** a
evidência já validada: as colunas novas são adicionais, não substitutivas.

## 3. Resultado principal — Recall@5: sem ganho

| | Recall@5 observado |
|---|---|
| A (sem clima) | 25,761 % |
| B (com clima em grade) | 25,652 % |
| **Delta B−A** | **−0,109 pp** |

Intervalos de confiança do delta B−A em K=5 (bootstrap 2.000, seed 42):

| Esquema de reamostragem | IC 95 % | Cruza zero? |
|---|---|---|
| Episódio | [−2,283; +2,065] pp | **sim** |
| Cluster bairro | [−2,464; +2,230] pp | **sim** |
| Cluster bairro × ano | [−2,471; +2,371] pp | **sim** |

Por ano (Recall@5): 2023 +1,71 pp · 2024 **−1,48 pp** · 2025 +0,76 pp — o
sinal **não é positivo em todos os anos**.

**As duas condições do critério falharam.** O clima em grade não melhora o
produto na faixa em que o produto faz sua única afirmação de ganho.

## 4. Achado secundário, robusto — Recall@10

Reportado por honestidade e explicitamente **não** usado para reverter o
critério da §1.1 (mudar o critério depois de ver o resultado seria
racionalização *post hoc*):

| | Recall@10 |
|---|---|
| A (sem clima) | 38,370 % |
| B (com clima em grade) | **41,196 %** |
| Delta B−A | **+2,826 pp** |

| Esquema | IC 95 % do delta B−A | Cruza zero? |
|---|---|---|
| Episódio | [+0,435; +5,326] pp | não |
| Cluster bairro | [+0,210; +5,335] pp | não |
| Cluster bairro × ano | [+0,403; +5,292] pp | não |

Positivo em **todos** os anos do teste (2023 +3,42 · 2024 +3,94 · 2025
+1,51 pp).

E mais relevante: em K=10, o modelo **A** não vence o melhor baseline
(delta +2,61 pp, IC [−0,76; +5,98], cruza zero — a limitação central
documentada na §18). Já o modelo **B** vence:

| K=10, vs melhor baseline (`razao_historica_local`) | delta | IC episódio | IC cluster bairro | IC cluster bairro×ano |
|---|---|---|---|---|
| A (sem clima) | +2,61 pp | [−0,76; +5,98] | [−1,82; +6,85] | [−1,14; +6,50] |
| **B (com clima)** | **+5,43 pp** | **[+1,96; +9,02]** | **[+0,87; +10,07]** | **[+1,34; +9,71]** |

Em K=15 o delta B−A também é positivo com IC acima de zero (+3,37 pp,
[+0,98; +5,87]), mas B ainda não vence o baseline nessa faixa. Em K=20 o
delta B−A já cruza zero.

Interpretação plausível (hipótese, não conclusão): o clima em grade não
diferencia bairros, mas diferencia **semanas**. Um sinal de "esta é uma
semana de risco climático elevado na cidade" ajuda o modelo a decidir
*quando* elevar vários bairros ao mesmo tempo — o que se traduz em ganho nas
faixas mais largas (K=10/15), onde há espaço para elevar vários, e não na
faixa mais estreita (K=5), onde a competição entre bairros é decidida por
características locais que o clima em grade não tem.

## 5. Recortes por tipo de episódio

Deltas B−A (pontos percentuais, IC 95 % por episódio):

| Recorte | n | Δ Recall@5 | Δ Recall@10 |
|---|---|---|---|
| Antecipação genuína | 762 | ver JSON | ver JSON |
| Recaída | 158 | ver JSON | ver JSON |
| Grandes episódios (top 10 %) | 92 | ver JSON | ver JSON |

Os números completos, com IC, estão em `resultado_clima_experimento.json`
(chave `recortes`). Nenhum recorte inverte a conclusão de K=5, e os ICs dos
recortes menores (92 e 158 episódios) são largos o suficiente para que
nenhuma diferença por recorte seja afirmável.

## 6. Decisão

**O clima NÃO é incorporado ao modelo do produto.**

Consequências práticas:

1. `dengue_onset_ranking_candidate_v1` permanece **congelado e sem clima** —
   38 features, mesmos hiperparâmetros, mesma evidência validada.
2. As 15 colunas climáticas em grade **permanecem na Gold** — elas são
   valiosas para descrição/EDA (a página *Clima × Dengue* passa a cobrir
   2013-2025 em vez de só 2024-2025) mesmo sem entrar no modelo.
3. Nenhum novo ciclo de tuning é iniciado.

## 7. Pendência registrada para uma versão futura

A variante **B em K=10** é a candidata mais promissora já observada neste
projeto para superar as regras simples numa faixa operacional mais larga.
Ela **não pode ser afirmada como resultado** hoje porque não passou pelo
protocolo completo de validação aplicado ao candidato congelado:
leave-one-year-out, análise territorial por RPA/bairro, lead time,
estabilidade semanal do ranking e carga operacional.

Se essa faixa for de interesse operacional para a Prefeitura, o caminho
correto é abrir uma **nova versão** (`dengue_onset_ranking_candidate_v2`,
com clima em grade) e submetê-la à validação completa — não reaproveitar os
números desta seção como se fossem validados.

**Classificação: B — utilizável com limitações** (a fonte climática é útil
para descrição e tem sinal real em K=10, mas não melhora a faixa de claim
do produto).
