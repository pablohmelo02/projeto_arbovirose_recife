# Experimento V2: onset/ranking territorial baseado em incidência

Comparação honesta entre o candidato congelado `dengue_onset_ranking_candidate_v1`
(contagem absoluta) e cinco variantes de um V2 baseado em incidência,
usando a mesma metodologia temporal e o mesmo modelo/hiperparâmetros. **V1
não foi retreinado, alterado ou re-avaliado com nova definição** — todos os
números de V1 citados aqui vêm de `reports/ml/resultado_evidence_validation_completo.json`
(já publicado). Reproduzível via `python -m src.experiment_incidence_ranking_v2`
e `python -m src.plot_incidence_ranking_v2`.

## 1. Git inicial

Working tree igual ao final da etapa de população (não commitado nesta
sessão); nenhum arquivo de V1 tocado — confirmado (`git status` vazio para
`artifacts/`, `src/ml/target.py`, `onset.py`, `features.py`, `dataset.py`,
`baselines.py`, `evidence_validation.py`, `alert_metrics.py` e os dois
`resultado_*.json` de V1).

## 2. Testes iniciais

**587/587** (baseline desta sessão, após a integração populacional). Após
este experimento: **629/629** (42 testes novos, 0 regressões).

## 3. V1 congelada confirmada

`artifacts/models/dengue_onset_ranking_candidate_v1/metadata.json`
inalterado: 38 features, `max_depth=4, learning_rate=0.1, max_iter=150`,
seed=42, `trained_until=2019`, target "onset ... percentil 90
histórico-sazonal local" sobre `casos`. Testado explicitamente
(`tests/test_ml_incidence_v2_v1_intacto.py`).

## 4. Target V2

`estado_alto_risco_incidencia`: mesmo algoritmo de limiar histórico-sazonal
local (P90, janela ±2 semanas, fallback geral, só anos anteriores) de V1,
aplicado sobre `incidencia_100k` em vez de `casos` — reusa
`target.calcular_estado_alto_risco` sem duplicar o algoritmo (substituição
de coluna, ver `src/ml/target_incidencia.py`). Onset h=3 sobre esse estado
(`src/ml/onset_incidencia.py`, reusa `onset.construir_target_onset` e
`alert_metrics.construir_episodios` sem alteração).

## 5. Número de eventos V1

**920 episódios** reais de onset (casos) no teste (2023-2025).

## 6. Número de eventos V2

**1.181 episódios** reais de onset (incidência) no teste — **28% mais
episódios** que V1. Esperado: bairros pequenos produzem picos de incidência
com poucos casos absolutos, que o critério de casos nunca capturaria (ver
seção 21 abaixo).

## 7. Sobreposição

| | valor |
|---|---|
| Em comum | 797 |
| Só V1 (casos) | 123 |
| Só V2 (incidência) | 384 |
| **Jaccard** | **0,61** |

61% de sobreposição: os dois critérios concordam na maioria dos casos, mas
quase 4 em 10 episódios são exclusivos de um dos dois — definições
genuinamente diferentes, não a mesma coisa com nomes diferentes.

## 8. Recall@5 V1

**25,76%** (IC [22,93%; 28,59%]) — número publicado, lido de
`resultado_evidence_validation_completo.json`, não recalculado.

## 9. Recall@5 V2

| variante | Recall@5 | IC 95% |
|---|---|---|
| v2_incidencia (só incidência) | 24,98% | [22,52%; 27,27%] |
| **v2_casos_incidencia (candidato principal)** | **25,15%** | **[22,78%; 27,60%]** |
| v2_casos_incidencia_populacao | 24,47% | [22,10%; 26,84%] |

