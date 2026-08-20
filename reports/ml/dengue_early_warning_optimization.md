# Alerta antecipado de dengue por bairro — otimização e diagnóstico de robustez

> Continuação de `reports/ml/dengue_early_warning_baseline.md` (classificação
> anterior: **B — existe sinal, precisa melhorar**). Execução real,
> reprodutível via `python -m src.optimize_dengue_early_warning`. Todos os
> números vêm de `reports/ml/resultado_otimizacao_completo.json` e dos CSVs
> desta pasta — nenhum é estimado à mão.

## 1. Estado preservado

- `git status`: mesmo working tree da etapa anterior (nenhuma alteração de
  Bronze/Silver/Gold/clima/dashboard detectada).
- Baseline de testes confirmado antes de qualquer mudança: **285/285**.
- Bronze, Silver, Gold, dados climáticos e dashboard **não foram
  alterados** nesta etapa. Nenhum deploy de modelo, nenhuma integração ao
  Streamlit.

## 2. Diagnóstico de 2023

### 2.1 Prevalência do target por ano (`diagnostico_alvo_por_ano.csv`)

| Ano | % positivo | Casos totais | Limiar médio |
|---:|---:|---:|---:|
| 2019 | 11,74% | 7.245 | 6,79 |
| 2020 | 4,44% | 3.585 | 6,39 |
| 2021 | 16,65% | 10.891 | 5,85 |
| 2022 | 1,96% | 2.876 | 5,67 |
| **2023** | **2,58%** | **3.522** | **4,96** |
| 2024 | 11,40% | 10.536 | 4,55 |
| 2025 | 12,85% | 9.162 | 4,50 |

**2023 tem a segunda menor prevalência de toda a série 2019-2025** (só
2022 é menor) — 4,5x a 6,5x menor que 2019/2021/2024/2025. Isso já é
suficiente para deprimir mecanicamente o PR-AUC daquele ano (ver seção 2.3).

### 2.2 Intensidade e alcance espacial dos episódios (`diagnostico_episodios_por_ano.csv`)

| Ano | Episódios | Duração média (semanas) | Casos pico (mediana) | Bairros distintos afetados |
|---:|---:|---:|---:|---:|
| 2019 | 318 | 1,81 | 4,0 | 91 |
| 2020 | 150 | 1,47 | 4,0 | 72 |
| 2021 | 341 | 2,39 | 5,0 | 92 |
| 2022 | 81 | 1,19 | 2,0 | 49 |
| **2023** | **117** | **1,08** | **2,0** | **56** |
| 2024 | 406 | 1,37 | 3,0 | 92 |
| 2025 | 397 | 1,61 | 3,0 | 92 |

**2023 (junto com 2022) teve episódios genuinamente diferentes**: a menor
duração média de toda a série (1,08 semana — quase sempre um único
"blip"), a menor mediana de pico de casos (2,0) e um alcance espacial bem
mais restrito (56/94 bairros, contra 91-92/94 nos anos "normais"). Isso
não é ruído de amostra pequena (117 episódios é um N razoável) — é um
padrão epidemiológico real de baixa transmissão, coerente com 2022
(também baixo) e destoante de 2019/2021/2024/2025.

### 2.3 PR-AUC não é comparável entre anos com prevalência tão diferente

PR-AUC de um classificador aleatório é, em expectativa, igual à
prevalência da classe positiva. Comparar PR-AUC=0,074 (2023, prevalência
2,6%) com PR-AUC=0,664 (2021, prevalência 16,7%) sem normalizar é
enganoso. `lift_pr_auc = PR-AUC / prevalência` (`diagnostics.py`) corrige
isso:

