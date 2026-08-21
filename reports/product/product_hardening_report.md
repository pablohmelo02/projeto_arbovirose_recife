# Relatório de *hardening* do produto

**Data:** 2026-08-21 · **Commit inicial:** `b6c7b92` · **Testes antes:** 342
· **Testes depois:** 532

Este documento registra o que foi encontrado, o que foi corrigido, o que
permanece como risco e como cada afirmação do produto se sustenta.

---

## 1. Achados e correções

Severidade: **crítico** = quebra o produto ou expõe dado; **alto** = leva a
decisão errada; **médio** = degrada confiança; **baixo** = higiene.

### 1.1 Ambiente e reprodutibilidade

| # | Achado | Severidade | Correção | Estado |
|---|---|---|---|---|
| 1 | **Nenhuma dependência do projeto estava instalada** na máquina. Nem `pytest`, nem `pyarrow`, nem `streamlit`. Nada podia ser executado nem verificado. | **Crítico** | Ambiente virtual criado e `requirements.txt` instalado; suíte de 342 testes executada como linha de base antes de qualquer alteração. | Corrigido |
| 2 | A Silver/Gold existia apenas dentro de um processo `moto` efêmero de sessão anterior — reconstruir a cadeia hoje mudaria a janela do backfill CEMADEN (que é sempre "últimos N dias a partir de agora") e alteraria todos os números de ML já validados. | **Alto** | O enriquecimento climático foi implementado como transformação **da camada Gold sobre a própria Gold** (mesmo grão, mesma chave, mesmas linhas), preservando byte a byte as 31 colunas pré-existentes. Verificado programaticamente. | Corrigido |

### 1.2 Dados e atualidade

| # | Achado | Severidade | Correção | Estado |
|---|---|---|---|---|
| 3 | **Nenhuma data de atualidade era exposta.** O painel mostrava 13 anos de série sem dizer que o último dado tem 230 dias. | **Alto** | Camada de freshness (`src/freshness.py`) + faixa "Atualização dos dados" no topo de **todas** as páginas, derivada do dado (nada escrito à mão). | Corrigido |
| 4 | Não havia dados de 2026 na fonte — mas também não havia como saber isso sem consultar manualmente. | **Médio** | Investigação registrada (`data_freshness.md`, §7) e leitura automática de `metadata_modified` e da periodicidade declarada pelo CKAN. | Corrigido |
| 5 | **2013–2023 sem nenhum dado climático** (0 % das linhas): a única rede com histórico útil cobria 2024–2025. | **Alto** | Investigação controlada de 4 fontes em grade; incorporação da reanálise ERA5/ERA5-Land. Cobertura climática de **6,1 % → 100 %** das linhas, 2013–2025. | Corrigido, com limitação declarada |
| 6 | `SEM_PRI` (semana dos primeiros sintomas) tem valores impossíveis nos arquivos de 2025 (`195002`, `196834`). | Baixo | Documentado. O projeto usa `SEM_NOT`, não afetado. | Documentado |
| 7 | Revisões retroativas na fonte: recurso de 2021 alterado em 2026 depois de criado em 2026-03. | Médio | Documentado — reprocessar anos antigos pode mudar números históricos. | Documentado |

### 1.3 Segurança

