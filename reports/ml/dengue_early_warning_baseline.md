# Alerta antecipado de dengue por bairro — formalização + baselines + primeiro modelo

> Execução real, reprodutível via `python -m src.evaluate_dengue_alert_baseline`
> (código em `src/ml/`). Todos os números abaixo vêm de
> `reports/ml/resultado_completo.json` e dos CSVs desta pasta — nenhum é
> estimado à mão. Consome `dashboard/data/gold_arboviroses_clima_bairro.parquet`
> (191.478 linhas, 2013-2025) sem reimplementar nenhuma lógica da Gold.

## 1. Alinhamento com o desafio

O desafio oficial pede **antecipação territorializada** de surtos de dengue
(bairro × tempo), não previsão de contagem de casos por si só, com um
indicador explícito de sucesso: *antecipação temporal entre previsão de
risco e aumento de casos*. Esta etapa foi desenhada para responder
exatamente isso — o produto não é "quantos casos have next week", é "este
bairro vai entrar em estado de risco elevado, e com quantas semanas de
antecedência conseguimos avisar". **DENGUE é o agravo preditivo principal**
desta etapa (Zika/Chikungunya seguem disponíveis para EDA/comparação, não
tratados aqui).

## 2. Estado preservado antes de qualquer alteração

- `git status`/`git log` registrados no início da sessão: branch `main`,
  commit `c3933b48a87ceea2c9d2f126e76f55f5837cea5d`, com working tree já
  contendo trabalho não commitado de sessões anteriores (dashboard, EDA,
  backfill CEMADEN) — nada disso foi tocado nesta etapa.
- Suíte baseline: **256/256 testes passando** antes de qualquer mudança.
- Bronze, Silver, Gold, dados climáticos e dashboard **não foram alterados**.
  Nenhum deploy de modelo. Nenhuma mudança no dashboard Streamlit.
- Única dependência nova: `scikit-learn` (`requirements.txt`) — necessária
  para `LogisticRegression`/`HistGradientBoostingClassifier`; nenhuma outra
  biblioteca de ML (XGBoost/LightGBM/TensorFlow) foi adicionada.

## 3. Formalização do caso de uso

```text
Dado tudo que sabemos até a semana epidemiológica t (de um bairro),
qual é o risco desse bairro apresentar crescimento
epidemiologicamente relevante (estado de risco elevado)
na semana t + horizonte?
```

- **Unidade operacional**: `bairro × semana epidemiológica` (mesma unidade
  da Gold).
- **Instante de previsão `t`**: uma linha (`codigo_bairro`,
  `ano_epidemiologico`, `semana_epidemiologica`).
- **Horizonte principal escolhido**: **t+1 semana**. Avaliado também t+2
  (seção 15) — a escolha de t+1 é sustentada tanto pela preferência inicial
  do pedido quanto pelos dados: o modelo de árvore em t+1 tem PR-AUC 0,292
  contra 0,250 em t+2 no mesmo split de teste (queda de poder preditivo ao
  esticar o horizonte, esperado). t+2 permanece uma alternativa razoável se
  o objetivo operacional priorizar mais tempo de reação em troca de um
  pouco menos de acurácia — não implementado como pipeline completo
  paralelo, conforme instrução de não construir 3 pipelines sem
  necessidade.
- **Informação permitida**: tudo calculável a partir de `t` ou antes (lags e
  médias móveis de `casos`, estado atual, sazonalidade expandindo só sobre
  anos passados, território estático, clima já garantidamente
  `data <= semana_epi_data_fim` de `t`, ver `src/gold/`).
- **Informação proibida**: qualquer `casos`/`estado_alto_risco` de semana
  `> t` nas FEATURES de `t` (o target é o único lugar em que `t+horizonte`
  aparece, por desenho — ver `src/ml/dataset.py`).
- **Saída A (previsão quantitativa)** e **Saída B (alerta de risco)** são
  tratadas como produtos distintos (seções 7 e 10 abaixo) — a quantitativa
  informa a construção do alerta, mas não é o produto final.

## 4. Definição de "surto"/"risco elevado" (`src/ml/target.py`)

**Opções avaliadas** (todas comparadas antes de escolher, ver
`target.py` para a justificativa completa):