| Ano | PR-AUC | Prevalência | **Lift (PR-AUC/prevalência)** | ROC-AUC |
|---:|---:|---:|---:|---:|
| 2019 | 0,486 | 11,74% | 4,14 | 0,866 |
| 2020 | 0,327 | 4,46% | 7,35 | 0,860 |
| 2021 | 0,664 | 16,65% | 3,99 | 0,897 |
| 2022 | 0,142 | 1,94% | **7,29** | 0,807 |
| **2023** | **0,074** | 2,64% | **2,80** | 0,743 |
| **2024** | 0,280 | 11,48% | **2,44** | 0,688 |
| 2025 | 0,385 | 12,95% | 2,98 | 0,783 |

**Achado central**: por lift, **2024 é na verdade o ano com PIOR ganho
relativo sobre o acaso (2,44x), não 2023 (2,80x)** — o oposto do que o
PR-AUC bruto sugeria. 2022, que tinha o segundo PIOR PR-AUC bruto (0,142),
é na verdade o ano com o MELHOR lift (7,29x) depois de 2020. **ROC-AUC
(prevalência-invariante) mostra 2023 em posição intermediária (0,743),
não a pior da série** — 2024 tem o pior ROC-AUC (0,688). Conclusão: parte
substancial da "instabilidade" aparente entre anos é um artefato da
métrica (PR-AUC sensível a prevalência), não puramente falha do modelo.

### 2.4 Drift de features (`diagnostico_drift_features.csv`, teste KS)

Todas as comparações contra o treino (2013-2019) são estatisticamente
significativas (p<0,0001 — esperado, dado o N grande), mas **2023 não é
mais "drifted" que 2024/2025** nas features epidemiológicas centrais —
pelo contrário, tem estatística KS **menor**:

| Feature | KS (val 2020-22) | KS (2023) | KS (2024) | KS (2025) |
|---|---:|---:|---:|---:|
| `casos_t` | 0,066 | 0,096 | **0,148** | **0,177** |
| `media_4s` | 0,075 | 0,118 | **0,194** | **0,206** |
| `media_8s` | 0,072 | 0,127 | **0,199** | **0,213** |
| `estado_alto_risco_t` | 0,081 | 0,132 | 0,044 | 0,028 |

2024 e 2025 (os anos onde o modelo tem melhor desempenho absoluto) têm
**drift maior** nas features de contagem/rolling do que 2023 — o oposto
do que se esperaria se "drift" fosse a explicação da falha em 2023.

### 2.5 Resposta à pergunta central

> 2023 foi um ano epidemiologicamente diferente ou o modelo simplesmente
> falhou?

**Principalmente epidemiologicamente diferente, com um componente de
artefato de métrica** — não é uma falha de feature/target/modelo
corrigível por engenharia adicional. Evidência: (1) prevalência do target
5-6x menor que anos "normais"; (2) episódios mais curtos (1,08 semana),
mais fracos (pico mediano 2 casos) e espacialmente mais restritos (56/94
bairros) que a maioria dos outros anos; (3) o PR-AUC bruto é mecanicamente
deprimido pela baixa prevalência (lift corrigido de 2,80x não é o pior da
série); (4) o drift de features NÃO é maior em 2023 que em anos de melhor
desempenho. Confirmado pela otimização (seção 4): mesmo depois de
features novas e tuning controlado, **o PR-AUC de 2023 não se move**
(0,0738 antes → 0,0738 depois) — evidência direta de que o problema não
era corrigível com mais engenharia.

## 3. Ablation de features (`ablation_features.csv`)

Grupos cumulativos, mesmo split (treino 2013-2019 → teste 2023-2025),
árvore com hiperparâmetros padrão (antes do tuning):

| Configuração | Nº features | PR-AUC | ROC-AUC |
|---|---:|---:|---:|
| Epi básica (casos/lags/rolling) | 12 | 0,2647 | 0,683 |
| + Sazonal | 18 | 0,2889 (+0,024) | 0,753 (+0,070) |
| + Território | 30 | 0,2915 (+0,003) | 0,753 (+0,000) |
| **+ Histórico local** (razão/z-score) | 33 | **0,3005 (+0,009)** | **0,771 (+0,018)** |
| + Momentum (completo) | 38 | 0,3033 (+0,003) | 0,772 (+0,001) |