| # | Achado | Severidade | Correção | Estado |
|---|---|---|---|---|
| 8 | `.env.example` com credenciais fracas (`admin` / `admin123`), copiáveis para produção. | **Médio** | Substituídas por placeholders explícitos. | Corrigido |
| 9 | `docker-compose.yml` usava os mesmos defaults fracos via `${VAR:-admin}`. | **Médio** | Trocado por `${VAR:?...}` — o Compose **aborta** sem credencial definida. | Corrigido |
| 10 | MinIO escutando em todas as interfaces (`0.0.0.0:9000`). | Médio | Portas restritas a `127.0.0.1`. | Corrigido |
| 11 | `.gitignore` não cobria `secrets.toml`, `*.pem`, `*.key`, `credentials*`, `.cdsapirc`, `.netrc`, `.aws/`. | **Médio** | Reescrito, com comentário do porquê de cada bloco. | Corrigido |
| 12 | `pytest 8.4.2` com `PYSEC-2026-1845`. | Baixo (dev-only) | Elevado para `>=9.0.3,<10`; suíte reexecutada (532 testes) na versão nova. `pip-audit`: zero vulnerabilidades nos dois arquivos de requisitos. | Corrigido |
| 13 | Requisição HTTP sem timeout garantido (`InmetClient`) — `bandit` B113. | Médio | Construtor rejeita timeout ausente/não positivo; timeout por chamada validado. | Corrigido |
| 14 | `assert` usado para invariante de experimento — desaparece com `python -O` (B101). | Baixo | Convertido em `raise ValueError` explícito. | Corrigido |
| 15 | `git` invocado por caminho parcial (B607) — um `git` plantado no `PATH` seria executado. | Baixo | `shutil.which` + caminho absoluto + `shell=False`. | Corrigido |
| 16 | Artefato de modelo (pickle) seria distribuído pelo repositório. | Médio | `.joblib` não versionado; o painel público não carrega modelo nenhum; caminho do artefato validado contra lista permitida (defesa contra *path traversal*, com testes). | Corrigido |

### 1.4 Qualidade e confiabilidade

| # | Achado | Severidade | Correção | Estado |
|---|---|---|---|---|
| 17 | **Nenhum portão de qualidade** antes de publicar artefato: uma Gold com chave duplicada, bairro faltando ou caso negativo seria publicada. | **Crítico** | `src/quality_gates.py` com 14 portões críticos; publicação **aborta** e preserva o artefato anterior. | Corrigido |
| 18 | **Escrita não atômica**: um processo interrompido deixaria Parquet meio escrito no lugar do artefato válido. | **Crítico** | `src/utils/io_atomico.py` — temporário no mesmo diretório → validar → `os.replace`. | Corrigido |
| 19 | Nenhum diagnóstico operacional. | **Médio** | `python -m src.healthcheck` com `PASS`/`WARN`/`FAIL` e código de saída. | Corrigido |
| 20 | Log sem estrutura e sem redação — um `logger.info(f"{config}")` vazaria a chave do MinIO. | **Médio** | `src/logging_config.py` com filtro de redação sobre a mensagem **já formatada** (cobre valor vindo de argumento), campos obrigatórios por fonte, JSON opcional. | Corrigido |
| 21 | **Bug real encontrado no dashboard modernizado**: conflito de assinatura do Plotly (`title` no layout padrão + `title` na chamada) fazia 6 gráficos falharem — e a fronteira de erro os transformava em mensagem amigável, ou seja, **o painel "funcionava" com gráficos faltando**. | **Alto** | Corrigido; e um arquivo de teste dedicado passou a exercitar **todos os 23 construtores de gráfico**, para que essa classe de falha seja pega pela suíte. | Corrigido |
| 22 | Nenhuma validação de entrada da interface. | Médio | `dashboard/utils/validacao.py` — todo filtro validado contra o **domínio real do dataset carregado**. | Corrigido |
| 23 | Nenhuma fronteira de erro na UI: uma exceção derrubava a página inteira. | Médio | `dashboard/components/erros.py`; o teste de navegador **falha** se a mensagem de degradação aparecer. | Corrigido |

### 1.5 Comunicação de resultado

| # | Achado | Severidade | Correção | Estado |
|---|---|---|---|---|
| 24 | Risco de exibir probabilidade do modelo como grau de confiança. | **Alto** | Probabilidade **nunca publicada**. O artefato traz posição e um score que é **posto relativo normalizado** (calculado por ordenação, não por reescala de probabilidade). Teste garante que colunas de probabilidade não vazem para o artefato. | Corrigido |
| 25 | Risco de reaproveitar os ~79 % de detecção em epidemias grandes, medidos numa formulação binária anterior, como se fossem do ranking atual (onde o valor real é 30,4 % em Top-10). | **Alto** | Cada métrica vinculada à versão que a produziu; aviso explícito na página e na documentação. | Corrigido |
| 26 | Risco de afirmar ganho do modelo em Top-10/15/20. | **Alto** | O painel publica as quatro faixas com a leitura correta de cada uma, incluindo a faixa em que a regra simples é **melhor**. | Corrigido |
| 27 | Risco de mostrar priorização "atual" sobre dado de 8 meses atrás. | **Alto** | Portão de atualidade: `latest_priority.parquet` não é gerado (e é removido se existir); healthcheck marca `FAIL` em caso de incoerência. | Corrigido |

