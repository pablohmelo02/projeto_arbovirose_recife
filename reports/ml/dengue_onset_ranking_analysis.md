# Onset + ranking territorial preventivo — dengue por bairro

> Continuação de `reports/ml/dengue_early_warning_optimization.md`
> (classificação anterior: B — melhorou, mas ainda apresenta fragilidades
> relevantes; decisão preservada: NÃO integrar ao dashboard). Execução
> real, reprodutível via `python -m src.evaluate_dengue_onset_ranking`.
> Todos os números vêm de `reports/ml/resultado_onset_ranking_completo.json`
> e dos CSVs desta pasta — nenhum é estimado à mão.

## 1. Estado preservado

- `git status`: mesmo working tree das etapas anteriores. Baseline de
  testes confirmado antes de qualquer mudança: **306/306**.
- Bronze, Silver, Gold, dados climáticos e dashboard **não foram
  alterados**. O modelo/target das etapas anteriores (`estado_alto_risco`,
  `montar_dataset`) **permanece intacto como referência comparativa** —
  nada foi removido ou sobrescrito.

## 2. Motivação e alinhamento com o desafio

O desafio da Prefeitura é **antecipação territorializada** — "quais
bairros vão precisar de ação preventiva em breve", não "este bairro está
tecnicamente em risco elevado amanhã" (que inclui trivialmente continuar
um surto já em andamento). Esta etapa reformula o problema em torno de
**onset** (início de um NOVO episódio) e trata o produto principal como
**ranking territorial semanal**, não classificação binária isolada —
mais próximo de como a Vigilância realmente precisaria consumir a
informação: "quais K bairros priorizar esta semana", não "sim/não para
94 bairros".

## 3. Definição formal de ONSET (`src/ml/onset.py`)

Reaproveita a definição de episódio já existente
(`alert_metrics.construir_episodios`) — um onset é a **primeira semana**
de um episódio de risco elevado; semanas seguintes do mesmo episódio são
continuação, não onsets novos (exemplo do pedido: SE 21-22-23 consecutivas
→ onset = SE 21, não três eventos). Testado explicitamente
(`test_onset_marca_so_a_primeira_semana_do_episodio`).

`target_onset_hN(t) = 1` se existir um onset do MESMO bairro em
`(t, t+N]`; `0` se não existir nenhum; `NaN` se parte da janela tiver
estado indefinido (histórico insuficiente) e nenhum onset tiver sido
encontrado antes disso.

**Episódio já ativo em `t` não vira onset "novo" por continuar em `t+1`**:
como onset exige a semana anterior em `estado=0`, uma continuação nunca é
"descoberta" como onset — testado explicitamente
(`test_onset_nao_marca_semanas_de_continuacao_mesmo_com_horizonte_maior`).
Onsets com um "gap" (episódio anterior termina, volta a `0`, novo episódio
começa depois) são corretamente contados como eventos novos e distintos
(`test_onset_com_gap_conta_como_novo_episodio`).

**Sem leakage**: teste adversarial (`test_alterar_casos_apenas_no_futuro_nao_muda_onset_de_linhas_anteriores`)
altera `casos` da última semana da série e confirma que `target_onset_h1/h2/h3`
de todas as linhas anteriores (fora do alcance da janela) permanecem
idênticos.

## 4. Horizontes avaliados

| Horizonte | Definição | Prevalência (dataset completo) |
|---|---|---:|
| h=1 | onset ocorrerá em t+1? | 5,18% |
| **h=3 (principal)** | **onset ocorrerá entre t+1 e t+3?** | **14,76%** |
| Formulação A (referência) | estado elevado em t+1 (inclui continuação) | 12,03% |