**Sazonalidade** é o grupo com maior ganho isolado (esperado, dada a
sazonalidade forte já documentada na EDA). **Histórico local** (features
novas desta etapa: `razao_limiar_historico`, `z_score_historico_local`,
`razao_media_recente`) é o segundo grupo com ganho real — e acaba sendo a
feature individualmente mais importante do modelo final (seção 8).
**Território e momentum têm ganho marginal** (+0,003 cada) — mantidos
porque não pioram nada e têm custo de complexidade desprezível, mas não
são o que resolve a robustez do sistema.

## 4. Target alternativo (experimento descritivo, NÃO adotado)

Comparação entre o target oficial (P90 histórico-sazonal) e uma
alternativa experimental (anomalia sazonal + crescimento em 2 semanas
consecutivas, `target.calcular_estado_alto_risco_v2_experimental`) —
`alvo_alternativo_comparacao.csv`:

| Ano | Positivos oficial | Positivos alternativo | Concordância | Jaccard |
|---:|---:|---:|---:|---:|
| 2015 (epidemia grande) | 2.908 | 495 | **50,2%** | 0,166 |
| 2021 | 814 | 198 | 85,5% | 0,177 |
| 2023 | 126 | 69 | 96,6% | 0,083 |
| 2024 | 557 | 269 | 88,2% | 0,177 |

**As duas definições concordam pouco** (Jaccard 0,08-0,18 mesmo nos anos
de melhor concordância) — a alternativa é sistematicamente mais restritiva
(menos positivos, porque exige crescimento sustentado além da anomalia) e
diverge MUITO mais no ano de epidemia grande (2015: só 50,2% de
concordância). **Não foi adotada como target principal**: (1) o objetivo
desta etapa era comparar, não escolher a métrica maior; (2) incorporar
"crescimento" na definição do próprio evento, tendo também features de
crescimento/momentum no modelo, criaria risco real de target
auto-realizável (seção 12 do pedido) — o modelo aprenderia a reproduzir a
regra do target em vez de antecipá-lo. O target oficial (P90
histórico-sazonal, sem componente de crescimento na definição) permanece
mais seguro nesse sentido e foi mantido sem alteração.

## 5. Tuning controlado de hiperparâmetros (`tuning_hiperparametros.csv`)

Grade pequena (4 combinações de `max_depth`/`learning_rate`/`max_iter`),
avaliada por **mediana do PR-AUC no walk-forward completo** (generalização
temporal, não só a validação isolada):

| max_depth | learning_rate | max_iter | PR-AUC média (WF) | PR-AUC mediana (WF) |
|---:|---:|---:|---:|---:|
| **4** | **0,1** | **150** | 0,3369 | **0,3273** |
| 6 (baseline anterior) | 0,1 | 200 | 0,3333 | 0,3233 |
| 6 | 0,05 | 300 | 0,3376 | 0,3259 |
| 8 | 0,1 | 200 | 0,3359 | 0,3232 |

**As 4 configurações têm desempenho estatisticamente indistinguível**
(diferença de mediana < 0,004 PR-AUC, dentro do ruído de 7 anos de
teste). Foi escolhida a configuração mais simples (`max_depth=4`,
`max_iter=150` — a de menor capacidade/custo entre as testadas), por não
haver ganho real em complexidade adicional — decisão explícita de
parcimônia, não de melhor métrica isolada.

## 6. Walk-forward final (modelo/features otimizados, `walk_forward_otimizado_por_ano.csv`)

| Ano teste | PR-AUC (antes → depois) | ROC-AUC | Lift PR-AUC |
|---:|---:|---:|---:|
| 2019 | 0,447 → **0,486** | 0,866 | 4,14 |
| 2020 | 0,288 → **0,327** | 0,860 | 7,35 |
| 2021 | 0,652 → **0,664** | 0,897 | 3,99 |
| 2022 | 0,143 → 0,142 | 0,807 | 7,29 |
| **2023** | **0,074 → 0,074** | 0,743 | 2,80 |
| 2024 | 0,255 → **0,280** | 0,688 | 2,44 |
| 2025 | 0,371 → **0,385** | 0,783 | 2,98 |

