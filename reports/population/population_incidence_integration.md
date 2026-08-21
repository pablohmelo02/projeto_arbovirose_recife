# Integração de população e incidência epidemiológica — Recife Alerta

Relatório final da etapa que adicionou uma camada populacional histórica
por bairro (2010-2025) e incidência por 100 mil habitantes ao Recife
Alerta, sem alterar o modelo de ML congelado
(`dengue_onset_ranking_candidate_v1`).

## 1. Fontes investigadas

Pesquisa sistemática (não limitada a Censo 2010/2022): IBGE (Censo 2010,
Censo 2022, Estimativas de População/SIDRA), Secretaria de Saúde do
Recife/CIEVS, ESIG/Prefeitura do Recife, CONDEPE/FIDEM, Anuário Estatístico
de Pernambuco. Detalhe completo, incluindo fontes descartadas e o motivo,
em [`population_source_inventory.md`](population_source_inventory.md).

## 2. Checkpoints encontrados

| ano | fonte | tipo | cobertura |
|---|---|---|---|
| 2010 | IBGE Censo 2010 (via CIEVS) | observado | 94/94 |
| 2011-2017 | CIEVS/Sesau Recife | estimativa institucional | 94/94 |
| 2022 | IBGE Censo 2022 | observado | 94/94 |
| 2011-2021, 2024-2025 (municipal) | IBGE/SIDRA | estimativa oficial | município |

A dúvida "existe uma estimativa para 2017?" — **sim, confirmada**: o
documento CIEVS "População do Recife: Censo Demográfico 2010 e Projeções
2010 a 2017" (dez/2017) tem os 94 bairros para cada ano de 2010 a 2017.

## 3. Censo 2010

Usado via a tabela do CIEVS (não há produto "Agregados por Bairro" do IBGE
para 2010 — só a partir de 2022). Soma dos 94 bairros = 1.537.704,
**idêntica** ao total oficial do Censo 2010 (SIDRA tabela 202). Tratado
como `CENSO_OBSERVADO`.

## 4. Intermediários (2011-2021)

- **2011-2017**: valores diretos do CIEVS (partilha proporcional fixa do
  Censo 2010 sobre as projeções municipais do IBGE) — usados como estão,
  marcados `ESTIMATIVA_INTERCENSITARIA`. Soma consistentemente ~0,65%
  abaixo do total municipal oficial (a própria fonte separa ~10 mil
  pessoas em "Bairro Ignorado", não distribuídas por bairro) — não
  forçado a bater, diferença documentada.
- **2018-2021**: sem checkpoint oficial. Reconstruído por CAGR por bairro
  entre os checkpoints 2017 e 2022, reconciliado ano a ano ao total
  municipal oficial do IBGE. Erro estimado por validação cruzada (seção 9).

## 5. Censo 2022

Produto oficial "Agregados por Bairro" do IBGE, baixado e filtrado para
Recife (94 linhas exatas). Soma = 1.488.920, **idêntica** ao total
municipal oficial (SIDRA tabela 9514). Tratado como `CENSO_OBSERVADO`.

## 6. Estimativas municipais (reconciliação)

Série anual completa via IBGE/SIDRA (tabelas 202, 6579, 9514), usada como
referência de reconciliação em todo ano reconstruído/projetado. 2023 não
tem publicação oficial (ano de transição pós-Censo) — interpolado
geometricamente entre 2022 e 2024, documentado como tal (não é dado
observado).

## 7. Método escolhido

Piecewise: valores diretos do CIEVS (2010-2017) + CAGR por bairro
reconciliado à série municipal (2018-2021, entre os checkpoints 2017 e
2022) + Censo direto (2022) + projeção pós-Censo (2023-2025, participação
de 2022 escalada pelo total municipal oficial — ver seção 8). Escolhido em
vez de interpolação linear simples porque usa o checkpoint intermediário
real (2017) e reconcilia ano a ano com a série municipal oficial.

## 8. Validação

**Reconciliação municipal** (soma dos 94 bairros vs. total oficial):
diferença zero nos anos observados (2010, 2022); diferença de 0 a 3
pessoas (arredondamento) nos anos reconstruídos com reconciliação ativa
(2018-2021, 2023-2025); ~0,65% nos anos 2011-2017 (explicado pela
categoria "Bairro Ignorado" da própria fonte CIEVS, não corrigido). Detalhe
completo em `data/silver/populacao_bairro_ano/_manifest.json` →
`reconciliacao_por_ano`.