**Recall@5 de V2 não é maior que o de V1** — os dois ficam dentro do mesmo
intervalo, estatisticamente indistinguíveis (920 vs. 1.181 episódios de
base diferentes, então a comparação é entre "taxas de detecção da própria
definição de cada um", não literalmente os mesmos eventos).

## 10. Melhor baseline de incidência

`razao_historica_incidencia` (Recall@5 = 19,48%) — análogo de incidência do
melhor baseline de V1 (`razao_historica_local`, 18,37% neste mesmo
recorte). Mesma regra simples, agora vencedora também no espaço de
incidência.

## 11. Delta V2 − V1 + IC

Não há um "delta V2−V1" direto e válido estatisticamente, porque os dois
avaliam bases de episódios diferentes (920 vs. 1.181) — reportar a
diferença simples dos dois pontos (25,15% − 25,76% = **−0,61 pp**) sem IC
pareado seria enganoso. Em vez disso, cada um foi comparado contra o
**próprio** melhor baseline (ver item 12), que é a comparação
estatisticamente válida.

## 12. Delta V2 − melhor baseline + IC

| k | delta | IC episódio | IC cluster bairro | IC cluster bairro×ano |
|---|---|---|---|---|
| 5 | **+5,67 pp** | [+2,79; +8,55] | [+1,07; +10,17] | [+1,90; +9,42] |
| 10 | +2,96 pp | [−0,68; +6,77] | [−2,96; +9,27] | [−1,60; +7,81] |
| 15 | −2,29 pp | [−5,93; +1,44] | — | — |
| 20 | **−7,03 pp** | [−10,75; −3,47] | — | — |

**Padrão idêntico ao de V1**: ganho robusto só em K=5 (todos os 3 esquemas
de IC > 0), inconclusivo em K=10/15, e **pior que o baseline em K=20** —
exatamente a mesma assinatura estatística que V1 já tinha. `leave-one-year-out`
em K=5: delta permanece positivo excluindo qualquer um dos 3 anos
(+8,3 / +5,0 / +2,8 pp) — mais robusto que o K=10 de V1 (que invertia de
sinal excluindo 2025).

## 13. Recall@10

V2 (candidato principal): 39,54% [36,66%; 42,34%] — v2_incidencia (só
incidência) chega a 39,71%, marginalmente mais alto, mas a diferença entre
as 5 variantes de V2 neste K é pequena (39,1%-39,7%).

## 14. Recall@15

Delta vs. melhor baseline (`crescimento_incidencia`) = −2,29 pp, IC cruza
zero — inconclusivo, mesmo padrão de V1 em K=15.

## 15. Recall@20

Delta vs. melhor baseline = **−7,03 pp**, IC **não cruza zero** — o
baseline simples é significativamente melhor que o modelo em K=20, mesmo
padrão de V1 (que também perdia para `crescimento_recente` em K=20).

## 16. Lead time

K=5, candidato principal (n=297 episódios detectados): mediana **2
semanas** (IC [2; 2]), média 2,32; **100%** com ≥1 semana (por construção
da janela), **65,7%** com ≥2 semanas, **43,1%** com ≥3 semanas. Ordem de
grandeza igual à de V1 em K=10 (mediana 2 semanas, ≥2 sem.=69,1%,
≥3 sem.=45,6%) — a incidência não muda a antecedência típica.

## 17. Onset genuíno

Recall@10: **33,48%** genuíno (n=920) vs. **60,92%** recaída (n=261) — a
MESMA disparidade de V1 (33,5% vs. 62,0%), quase número idêntico. A
incidência **não resolve** o problema central: antecipar um episódio que
não é continuação de um problema recente continua sendo muito mais difícil
que "prever" uma recaída.

## 18. Grandes episódios

Recall@5 = 26,05% [18,49%; 33,61%], Recall@10 = 41,18% [32,77%; 49,58%]
(n=119, top 10% por casos). **Diferente de V1**: em V1 grandes episódios
tinham desempenho PIOR que a média (30,4% em Top-10 vs. 38,4% geral); em
V2, grandes episódios têm desempenho **em linha ou levemente melhor** que
a média geral (41,2% vs. 39,5% em Top-10) — um resultado genuinamente
diferente, favorável a V2 neste recorte específico.

## 19. Performance por ano

| ano | n episódios | Recall@5 | Recall@10 |
|---|---|---|---|
| 2023 | 208 | 25,0% | 38,9% |
| 2024 | 504 | 24,2% | 38,7% |
| 2025 | 469 | 26,2% | 40,7% |

Mais estável entre anos que a variação vista em V1 no exercício de
walk-forward original (que ia de PR-AUC 0,074 a 0,664) — mas essa
comparação usa formulações/métricas diferentes (episódio-Recall aqui,
PR-AUC linha-a-linha lá), então é indicativa, não uma prova direta de maior
estabilidade.

## 20. Performance por RPA

| RPA | n | Recall@10 |
|---|---|---|
| 1 | 159 | 35,2% |
| 2 | 202 | 38,1% |
| 3 | 377 | 37,4% |
| 4 | 122 | 30,3% |
| **5** | 243 | **56,4%** |
| **6** | 78 | **24,4%** |

**A disparidade territorial PERSISTE**: RPA 5 segue muito acima de RPA 6
(2,3×), quase a mesma razão de V1 (2,6×). Incidência **não resolve** a
disparidade regional.

## 21. IPSEP

**Melhora real**: V1 tinha IPSEP em 0/6 episódios detectados em Top-10
(0%). V2: **2/9 em Top-10 (22,2%)** e **4/9 em Top-20 (44,4%)**. IPSEP
segue abaixo da média da cidade, mas deixou de ser um caso de detecção
zero — a mudança de denominador ajudou especificamente este bairro
historicamente difícil.

## 22. POÇO

**Sem melhora**: 0/10 em Top-10 e 0/10 em Top-20, igual à situação anterior
de bairros de detecção zero. Incidência não resolveu este caso.

## 23. Bairros pequenos

94 bairros, quartil inferior de população (≤ 5.956 habitantes, 24 bairros).
Comparando o número de semanas em "risco elevado" pela definição semanal
vs. pela janela móvel de 4 semanas:

| grupo | incidência semanal | incidência móvel 4 sem. | variação |
|---|---|---|---|
| Bairros pequenos (n=24) | 1.494 | 1.886 | **+26,2%** |
| Demais bairros (n=70) | 6.501 | 6.575 | +1,1% |

**Confirma a preocupação da seção 10 do pedido**: a escolha entre
incidência semanal e móvel afeta MUITO mais os bairros pequenos (+26%) que
os grandes (+1%) — a janela móvel suaviza picos isolados, e essa suavização
importa desproporcionalmente onde a população é pequena e a variância
relativa é alta. Nenhum bairro foi excluído da análise por isso.

## 24. Estabilidade

Jaccard médio do Top-10 entre semanas consecutivas: 0,256 a 0,280 entre as
5 variantes de V2 — candidato principal (`v2_casos_incidencia`) = **0,280**,
o mais estável das 5 variantes e comparável ao 0,29 (médio) já reportado
para V1. **Incidência não piora a estabilidade do ranking.**

## 25. Efeito da incerteza populacional

- **Sensibilidade A** (por tipo de população/ano): os 3 anos de teste
  (2023-2025) são **inteiramente** `PROJECAO_POS_CENSO` — não há variação
  de confiança populacional DENTRO do período de teste para correlacionar
  com desempenho. Limitação documentada, não escondida: esta análise não
  pode concluir nada sobre "anos de maior confiança" porque não existem no
  recorte de teste.
- **Sensibilidade B** (perturbação com erro real, 20 réplicas, erro
  reamostrado da distribuição real de validação cruzada — MAE 10,8%, viés
  +4,65%, variando de −25,2% a +210,6%): Recall@5 sem perturbação = 25,15%;
  com perturbação, média = **25,01%** (desvio 0,90 pp, mín. 22,9%, máx.
  27,4%). **O resultado principal é robusto a variações plausíveis de
  população** — mesmo com o erro real medido (incluindo o caso extremo de
  +211%), o Recall@5 nunca saiu de uma faixa de ±2,5 pp. Número de
  episódios variou um pouco mais (1.166 ± 21, vs. 1.181 sem perturbação).

## 26. Ablation

| variante | n features | Recall@5 | Recall@10 |
|---|---|---|---|
| v1_features (A) | 38 | 24,22% | 38,61% |
| v1_mais_populacao (B) | 40 | 24,22% | 38,44% |
| v2_incidencia | 29 | 24,98% | 39,71% |
| **v2_casos_incidencia (C)** | 49 | **25,15%** | 39,54% |
| v2_casos_incidencia_populacao (D) | 51 | 24,47% | 39,12% |

**Achado principal do ablation**: as 5 variantes ficam todas dentro de
~1 ponto percentual uma da outra em Recall@5 (24,2%-25,2%). **O ganho sobre
o baseline não vem de qual conjunto de features é usado** — vem de trocar
o TARGET (de casos para incidência), que já muda a composição de episódios
(mais numerosos, mais concentrados em bairros pequenos) o suficiente para
alterar o panorama de baselines vencíveis. Adicionar população/densidade
como feature explícita (variantes B e D) não ajudou — leve queda em ambos
os casos.

## 27. Arquivos criados

- `src/ml/target_incidencia.py`, `onset_incidencia.py`,
  `features_incidencia.py`, `dataset_incidencia.py`, `baselines_incidencia.py`.
- `src/population/population_sensitivity.py`.
- `src/experiment_incidence_ranking_v2.py`, `src/plot_incidence_ranking_v2.py`.
- `reports/ml/incidence_v2_*.csv` (12 arquivos), `resultado_incidence_v2_completo.json`,
  `incidence_v2_fig01..11_*.png` (11 figuras).
- `tests/test_ml_target_incidencia.py`, `test_ml_onset_incidencia.py`,
  `test_ml_features_incidencia.py`, `test_ml_dataset_incidencia.py`,
  `test_ml_baselines_incidencia.py`, `test_population_sensitivity.py`,
  `test_ml_incidence_v2_v1_intacto.py` (42 testes novos).
- Este relatório.

## 28. Testes finais

**629/629 passando** (baseline 587 + 42 novos, 0 regressões). Nenhum teste
existente de V1 foi alterado.

## 29. Classificação

**B — V2 melhora alguns cenários, mas não substitui V1.**

Evidência a favor de B (não A): Recall@5 de V2 não supera o de V1
(estatisticamente indistinguíveis); a disparidade territorial (RPA 5×6)
persiste quase idêntica; o gap antecipação-genuína-vs-recaída persiste
quase idêntico; POÇO continua em detecção zero; o ablation mostra que o
ganho sobre baseline vem da troca de target, não das features de
incidência especificamente.

Evidência de que há valor real (não D, "só descritivo"): IPSEP sai de
detecção zero; grandes episódios têm desempenho melhor (não pior, como em
V1); o ganho em K=5 é robusto (episódio + 2 esquemas de cluster + LOYO sem
inversão de sinal); baixa sensibilidade à incerteza populacional
(Sensibilidade B); estabilidade do ranking preservada ou levemente melhor.

## 30. Recomendação final

**Não substituir V1 por nenhuma variante de V2 nesta etapa.** O caso mais
forte é que a definição de incidência **complementa** V1 — identifica
episódios genuinamente diferentes (39% de não-sobreposição) com uma taxa de
antecipação comparável, e resolve um problema territorial específico
(IPSEP) sem introduzir instabilidade ou fragilidade nova à incerteza
populacional. Se uma decisão de produto exigir escolher só um, `v1` (casos)
e `v2_casos_incidencia` são igualmente defensáveis — a escolha deveria
depender de qual FALSO NEGATIVO é operacionalmente mais caro (perder um
bairro pequeno com pico de incidência real, ou dar peso a um evento que só
existe pela normalização populacional), não de qual número é maior nesta
tabela. Não avançar para tuning, novo algoritmo, incorporação de clima, ou
alteração do dashboard — regra de parada desta etapa. A pesquisa de ML é
encerrada novamente aqui.
