# Da informação à ação — como a Prefeitura usa o Recife Alerta

**Documento para gestão.** Formaliza em texto a mesma matriz que a página
**Da informação à ação** (`dashboard/pages/11_da_informacao_a_acao.py`)
mostra no painel — para quem precisa citar ou distribuir isso sem abrir o
Streamlit. Base: `product_overview.md` §3 (as dez perguntas que a
plataforma responde) e `experimental_ml.md` (o que o módulo experimental
publica e por quê).

> **A plataforma apoia, prioriza, informa e contextualiza. Ela NÃO ordena
> equipes automaticamente, NÃO substitui avaliação epidemiológica, NÃO
> garante redução de casos/internações e NÃO diagnostica surto.** Toda
> decisão final é humana.

---

## 1. A matriz pergunta → indicador → decisão

| # | Pergunta operacional | Indicador | Decisão que o indicador apoia | Onde ver |
|---|---|---|---|---|
| 1 | Onde há mais volume de casos? | Casos acumulados / casos recentes | Dimensionamento operacional — alocar equipe/insumo por quantidade absoluta | Mapa territorial · Bairros prioritários |
| 2 | Onde há maior intensidade relativa? | Incidência por 100 mil habitantes | Priorização proporcional ao tamanho da população, não só ao volume bruto | Mapa territorial · Situação epidemiológica · Bairros prioritários |
| 3 | Onde está crescendo agora? | Tendência / variação % recente | Atenção precoce a um movimento que ainda não virou volume grande | Bairros prioritários |
| 4 | Está fora do padrão daquele lugar? | Razão contra o próprio histórico sazonal | Investigação local — o bairro está acima do que a própria história dele sugere | Bairros prioritários |
| 5 | Onde olhar primeiro, com recursos restritos? | Top-5 experimental (único K com ganho estatístico validado) | Uso de capacidade operacional restrita — nunca Top-15/20, onde o modelo não supera regras simples | Priorização experimental |
| 6 | Quando, historicamente, os casos aumentam? | Sazonalidade (semana epidemiológica de pico histórico) | Planejamento de campanha antes da época de maior risco histórico | Evolução histórica · Projeção 2026 |
| 7 | O clima antecede os casos? | Associação por defasagem (lag), bruta e ajustada por sazonalidade | Insumo para planejamento sazonal — nunca causalidade, nunca gatilho automático | Clima × Arboviroses |
| 8 | O que esperar de 2026? | Projeção estatística sazonal (casos, intervalo 80%/95%, pico esperado) | Planejamento — nunca meta, nunca previsão oficial, nunca substitui dado observado | Projeção 2026 |
| 9 | Os dados estão atuais? | Freshness (atraso da fonte em dias/semanas) | Confiabilidade da decisão — uma leitura desatualizada não deve orientar ação imediata | Faixa "Atualização dos dados", topo de toda página |

Esta matriz estende (não substitui) a tabela de dez perguntas de
`product_overview.md` §3 — as duas coexistem porque respondem públicos
distintos: aquela é "o que o produto responde", esta é "que decisão cada
resposta apoia".

---

## 2. Os três modos do produto, e por que nunca se misturam

| Modo | O que é | O que NÃO é |
|---|---|---|
| **Observado** (Situação epidemiológica, Mapa territorial, Bairros prioritários, Evolução histórica, Clima × Arboviroses) | Descreve o que os registros já mostram | Nunca prevê o futuro, nunca afirma causalidade climática |
| **Priorização experimental** | Ranking territorial para dengue, validado só em Top-5, com backtest público inclusive dos episódios perdidos | Não é probabilidade, não é categoria de risco, não vale para Zika/Chikungunya |
| **Projeção 2026** | Série temporal agregada (Recife total, por agravo) — baselines + ETS, escolhido por backtest | Não é dado observado, não é incidência (sem população 2026 oficial), não usa nem alimenta a priorização territorial |

Nenhum dos três modos usa outro como insumo. Nenhum ordena ação
automaticamente — todos existem para que uma pessoa com conhecimento
epidemiológico decida com mais informação, não para decidir por ela.

---

## 3. Por que a priorização experimental só vale para dengue

O candidato `dengue_onset_ranking_candidate_v1` foi treinado e validado
**exclusivamente com dados de dengue** (38 features, sem clima, split
2013-2019/2020-2022/2023-2025). Zika e Chikungunya nunca passaram pelo
mesmo processo de validação — usar o modelo para elas seria aplicar um
resultado estatístico fora do domínio em que foi medido. Por isso a página
experimental mostra, de forma permanente:

> "Priorização experimental atualmente validada apenas para dengue."

e não oferece seletor de agravo. Se um dia houver validação equivalente
para Zika/Chikungunya, isso exigirá um novo candidato e uma nova rodada
completa de validação estatística (mesmo processo do V1) — nunca uma
extensão silenciosa do V1.

---

## 4. Por que a Projeção 2026 é separada da Priorização Experimental

São duas perguntas diferentes, respondidas por dois pipelines
independentes (`src/ml/` para a priorização territorial, congelado;
`src/forecast/` para a projeção sazonal, novo nesta etapa):

- Priorização experimental: **"quais bairros merecem atenção nas próximas
  3 semanas?"** — ranking relativo entre os 94 bairros, dengue apenas.
- Projeção 2026: **"qual é a trajetória esperada de casos ao longo de
  2026, por agravo, para o Recife inteiro?"** — série temporal agregada,
  sem bairro, para os 3 agravos.

Nenhuma foi ajustada para concordar com a outra, e nenhuma usa a saída da
outra como entrada — a separação existe para que uma mudança de
metodologia numa não force uma reavaliação silenciosa da outra.

---

## 5. Limitações que toda decisão baseada neste painel deve considerar

- **Subnotificação**: casos notificados não são o total de casos reais.
- **Atraso da fonte**: a fonte pública de casos é atualizada
  trimestralmente e pode estar defasada — ver a faixa de atualização.
- **Reconstrução populacional**: a incidência usa população reconstruída/
  projetada para vários anos (não só Censo) — margem de erro documentada
  em `reports/population/population_incidence_integration.md`.
- **Granularidade climática**: a reanálise em grade cobre só 2-3 células
  para os 94 bairros — análise climática é só Recife total, nunca bairro.
- **Instabilidade do modelo experimental**: desempenho varia fortemente
  entre anos e regiões (ver `experimental_ml.md`); só Top-5 tem ganho
  estatisticamente defensável sobre regras simples.
- **Ausência de observado 2026**: nenhuma fonte oficial verificada tem
  caso de 2026; a projeção é extrapolação estatística do padrão histórico,
  nunca dado observado.
- **Nenhuma medição de efetividade de campo**: nada aqui mede se uma ação
  tomada com base no painel efetivamente reduziu casos — essa medição
  exigiria um desenho experimental que este projeto não tem.
