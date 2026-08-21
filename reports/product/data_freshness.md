# Atualidade dos dados (*data freshness*)

**Regra do produto:** nenhuma data aparece escrita à mão em texto de
interface ou de relatório. Toda data exibida é derivada do dado real, na
hora da geração do artefato.

---

## 1. Por que isto é um requisito de primeira classe

Um painel epidemiológico que não diz **até quando** os dados vão é
enganoso, mesmo com todos os números individualmente corretos: o leitor
assume implicitamente que está vendo a situação de hoje. No caso do Recife,
a fonte oficial publica em **periodicidade trimestral declarada**, e a
defasagem real observada é de meses. Sem declarar isso, o painel
comunicaria uma falsidade por omissão.

---

## 2. Contrato de metadados

`python -m src.generate_freshness` produz `dashboard/data/_freshness.json`
com um bloco por conjunto de dados:

| Campo | Significado |
|---|---|
| `dataset` | epidemiologia · territorio · clima_estacao · clima_grade · modelo |
| `fonte` | de onde vem, em texto legível por um gestor |
| `ultima_atualizacao_fonte` | quando a **fonte** publicou/alterou por último |
| `data_maxima_evento` | data do evento mais recente presente no dado |
| `semana_epi_maxima` | última semana epidemiológica coberta (`AAAA-SS`) |
| `pipeline_executado_em` | quando o nosso pipeline processou |
| `atraso_dias` | `hoje − data_maxima_evento` |
| `limiar_atraso_dias` | limiar daquele conjunto |
| `status` | `ATUAL` · `ATRASADO` · `DESCONHECIDO` |
| `observacao` | frase de contexto exibida na interface |
| `detalhe` | contadores específicos do conjunto |

O artefato traz ainda `projecao_atual` (o portão descrito na §5) e
`resumo_status` (um mapa conjunto → status).

---

## 3. Regra de status — objetiva, não impressão

| Status | Condição |
|---|---|
| `ATUAL` | `atraso_dias <= limiar_atraso_dias` do conjunto |
| `ATRASADO` | acima do limiar — **não é erro do sistema**, é o estado real da publicação oficial |
| `DESCONHECIDO` | não foi possível determinar |

**Nada é considerado atual por omissão.** Se a fonte estiver fora do ar e
não houver metadado, o status é `DESCONHECIDO`, nunca `ATUAL`.

### Limiares e por que cada um

| Conjunto | Limiar | Justificativa |
|---|---|---|
| `epidemiologia` | 120 dias | A própria fonte declara periodicidade **trimestral** no metadado do CKAN. 120 dias = um trimestre com um mês de folga para o atraso de publicação. |
| `territorio` | 1.095 dias (3 anos) | Limites de bairro mudam raramente; 3 anos detecta um dataset abandonado sem gerar alarme falso. |
| `clima_estacao` | 30 dias | Telemetria diária: mais de um mês sem leitura indica problema de coleta. |
| `clima_grade` | 30 dias | Série diária de reanálise: idem. |

---

## 4. Estado medido na última execução

| Conjunto | Atualizado até | Publicação da fonte | Atraso | Status |
|---|---|---|---|---|
| Casos notificados | **SE 53 / 2025** (03/01/2026) | 20/05/2026 | 230 dias | `ATRASADO` |
| Limites territoriais | 02/03/2026 | 02/03/2026 | 172 dias | `ATUAL` |
| Clima — estações | SE 53 / 2025 | — | 230 dias | `ATRASADO` |
| Clima — reanálise | SE 53 / 2025 | — | 230 dias | `ATRASADO` |
| Modelo experimental | treinado até 2019 · corte SE 52 / 2019 | 21/08/2026 | — | `ATUAL` |

Notas de leitura:

- O clima aparece "atrasado" porque a série climática é gerada **para cobrir
  exatamente o intervalo epidemiológico** — ela não é estendida além do
  último período com casos, porque não haveria com o que cruzar.
- A periodicidade declarada pela fonte (`trimestral`) é lida do CKAN e
  exibida na interface junto ao atraso, para que o número tenha explicação.

---

## 5. O portão da priorização do período atual

Este é o mecanismo que impede o produto de mostrar um ranking sem base.

**Regra:** a priorização referente ao período mais recente só é oferecida se
a última semana epidemiológica com dado estiver a no máximo
**4 semanas** do presente.

**Por que 4:** o modelo sinaliza o início de um episódio em `t+1..t+3`. Uma
priorização cujo instante de decisão `t` já esteja mais de 4 semanas no
passado aponta para uma janela-alvo inteiramente vencida — o gestor não tem
sobre o que agir. 4 = horizonte (3) + 1 semana de folga.

**Estado atual:**

```
current_projection_available = false
reason                       = epidemiological_data_stale
semanas_de_atraso            = 32
semanas_limite               = 4
semana_epi_maxima            = 2025-53
```

Consequências, todas verificadas por teste automatizado:

1. `dashboard/data/latest_priority.parquet` **não é gerado**; se existir de
   uma execução anterior, é **removido** (para não haver artefato
   enganoso).
2. A aba "Período atual" da página experimental mostra a explicação do
   bloqueio e oferece a simulação histórica.
3. O healthcheck marca `FAIL` se houver incoerência entre o estado e os
   arquivos (por exemplo, `latest_priority.parquet` presente com o portão
   fechado).

---

## 6. Consulta à fonte é opcional e nunca em tempo de renderização

`ultima_atualizacao_fonte` exige uma requisição HTTP ao CKAN. Ela acontece
**no pipeline**, não no painel:

- `python -m src.generate_freshness` consulta a fonte;
- `python -m src.generate_freshness --offline` deriva apenas do dado local;
- o painel **lê o JSON** — nunca chama a rede.

Se a fonte estiver fora do ar durante a geração, o campo fica nulo com
`status=DESCONHECIDO` e o resto do artefato continua válido (modo
degradado).

---

## 7. Investigação da fonte epidemiológica (2026-08-21)

Consulta real ao CKAN (`package_show` do dataset
`casos-de-dengue-zika-e-chikungunya`):

| Verificação | Resultado |
|---|---|
| Existem dados oficiais de 2026? | **Não.** O dataset tem 49 recursos; os mais recentes de casos são de **2025** (dengue, zika e chikungunya). |
| Última semana disponível | **SE 53 / 2025** — `SEM_NOT` vai de `202501` a `202553` nos três agravos; `DT_NOTIFIC` chega a 31/12/2025. |
| O ano de 2025 está completo? | Sim (52/53 semanas presentes). |
| `metadata_modified` do dataset | 2026-05-20T10:28:07 |
| Periodicidade declarada | `trimestral` |
| Endpoint/schema mudaram? | Não. As 40 fontes que o projeto ingere continuam presentes, com o mesmo formato (`;` separador, `latin-1`, `SEM_NOT` em `AAAASS`). |
| Há revisões retroativas? | **Sim.** Ao menos um recurso de ano antigo foi alterado depois de criado (chikungunya 2021, `last_modified` 2026-05-20 contra `created` 2026-03-04) — ou seja, reprocessar anos antigos pode mudar números históricos. |

**Conclusão:** não há dado de 2026 a ingerir. A ingestão não foi executada
para "atualizar" nada, porque não existe nada novo. O painel declara o
último período publicado em vez de sugerir atualidade que a fonte não tem.

**Achado de qualidade registrado:** o campo `SEM_PRI` (semana dos primeiros
sintomas) contém valores impossíveis nos arquivos de 2025 (`195002`,
`196834`). O projeto não usa esse campo — usa `SEM_NOT` — mas quem for usar
precisa saber.