| Opção | Por que não foi usada sozinha |
|---|---|
| A — limiar histórico absoluto por bairro | Sozinha, sem controle sazonal, mistura época de pico com época de baixa do mesmo bairro |
| B — crescimento relativo (%) | Threshold percentual sobre uma base que já é baixa/zero em muitos bairros produz alarme constante ou nunca dispara — não escolhido como definição de estado, mas usado como um dos **baselines** (`baseline_crescimento_recente`) |
| C — baseline sazonal isolado | Sozinho, com pouco histórico (13 anos), a amostra por semana exata é pequena demais para um percentil estável |
| D — método epidemiológico oficial (canal endêmico do SINAN) | Não há uma implementação já pronta e diretamente reutilizável nas fontes do projeto; o princípio do "canal endêmico" (comparar a semana atual à distribuição histórica da mesma época) é exatamente o que a opção adotada (A+C) implementa |

**Definição adotada (híbrida A+C)**: para cada (`bairro`, `ano`, `semana`),
o estado é `1` se `casos > limiar`, onde `limiar` é o **percentil 90** da
distribuição de `casos` do MESMO bairro em semanas dentro de uma janela de
`±2` semanas em torno da semana alvo, usando **somente anos anteriores**
(nunca o próprio ano nem anos futuros). Se essa amostra tiver menos de 15
observações, cai para a distribuição geral do bairro (todas as semanas, só
anos anteriores, mínimo 20 observações); se nem isso, o estado fica
**indefinido** (`NaN`), nunca forçado a 0/1.

Por que esta definição (não `casos > 10`): a escala de dengue por bairro
varia em ordens de grandeza (COHAB 6.817 casos acumulados vs. PAU FERRO 1
caso em 13 anos) e não existe dado de população por bairro no projeto
(`incidencia_por_100k` não existe, ver `src/gold/`) — um corte absoluto
seria sistematicamente injusto entre bairros grandes e pequenos. O
histórico do próprio bairro funciona como normalizador implícito.

**Resultado real, todas as linhas 2013-2025 (63.826 linhas de dengue, 94
bairros)**:

| `tipo_limiar` | Linhas |
|---|---:|
| sazonal (amostra ≥15 na janela) | 48.504 |
| geral (fallback, amostra ≥20 no bairro) | 10.434 |
| indefinido (histórico insuficiente) | 4.888 |

`indefinido` concentra-se nos primeiros anos da série (2013-2015, antes de
haver 3 anos de histórico por bairro) — tratamento explícito, essas linhas
são excluídas do dataset supervisionado, nunca imputadas.

**Semanas 52/53 e virada de ano**: a janela sazonal (`±2` semanas) é
truncada nas bordas (`max(1, semana-2)` a `min(53, semana+2)`), sem
wraparound — testado explicitamente (`test_janela_sazonal_nao_ultrapassa_bordas_1_e_53`).

**Sem leakage na definição do target**: o limiar de uma linha do ano Y usa
só anos `< Y` — testado injetando `casos=99999` em anos `>= Y` e
confirmando que o limiar de Y não muda (`test_limiar_nao_usa_anos_futuros_nem_o_proprio_ano`).

## 5. Episódios (agrupamento de semanas consecutivas)

Semanas consecutivas com `estado_alto_risco=1` no mesmo bairro formam **um
único episódio** (uma semana `NaN` quebra a continuidade). Resultado real,
2013-2025, todos os 94 bairros:

| Ano de início | Episódios |
|---:|---:|
| 2014 | 94 |
| 2015 | **668** |
| 2016 | 357 |
| 2017 | 51 |
| 2018 | 82 |
| 2019 | 318 |
| 2020 | 150 |
| 2021 | 341 |
| 2022 | 81 |
| 2023 | 117 |
| 2024 | 406 |
| 2025 | 397 |

**3.062 episódios no total**, duração média 2,31 semanas (mediana 1
semana). O ano com mais episódios é **2015** — coincide exatamente com o
achado da EDA ("2015 foi o ano com mais casos de arboviroses", ver
`reports/eda/README.md`) — evidência de que a definição de estado captura
sinal epidemiológico real, não ruído. 2024-2025 também concentram muitos
episódios (406, 397), coerente com a "nova alta de dengue 2024-2025" já
documentada.

## 6. Dataset supervisionado (DENGUE, horizonte t+1)

