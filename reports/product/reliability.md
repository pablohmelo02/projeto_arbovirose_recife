# Confiabilidade

Como o pipeline e o painel se comportam quando algo dá errado — e como se
garante que um resultado ruim nunca substitua um resultado bom.

---

## 1. Princípios

1. **Falhar cedo e alto.** Schema inesperado, resposta vazia, chave
   duplicada, caso negativo: tudo levanta exceção. Nada é "corrigido"
   silenciosamente.
2. **Nunca sobrescrever o bom com o ruim.** Escrita atômica + portões de
   qualidade antes da publicação.
3. **Ausência é ausência.** `missing ≠ 0` em toda variável climática.
4. **Degradar por módulo, não por aplicação.** Uma seção que falha não
   derruba a página; uma página que falha não derruba o painel.
5. **Nunca engolir erro.** Toda exceção capturada é registrada com
   *traceback* antes de virar mensagem amigável.

---

## 2. Robustez de acesso às fontes

| Ponto frágil | Tratamento | Onde |
|---|---|---|
| **Retentativa HTTP** | 3 tentativas com espera exponencial (2 s → 4 s) no cliente de clima em grade; aviso a cada falha; erro de domínio ao esgotar | `src/clients/gridded_climate_client.py` |
| **Timeout** | Obrigatório em todo cliente. `InmetClient` **rejeita** timeout ausente ou não positivo no construtor | todos os clientes |
| **Resposta vazia** | `0 bytes` é tratado como falha (e re-tentado), não como "nenhum dado" | cliente de grade |
| **Schema drift** | Validação estrutural antes de a Silver receber qualquer coisa: número de pontos, presença de `daily.time`, presença de cada variável pedida, comprimento igual ao das datas | cliente de grade + `src/silver/climate_grade.py` |
| **Encoding** | Bronze do SINAN lida como `latin-1` com separador `;` (formato real da fonte); JSON validado como UTF-8 explicitamente | `src/utils/csv_bruto.py`, clientes |
| **Datas** | Conversão com `errors="coerce"`; linha com data inválida é rejeitada **e contada por motivo** | `normalizar_clima_grade_diario` |
| **Decimal brasileiro** | Conversores por fonte, não intercambiáveis (`converter_decimal_brasileiro` para INMET, `converter_float` para APAC/CEMADEN) — usar o errado corrompe coordenadas silenciosamente, bug real já corrigido no histórico do projeto | `src/silver/quality.py` |
| **Duplicatas** | Deduplicação explícita por chave composta, com contagem no manifest | Silver de clima (estação e grade) |
| **Chaves compostas** | `(fonte, codigo_estacao)` na camada de estação; `(grade, celula_id, data)` na de grade. `celula_id` ou `codigo_estacao` sozinhos **não são chave** | schemas |
| **Timezone** | Toda requisição de reanálise fixa `America/Recife`, alinhando o dia-calendário ao referencial das datas do SINAN. O default (UTC) deslocaria a fronteira do dia em 3 h | cliente de grade |
| **API indisponível** | Erro de domínio; a etapa falha e interrompe a atualização (ou registra aviso, se marcada como tolerante). A geração de freshness é tolerante por desenho: campo nulo + `DESCONHECIDO` | orquestrador |
| **Arquivo parcial** | Impossível por construção (escrita atômica) | `src/utils/io_atomico.py` |
| **Execução interrompida** | O temporário é removido; o destino permanece na versão anterior | idem |
| **Parquet corrompido** | Detectado na leitura; healthcheck marca `FAIL`; painel mostra mensagem amigável | healthcheck + loaders |

---

## 3. Validação de schema e domínio

`src/quality_gates.py` valida a Gold antes de qualquer publicação:

| Portão | Severidade |
|---|---|
| Gold não vazia | `CRITICO` |
| Colunas obrigatórias presentes | `CRITICO` |
| Chave `(bairro, agravo, ano, semana)` única | `CRITICO` |
| Exatamente 94 bairros | `CRITICO` |
| Exatamente os 3 agravos esperados | `CRITICO` |
| `casos >= 0` | `CRITICO` |
| `casos` sem nulo (notificação compulsória: ausência é 0) | `CRITICO` |
| Semana epidemiológica em 1–53 | `CRITICO` |
| `data_fim >= data_inicio` | `CRITICO` |
| Semana com exatamente 7 dias | `CRITICO` |
| Precipitação/chuva nunca negativa | `CRITICO` |
| Umidade relativa em 0–100 % | `CRITICO` |
| Integridade referencial com o território (nos dois sentidos) | `CRITICO` |
| Território não informado | `AVISO` |

Regra de ausência explicitamente testada: **precipitação toda nula não é
erro** — `missing ≠ 0` continua válido e não bloqueia a publicação.

Se qualquer portão crítico falha, `QualityGateError` é levantada, **nada é
escrito**, e o artefato anterior permanece intacto.

---

## 4. Idempotência