**Áreas atípicas** (seção 11 do pedido): 72/94 bairros têm população
< 1.000 (2022), crescimento > 50% ou redução entre 2010-2022 — não
suavizados. Maiores reduções: PEIXINHOS (-41,7%), APIPUCOS (-24,5%),
CAJUEIRO (-23,1%), COELHOS (-22,4%) — esvaziamento real de bairros
centrais/industriais, não artefato de dado.

**Método pós-Censo** (2023-2025): 3 métodos comparados (participação de
2022 fixa; tendência longa 2010-2022; tendência recente 2017-2022),
critério de escolha = menor dispersão de crescimento entre bairros
(estabilidade), declarado antes de olhar o resultado. Participação de 2022
fixa venceu (dispersão ≈ 0 — matematicamente equivalente a distribuir o
crescimento municipal oficial proporcionalmente à participação 2022; "A" e
"D" do pedido original são o mesmo método).

## 9. Erro contra checkpoints (validação cruzada, seção 10 do pedido)

Reconstrução 2010→2022 **sem usar o checkpoint de 2017**, comparada contra
o valor real do CIEVS em 2017:

| métrica | valor |
|---|---|
| MAE | ≈ 886 pessoas/bairro |
| MAPE | ≈ 10,8% |
| Bias médio | +112 pessoas (leve superestimação) |
| Pior caso | Mangabeira, erro ≈ 211% (bairro pequeno, trajetória irregular) |

Este erro é a margem de incerteza real da reconstrução 2018-2021 (mesmo
método, sem checkpoint para comparar) — documentado, não escondido.
`tipo_populacao = ESTIMATIVA_INTERCENSITARIA` sinaliza isso em toda linha.

## 10. Cobertura 2013-2025

100% das 191.478 linhas da Gold têm população associada (94/94 bairros,
todos os 13 anos epidemiológicos). Nenhuma linha ficou sem `populacao_bairro_ano`.

## 11. Incidência

Implementada aditivamente na Gold (1.1 → 1.2, `src/gold/populacao.py`):
`incidencia_100k` (própria semana) e janelas móveis de 4/8/12/52 semanas
(soma de casos ÷ população × 100.000 — nunca soma de taxas já calculadas).
`incidencia_anual_100k` é uma janela móvel de 52 semanas, não "ano civil
completo", para preservar a mesma regra de ausência de vazamento temporal
já aplicada ao clima. Verificado campo a campo: as 46 colunas
pré-existentes da Gold 1.1 ficaram **idênticas** depois do enriquecimento.

## 12. Impacto nos rankings

Comparando o ranking de **casos acumulados 2013-2025** (dengue) contra o
ranking de **incidência média anual** do mesmo período: correlação de
Spearman = **0,31** — uma relação fraca, confirmando que os dois critérios
respondem perguntas diferentes na prática, não só na teoria.

| critério | top 3 |
|---|---|
| Casos acumulados | COHAB (6.817), IBURA (5.730), VÁRZEA (4.963) |
| Incidência média anual | RECIFE (3.099/100k), MANGABEIRA (2.532/100k), SANTO ANTÔNIO (1.944/100k) |

## 13. Bairros que mais mudam de posição (casos × incidência)

| bairro | posição por casos | posição por incidência | Δ posição |
|---|---|---|---|
| Boa Viagem | 5º | 89º | −84 |
| Santo Antônio | 87º | 3º | +84 |
| Paissandu | 93º | 10º | +83 |
| Cidade Universitária | 84º | 6º | +78 |
| Recife | 75º | 1º | +74 |
| Barro | 29º | 84º | −55 |

Boa Viagem (grande, populoso, turístico) tem muitos casos absolutos mas
incidência modesta; bairros pequenos e centrais (Recife, Santo Antônio,
Paissandu) têm poucos casos absolutos mas incidência alta — exatamente o
efeito que a incidência existe para corrigir.

## 14. Alterações no Streamlit

- **Mapa territorial**: 2 novas camadas (`Incidência /100k`, `Incidência
  móvel 4 semanas /100k`) + `Densidade populacional`; tooltip e tabela de
  detalhe mostram população usada, tipo de população e incidência; aviso
  de volatilidade quando a métrica ativa é incidência.
- **Bairros prioritários**: 4º critério de ordenação ("Maior incidência"),
  tabela com incidência/população/tipo de população, mesmo aviso de
  volatilidade.
- **Evolução histórica**: seletor Casos/Incidência/População no gráfico
  anual, sempre usando a população do próprio ano de cada barra (nunca um
  ano fixo como denominador de toda a série).