---

## 2. Matriz de risco residual

| Risco | Probabilidade | Impacto | Severidade | Mitigação atual | Residual |
|---|---|---|---|---|---|
| Dado epidemiológico atrasado | **Alta** (é o estado atual) | Médio | **Médio** | Faixa de atualidade em toda página; portão da projeção; healthcheck `WARN` | **Médio** — inerente à fonte; nenhuma ação técnica resolve |
| API da fonte fora do ar | Média | Baixo | Baixo | Retentativa com espera crescente; falha explícita; artefato anterior preservado; `--sem-rede` | Baixo |
| *Schema drift* na fonte | Média | **Alto** | **Médio** | Validação estrutural antes da Silver; portões de qualidade; contratos de schema versionados | Baixo |
| Dado climático ausente | Baixa (100 % em grade) | Baixo | Baixo | `missing ≠ 0`; contadores de dias válidos; duas famílias independentes | Baixo |
| Incompatibilidade de artefato de ML | Média (a cada atualização de biblioteca) | Médio | **Médio** | Validação de assinatura de features + schema da Gold + versão do sklearn; falha fechada | Baixo |
| *Model drift* (padrão epidemiológico muda) | **Alta** (ciclos de arbovirose mudam) | **Alto** | **Alto** | Instabilidade entre anos publicada, não suavizada; treino/teste temporais; walk-forward | **Alto** — não mitigável sem monitoramento contínuo e retreino validado |
| Subnotificação | **Alta** | **Alto** | **Alto** | Declarada em página própria e em toda a documentação | **Alto** — exigiria fonte externa |
| Exposição de segredo | Baixa | **Alto** | **Médio** | `.gitignore` abrangente; histórico auditado e limpo; sem defaults fracos; verificação no script de deploy | Baixo |
| Arquivo incompleto/corrompido | Baixa | **Alto** | **Médio** | Escrita atômica; portões; healthcheck detecta Parquet ilegível | Baixo |
| **Erro de interpretação do score** | **Média** | **Alto** | **Alto** | Probabilidade nunca publicada; score é posto relativo; avisos em toda página experimental; tabela de claims; limitações listadas na própria página | **Médio** — risco de comunicação, não técnico; depende de leitura humana |
| Vazamento de dado pessoal | Baixa | **Crítico** | **Médio** | 3 barreiras de verificação de privacidade; Bronze/Silver nunca publicados; redação no log | Baixo |
| Mudança climática alterando a relação clima-arbovirose | Média | Médio | Médio | O clima **não** está no modelo; a página de clima trata associação, não causalidade | Baixo (para o modelo) |
| Capacidade operacional insuficiente para agir | **Alta** | Médio | **Médio** | Desempenho publicado por faixa de K, inclusive onde o modelo não ajuda; carga operacional em duas unidades | **Médio** — decisão de gestão |

---

## 3. Tabela de claims