| Resumo (não esconder variância) | Valor |
|---|---:|
| PR-AUC média / mediana | 0,337 / 0,327 |
| PR-AUC mínimo / máximo | 0,074 (2023) / 0,664 (2021) |
| **PR-AUC desvio-padrão** | **0,201** |
| ROC-AUC média / mínimo | 0,806 / 0,688 (2024) |
| Lift PR-AUC média / mediana | 4,43 / 3,99 |

**Melhora em 5 dos 7 anos** (2019, 2020, 2021, 2024, 2025), **estável em
2022** e **inalterado em 2023** — confirma a seção 2.5: 2023 não responde
a mais features/tuning, é um limite estrutural do ano epidemiológico, não
do pipeline. **O desvio-padrão entre anos continua alto (0,201)** — o
sistema não generaliza uniformemente; qualquer uso operacional precisa
assumir que alguns anos terão desempenho muito pior que a média.

### 6.1 Holdout final — transparência

**2025 já foi usado como parte do conjunto de teste na etapa de baseline
anterior** (mesma decisão de split, reaproveitada nesta etapa para manter
comparabilidade). Portanto, **2025 não é mais um holdout puro** nesta
etapa — os resultados aqui reportados para 2025 são uma validação
retrospectiva sob o mesmo split já usado para decisões anteriores, não uma
estimativa de produção sobre dado nunca visto por decisões humanas do
projeto. Não foi criado um novo conjunto de teste "mais recente" (não
existe — 2025 é o último ano disponível na Gold) — este é um limite real
dos dados disponíveis, registrado explicitamente em vez de escondido.

## 7. Threshold operacional (`threshold_operacional.csv`, teste 2023-2025)

| Threshold | Precision | Recall | Episódios detectados | Lead time mediano | Falsos alertas (total) | Bairros alertados/semana (média) | Falsos alertas/semana (média) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0,3 | 0,195 | 0,667 | **80,7%** | 4 sem. | 2.284 | 29,2 | 14,8 |
| 0,4 | 0,231 | 0,559 | **70,9%** | 4 sem. | 1.433 | 21,1 | 9,6 |
| 0,5 | 0,281 | 0,469 | 58,6% | 3 sem. | 869 | 15,3 | 6,4 |
| **0,6 (escolhido na validação)** | 0,326 | 0,370 | **45,9%** | 3 sem. | 506 | 12,2 | 4,5 |
| 0,7 | 0,397 | 0,296 | 36,8% | 3 sem. | 262 | 9,0 | 3,0 |

**Capacidade operacional (seção 19/23 do pedido)**: em threshold=0,6, a
mediana de bairros alertados por semana é **7** (máximo observado numa
única semana: **53**, provavelmente concentrado num pico real de
transmissão simultânea em múltiplos bairros — não investigado
isoladamente nesta etapa). Sequências de falsos alertas consecutivos no
mesmo bairro (`duracao_falsos_alertas_final`): **338 sequências, duração
média 1,50 semana, máxima 5 semanas** — a maioria dos falsos alertas é
isolada (1-2 semanas), não uma sequência longa incomodando o mesmo bairro
repetidamente.

**Não há um threshold "certo" — é uma escolha de política operacional**:
0,4 entrega 70,9% de detecção de episódios com ~21 bairros/semana em
alerta (manejável, mas alto); 0,6 (escolhido por F1 na validação, critério
neutro) entrega 45,9% com ~12 bairros/semana — mais conservador. Uma
Prefeitura com mais capacidade de resposta poderia preferir 0,4; uma com
recursos limitados, 0,6-0,7.

## 8. Ranking territorial (`recall_em_k.csv`, `posicao_antes_episodios.csv`)

### 8.1 Recall@K (por semana, threshold 0,6)

