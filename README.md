# Recife Alerta

**Plataforma de inteligência epidemiológica e priorização territorial para
apoiar ações preventivas contra a dengue nos 94 bairros do Recife.**

---

## Problema

A dengue no Recife é recorrente, sazonal e desigual entre territórios. Entre
2013 e 2025 foram notificados **156.504 casos** de arboviroses na cidade,
com anos de epidemia intercalados por anos de baixa e um pico sazonal
consistente entre fevereiro e março.

Quem decide onde atuar enfrenta três dificuldades práticas:

1. **O dado existe, mas está espalhado.** Casos vêm de um portal, limites de
   bairro de outro, clima de um terceiro — cada um com formato, granularidade
   e atualidade diferentes.
2. **Volume absoluto engana.** Um bairro grande sempre aparece no topo de
   qualquer lista de contagem, mesmo quando não está pior que o seu próprio
   normal. E não existe população por bairro nas fontes públicas usadas, então
   não há como calcular incidência.
3. **Agir depois do pico é agir tarde.** A pergunta operacional não é "onde
   há mais casos", é "onde algo está começando".

## Solução

Uma aplicação web que reúne as três fontes numa tabela analítica única
(`bairro × semana epidemiológica × agravo`) e responde, em páginas separadas
por natureza do conteúdo:

- **o que aconteceu** — série completa, sazonalidade, mapa, ranking
  observado por três critérios complementares (volume, aceleração, desvio do
  próprio histórico);
- **o que um modelo sinaliza** — um módulo **experimental** que ordena os
  bairros por prioridade de atenção preventiva, com todo o desempenho
  medido e publicado, inclusive onde ele não funciona.

A separação entre as duas coisas é estrutural, não decorativa: páginas
distintas, etiqueta no cabeçalho, avisos próprios, e nenhuma métrica que
misture observado com projetado.

## Demonstração

```bash
python -m venv .venv && .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard/app.py
```

O painel abre com os artefatos já versionados no repositório — **não precisa
de banco de dados, credencial, Docker ou acesso à internet** para funcionar.

---

## O que o sistema responde

| Pergunta | Página |
|---|---|
| Como a dengue está evoluindo no Recife? | Início · Situação epidemiológica |
| Quais bairros concentram mais casos? | Mapa territorial · Bairros prioritários |
| Quais áreas mudaram de comportamento recentemente? | Bairros prioritários |
| Quais bairros merecem maior atenção preventiva? | Bairros prioritários (observado) · Priorização experimental (modelo) |
| Existe algum sinal antecipado? | Priorização experimental |
| Com quanta antecedência esses sinais ocorreram? | Priorização experimental (lead time) |
| Como a capacidade operacional muda a priorização? | Priorização experimental (Top-5/10/15/20) |
| O clima acrescenta informação? | Clima × Dengue |
| Quais são as limitações? | Qualidade e limitações |
| **Até quando os dados são confiáveis?** | Faixa "Atualização dos dados", no topo de **toda** página |

---

## Resultados

### Base analítica

| | |
|---|---|
| Cobertura | 2013–2025 · 679 semanas epidemiológicas · 94 bairros · 3 agravos |
| Casos notificados | 156.504 |
| Linhas da tabela analítica | 191.478 |
| Cobertura climática | **100 %** das linhas (reanálise em grade, 2013–2025) |
| Última semana publicada pela fonte | **SE 53 / 2025** — a fonte declara periodicidade trimestral |

A cobertura climática passou de **6,1 % para 100 %** nesta etapa, com a
incorporação de uma fonte de reanálise em grade, depois de uma investigação
controlada de quatro candidatas
([relatório](reports/climate_source_analysis/gridded_climate_investigation.md)).

### O que a série mostra

- Ano de maior volume no período: **2015**.
- Pico sazonal médio em torno da **semana epidemiológica 11** (fevereiro/março).
- Maior carga acumulada: **COHAB, IBURA, VÁRZEA, ÁGUA FRIA** — contagem
  absoluta, não incidência.

### Sinal antecipado (módulo experimental)

Avaliado sobre **920 episódios reais** de dengue em 2023–2025, com bootstrap
ao nível de episódio:

| Cenário | Modelo | Melhor regra simples | Diferença | Leitura |
|---|---|---|---|---|
| **Priorizar 5 bairros/semana** | **25,8 %** dos episódios antecipados | 19,8 % | **+5,98 pp** (IC [+2,83; +9,13]) | **ganho robusto** |
| Priorizar 10 | 38,4 % | 35,8 % | +2,61 pp (IC cruza zero) | inconclusivo |
| Priorizar 20 | 57,6 % | 63,2 % | **−5,54 pp** | a regra simples é melhor |