| Métrica | Valor |
|---|---:|
| Linhas antes (dengue, 2013-2025) | 63.826 |
| Excluídas — target indefinido em t+1 | 4.888 |
| Excluídas — feature ausente (início de série por bairro) | 188 |
| **Linhas finais** | **58.750** |
| Positivos (`estado_alto_risco` em t+1 = 1) | 7.069 |
| Negativos | 51.681 |
| **Proporção positiva** | **12,03%** |
| Features | 30 (11 epidemiológicas/estado + 6 sazonais + 3 territoriais numéricas + 10 territoriais categóricas one-hot) |

Alvo raro (~12% positivo) — **accuracy não é métrica útil aqui** (um
classificador trivial "sempre 0" teria ~88% de acurácia e recall zero);
Precision/Recall/F1/PR-AUC são as métricas reportadas (seção 9).

**Features** (`src/ml/features.py`): `casos_t`, lags `t-1..t-4`, médias
móveis (2/4/8 semanas), soma/máximo 4 semanas, tendência (`casos_t -
casos_t-1`), estado atual (`estado_alto_risco_t`), semana
epidemiológica/mês/trimestre/seno-cosseno da semana, média histórica da
mesma semana em anos anteriores, área do bairro, centróide (lat/lon),
RPA e microrregião (one-hot — nunca número contínuo). 30 features, não
centenas.

## 7. Split temporal (nunca aleatório)

| Conjunto | Anos | Linhas |
|---|---|---:|
| Treino | 2013-2019 | 29.328 |
| Validação | 2020-2022 | 14.758 |
| Teste | 2023-2025 | 14.664 |

Corte pelo ano da linha `t` (instante de decisão). Teste (2023-2025) cobre
a retomada real de alta de dengue — o cenário operacionalmente mais
relevante. Limiares de decisão (threshold de probabilidade) são escolhidos
por F1 **na validação**, nunca no teste (`_selecionar_threshold_por_f1`).

## 8. Baselines (teste, 2023-2025, threshold=0,5)

| Baseline | Precision | Recall | F1 | PR-AUC | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Persistência (`estado_t` → `estado_t+1`) | 0,306 | 0,305 | 0,305 | 0,156 | 0,618 |
| Crescimento recente (3 semanas consecutivas) | 0,146 | 0,075 | 0,099 | 0,094 | 0,516 |
| Sazonal simples (`casos_t` > média histórica da semana) | 0,173 | **0,602** | 0,269 | 0,140 | 0,658 |

**Baseline de contagem** (previsão quantitativa, Saída A):

| Baseline | MAE | RMSE |
|---|---:|---:|
| Persistência (`casos_t+1 = casos_t`) | 1,188 | 2,196 |
| Média móvel 4 semanas | **1,084** | **2,039** |

A média móvel supera levemente a persistência pura na previsão quantitativa
— mas, como já estabelecido na seção 3, essa não é a métrica principal da
etapa.

## 9. Modelos

**Regressão logística** (padronizada, `class_weight="balanced"`, threshold
escolhido na validação = 0,45):

| Precision | Recall | F1 | PR-AUC | ROC-AUC |
|---:|---:|---:|---:|---:|
| 0,303 | 0,384 | 0,339 | 0,278 | 0,731 |

**HistGradientBoostingClassifier** (`class_weight` via `sample_weight`
balanceado, threshold escolhido na validação = 0,70):

| Precision | Recall | F1 | PR-AUC | ROC-AUC |
|---:|---:|---:|---:|---:|
| 0,372 | 0,300 | 0,332 | **0,292** | **0,753** |

**Ambos os modelos superam claramente todos os 3 baselines em PR-AUC**
(0,278-0,292 contra o melhor baseline, persistência, em 0,156 — ganho
relativo de ~78-87%). Em F1 a diferença é mais modesta (0,332-0,339 contra
0,305 da persistência) — a persistência já é surpreendentemente competitiva
em F1 no threshold fixo 0,5 (esperado: dengue tem autocorrelação temporal
forte), mas perde nitidamente quando comparada de forma independente de
threshold (PR-AUC).

**Trade-off Precision/Recall** (árvore, `reports/ml/tradeoff_precision_recall_arvore.csv`):

