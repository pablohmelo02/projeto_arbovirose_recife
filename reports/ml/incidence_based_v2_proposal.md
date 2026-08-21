# Proposta `dengue_onset_ranking_candidate_v2`: incorporar incidência

**Status: proposta. Nada aqui foi executado.** O candidato congelado
`dengue_onset_ranking_candidate_v1` (onset h=3, 38 features, sem clima,
validado em `reports/ml/dengue_ranking_evidence_validation.md`) não foi
retreinado, alterado ou re-avaliado com uma nova definição de target nesta
etapa — regra de parada explícita do pedido que motivou este documento
(camada populacional + incidência).

## Por que agora é possível propor isto

Antes desta etapa, não havia população por bairro (`schema_gold_arboviroses_clima.py`
até a versão 1.1 dizia isso explicitamente). Com
`silver_populacao_bairro_ano` e as colunas de incidência na Gold 1.2
(`src/gold/populacao.py`), passa a existir um denominador populacional
para normalizar o volume de casos — o que abre 3 direções que o v1 não
podia explorar.

## O que mudaria (proposta, não implementado)

### 1. Lags de incidência como feature

Hoje o v1 usa `razao_limiar_historico` e `z_score_historico_local`
(histórico do próprio bairro em contagem absoluta). Uma versão v2 poderia
adicionar `incidencia_100k` e suas janelas móveis (4/8/12 semanas) como
features adicionais — testando se a **taxa por população** carrega sinal
que a contagem absoluta não carrega (ex.: dois bairros com o mesmo número
de casos, mas populações muito diferentes, podem ter dinâmicas de
transmissão distintas).

### 2. Razão da incidência contra o histórico local

Analogamente a `razao_limiar_historico` (casos vs. limiar histórico do
próprio bairro), uma versão baseada em incidência compararia
`incidencia_100k` da semana contra o histórico de incidência do mesmo
bairro na mesma época do ano — **não** contra outros bairros. Isso mantém
o princípio já usado no v1 (comparar cada bairro só com o próprio
passado), só trocando a unidade de contagem por taxa.

### 3. Target baseado em incidência; onset baseado em incidência

O target atual (`estado_alto_risco`, `src/ml/target.py`) usa percentil 90
da distribuição **de casos** do próprio bairro. Uma versão v2 poderia
redefinir esse percentil sobre a distribuição de **incidência**. Isso
mudaria potencialmente quais semanas contam como "risco elevado" para
bairros pequenos (onde poucos casos já produzem incidência alta) vs.
bairros grandes (onde o mesmo número absoluto de casos é proporcionalmente
menor). O onset (`src/ml/onset.py`, primeira semana de um episódio) herdaria
a mesma mudança de definição.

### 4. Influência da densidade populacional

`densidade_populacional_hab_km2` (nova coluna) é um candidato a feature
territorial adicional — hipótese a testar, não resultado: densidade mais
alta poderia correlacionar com transmissão mais rápida (mais criadouros
por área, mais contato entre pessoas), mas isso não foi medido nesta
etapa.

## Risco de vazamento (leakage) — a parte que precisa de mais cuidado que o v1

O v1 já tem uma regra de leakage temporal testada para clima (nunca usar
dado de data posterior à própria linha). Incidência introduz um **segundo
eixo de vazamento, não temporal**: a população usada como denominador em
anos reconstruídos/projetados (`tipo_populacao != CENSO_OBSERVADO`) foi
calculada nesta sessão, **depois** dos eventos que ela normaliza.

Concretamente: a reconstrução 2018-2021 usa o checkpoint de 2022 (Censo,
publicado em 2023-2024) como uma das duas âncoras do CAGR. Um backtest que
finge avaliar "o que o modelo saberia em 2019" **não pode** usar
silenciosamente uma população reconstruída com informação de 2022 — isso
seria conhecimento do futuro, mesmo que indireto (via denominador, não via
feature climática). Duas alternativas, nenhuma escolhida aqui:

- **(a) Documentar a hipótese explicitamente**: aceitar a população
  reconstruída como está, mas registrar no relatório de qualquer backtest
  v2 que os anos 2018-2021 usam um denominador que não estava disponível
  na época — enfraquece a interpretação de "antecipação genuína" para
  esses anos especificamente.
- **(b) Reconstrução "point-in-time"**: para cada ano de backtest, usar
  somente os checkpoints que já existiriam naquele momento (ex.: para
  avaliar 2019, reconstruir 2018-2019 só com a âncora de 2010 e a
  estimativa institucional 2017 — nunca com 2022). Mais rigoroso, mais
  caro de implementar (uma reconstrução populacional por ano de corte, não
  uma única série fixa), e não testado nesta etapa.

Qualquer versão v2 que incorpore incidência **precisa** declarar
explicitamente qual das duas alternativas usou — nunca omitir a pergunta.

## O que uma validação completa de v2 exigiria (mesmo protocolo do v1)

Não é uma feature a mais e pronto — repetir o rigor de
`dengue_ranking_evidence_validation.md`:

1. Mesmo split temporal (2013-2019/2020-2022/2023-2025), sem mudar por
   conveniência.
2. Bootstrap por episódio (não por linha semanal), delta pareado contra o
   v1 e contra os baselines simples, nos mesmos K (5/10/15/20).
3. Sensibilidade por cluster (`bairro`, `bairro×ano`).
4. Leave-one-year-out para checar dependência de um único ano.
5. Repetir a checagem territorial (RPA, antecipação genuína vs. recaída)
   já feita para o v1 — a incidência pode mudar exatamente essa
   heterogeneidade (bairros pequenos, hoje sub-representados em volume
   absoluto, podem se tornar mais visíveis em incidência).
6. Registrar explicitamente qual tratamento de leakage populacional (seção
   acima) foi usado.

## Recomendação

**Não implementar nesta etapa.** A proposta acima é suficiente para uma
decisão informada de continuar ou não — implementá-la exigiria as mesmas
~3 sessões de rigor que o v1 levou (baseline → otimização → onset/ranking →
validação estatística), e o pedido que originou este documento tem uma
regra de parada explícita antes de qualquer retreino. Se autorizado no
futuro, começar pela pergunta de leakage populacional (seção acima) antes
de qualquer feature nova — decidir isso primeiro evita retrabalho.