Antecedência mediana quando o bairro é detectado (Top-10): **2 semanas**;
69 % dos casos com 2 semanas ou mais.

**O clima não melhorou o modelo** na faixa de afirmação do produto
(experimento controlado, diferença de −0,11 pp em Top-5, intervalo cruzando
zero) — e não foi incorporado
([relatório](reports/ml/dengue_ranking_clima_experiment.md)).

### O que o sistema não demonstra

Não há evidência, aqui, de **redução de incidência** ou de **internações** —
e nenhuma afirmação nesse sentido é feita em qualquer lugar do produto. O
módulo experimental **não prevê surtos**: ele ordena prioridades relativas.

---

## Estado do módulo experimental

**Classificação: A — experimental demonstrável.** Congelado como
`dengue_onset_ranking_candidate_v1`.

| Item | Situação |
|---|---|
| Backtest navegável (154 semanas, 2023–2025) | **disponível** |
| Priorização do período atual | **indisponível** — o dado oficial está 32 semanas atrás do presente, acima do limite de 4 semanas |
| O que é publicado | posição no ranking e score relativo |
| O que **não** é publicado | probabilidade, categoria de risco, previsão |

Limitações medidas e publicadas no próprio painel:

- ganho defensável **apenas** em Top-5;
- desempenho muito desigual entre regiões (RPA 5: 59 % · RPA 6: 23 % em Top-10);
- o cenário mais relevante — detectar um episódio que **está começando** — é
  o de pior desempenho (33,5 % contra 62 % em recaídas);
- grandes episódios têm desempenho **pior** que a média sob ranking;
- a lista muda substancialmente de uma semana para a outra;
- 65,5 % das priorizações em Top-5 não precederam episódio.

Detalhe completo: [`reports/product/experimental_ml.md`](reports/product/experimental_ml.md).

---

## Arquitetura

```
Fontes públicas                Camadas                      Produto
─────────────────              ───────────                  ───────
CKAN Recife (SINAN)      ┐
CKAN Recife (bairros)    ├──►  Bronze  ──►  Silver  ──►  Gold  ──►  dashboard/data/  ──►  Streamlit
CEMADEN (pluviômetros)   │     (bruto)     (contratos)   (analítica)   (artefatos)         (9 páginas)
ERA5 / ERA5-Land (grade) ┘                                    │
                                                              └──►  modelo congelado  ──►  backtest
```

Princípios que valem em todas as camadas:

- **`missing ≠ 0`** — ausência de leitura climática nunca vira `0 mm`.
- **`casos = 0` é dado real** — notificação é compulsória, então ausência de
  notificação é zero, não lacuna.
- **Sem leakage** — toda feature de uma semana usa apenas dados até o fim
  dela; verificado por injeção adversarial de valor futuro.
- **Portões de qualidade antes de publicar** — 14 verificações críticas; se
  alguma falha, nada é escrito e o artefato anterior permanece.
- **Escrita atômica** — temporário → validação → substituição. Um processo
  interrompido nunca deixa artefato meio escrito.
- **Grade não é estação** — a reanálise é sempre descrita como estimativa em
  grade, com resolução declarada, nunca como "a estação do bairro".

Detalhe técnico completo de cada camada:
[`docs/arquitetura_e_pipeline.md`](docs/arquitetura_e_pipeline.md).

---

## Segurança e privacidade

- **Nenhum dado individual é publicado.** A menor unidade de qualquer
  artefato é bairro × semana. As camadas com registro individual do SINAN
  (Bronze e Silver) nunca saem do ambiente local.
- **Três barreiras de verificação de privacidade**, executadas a cada
  publicação, procurando 19 nomes de coluna potencialmente identificáveis.
- **Nenhum segredo no repositório** — auditoria de código e de todo o
  histórico do Git, sem achados. Sem credencial padrão fraca.
- **Zero vulnerabilidades conhecidas** nas dependências (`pip-audit`, nos
  dois arquivos de requisitos).
- **Análise estática**: `bandit` em 18.419 linhas — 0 achados de severidade
  alta ou média (3 restantes, todos baixos, investigados e documentados).
- **O painel público não desserializa modelo**: lê apenas Parquet e JSON já
  calculados.
- **Nenhum *stack trace* chega ao usuário**: cada seção degrada isoladamente.

Auditoria completa:
[`reports/product/security_and_privacy.md`](reports/product/security_and_privacy.md).

---

## Como executar

### Rodar o painel (não precisa de infraestrutura)