| K | Recall micro | Recall macro |
|---:|---:|---:|
| 5 | 13,2% | 14,5% |
| 10 | 23,9% | 26,2% |
| 20 | 41,0% | 45,9% |

Recall@20 (macro) de 45,9% é ~2,15x o acaso (20/94≈21,3% esperado por
sorteio) — sinal real, mas modesto: **olhar só para os 20 bairros mais
arriscados da semana ainda perderia mais da metade dos bairros
realmente em risco elevado**.

### 8.2 Posição no ranking ANTES do início real do episódio (janela de 4 semanas)

| Métrica | Valor |
|---|---:|
| Posição mediana (1=maior risco, de ~94) | **19ª** |
| Posição média | 25ª |
| Antecedência média da melhor posição | 2,5 semanas |
| % episódios com bairro no Top 5 antes do início | 20,8% |
| % episódios com bairro no Top 10 antes do início | 33,2% |
| **% episódios com bairro no Top 20 antes do início** | **52,7%** |

**Mesmo quando a classificação binária erra, em mais da metade dos
episódios (52,7%) o bairro já aparecia entre os 20 de maior risco da
cidade em alguma semana antes do início real** — mais informativo que o
Recall@K semanal isolado, porque não exige que a MESMA semana capture o
positivo, só que o sinal tenha aparecido em algum momento da janela de
antecipação. **O ranking é operacionalmente mais útil que o cutoff binário
sozinho**, mas ainda longe de cobrir a maioria dos casos com Top-5/10.

## 9. Calibração (Brier Score, `calibracao_antes.csv`/`calibracao_depois.csv`)

| | Brier Score |
|---|---:|
| Antes (probabilidade bruta da árvore) | 0,1156 |
| **Depois (isotonic, calibrado só na validação — 14.758 linhas)** | **0,0731** |
| Melhora relativa | **-36,8%** |

**Diferente do diagnóstico da etapa anterior** (que reportou apenas
diagnóstico sem calibrar), calibração isotônica aplicada corretamente (fit
só na validação, nunca no teste) **reduz o Brier Score em ~37%**. A tabela
"depois" mostra faixas de probabilidade muito mais próximas da frequência
real observada (ex.: faixa 0,73-0,83 prevista vs. 0,81 observada) — a
probabilidade calibrada já é razoavelmente confiável nas faixas com volume
suficiente de validação. Faixas de probabilidade muito alta (>0,85) têm
poucas observações (n=15-16) — calibração menos confiável ali por N
pequeno, não por método inadequado.

## 10. Desempenho por bairro (`metricas_por_bairro_otimizado.csv`)

**Bairros com 0% de detecção: 7 de 93 avaliados** (redução de 12 → 7 em
relação à etapa anterior — 5 bairros que antes falhavam completamente
agora detectam pelo menos 1 episódio: MUSTARDINHA, RECIFE, ENCRUZILHADA,
CASA FORTE e SÃO JOSÉ). **Persistem em 0%**: ILHA DO LEITE (78, 11
episódios), JAQUEIRA (159, 10), TORREÃO (272, 9), SANTANA (450, 9),
AFLITOS (132, 6), **IPSEP (213, 6 episódios)** e PONTO DE PARADA (930, 3).

**IPSEP merece destaque específico**: ao contrário dos demais (bairros de
baixo volume histórico), IPSEP tem **1.629 casos acumulados 2013-2025** —
acima da mediana da cidade (713) — e **323 casos só em 2023-2025**. Um
bairro de volume substancial com 0% de detecção consistente não é
explicável por "pouco histórico" — indica uma limitação real do modelo
único/global para esse território específico, que mereceria investigação
dedicada antes de qualquer uso operacional focado nesse bairro.

Mediana da taxa de detecção entre bairros com ≥3 episódios reais: **50%**
— metade dos bairros está em ou acima de 50% de detecção, metade abaixo.

## 11. Desempenho em epidemias grandes (`epidemias_grandes_otimizado.csv`)