**h=3 escolhido como principal** — maior valor preventivo (mais tempo de
reação) e melhor desempenho preditivo bruto: PR-AUC médio no walk-forward
**0,314 (h=3) vs 0,197 (h=1)** — a janela mais larga não é só mais útil
operacionalmente, é também mais fácil de acertar (mais eventos por linha,
sinal mais denso). Interessante: a taxa de "bairro no Top-10 antes do
onset" é **similar ou até levemente melhor para h=1 em alguns anos**
(ex.: 2019: 54,7% h=1 vs 50,3% h=3) — o horizonte não muda drasticamente
o comportamento do RANKING em si, só a métrica de classificação
subjacente. h=2 não recebeu pipeline completo (regra de não construir 3
pipelines completos sem necessidade), mas está implementado e disponível
(`HORIZONTES_ONSET`) para uso futuro.

## 5. Datasets (`dataset_formulacao_*` em `resultado_onset_ranking_completo.json`)

| Formulação | Linhas finais | Positivos | Prevalência |
|---|---:|---:|---:|
| A (estado t+1) | 58.750 | 7.069 | 12,03% |
| B h=1 (onset) | 58.750 | 3.043 | 5,18% |
| **B h=3 (onset, principal)** | 58.562 | 8.645 | **14,76%** |

Mesmas features de sempre (`epi básica + sazonal + território + histórico
local + momentum`, sem clima — decisão explícita mantida, ver seção 8 do
pedido e `reports/ml/dengue_early_warning_optimization.md`). Mesmo modelo
de árvore (`HistGradientBoostingClassifier`, hiperparâmetros já
escolhidos na etapa de otimização: `max_depth=4, learning_rate=0.1,
max_iter=150` — reaproveitados sem nova busca).

## 6. Walk-forward por ano (`onset_walk_forward_h3.csv`)

| Ano | Prevalência | PR-AUC | Recall | Precision | F1 | Episódios reais | No Top-10 antes (%) | Lead time mediano |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 18,5% | 0,479 | 0,712 | 0,401 | 0,513 | 318 | 50,3% | 2,0 |
| 2020 | 8,7% | 0,262 | 0,505 | 0,234 | 0,320 | 150 | 46,0% | 2,0 |
| 2021 | 19,8% | 0,474 | 0,726 | 0,388 | 0,506 | 341 | 43,1% | 2,0 |
| **2022** | 4,6% | **0,108** | 0,371 | 0,089 | 0,143 | 81 | 44,4% | 2,5 |
| 2023 | 7,3% | 0,168 | 0,410 | 0,153 | 0,223 | 117 | 48,7% | 3,0 |
| 2024 | 24,1% | 0,294 | 0,520 | 0,258 | 0,344 | 406 | 37,9% | 2,0 |
| 2025 | 23,0% | 0,416 | 0,784 | 0,320 | 0,454 | 397 | 37,5% | 2,0 |

| Resumo | PR-AUC |
|---|---:|
| Média / mediana | 0,314 / 0,294 |
| Mínimo / máximo | 0,108 (2022) / 0,479 (2019) |
| **Desvio-padrão** | **0,147** |

**Achado central desta etapa**: comparado à Formulação A (mesma
comparação, `reports/ml/dengue_early_warning_optimization.md`: média
0,337, mediana 0,327, **mínimo 0,074**, máximo 0,664, **desvio 0,201**),
a formulação de onset tem pico mais baixo mas **piso bem mais alto (0,108
vs 0,074) e desvio-padrão menor (0,147 vs 0,201)** — o sistema é
genuinamente **mais estável entre anos epidemiológicos**, mesmo sem
resolver completamente a instabilidade (2022 ainda é claramente o pior
ano). Isso é uma melhora real na fragilidade mais citada nas duas etapas
anteriores.

**2022 (não 2023) é agora o pior ano** — coerente com o diagnóstico da
etapa anterior: 2022 teve o menor número de episódios (81) e a menor
prevalência de todos os anos avaliados, o que já limitava qualquer target
baseado em eventos raros.

## 7. Recall@K (definição operacional — % de episódios com o bairro no Top-K antes do início)