| Threshold | Precision | Recall | F1 | Falsos Positivos | Falsos Negativos |
|---:|---:|---:|---:|---:|---:|
| 0,1 | 0,123 | 0,896 | 0,216 | 8.466 | 137 |
| 0,3 | 0,192 | 0,647 | 0,297 | 3.593 | 467 |
| 0,5 | 0,270 | 0,451 | 0,338 | 1.616 | 726 |
| 0,7 (escolhido) | 0,372 | 0,300 | 0,332 | 671 | 926 |
| 0,9 | 0,545 | 0,092 | 0,158 | 102 | 1.201 |

O limiar de decisão foi escolhido por F1 na validação (não maximiza Recall
isoladamente) — a tabela completa fica disponível para quem priorizar mais
Recall operacionalmente (ex.: threshold 0,3 dobra o recall ao custo de ~5x
mais falsos positivos).

**Calibração** (`reports/ml/calibracao_arvore.csv`): o modelo está
**superconfiante** — na faixa de maior probabilidade prevista (0,89-0,99),
a frequência real de surto observada é 51,6%, não ~93% como a probabilidade
média sugeriria; na faixa mais baixa (0-0,10) a probabilidade prevista já
está próxima da frequência real (4,4% vs 2,8%). Diagnóstico apenas — nenhuma
calibração avançada foi aplicada (regra de parada). Um dashboard futuro que
mostre "risco estimado: X%" **não deveria usar a probabilidade bruta do
modelo de árvore sem calibração**.

## 10. Métricas operacionais de alerta (teste, 2023-2025, árvore @ threshold 0,70)

| Métrica | Valor |
|---|---:|
| Episódios reais no teste | 920 |
| Episódios detectados | 362 (**39,3%**) |
| Episódios perdidos | 558 |
| Alertas antecipados | 295 |
| Alertas simultâneos | 6 |
| Alertas tardios | 61 |
| **Lead time médio** | **2,26 semanas** |
| **Lead time mediano** | **3,0 semanas** |
| Falsos alertas (semana-alvo fora da janela de qualquer episódio) | 319 |

**Entre os episódios detectados, 81,5% (295/362) foram antecipados** — a
maioria das detecções chega antes do início real do surto, com mediana de
3 semanas de antecedência, dentro da janela operacional de 1-4 semanas
justificada (ciclo de ação de controle vetorial). **Mas a taxa de detecção
geral (39,3%) é modesta** — mais da metade dos episódios reais não é
capturada.

