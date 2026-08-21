# Recife Alerta — visão do produto

**Documento para gestão.** Descreve o que a plataforma faz, o que ela
responde, e — com igual destaque — o que ela não faz.

---

## 1. O que é

Plataforma web de inteligência epidemiológica e priorização territorial
para apoiar ações preventivas contra a dengue nos **94 bairros do Recife**.

Ela reúne, num único painel, três coisas que hoje vivem separadas:

1. **O histórico**: 13 anos de casos notificados (2013–2025), por bairro e
   por semana epidemiológica, com sazonalidade e comparação entre anos.
2. **A leitura da situação**: onde há mais casos agora, quais bairros estão
   acelerando e quais estão acima do próprio padrão histórico para a época
   do ano.
3. **Um módulo experimental de priorização**: um modelo estatístico que
   ordena os bairros por prioridade de atenção preventiva, avaliado
   retrospectivamente e apresentado com suas limitações medidas.

Toda a plataforma consome **dados públicos**: Portal de Dados Abertos do
Recife (casos notificados ao SINAN e limites territoriais oficiais), rede
de pluviômetros do CEMADEN e reanálise climática ERA5/ERA5-Land.

---

## 2. Alinhamento com o desafio da Prefeitura

| Item do desafio | Como a plataforma se posiciona |
|---|---|
| **Objetivo de longo prazo**: reduzir incidência e gravidade dos surtos por atuação antecipada orientada por dados | Orienta o produto. A plataforma fornece a base analítica e um sinal de priorização; **não demonstra** redução de incidência nem de gravidade, e não faz essa afirmação. |
| **Antecipação de áreas e períodos de maior risco** | Parcialmente atendido, de forma experimental e mensurada: em Top-5 há ganho estatisticamente defensável sobre regras simples; a antecedência mediana observada é de 2 semanas (medida em Top-10). |
| **Priorização mais eficiente de ações** | Atendido na dimensão observada (três critérios complementares, com base amostral informada) e, de forma experimental, no ranking do modelo. |
| **Redução futura da pressão sobre a rede de saúde** | Objetivo de longo prazo. Não medido, não afirmado. |
| **Maior efetividade das ações territoriais** | Objetivo de longo prazo. A plataforma torna a escolha do território explícita e auditável; a efetividade da ação em campo não é medida. |
| **Indicador: incidência** | **Não disponível.** Nenhuma fonte pública usada traz população por bairro. Em vez de inventar denominador, a plataforma usa contagem absoluta e a razão contra o próprio histórico do bairro. |
| **Indicador: antecedência entre sinal e aumento observado** | Medido e publicado (mediana, distribuição, percentuais ≥ 2 e ≥ 3 semanas), sempre com o K e o período declarados. |
| **Indicador: internações evitáveis** | Fora de alcance. O projeto não tem dado de internação. |
| **Risco: subnotificação** | Declarado em página própria; não corrigido (corrigir exigiria fonte externa e premissas não verificáveis). |
| **Risco: mudanças climáticas** | A série climática descreve o passado; a plataforma não projeta cenário climático. |
| **Risco: limitações de capacidade operacional** | Tratado como parâmetro de primeira classe: o desempenho é publicado para Top-5, 10, 15 e 20, inclusive nas faixas em que o modelo **não** ajuda. |
| **Risco: mudança de padrão epidemiológico** | Declarado; a instabilidade do modelo entre anos é publicada, não suavizada. |
| **Risco: limitações das fontes** | Página de qualidade dedicada, com atualidade, cobertura e lacunas de cada fonte. |

---

## 3. As dez perguntas que a plataforma responde