Esta é a métrica pedida na seção 12: **para cada K, percentual de novos
episódios cujo bairro apareceu no Top-K em alguma semana das 4 anteriores
ao início real** (`ranking.posicao_antes_de_episodios` +
`resumo_posicao_antes_de_episodios`) — não confundir com o "Recall@K
semanal" (linha-a-linha, reportado à parte na seção 7.1) usado nas etapas
anteriores.

### 7.1 Modelo (onset h=3) vs Formulação A vs baselines (`onset_comparacao_baselines_ranking.csv`)

| Método | Recall@5 | Recall@10 | Recall@15 | Recall@20 | Lead time mediano |
|---|---:|---:|---:|---:|---:|
| Casos atuais (`casos_t`) | 11,4% | 20,4% | 29,8% | 37,7% | 2,7 sem. |
| Crescimento recente (`taxa_crescimento_suavizada`) | 18,4% | 34,7% | **48,8%** | **63,2%** | 2,6 sem. |
| Razão histórica local (`razao_limiar_historico`) | 19,8% | 35,8% | 48,7% | 57,9% | 2,7 sem. |
| **Modelo (onset h=3)** | **25,8%** | **38,4%** | 48,2% | 57,6% | 2,4 sem. |
| Formulação A (estado t+1, referência) | 20,8% | 33,2% | 43,3% | 52,7% | 2,5 sem. |

**Achado honesto e central**: o modelo supera claramente os baselines só
em **Top-5** (25,8% vs melhor baseline 19,8% — +6 pontos, ganho relativo
de ~30%) e ainda vence com folga em **Top-10** (38,4% vs 35,8%). Mas em
**Top-15/20, os baselines simples (crescimento recente, razão histórica)
empatam ou superam o modelo** (63,2% vs 57,6% do modelo em Top-20!). Isso
significa: **o valor do Machine Learning se concentra exatamente no
cenário operacional mais restritivo** (poucos bairros priorizáveis por
semana) — quando a "capacidade" aumenta para 15-20 bairros, um ranking
simples por crescimento recente já captura praticamente o mesmo sinal.
Esse é um resultado importante para a decisão de produto (seção 20): não
force ML onde um ranking simples já resolve.

O modelo (onset h=3) também supera a Formulação A (estado t+1) em TODOS
os K — confirma que reformular o problema em torno de onset (não estado)
ajuda a ranquear melhor os bairros que precisam de atenção, mesmo com a
mesma arquitetura de modelo.

### 7.2 Recall@K semanal (linha-a-linha, complementar)

| K | Recall micro | Recall macro |
|---:|---:|---:|
| 5 | 10,2% | 15,1% |
| 10 | 17,6% | 22,4% |
| 15 | 24,8% | 31,0% |
| 20 | 31,3% | 37,8% |