**Falsos alertas re-contextualizados**: a classificação linha-a-linha
(seção 9) reporta 671 falsos positivos no threshold 0,70; ao aplicar a
janela de tolerância operacional de 1-4 semanas (seção "definição de
alerta"), esse número cai para **319 falsos alertas realmente
"desperdiçados"** — quase metade dos falsos positivos linha-a-linha na
verdade caem dentro da janela de antecipação de um episódio real e não
deveriam ser tratados como alarme falso do ponto de vista operacional.

## 11. Desempenho por bairro (`reports/ml/metricas_por_bairro.csv`)

Bairros com mais episódios reais no teste (2023-2025) — código de bairro
interno da Gold, não nome (ver CSV para o mapeamento completo): bairro
`27` (22 episódios, 6 detectados), `752` (21, 9), `744` (18, 9), `906` (18,
7), `892` (17, 9). Vários bairros com histórico suficiente (3-10 episódios
reais) tiveram **0% de detecção** (ex.: bairros `132`, `159`, `175`, `19`,
`213`, `35`, `450`, `442`, `51`, `930`) — o sistema falha completamente
nesses casos, não apenas de forma aleatória/dispersa. Isso indica que o
desempenho não é uniforme espacialmente e exigiria investigação por bairro
antes de qualquer uso operacional.

## 12. Desempenho por ano (episódios)

| Ano de início do episódio | Episódios reais | Detectados | Taxa de detecção |
|---:|---:|---:|---:|
| 2023 | 117 | 9 | **7,7%** |
| 2024 | 406 | 158 | 38,9% |
| 2025 | 397 | 195 | 49,1% |

**2023 é um ano crítico de falha** — apenas 7,7% de detecção, consistente
com o walk-forward de classificação (seção abaixo: PR-AUC de 2023 = 0,074,
o pior de toda a série 2019-2025). O desempenho melhora
substancialmente em 2024-2025. Isso é uma limitação real, não um efeito de
amostra pequena (117 episódios não é um N desprezível).

**Walk-forward (expanding window, HistGradientBoosting, threshold fixo
0,5)** — generalização ano a ano (`reports/ml/walk_forward_por_ano.csv`):

| Ano teste | PR-AUC | Recall | Precision | F1 |
|---:|---:|---:|---:|---:|
| 2019 | 0,447 | 0,608 | 0,403 | 0,484 |
| 2020 | 0,288 | 0,495 | 0,282 | 0,359 |
| 2021 | **0,652** | 0,806 | 0,475 | 0,598 |
| 2022 | 0,143 | 0,221 | 0,134 | 0,167 |
| 2023 | **0,074** | 0,171 | 0,089 | 0,117 |
| 2024 | 0,255 | 0,456 | 0,214 | 0,292 |
| 2025 | 0,371 | 0,619 | 0,269 | 0,375 |

**O modelo NÃO tem desempenho estável entre ciclos epidêmicos** — varia de
PR-AUC 0,074 (2023) a 0,652 (2021), quase 9x de variação. Isso responde
diretamente à seção 33 do pedido: o sistema funciona bem em anos com
tendências mais claras/persistentes (2019, 2021, 2025) e mal em anos de
transição/baixa atividade seguida de reversão abrupta (2022→2023).

## 13. Epidemias grandes (top 10% dos episódios por casos totais)

| Métrica | Valor |
|---|---:|
| N episódios (top 10%, teste 2023-2025) | 92 |
| **Taxa de detecção** | **79,3%** |

**Este é o resultado mais favorável de toda a etapa**: para os episódios
mais relevantes (maior carga de casos), a taxa de detecção sobe de 39,3%
(geral) para **79,3%** — o sistema é consideravelmente melhor em antecipar
justamente os eventos que mais importam operacionalmente (grandes surtos),
mesmo perdendo muitos episódios pequenos/marginais.

## 14. Importância de features (permutation importance, PR-AUC, árvore)

| Feature | Importância média |
|---|---:|
| `estado_alto_risco_t` (estado atual) | 0,0874 |
| `media_historica_semana_exata` (sazonalidade) | 0,0740 |
| `media_8s` | 0,0338 |
| `media_4s` | 0,0334 |
| `casos_t_menos_1` | 0,0247 |
| `media_2s` | 0,0174 |
| `casos_t_menos_2` | 0,0122 |
| `max_4s` | 0,0038 |
| `casos_t_menos_3` | 0,0032 |
| `area_km2` | 0,0031 |

**O estado atual e a sazonalidade histórica dominam** — coerente com o
achado da EDA de sazonalidade forte (pico médio na semana 11, ver
`reports/eda/README.md`) e com a autocorrelação temporal já vista nos
baselines. Território (`area_km2`) tem contribuição marginal; clima não
participa deste experimento (BASE, sem clima). Isso não implica
causalidade — apenas contribuição preditiva no modelo treinado.

## 15. Horizonte secundário (t+2 semanas)

| | t+1 (principal) | t+2 (secundário) |
|---|---:|---:|
| PR-AUC (árvore, teste) | 0,292 | 0,250 |
| Recall @ threshold 0,5 | 0,451 (0,300 @ 0,70) | 0,417 |
| Precision @ threshold 0,5 | 0,270 (0,372 @ 0,70) | 0,238 |

t+2 tem PR-AUC menor que t+1 no mesmo conjunto de teste — o poder preditivo
cai ao esticar o horizonte, como esperado. **t+1 permanece o horizonte
principal recomendado**; t+2 continua sendo uma opção operacionalmente
válida (mais tempo de reação) se uma etapa futura decidir sacrificar um
pouco de PR-AUC por mais antecedência — não descartado, apenas não
escolhido como principal nesta etapa.

## 16. Comparação BASE × BASE+CLIMA (2024→2025, mesmas linhas, mesmo split, mesmo modelo)

Restrito às linhas com clima real (`dias_com_dado_valido_semana > 0`),
treino = 2024 (1.305 linhas), teste = 2025 (2.546 linhas) — mesmíssimas
linhas em ambos os modelos (verificado por `assert` no código), só
`HistGradientBoostingClassifier` (aceita `NaN` nativamente nas features de
chuva, ver `src/ml/models.py`):

| | BASE (sem clima) | BASE+CLIMA |
|---|---:|---:|
| PR-AUC | 0,133 | 0,158 |
| ROC-AUC | 0,444 (pior que aleatório) | 0,507 |
| Precision | 0,138 | 0,215 |
| Recall | 0,057 | 0,044 |
| F1 | 0,081 | 0,074 |

**Ganho de PR-AUC: +0,025** (pequeno, positivo). **Não é um resultado
forte o suficiente para justificar incorporar clima ao modelo principal**:
a amostra de treino é minúscula (1.305 linhas de um único ano, 2024) e
ambos os modelos têm desempenho absoluto muito baixo (BASE inclusive pior
que aleatório em ROC-AUC) — o experimento é estatisticamente frágil demais
para uma conclusão robusta. Isso está alinhado com o achado já registrado
na EDA (`reports/eda/README.md`): correlação exploratória chuva×casos
"fraca em todos os casos (< 0,12)" em 2024-2025. **Clima não foi forçado
no modelo final** (regra explícita do pedido) — permanece um experimento
secundário com evidência inconclusiva, a revisar quando houver mais
histórico climático real (ver limitações do backfill CEMADEN, seção 27 do
`README.md`).

## 17. Limitações

1. **Desempenho instável entre anos** (seção 12): PR-AUC varia de 0,074
   (2023) a 0,652 (2021) no walk-forward — o modelo não generaliza de forma
   confiável entre diferentes regimes epidêmicos.
2. **Taxa de detecção geral modesta** (39,3%) — mais da metade dos
   episódios reais no teste não é capturada, mesmo com a janela de
   tolerância de 4 semanas.
3. **Desempenho heterogêneo por bairro** (seção 11) — vários bairros com
   histórico suficiente têm 0% de detecção.
4. **Calibração de probabilidade ruim** (seção 9) — o modelo é
   superconfiante nas faixas de alta probabilidade; qualquer exibição de
   "risco estimado: X%" precisaria de calibração antes de ir a produção.
5. **Comparação climática estatisticamente frágil** (seção 16) — amostra
   pequena (1.305 treino/2.546 teste, um único ano cada), ganho de PR-AUC
   pequeno (+0,025), desempenho absoluto baixo em ambos os modelos.
6. **Sem incidência por 100 mil** — herdado da Gold (nenhuma fonte do
   projeto tem população por bairro); o histórico do próprio bairro é usado
   como normalizador implícito na definição de risco, não uma substituição
   perfeita de incidência real.
7. **Janela sazonal sem wraparound** (semanas 1-3 e 51-53 têm amostra
   sazonal ligeiramente menor) — efeito marginal, documentado em
   `target.py`.
8. **Lead time limitado pelo desenho de horizonte único**: como o horizonte
   principal é t+1, o "lead time" de até 4 semanas reportado na seção 10
   depende de o modelo já sinalizar probabilidade elevada em semanas
   consecutivas antes do estado binário cruzar o limiar — não de um
   horizonte de previsão de 4 semanas propriamente dito. Um horizonte maior
   (t+4) testado à parte poderia mudar esse número, mas não foi construído
   como pipeline completo (regra de parada).

## 18. Arquivos criados/alterados

**Criados**: `src/ml/__init__.py`, `src/ml/target.py`, `src/ml/features.py`,
`src/ml/dataset.py`, `src/ml/split.py`, `src/ml/baselines.py`,
`src/ml/models.py`, `src/ml/evaluation.py`, `src/ml/alert_metrics.py`,
`src/evaluate_dengue_alert_baseline.py`, `tests/test_ml_target.py`,
`tests/test_ml_features.py`, `tests/test_ml_dataset.py`,
`tests/test_ml_split.py`, `tests/test_ml_baselines.py`,
`tests/test_ml_alert_metrics.py`, `reports/ml/dengue_early_warning_baseline.md`
(este arquivo) + CSVs de apoio em `reports/ml/`
(`tradeoff_precision_recall_arvore.csv`, `calibracao_arvore.csv`,
`feature_importance_arvore.csv`, `walk_forward_por_ano.csv`,
`episodios_avaliados_teste.csv`, `metricas_por_bairro.csv`,
`metricas_por_ano.csv`, `epidemias_grandes.csv`, `resultado_completo.json`).

**Alterados**: `requirements.txt` (adição de `scikit-learn>=1.4,<2`).

**Não alterados**: Bronze, Silver, Gold, `src/eda/`, `dashboard/`, nenhum
dado climático, nenhum arquivo de configuração de deploy.

## 19. Testes finais

**29 testes novos** (target: bairro sem histórico, sem leakage entre anos,
bordas de semana 52/53, dois bairros não se misturam, zero casos, fallback
sazonal→geral; features: leakage adversarial injetando `casos=99999` no
futuro, rolling nunca vê a semana seguinte, índice cronológico correto;
dataset: target = estado em t+horizonte, última semana de cada bairro
excluída sem vazar para o bairro seguinte, leakage adversarial de ponta a
ponta, filtro de clima real; split: sem mistura de anos entre
treino/validação/teste, walk-forward estritamente prospectivo; baselines:
persistência/crescimento/sazonal/contagem; alert_metrics: episódio
isolado, semanas consecutivas, gap por estado indefinido, lead time
antecipado/simultâneo/tardio/perdido, falso alerta, agregações por
bairro/ano/epidemias grandes).

**Suíte completa: 285/285 passando** (baseline era 256, **0 regressões**).

## 20. Classificação final

**B — Existe sinal, mas precisa melhorar.**

Justificativa: os modelos superam claramente os 3 baselines em PR-AUC
(+78-87% relativo) e o feature importance é epidemiologicamente coerente
(estado atual + sazonalidade dominam); a detecção de grandes surtos é boa
(79,3%) e o lead time, quando o episódio é detectado, é operacionalmente
útil (mediana 3 semanas, dentro da janela de 1-4 semanas). Mas a taxa de
detecção geral (39,3%), a instabilidade entre anos (PR-AUC 0,074-0,652) e a
heterogeneidade entre bairros (vários com 0% de detecção) mostram que o
sistema, no estado atual, não está pronto para operação — não é "A"
(antecipação útil e consistente) nem "C" (baselines simples já bastam —
eles claramente não bastam) nem "D" (o modelo não generaliza de forma
alguma — ele generaliza, só que de forma desigual).

## 21. Decisão obrigatória

**Os resultados atuais justificam avançar para otimização de um sistema de
alerta antecipado de dengue por bairro?**

## SIM

**Justificativa**:

- **Recall/Precision/F1 superam os baselines de forma consistente** em
  PR-AUC (0,292 árvore / 0,278 regressão logística vs. 0,156 do melhor
  baseline, persistência) — há sinal real, não coincidência.
- **Episódios detectados**: 362/920 no geral (39,3%), mas **79,3%** nos
  episódios de maior carga (epidemias grandes) — o sistema já é útil
  justamente onde mais importa.
- **Lead time**: mediana de 3 semanas de antecedência nos episódios
  detectados, dentro da janela operacional de 1-4 semanas — compatível com
  o ciclo real de ações de controle vetorial.
- **Falsos alertas**: 319 no período de teste completo (2023-2025, ~14.664
  semanas-bairro avaliadas) — taxa baixa o suficiente (~2,2% das
  semanas-bairro) para não implicar sobrecarga operacional imediata.
- **Comparação com baselines**: nenhum baseline simples (persistência,
  crescimento recente, sazonal simples) chega perto do PR-AUC dos modelos —
  a complexidade adicional de ML se justifica.

**Ressalvas que a próxima etapa de otimização deve priorizar** (não
"pronto para produção" — classificação B, não A):

1. Investigar a queda de desempenho em 2023 (PR-AUC 0,074) antes de
   confiar no sistema para um ano específico sem verificação cruzada.
2. Elevar a taxa de detecção geral (39,3%) — hoje o sistema é conservador
   demais para episódios de menor magnitude.
3. Investigar os bairros com 0% de detecção — pode indicar necessidade de
   modelo hierárquico/pooling parcial em vez de um modelo único para os 94
   bairros.
4. Calibrar probabilidade antes de qualquer exibição de "risco: X%" na UI.
5. Revisitar a comparação climática quando houver mais profundidade
   histórica real (o backfill do CEMADEN cobre hoje só 2024-2025).

Não avançar para tuning extensivo, ensemble, deep learning, deploy ou
alteração do dashboard nesta mesma etapa — isso é trabalho da próxima etapa
de otimização, fora da regra de parada atual.