| Afirmação | Permitida? | Evidência | Ressalva obrigatória |
|---|---|---|---|
| Acompanha o histórico territorial de arboviroses no Recife | **Sim** | 191.478 linhas · 94 bairros · 679 semanas · 2013–2025 · 156.504 casos, direto da fonte oficial | Sujeito a subnotificação e a revisões retroativas da fonte |
| Identifica bairros com maior número de casos observados | **Sim** | Contagem direta na Gold | É **volume absoluto**, não incidência — não há população por bairro |
| Compara o padrão sazonal entre anos | **Sim** | Curvas por semana epidemiológica derivadas da própria série | Descreve; não projeta |
| Aponta bairros acima do próprio padrão histórico | **Sim** | Razão contra a mesma época do ano em anos anteriores, com N informado | `n` pequeno torna a razão instável — o `n` é exibido |
| Fornece um ranking experimental de priorização | **Sim, com ressalva** | 154 semanas de backtest, 920 episódios | Experimental; retrospectivo; não é previsão oficial |
| **O modelo supera regras simples ao priorizar 5 bairros/semana** | **Sim, com ressalva** | +5,98 pp; IC [+2,83; +9,13]; IC > 0 também nos dois esquemas de cluster; positivo nos 3 anos; robusto a leave-one-year-out | Vale para **Top-5**, período 2023–2025, sobre 920 episódios. Taxa absoluta: 25,76 % dos episódios |
| O modelo supera regras simples ao priorizar 10 bairros | **Não** | IC [−0,76; +5,98] cruza zero; excluir 2025 inverte o sinal | — |
| O modelo supera regras simples ao priorizar 15 ou 20 bairros | **Não** | Em Top-20 a regra simples é **melhor** (−5,54 pp, IC [−10,11; −1,30]) | — |
| Identifica antecipadamente bairros prioritários | **Sim, com ressalva** | Mediana de 2 semanas (IC 2–3) em Top-10; 69,1 % com ≥ 2 semanas | Medida em **Top-10** — não combinar com o ganho de Top-5. Só sobre os episódios detectados |
| Pode apoiar priorização preventiva | **Sim, com ressalva** | Ganho em Top-5 + antecedência medida | 65,5 % das priorizações em Top-5 não precederam episódio; desempenho muito desigual entre RPAs |
| O clima melhora o modelo | **Não** | Experimento controlado: −0,11 pp em Top-5, IC cruza zero nos 3 esquemas, sinal negativo em 2024 | Ganho em Top-10 registrado como candidato a versão futura, **não** como resultado |
| Detecta bem os grandes episódios | **Não** | 30,4 % em Top-10 contra 38,4 % geral — **pior** que a média | Os ~79 % de uma formulação binária anterior **não** se aplicam a este módulo |
| É igualmente confiável em todos os bairros | **Não** | RPA 5: 59,4 % · RPA 6: 23,0 % em Top-10. IPSEP: 0 % em Top-10 com 6 episódios | — |
| Prevê surtos | **Não** | O produto ordena prioridades relativas; não estima ocorrência nem magnitude | — |
| Reduz a incidência de dengue | **Não** | Não medido; não mensurável com os dados disponíveis | — |
| Reduz internações | **Não** | O projeto não tem dado de internação | — |
| Mostra dados em tempo real | **Não** | Fonte com periodicidade trimestral declarada; último dado 230 dias atrás | O painel declara o último período publicado |
| Calcula incidência por 100 mil habitantes | **Não** | Nenhuma fonte usada tem população por bairro | — |
| Classifica bairros por nível de risco (verde/amarelo/vermelho) | **Não** | Categorizar risco exigiria validação inexistente | A paleta do produto não tem cores de semáforo |

---

## 4. Testes

| Categoria | Testes |
|---|---|
| Linha de base (herdada) | 342 |
| Clima em grade (cliente, Silver, Gold, leakage adversarial, idempotência) | 27 |
| Gráficos do dashboard (23 construtores) | 20 |
| Freshness e portão da projeção | 19 |
| Portões de qualidade e escrita atômica | 24 |
| Artefatos de ML e healthcheck | 26 |
| Validação de entrada, priorização observada, EDA em grade | 44 |
| Artefatos de priorização (backtest, cutoff, score) | 17 |
| Log estruturado e resiliência | 31 |
| Não-regressão nas remoções | (coberto pela suíte herdada) |
| **Total** | **532 · 100 % passando** |

Destaques de conteúdo:

- **Leakage adversarial** em três lugares: features climáticas em grade,
  ranking do backtest e (herdado) target/features do modelo. O padrão é o
  mesmo: injetar valor extremo **depois** do corte e exigir que nada antes
  dele mude.
- **Ausência ≠ zero**: testado em cada camada.
- **Portões preservam o artefato bom**: validação que falha e exceção
  durante a escrita, ambos verificando que o arquivo anterior sobrevive.