Números mais baixos que a versão "por episódio" acima — esperado: como o
target `h=3` marca várias semanas seguidas como positivas por episódio
(até 3 por evento), exigir que TODA semana individualmente rankeie bem
(não só uma vez na janela) é um padrão mais rígido. As duas métricas
respondem perguntas diferentes; a versão "por episódio" (seção 7.1) é a
mais alinhada ao uso operacional real (perguntar "este bairro apareceu
destacado alguma vez antes do surto?", não "toda semana individualmente").

## 8. Precision@K (`ranking_modelo_onset_h3.precision_em_k`)

| K | Precision média (por semana) |
|---:|---:|
| 5 | 34,5% |
| 10 | 29,9% |
| 15 | 28,1% |
| 20 | 26,6% |

Em qualquer semana, ~1 em cada 3 bairros do Top-5 realmente tem um onset
dentro da janela de 3 semanas — cai gradualmente para ~1 em 4 no Top-20
(esperado: K maior dilui precisão). Isso é MUITO acima da prevalência de
base (14,76%) — o Top-5 concentra risco real ~2,3x acima do acaso.

## 9. Lead time e antecedência mínima

| | Modelo onset h=3 |
|---|---:|
| Lead time médio (episódios detectados no Top-K) | 2,43 semanas |
| % episódios com ≥1 semana de antecedência | **100%** (por desenho — janela mínima é 1 semana) |
| % episódios com ≥2 semanas | **69,2%** |
| % episódios com ≥3 semanas | **46,7%** |

Quase metade dos episódios detectados têm 3+ semanas de antecedência real
— compatível com a janela operacional de 1-4 semanas já usada nas etapas
anteriores.

## 10. Estabilidade do ranking (`estabilidade_por_k`)

| K | Jaccard médio (Top-K entre semanas consecutivas) |
|---:|---:|
| 5 | 0,230 |
| 10 | 0,294 |
| 15 | 0,346 |
| 20 | 0,399 |

O Top-K **muda de forma substancial semana a semana** (Jaccard bem abaixo
de 0,5 em todos os K) — não é caótico (0,0 seria troca total), mas está
longe de ser uma lista "fixa" de bairros crônicos. Isso é esperado dado
que o alvo é dinâmico (onset, não risco crônico), mas é um limite real
para comunicar "estes são os bairros de risco" como algo estável — a
lista precisa ser recalculada e comunicada toda semana.

## 11. Persistência no ranking antes do onset (`onset_persistencia_topk_h3.csv`)

| Métrica | Valor |
|---|---:|
| Semanas consecutivas médias no Top-10 antes do onset | 0,36 |
| **% de episódios com ≥2 semanas consecutivas no Top-10** | **8,3%** |

**Limitação real**: na maioria dos episódios, a aparição do bairro no
Top-10 antes do onset é um evento **isolado de 1 semana**, não uma
tendência sustentada de vários dias seguidos subindo no ranking — só
8,3% dos episódios têm 2+ semanas consecutivas de destaque. Isso limita a
confiança que se pode depositar num único "pico" de ranking como sinal
robusto — é mais um alerta pontual do que uma trajetória clara e
crescente de risco.

## 12. Grandes episódios (top 10% por intensidade)

| | Todos os episódios | Grandes episódios (top 10%) |
|---|---:|---:|
| Recall@5 | 25,8% | 18,5% |
| Recall@10 | 38,4% | 30,4% |
| Recall@15 | 48,2% | 39,1% |
| Recall@20 | 57,6% | 51,1% |

**Diferente da etapa anterior** (onde grandes surtos tinham desempenho
MELHOR — 79% de detecção via classificação binária), aqui os grandes
episódios têm desempenho **pior** que a média sob a métrica de ranking.
Explicação plausível: a métrica de ranking é **competitiva/relativa**
(top-K entre os 94 bairros da cidade na mesma semana) — durante uma
epidemia grande, MÚLTIPLOS bairros costumam subir simultaneamente
("epidemia grande" tende a ser um fenômeno de cidade, não só de um
bairro isolado), então mesmo um bairro genuinamente em risco alto pode
não entrar no Top-20 porque vários outros bairros também estão em alta
ao mesmo tempo. Isso não invalida o achado anterior (detecção binária
"este bairro passou do limiar" continua alta em grandes surtos) — mas
mostra que **ranking competitivo e classificação binária respondem
perguntas operacionalmente diferentes**, e essa diferença deve ser
comunicada explicitamente se o produto for adiante.

## 13. Desempenho por ano (`onset_desempenho_por_ano.csv`)

| Ano | Episódios | Recall@10 | Recall@20 | Lead time mediano |
|---:|---:|---:|---:|---:|
| 2023 | 117 | 42,7% | 62,4% | 3,0 |
| 2024 | 406 | 37,2% | 57,4% | 2,0 |
| 2025 | 397 | 38,3% | 56,4% | 2,0 |

**2023 (incluído, não excluído)**: sob a métrica de ranking, 2023 tem o
MELHOR Recall@10/20 dos três anos de teste — reforça o achado da etapa
anterior de que 2023 não é uma falha generalizada do sistema, é
específico da métrica de classificação sensível a baixa prevalência.

## 14. Desempenho por bairro e por RPA

**Bairros com 0% de detecção (Top-20)**: caiu de **7 (etapa anterior) para
2** — POÇO (1 episódio) e PONTO DE PARADA (3 episódios). Mediana da taxa
de detecção (Top-20) entre bairros com ≥3 episódios: **55,6%** (subiu de
50% na etapa anterior).

**RPA (`onset_desempenho_por_rpa.csv`)** — diagnóstico territorial, não
substitui o bairro:

| RPA | Episódios | Recall@10 | Recall@20 |
|---:|---:|---:|---:|
| 1 | 129 | 31,0% | 50,4% |
| 2 | 146 | 39,7% | 63,7% |
| 3 | 277 | 31,4% | 53,8% |
| 4 | 97 | 35,1% | 53,6% |
| **5** | 197 | **59,4%** | **74,1%** |
| **6** | 74 | **23,0%** | **33,8%** |

**Achado novo e relevante**: há uma disparidade regional real — RPA 5 tem
o dobro do Recall@10 da RPA 6 (59,4% vs 23,0%). Essa é uma limitação que
não aparecia na análise por classificação binária das etapas anteriores
(que olhava só por bairro) e merece investigação antes de qualquer
comunicação territorial agregada.

### 14.1 IPSEP

| | Etapas anteriores (classificação) | Esta etapa (onset + ranking) |
|---|---|---|
| Detecção | 0% (0 de 6 episódios) | **16,7% (1 de 6)** — ainda fraco, mas não mais zero |
| Posição mediana antes do início | — | 39ª (de ~94 — ainda ruim) |
| Lead time (episódio detectado) | — | 3 semanas |

IPSEP (RPA 6 — a RPA de pior desempenho da tabela acima) melhora
marginalmente mas **continua sendo um caso de falha relevante**: mesmo
reformulando o problema inteiro (onset em vez de estado, ranking em vez
de classificação), o modelo não consegue destacar esse bairro de volume
substancial de forma consistente. Isso reforça a hipótese, já levantada
na etapa anterior, de que o problema é específico do bairro/região (RPA
6), não da formulação do problema.

## 15. Cenário de antecipação genuína (seção 26 do pedido)

Separando episódios em que o bairro **já estava ativo numa janela recente
anterior** (episódio prévio que terminou pouco antes, "recaída") dos que
representam uma **retomada genuína após período de baixa** (sem atividade
elevada nas 4 semanas antes do início da janela de antecipação):

| | Episódios genuínos (762/920) | Após episódio recente (158/920) |
|---|---:|---:|
| Recall@5 | 21,0% | **48,7%** |
| Recall@10 | 33,5% | **62,0%** |
| Recall@20 | 53,8% | **76,0%** |

**Achado importante**: é muito mais fácil para o sistema antecipar um
onset que ocorre logo depois de um episódio recente ("recaída" — feições
de momentum/histórico ainda elevadas) do que um onset genuinamente novo
depois de um período de baixa atividade. **O cenário de verdadeira
antecipação preventiva (seção 26 — exatamente o que a Prefeitura mais
precisa, detectar o INÍCIO de algo novo, não a continuação de um padrão
recente) é o mais difícil e o mais frequente (762 de 920 episódios)** —
uma limitação honesta e central para a avaliação de utilidade real do
sistema.

## 16. Formulação A × Formulação B — qual é mais útil?

| Critério | Formulação A (estado t+1) | Formulação B (onset h=3) |
|---|---|---|
| PR-AUC médio (walk-forward) | 0,337 | 0,314 |
| **Desvio-padrão entre anos** | 0,201 | **0,147 (mais estável)** |
| Recall@10 (por episódio, antes do início) | 33,2% | **38,4%** |
| Recall@20 (por episódio, antes do início) | 52,7% | 57,6% |
| Semântica | Mistura persistência com início | **Isola o evento relevante (início)** |
| Alinhamento com o desafio | Indireto | **Direto** ("antecipar início de surto") |

**A Formulação B (onset + ranking) é mais útil para o problema da
Prefeitura** — não por ter PR-AUC absoluto maior (é ligeiramente menor),
mas por (1) isolar exatamente o evento que importa prevenir (início, não
persistência), (2) ser mais estável entre anos epidemiológicos, e (3)
rankear melhor os bairros antes do início real em todos os K testados.
A escolha não foi feita "apenas pela métrica estatística" — o critério
decisivo foi a semântica mais alinhada ao desafio, sustentada por métricas
comparáveis ou melhores.

## 17. Limitações

1. **Baselines simples empatam ou superam o modelo em Top-15/Top-20** —
   o valor de ML se concentra em Top-5/Top-10.
2. **Persistência de sinal fraca**: só 8,3% dos episódios têm 2+ semanas
   consecutivas de destaque no ranking antes do início — a maioria é um
   sinal de 1 semana.
3. **Disparidade regional real** (RPA 5: 74% vs RPA 6: 34% em Recall@20)
   — não investigada a fundo nesta etapa (diagnóstico, não correção).
4. **Cenário de antecipação genuína é o mais difícil e o mais comum**
   (762/920 episódios) — o sistema ajuda mais em "recaídas" que em
   surtos genuinamente novos.
5. **Grandes episódios têm desempenho relativamente pior sob ranking
   competitivo** (ao contrário do achado da etapa anterior sob
   classificação binária) — os dois enquadramentos medem coisas
   diferentes.
6. **IPSEP continua fraco** (16,7%, ainda a pior posição mediana entre
   todos os bairros com episódios).
7. **Estabilidade do ranking moderada** (Jaccard 0,23-0,40 entre semanas
   consecutivas) — a lista de priorização muda de forma substancial
   semana a semana.
8. Clima **não foi revisitado** (decisão explícita mantida da etapa
   anterior).

## 18. Arquivos criados/alterados

**Criados**: `src/ml/onset.py`, `src/evaluate_dengue_onset_ranking.py`,
`tests/test_ml_onset.py`, `tests/test_ml_ranking_avancado.py`,
`reports/ml/dengue_onset_ranking_analysis.md` (este arquivo) + CSVs de
apoio (`onset_walk_forward_h1.csv`, `onset_walk_forward_h3.csv`,
`onset_posicao_antes_episodios_h3.csv`, `onset_persistencia_topk_h3.csv`,
`onset_comparacao_baselines_ranking.csv`, `onset_desempenho_por_ano.csv`,
`onset_desempenho_por_bairro.csv`, `onset_desempenho_por_rpa.csv`,
`resultado_onset_ranking_completo.json`).

**Alterados**: `src/ml/dataset.py` (+`montar_dataset_onset`),
`src/ml/ranking.py` (+`precision_em_k`, +`estabilidade_ranking`,
+`persistencia_consecutiva_antes_de_onset`),
`src/ml/alert_metrics.py` (correção: `construir_episodios` agora
devolve as colunas corretas mesmo com 0 episódios — bug real encontrado
ao testar histórico totalmente indefinido, corrigido antes de afetar
resultados).

**Não alterados**: Bronze, Silver, Gold, `src/eda/`, `dashboard/`,
dados climáticos, `src/ml/target.py`/`src/ml/dataset.py::montar_dataset`
(Formulação A, modelo/target das etapas anteriores preservados como
referência comparativa), `src/ml/baselines.py`.

## 19. Testes finais

**17 testes novos** (definição de onset — só primeira semana conta,
episódio já ativo não vira onset novo, gap entre episódios conta como
novo evento, horizontes h1/h3, leakage adversarial, dois bairros não se
misturam, histórico insuficiente fica indefinido; Precision@K,
estabilidade do ranking — Jaccard 0/1, persistência consecutiva no Top-K
antes do onset). **Suíte completa: 317/317 passando** (baseline era 306,
**0 regressões**).

## 20. Classificação final

**B — Existe valor, mas as limitações ainda são fortes.**

Justificativa: há ganho real e específico (Recall@5 do modelo 25,8% vs
melhor baseline 19,8%; maior estabilidade entre anos que a Formulação A;
zero-detecção caiu de 7 para 2 bairros), mas os baselines simples
(crescimento recente, razão histórica) **empatam ou superam o modelo**
em Top-15/20 — o valor de ML não é uniforme em toda a faixa operacional.
Persistência de sinal é fraca (8,3% com 2+ semanas consecutivas),
disparidade regional real e não explicada (RPA 6), e o cenário mais
importante para o desafio (antecipação genuína, não recaída) é
justamente o mais fraco (Recall@20 de 53,8% vs 76,0% em recaídas). Não é
"A" (faltam evidência de robustez territorial e vantagem consistente em
toda faixa de K); não é "C" (há vantagem real e mensurável em Top-5/10,
não é "praticamente equivalente" em toda a análise); não é "D" (o sinal é
real, replicável, mais estável entre anos que a formulação anterior).

## 21. Decisão obrigatória

> Devemos integrar o ranking de risco ao dashboard Recife Alerta como
> funcionalidade experimental de prova de conceito?

## NÃO

A decisão de não integrar, herdada da etapa anterior, **é preservada**.
Justificativa adicional específica desta etapa: o valor do modelo sobre
baselines simples não é uniforme (só Top-5/10), a disparidade regional
(RPA 6) é um achado novo não investigado, e o cenário mais relevante para
o objetivo do desafio (antecipação genuína) é o mais fraco de todos os
subgrupos analisados. Expor isso como funcionalidade de produto agora
arriscaria comunicar mais confiança do que os dados sustentam
especialmente na região/cenário que mais importa.

**Se e quando integrado no futuro**: a saída deveria ser **score/ranking
de prioridade** (posição relativa entre os 94 bairros), não probabilidade
— não porque a calibração seja tecnicamente ruim (a etapa anterior já
melhorou isso com isotonic), mas porque a instabilidade do ranking
semana a semana (Jaccard 0,23-0,40) e a fraqueza específica no cenário de
antecipação genuína tornam mais honesto comunicar "este bairro está entre
os N de maior atenção esta semana" do que "X% de chance de surto".

## 22. Frase para a Prefeitura (preparada, não publicada — decisão é NÃO integrar ainda)

> "No backtest histórico (2023-2025), considerando capacidade de
> priorização de até 10 bairros por semana, o sistema conseguiu sinalizar
> antecipadamente **38,4%** dos episódios de risco elevado de dengue, com
> antecedência mediana de **2,4 semanas**. Com capacidade para 20
> bairros, esse valor sobe para **57,6%**. Em episódios de maior
> intensidade (top 10% por volume de casos), esses valores são,
> respectivamente, **30,4%** e **51,1%**."

Nenhuma afirmação de redução de incidência, internações ou eficácia de
intervenção foi feita — esses impactos exigiriam um piloto real, fora do
escopo desta etapa analítica.

## 23. Recomendação seguinte

1. Investigar a disparidade regional (RPA 6, incluindo IPSEP) antes de
   qualquer nova iteração — pode ser um problema de dado (menos
   histórico local confiável) ou um padrão epidemiológico genuinamente
   diferente naquela região.
2. Investigar por que "antecipação genuína" (sem recaída recente) é tão
   mais difícil — pode indicar que features de gatilho externo (não
   capturadas por casos/sazonalidade/histórico local) seriam necessárias
   para esse cenário específico.
3. Considerar um "ranking híbrido" simples (combinação do modelo com
   `razao_limiar_historico`, já que os dois têm desempenho parecido em
   K maiores) como forma de robustecer o Top-15/20 sem adicionar
   complexidade de um novo modelo.
4. Só depois disso, reconsiderar uma página experimental no dashboard —
   com ranking (não probabilidade), aviso de instabilidade semanal, e
   destaque específico para a limitação regional.