| Etapa | Garantia | Verificação |
|---|---|---|
| Silver em grade | regravada por inteiro a partir da última ingestão com sucesso, nunca por *append*; deduplicação por chave composta com "a mais recente vence" | teste de deduplicação e de mesma célula em grades diferentes |
| Gold + clima em grade | o bloco em grade é **removido e recalculado** a cada execução, nunca atualizado em cima do valor anterior | teste dedicado; e verificação real: duas execuções seguidas produziram tabela idêntica em todas as 46 colunas, exceto os dois metadados de execução |
| Artefatos de priorização | recalculados do zero a partir do modelo congelado | reprodutibilidade do candidato verificada campo a campo |
| Freshness | derivado do dado; mesma entrada → mesma saída (exceto `gerado_em`) | — |

---

## 5. Atomicidade

Padrão único, em `src/utils/io_atomico.py`:

```
escrever no temporário (mesmo diretório)  →  validar  →  os.replace
```

- Mesmo diretório garante mesmo sistema de arquivos, condição para
  `os.replace` ser atômico (POSIX e Windows).
- Se a validação falhar, o temporário é removido e a exceção sobe.
- Se o processo for interrompido, o destino permanece na versão anterior.
- Não sobra arquivo intermediário (verificado por teste).

Cobre Parquet, JSON, CSV e texto.

---

## 6. Modo degradado

| Falha | Comportamento |
|---|---|
| `_freshness.json` ausente | Faixa mostra "não foi possível determinar a atualidade"; resto funciona |
| `bairro_geo.geojson` ausente | Mapa desabilitado com explicação; **tabela por bairro substitui o mapa**; resto funciona |
| Módulo experimental ausente (status/backtest) | Página experimental mostra indisponibilidade; as 8 páginas observadas funcionam |
| `_evidence_summary.json` ausente | Backtest continua navegável; só a seção de desempenho histórico desaparece |
| `latest_priority.parquet` ausente | Estado **esperado** quando o portão bloqueia; a aba explica o motivo |
| Artefato de modelo incompatível | Nenhum artefato é publicado; status registra `model_artifact_incompatible`; painel mostra "Priorização indisponível — artefato/modelo não validado para o período atual" |
| Fonte de clima fora do ar | Etapa de grade falha e interrompe a atualização; a Gold anterior permanece publicada |
| CKAN fora do ar na geração de freshness | Campo de publicação da fonte fica nulo com `DESCONHECIDO`; resto do artefato válido |
| Uma seção de página levanta exceção | Fronteira de erro isola a seção; log recebe o *traceback*; a página continua |

**Ponto único de falha:** apenas `gold_arboviroses_clima_bairro.parquet`.
Sem ele não há painel — e isso é declarado com mensagem acionável, não com
tela branca.

---

## 7. Healthcheck

`python -m src.healthcheck` (ou `--json`) responde às quatro perguntas
operacionais e devolve `PASS`/`WARN`/`FAIL` por verificação. Saída `1`
apenas se houver `FAIL`.

Última execução: **13 PASS · 1 WARN · 0 FAIL** (status geral `WARN`).

O único `WARN` é o atraso da fonte epidemiológica — estado real do dado, não
falha do sistema. Um artefato opcional ausente também é `WARN`, nunca
`FAIL`: modo degradado não é defeito.

Verificação de coerência que merece destaque: se
`current_projection_available=false` mas `latest_priority.parquet` existir
(ou o inverso), o healthcheck marca **`FAIL`** — um artefato de projeção que
não deveria existir é potencialmente enganoso, e isso é tratado como falha.

---

## 8. Recuperação de falha

| Situação | O que fazer |
|---|---|
| Atualização interrompida no meio | Rodar `python -m src.update_recife_alerta` de novo. Toda etapa é idempotente; nada acumula. |
| Artefato publicado suspeito | `python -m src.healthcheck` aponta a verificação que falhou. Como toda escrita é atômica, o estado é sempre uma versão íntegra (a anterior ou a nova). |
| Fonte de clima fora do ar | `python -m src.update_recife_alerta --sem-rede` recalcula tudo a partir do que já está em disco. |
| Modelo incompatível após atualizar biblioteca | `python -m src.train_priority_model` regenera o artefato; o healthcheck confirma a compatibilidade. |
| Rollback | Os artefatos publicados são versionados no Git; `git checkout <commit> -- dashboard/data/` restaura um estado anterior conhecido. |

---

## 9. Testes de resiliência

Cobertura automatizada, sem depender de internet (respostas HTTP simuladas):

- HTTP 500, 503, timeout de conexão, resposta vazia, JSON inválido, payload
  com erro declarado pela API;
- retentativa que recupera na segunda tentativa (e contagem de chamadas);
- schema drift: variável ausente, número de pontos diferente do pedido,
  comprimento de série divergente;
- arquivo ausente, Parquet corrompido, artefato de modelo ausente,
  assinatura de features incompatível, reordenação de features, versão de
  scikit-learn divergente;
- período sem dados, bairro sem dados, zero casos, clima ausente,
  DataFrame vazio em cada função de EDA;
- fonte desatualizada (portão da projeção, inclusive no limite exato);
- validação que falha preservando o arquivo anterior; exceção durante a
  escrita preservando o anterior; nada escrito levantando erro.

**Suíte total: 532 testes, todos passando** (linha de base da auditoria
inicial: 342).