| # | Pergunta | Onde |
|---|---|---|
| 1 | Como a dengue está evoluindo no Recife? | Início · Situação epidemiológica |
| 2 | Quais bairros concentram maior incidência/crescimento? | Mapa territorial · Bairros prioritários |
| 3 | Quais áreas apresentam mudança recente de comportamento? | Bairros prioritários (tendência e variação) |
| 4 | Quais bairros merecem maior atenção preventiva? | Bairros prioritários (observado) · Priorização experimental (modelo) |
| 5 | O sistema consegue fornecer algum sinal antecipado? | Priorização experimental — sim, de forma limitada e mensurada |
| 6 | Com quanta antecedência histórica esses sinais ocorreram? | Priorização experimental (lead time) |
| 7 | Quais limitações existem nos dados/modelo? | Qualidade e limitações |
| 8 | Quando os dados foram atualizados? | Faixa "Atualização dos dados", no topo de toda página |
| 9 | Até que semana epidemiológica podemos confiar na análise? | Mesma faixa, com a semana explícita |
| 10 | Como a capacidade operacional altera a priorização? | Priorização experimental (Top-5/10/15/20) |

---

## 4. Estrutura do painel

Nove páginas em quatro grupos, para que a natureza do conteúdo seja óbvia
antes da leitura:

**Situação observada** — o que os registros mostram
1. **Início** — objetivo, cobertura, período, atualização, situação atual, onde olhar primeiro.
2. **Situação epidemiológica** — casos por semana, comparação com o período anterior e comparação sazonal.
3. **Mapa territorial** — os 94 bairros, com métrica alternável.
4. **Evolução histórica** — ciclos, picos, sazonalidade e comparação entre regiões.

**Apoio à decisão**
5. **Bairros prioritários** — priorização observada, sem modelo, por três critérios.
6. **Priorização experimental** — módulo de modelo, marcado como experimental.

**Contexto climático**
7. **Clima** — as duas fontes climáticas, separadas e comparadas.
8. **Clima × Dengue** — associação observada, nunca causalidade.

**Transparência**
9. **Qualidade e limitações** — cobertura, proveniência, riscos e a tabela do que pode e não pode ser afirmado.

---

## 5. Os dois modos do produto

A plataforma separa rigorosamente **o que aconteceu** de **o que um modelo
sinaliza**, tanto visualmente (etiqueta no cabeçalho de cada página) quanto
estruturalmente (páginas distintas, avisos próprios, nenhuma métrica
mistura os dois).

| | Modo histórico | Modo priorização experimental |
|---|---|---|
| Etiqueta | "Dados observados" | "Experimental" |
| Fonte | registros oficiais | modelo estatístico sobre os registros |
| O que afirma | o que foi notificado | ordem relativa de atenção |
| O que não afirma | — | probabilidade, categoria de risco, previsão oficial |
| Disponibilidade | sempre | depende de artefato válido e de dado recente |

---

## 6. O que a plataforma deliberadamente não faz

- **Não calcula incidência por 100 mil habitantes.** Sem população por
  bairro, o número seria inventado.
- **Não mostra probabilidade de surto.** A validação estatística mostrou que
  a probabilidade do modelo não deve ser comunicada como grau de confiança.
  O produto mostra **posição e score relativo**.
- **Não usa categoria de risco** (verde/amarelo/vermelho). Categorizar risco
  exigiria uma validação que não existe.
- **Não apresenta dado antigo como tempo real.** A fonte publica em
  periodicidade trimestral, e o painel diz até quando ela foi.
- **Não gera priorização para o período atual quando os dados estão
  desatualizados.** Nesse caso oferece apenas simulação histórica.
- **Não expõe dado individual.** A menor unidade publicada é bairro × semana.
- **Não afirma redução de dengue nem de internações.**

---

## 7. Estado atual

| Dimensão | Situação |
|---|---|
| Cobertura epidemiológica | 2013 a 2025 · 679 semanas · 94 bairros · 3 agravos · 156.504 casos |
| Última semana publicada pela fonte | SE 53 / 2025 (semana encerrada em 03/01/2026) |
| Cobertura climática (reanálise em grade) | 100 % das linhas, 2013–2025 |
| Cobertura climática (estações físicas) | 6,1 % das linhas, concentradas em 2024–2025 |
| Módulo experimental | disponível apenas em modo backtest (dados oficiais defasados) |
| Priorização do período atual | **indisponível** — dado publicado ~32 semanas atrás do presente |

Os números acima não são fixos no texto do painel: são derivados dos dados
carregados a cada execução (ver `data_freshness.md`).