```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```

### Atualizar os dados

```bash
python -m src.update_recife_alerta              # ~23 s · nunca treina modelo
python -m src.update_recife_alerta --sem-rede    # só recalcula com o que está em disco
python -m src.update_recife_alerta --com-datalake # cadeia canônica completa (exige .env + MinIO)
```

### Verificar

```bash
python -m src.healthcheck                        # PASS / WARN / FAIL
python -m pytest -q                              # 532 testes
python scripts/verificar_deploy_dashboard.py     # aptidão para publicação
```

### Treinar o modelo (operação separada e controlada)

```bash
python -m src.train_priority_model
python -m src.generate_priority_artifacts
```

Roteiro operacional completo, incluindo publicação e solução de problemas:
[`reports/product/deployment_runbook.md`](reports/product/deployment_runbook.md).

---

## Documentação

| Para quem | Documento |
|---|---|
| Gestão — o que é o produto | [`reports/product/product_overview.md`](reports/product/product_overview.md) |
| Gestão — até quando os dados vão | [`reports/product/data_freshness.md`](reports/product/data_freshness.md) |
| Gestão — o módulo experimental | [`reports/product/experimental_ml.md`](reports/product/experimental_ml.md) |
| Segurança | [`reports/product/security_and_privacy.md`](reports/product/security_and_privacy.md) |
| Confiabilidade | [`reports/product/reliability.md`](reports/product/reliability.md) |
| Operação | [`reports/product/deployment_runbook.md`](reports/product/deployment_runbook.md) |
| Auditoria desta etapa | [`reports/product/product_hardening_report.md`](reports/product/product_hardening_report.md) |
| Arquitetura técnica | [`docs/arquitetura_e_pipeline.md`](docs/arquitetura_e_pipeline.md) |
| Investigações de fonte climática | [`reports/climate_source_analysis/`](reports/climate_source_analysis/) |
| Pesquisa de ML (4 etapas + validação) | [`reports/ml/`](reports/ml/) |
| Análise exploratória | [`reports/eda/`](reports/eda/) |
| Análise da camada Gold | [`reports/gold_analysis/`](reports/gold_analysis/) |
| Notas operacionais de desenvolvimento | [`CLAUDE.md`](CLAUDE.md) |

---

## Limitações

Estas limitações são estruturais — não são pendências a resolver numa
próxima versão, são propriedades do que os dados disponíveis permitem.

1. **Subnotificação.** Casos que não chegam ao SINAN não existem para
   nenhuma análise aqui. Um bairro com menor acesso a serviços de saúde pode
   aparecer com menos casos por esse motivo, não por menor transmissão.
2. **Sem incidência.** Nenhuma fonte pública usada traz população por
   bairro. Todos os números são contagem absoluta; a comparação entre
   bairros de tamanhos diferentes usa o histórico de cada um como referência.
3. **Atraso da fonte.** A publicação oficial é trimestral e o último período
   disponível está 230 dias atrás. O painel declara isso em toda página e
   desabilita a priorização do período atual.
4. **Clima em grade quase não distingue bairros.** A reanálise cobre todo o
   período, mas resolve apenas **2 células de precipitação para os 94
   bairros**: ela informa *quando* chove, não *onde dentro do Recife*. E
   subestima o volume medido pelos pluviômetros em ~29 %.
5. **O modelo é instável entre anos e entre territórios.** O desempenho
   médio esconde variação grande; a página experimental publica a variação em
   vez de suavizá-la.
6. **O cenário mais relevante é o mais difícil.** Detectar um episódio que
   está começando (83 % dos casos) tem desempenho muito inferior a detectar
   uma recaída.
7. **Correlação não é causalidade.** A página Clima × Dengue mostra
   associação observada; chuva e arboviroses compartilham a mesma
   sazonalidade anual, o que sozinho produz correlação.
8. **Nada aqui mede efetividade de ação em campo.** A plataforma apoia a
   escolha do território; o que acontece depois não é observável por ela.

---

## Fontes

| Fonte | Uso | Acesso |
|---|---|---|
| Portal de Dados Abertos do Recife (CKAN) | casos notificados ao SINAN, 2013–2025 | público, sem autenticação |
| Portal de Dados Abertos do Recife (CKAN) | limites oficiais dos 94 bairros | público |
| CEMADEN | rede de pluviômetros (leitura de estação) | público |
| ERA5 / ERA5-Land (via Open-Meteo Archive) | reanálise climática em grade | público, sem chave |

---

<sub>Ferramenta de apoio à decisão. Não representa previsão oficial da
Prefeitura do Recife.</sub>