- **Coerência do portão de projeção**: artefato presente com portão fechado
  é `FAIL`, não aviso.
- **Contrato do artefato publicado**: teste garante que nem probabilidade
  nem desfecho futuro vazam para `latest_priority`.

---

## 5. Verificação em navegador real

Chrome *headless*, 9 páginas × 3 larguras = **27 cargas de página**.

| Perfil | Carregamento inicial | Troca de página | Exceções | Seções degradadas | Rolagem horizontal |
|---|---|---|---|---|---|
| Desktop (1440×960) | 278 ms · 11 KB | 1,99–3,64 s | 0 | 0 | nenhuma |
| Tablet (834×1112) | 252 ms · 11 KB | 1,37–2,42 s | 0 | 0 | nenhuma |
| Mobile (390×844) | 268 ms · 11 KB | 1,66–2,40 s | 0 | 0 | nenhuma |

Resultado da execução final: **27/27 cargas de página aprovadas**.

Elementos verificados por página: gráficos Plotly renderizados (1 a 5 por
página), tabelas (0 a 7), alertas intencionais, ausência de marcadores de
exceção no texto (`Traceback`, `KeyError:`, `StreamlitAPIException`, …).

O teste **falhou** na primeira execução e revelou o achado #21 — três
páginas com seção degradada. Foi corrigido e reexecutado até 0 falhas.

Resultado bruto: `reports/product/browser_test_result.json`.

---

## 6. Aptidão para deploy

`python scripts/verificar_deploy_dashboard.py` → **APTO**, 0 bloqueios.

| Verificação | Resultado |
|---|---|
| 24 arquivos `.py` do painel: sintaxe, imports proibidos, caminhos absolutos, segredos | ok |
| 9 módulos de `src/eda/` consumidos pelo painel: nenhuma dependência de infraestrutura | ok |
| Artefatos obrigatórios presentes e não vazios | ok |
| Privacidade de 2 Parquet + 1 GeoJSON publicados | ok — nenhuma coluna identificável |
| `.gitignore` cobre `.env`, `secrets.toml`, `*.pem`, `*.key` | ok |
| Tamanho publicado | 3,72 MB |

**"Tecnicamente apto" não é "publicado".** A publicação depende de conta no
Streamlit Community Cloud e de repositório no GitHub — pendências humanas.

---

## 7. Classificação final

### Produto: **B — demonstrável com pendências pequenas**

Justificativa: as nove páginas funcionam em três larguras sem exceção; a
atualidade é declarada em toda página; os portões de qualidade e a escrita
atômica protegem os artefatos; a privacidade é verificada a cada publicação;
o healthcheck é limpo. A classificação não é **A** por dois motivos, ambos
externos ao código: os dados oficiais estão 32 semanas defasados (o que
desabilita a priorização do período atual) e a publicação efetiva ainda não
ocorreu por falta de credencial.

### Módulo de ML: **A — experimental demonstrável**

Justificativa: existe um ganho estatisticamente defensável e reprodutível em
Top-5, com antecedência medida; o backtest é navegável semana a semana,
mostrando acertos **e** erros; as limitações (disparidade regional, início
genuíno, grandes episódios, instabilidade da lista, custo operacional) são
publicadas com números. É demonstrável **como experimento** — e apenas como
experimento.

---

## 8. Pendências humanas

1. **Publicar no Streamlit Community Cloud** — exige repositório GitHub e
   conta conectada. Receita completa em `deployment_runbook.md`, §6.
2. **Decidir se o app técnico ganha URL própria** — a recomendação atual é
   manter local (justificativa no runbook, §7).
3. **Aguardar a fonte publicar 2026** — quando publicar, uma única execução
   de `python -m src.update_recife_alerta --com-datalake` incorpora, e o
   portão da projeção se abre sozinho.
4. **Investigar a disparidade da RPA 6 / IPSEP** — limitação sistemática
   identificada e quantificada, causa não investigada.
5. **Considerar uma versão v2 com clima em Top-10** — só com o protocolo
   completo de validação.
6. **Reexecutar `pip-audit` periodicamente** — a ausência de vulnerabilidade
   hoje não é permanente.