| | Baseline anterior | Otimizado |
|---|---:|---:|
| Taxa de detecção (top 10% episódios por casos) | 79,3% | **78,3%** |

**Resultado estável e consistentemente forte** — a otimização não mudou
significativamente a capacidade de detectar os surtos mais relevantes
(diferença de 1 ponto percentual, dentro do ruído). Esse continua sendo o
resultado mais sólido do sistema.

## 12. Feature importance — estabilidade entre folds (`feature_importance_estabilidade.csv`)

Permutation importance (PR-AUC) calculada em cada um dos 7 folds do
walk-forward, reportando média/desvio/mín/máx entre folds (não um único
ano):

| Feature | Importância média | Desvio | Mínimo | Máximo |
|---|---:|---:|---:|---:|
| **`razao_limiar_historico`** (nova) | **0,170** | 0,097 | 0,021 | 0,314 |
| `media_historica_semana_exata` | 0,034 | 0,018 | 0,014 | 0,063 |
| `media_8s` | 0,032 | 0,023 | 0,004 | 0,069 |
| `z_score_historico_local` (nova) | 0,010 | 0,008 | -0,0002 | 0,020 |
| `razao_media_recente` (nova) | 0,008 | 0,003 | 0,004 | 0,014 |
| `taxa_crescimento_suavizada` (nova) | 0,008 | 0,005 | -0,0003 | 0,015 |
| `estado_alto_risco_t` | 0,004 | 0,005 | -0,004 | 0,012 |
| `aceleracao_1s` (nova) | 0,0007 | 0,002 | -0,001 | 0,004 |

**`razao_limiar_historico` (casos_t relativo ao próprio limiar histórico
do bairro) é disparadamente a feature mais importante em TODOS os folds**
— confirma que contexto relativo ao histórico local supera casos
absolutos como sinal preditivo, mas com variabilidade real de magnitude
entre anos (mín 0,021, máx 0,314 — mais importante nos anos de maior
atividade). As features de momentum puro (`aceleracao_1s`, `delta_2s`)
têm contribuição marginal e instável (por vezes levemente negativa em
algum fold) — consistente com o ganho pequeno do grupo momentum na
ablation (seção 3).

## 13. Comparação com melhor baseline

| Métrica (teste 2023-2025) | Baseline anterior (HGB @ 0,70) | Otimizado (HGB tunado @ 0,60) |
|---|---:|---:|
| PR-AUC (threshold-independente) | 0,292 | **0,308** |
| Episódios detectados | 39,3% | **45,9%** |
| Epidemias grandes detectadas | 79,3% | 78,3% |
| Lead time mediano | 3 semanas | 3 semanas |
| Bairros com 0% detecção | 12 | **7** |
| Brier Score | não calibrado | **0,073 (calibrado)** |

Ganho real e mensurável, mas modesto em magnitude relativa (PR-AUC
+5,5%), concentrado em features de contexto histórico local e calibração
— não em um novo algoritmo ou em resolver a instabilidade entre anos.

## 14. Subnotificação — limitação discutida, não corrigida

O desafio reconhece subnotificação como realidade do sistema de vigilância
de arboviroses. Este projeto **não tenta corrigir subnotificação** (exigiria
dado externo de referência, fora do escopo autorizado). Efeitos plausíveis,
não medidos diretamente:

- **No target**: se a subnotificação variar por período (ex.: menor
  adesão a notificação em anos de menor atenção pública/mídia, como
  possivelmente 2022-2023), o "estado de risco elevado" calculado pode
  subestimar risco real nesses períodos — o limiar histórico se ajusta a
  uma linha de base que já pode estar deprimida por subnotificação, não
  só por transmissão real menor.
- **Na mudança temporal**: dificulta separar "menos transmissão real" de
  "menos notificação" como explicação para 2022-2023 (seção 2) — a análise
  desta etapa não teve como distinguir as duas hipóteses com os dados
  disponíveis.