- Texto de recusa de incidência removido de todo lugar; `INCIDENCIA_DISPONIVEL = True`.

## 15. Camada Power BI

`powerbi/data/` (7 tabelas, esquema estrela: `dim_bairro`, `dim_tempo`,
`dim_agravo`, `fact_epidemiologia_semanal`, `fact_clima_semanal`,
`fact_priorizacao_backtest`, `data_freshness`), gerada por
`python -m src.export_powerbi_dataset`, com portão de QA (94 bairros,
chaves únicas, integridade referencial, casos/população não-negativos).
Documentação: [`powerbi/README.md`](../../powerbi/README.md),
[`modelo_semantico.md`](../../powerbi/modelo_semantico.md),
[`medidas_dax.md`](../../powerbi/medidas_dax.md).

## 16. Limitações

1. Sem checkpoint oficial por bairro entre 2017-2022 e depois de 2022 —
   esses anos são reconstrução/projeção deste projeto.
2. MAPE ≈ 10,8% na reconstrução 2018-2021 (medido, não estimado
   otimisticamente).
3. 2023 usa total municipal interpolado (não publicado pelo IBGE).
4. Método pós-Censo (participação fixa) não captura mudanças de tendência
   específicas de bairro que possam ter ocorrido depois de 2022 — é
   deliberadamente conservador, não uma previsão de tendência.
5. `fact_priorizacao_backtest` (Power BI e dashboard) não foi recalculado
   com incidência — continua sendo o candidato v1 congelado, em contagem
   absoluta.

## 17. Proposta ML V2

Ver [`reports/ml/incidence_based_v2_proposal.md`](../ml/incidence_based_v2_proposal.md) —
proposta apenas, não executada. Destaque: incorporar população introduz um
risco de vazamento **não temporal** (denominador reconstruído com
informação futura, ex.: Censo 2022 usado para reconstruir 2018-2021) que
precisa ser resolvido antes de qualquer feature de incidência entrar num
modelo.

---

## Arquivos criados

- `data/bronze/populacao/` — 4 arquivos (CIEVS, Censo 2022, estimativas
  municipais, manifest) com proveniência completa.
- `src/ingestion/population_ingestion.py`, `src/population/reconstruction.py`,
  `src/silver/schema_population.py`, `src/silver/pipeline_population.py`,
  `src/transform_population.py`.
- `src/gold/populacao.py`, `src/enrich_gold_populacao.py`.
- `src/export_powerbi_dataset.py` + `powerbi/{README,modelo_semantico,medidas_dax}.md`.
- `reports/population/{population_source_inventory,population_incidence_integration}.md`.
- `reports/ml/incidence_based_v2_proposal.md`.
- `tests/{test_population_reconstruction,test_population_silver,test_gold_populacao,test_powerbi_export}.py` (48 testes novos) + 7 testes adicionados a `tests/test_dashboard_validacao_e_prioridade.py`.

## Arquivos alterados

- `dashboard/data/gold_arboviroses_clima_bairro.parquet` (1.1 → 1.2, aditivo).
- `dashboard/pages/{3_mapa_territorial,4_bairros_prioritarios,5_evolucao_historica}.py`.
- `dashboard/components/graficos_produto.py` (nova função `grafico_metrica_por_ano`).
- `src/eda/schema_eda.py` (`INCIDENCIA_DISPONIVEL = True`).
- `src/eda/prioridade_observada.py` (colunas de população/incidência + 4 rankings).
- `src/gold/schema_gold_arboviroses_clima.py` (docstring).
- `README.md`, `.gitignore`.

## Testes finais

Suíte completa: **587 testes passando** (baseline 532 + 55 novos/alterados
nesta etapa: 16 reconstrução populacional, 8 Silver de população, 11
features de população na Gold, 13 exportação Power BI, 7 rankings de
incidência/prioridade — 0 regressões). Reprodutibilidade do candidato de ML
congelado verificada campo a campo contra a Gold enriquecida — nenhuma
métrica de evidência mudou (a única diferença encontrada num diff bruto do
JSON de resultado foi um campo de metadado (`incluir_clima_grade`) já
desatualizado no artefato commitado antes desta sessão, não causada por
este trabalho — revertido para não misturar com esta entrega).

## Recomendação

Camada populacional e de incidência prontas para uso no produto e em Power
BI. Próximo passo natural, se autorizado: avaliar a proposta ML V2
(seção 17), começando pela questão de vazamento populacional antes de
qualquer feature nova.