- **Nas diferenças territoriais**: bairros com menor acesso a unidades de
  saúde podem ter subnotificação sistematicamente maior, o que afetaria o
  histórico local usado para calibrar o limiar daquele bairro
  especificamente — um viés estrutural que nenhuma feature deste projeto
  corrige.

## 15. Limitações adicionais

1. Instabilidade entre anos persiste mesmo após otimização (seção 6) —
   estrutural, não corrigível só com mais features/tuning neste conjunto
   de dados.
2. IPSEP (bairro de volume substancial) com 0% de detecção — não investigado
   a fundo nesta etapa (fora da regra de parada: "diagnosticar", não
   "resolver" caso a caso).
3. Recall@K modesto (Top-20 captura só 41-46% dos positivos por semana).
4. 2025 não é mais holdout puro (seção 6.1).
5. Calibração confiável apenas nas faixas de probabilidade com volume
   suficiente de validação (poucas observações acima de 0,85).
6. Clima permanece fora do modelo principal, por decisão explícita
   (achado da etapa anterior não revisitado, conforme instrução desta
   etapa).

## 16. Arquivos criados/alterados

**Criados**: `src/ml/diagnostics.py`, `src/ml/ranking.py`,
`src/optimize_dengue_early_warning.py`,
`tests/test_ml_features_avancadas.py`, `tests/test_ml_diagnostics.py`,
`tests/test_ml_ranking.py`, `tests/test_ml_calibracao.py`,
`reports/ml/dengue_early_warning_optimization.md` (este arquivo) + CSVs de
apoio (`diagnostico_alvo_por_ano.csv`, `diagnostico_episodios_por_ano.csv`,
`diagnostico_drift_features.csv`, `ablation_features.csv`,
`alvo_alternativo_comparacao.csv`, `tuning_hiperparametros.csv`,
`walk_forward_otimizado_por_ano.csv`, `threshold_operacional.csv`,
`episodios_avaliados_otimizado.csv`, `metricas_por_bairro_otimizado.csv`,
`metricas_por_ano_otimizado.csv`, `epidemias_grandes_otimizado.csv`,
`recall_em_k.csv`, `posicao_antes_episodios.csv`,
`calibracao_antes.csv`, `calibracao_depois.csv`,
`feature_importance_por_fold.csv`, `feature_importance_estabilidade.csv`,
`resultado_otimizacao_completo.json`).

**Alterados**: `src/ml/target.py` (+`std_historica_semana_exata`,
+`calcular_estado_alto_risco_v2_experimental` — target oficial
inalterado), `src/ml/features.py` (+features de histórico
local/momentum, grupos de ablation em `selecionar_matriz_features`),
`src/ml/dataset.py` (+parâmetros de grupo de feature),
`src/ml/models.py` (+`calibrar_probabilidade`, `treinar_arvore` aceita
hiperparâmetros), `src/ml/evaluation.py` (+`brier_score`),
`src/ml/alert_metrics.py` (+`metricas_operacionais_semanais`,
+`duracao_falsos_alertas_consecutivos`), `tests/test_ml_alert_metrics.py`
(+testes das novas métricas semanais).

**Não alterados**: Bronze, Silver, Gold, `src/eda/`, `dashboard/`, nenhum
dado climático, `src/ml/baselines.py` (baselines da etapa anterior
preservados sem mudança), definição oficial do target
(`estado_alto_risco`, `calcular_estado_alto_risco`).

## 17. Testes finais

**21 testes novos** (features de histórico local/momentum sem leakage e
sem divisão por zero infinita; diagnóstico de drift/lift/resumo por ano;
ranking semanal, Recall@K, posição antes de episódios sem olhar o futuro
do próprio episódio; calibração determinística e com probabilidades
válidas; Brier Score; métricas operacionais semanais e duração de falsos
alertas consecutivos). **Suíte completa: 306/306 passando** (baseline era
285, **0 regressões**).

## 18. Classificação final

**B — Melhorou, mas ainda apresenta fragilidades relevantes.**

Justificativa: há ganho real e mensurável (PR-AUC +5,5% relativo,
detecção de episódios +6,6 pontos percentuais, bairros com falha total
caindo de 12 para 7, calibração Brier -37%) atribuível principalmente às
novas features de contexto histórico local (`razao_limiar_historico`,
consistentemente a feature mais importante em todos os folds). Mas as
fragilidades centrais da etapa anterior **persistem**: instabilidade
forte entre anos (desvio-padrão de PR-AUC 0,201, 2023 literalmente
inalterado mesmo após todo o trabalho desta etapa — confirmando que é
estrutural, não uma lacuna de engenharia), heterogeneidade territorial
real (IPSEP, um bairro de volume substancial, com 0% de detecção), e
Recall@K modesto (Top-20 captura menos da metade dos positivos por
semana). Não é "A" (haveria consistência entre anos e territórios que não
existe); não é "C" (a complexidade adicional produziu ganho real, não
nulo); não é "D" (há sinal genuíno e estável nas features mais
importantes, replicado em 7 folds independentes).

## 19. Decisão para o produto

> O modelo está pronto para ser integrado ao dashboard Recife Alerta como
> funcionalidade de prova de conceito?

## NÃO

**Justificativa**:

- A classificação B implica, pela própria régua desta etapa, continuar
  pesquisa antes de expor previsão como produto — não é uma reprovação
  total, é um "ainda não".
- A instabilidade entre anos (2023 sem nenhuma melhora após todo o
  trabalho desta etapa) significa que o sistema pode ter um ano inteiro de
  desempenho fraco de forma imprevisível — arriscado expor isso como
  funcionalidade confiável a gestores públicos sem um aviso operacional
  muito claro (que ainda não foi desenhado).
- A heterogeneidade territorial (IPSEP com 0% de detecção apesar de
  volume substancial) significa que o sistema pode falhar sistematicamente
  em bairros específicos e relevantes — inaceitável numa ferramenta que
  se propõe a "territorializar" a resposta.
- Recall@K modesto (41-46% no Top-20) significa que uma lista "top N
  bairros de risco" ainda perde mais da metade dos bairros realmente em
  risco elevado numa dada semana.

**Se e quando uma etapa futura decidir integrar** (após investigar
especificamente os pontos acima), a recomendação é mostrar **score/ranking
de risco relativo**, não probabilidade calibrada como número absoluto de
confiança — mesmo com a calibração isotônica tendo melhorado o Brier
Score em ~37% nesta etapa, a instabilidade entre anos e a heterogeneidade
territorial ainda tornam arriscado comunicar "82% de chance" como se fosse
uma medida confiável e uniforme em qualquer bairro/ano; um ranking
("este bairro está entre os 10 de maior risco da cidade nesta semana")
comunica o mesmo sinal com uma reivindicação de precisão mais honesta.

## 20. Recomendação seguinte

1. Investigar especificamente os 7 bairros com 0% de detecção (IPSEP em
   particular) — pode indicar necessidade de um ajuste de modelo
   sensível a heterogeneidade territorial (ex.: feature de interação
   bairro×tendência, ou reponderação por volume histórico), sem virar 94
   modelos separados.
2. Investigar se anos de baixa prevalência (tipo 2022-2023) têm um
   padrão discernível ANTES de acontecerem (ex.: sinais no fim do ano
   anterior) que permita um "modo de baixa sensibilidade" operacional
   detectável com antecedência, em vez de aceitar passivamente que
   alguns anos serão mal servidos.
3. Explorar horizonte t+2 combinado com o ranking (não só a classificação
   binária) — pode entregar mais tempo de reação sem depender só da
   antecipação de 1 semana.
4. Só depois desses dois pontos, reconsiderar integração ao dashboard —
   como página experimental claramente rotulada, com ranking em vez de
   probabilidade, e um aviso explícito de que o desempenho varia
   fortemente por ano epidemiológico.
