# Runbook operacional

Roteiro para atualizar, verificar e publicar o Recife Alerta. Todos os
comandos são reais e foram executados nesta forma.

---

## 0. Preparar o ambiente (uma vez)

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate no Linux/macOS
pip install -r requirements.txt
cp .env.example .env              # e preencher (só necessário para a cadeia com Data Lake)
```

O painel **não** precisa de `.env`: ele lê apenas os artefatos de
`dashboard/data/`.

---

## 1. Atualizar os dados

```bash
python -m src.update_recife_alerta
```

Executa, em ordem, e para na primeira falha não tolerada:

```
1. ingestão/Silver: clima em grade (reanálise)      ~7 s
2. transformação: Gold += clima em grade            ~1 s
3. metadados: freshness                             ~3 s
4. artefatos: priorização experimental (sem treinar) ~12 s
5. healthcheck                                       <1 s
                                              total ~23 s
```

Variantes:

| Comando | Quando usar |
|---|---|
| `python -m src.update_recife_alerta --sem-rede` | fonte de clima fora do ar; recalcula só com o que está em disco |
| `python -m src.update_recife_alerta --com-datalake` | reprocessar a cadeia canônica completa (CKAN/INMET/CEMADEN → Bronze → Silver → Gold → exportação). Exige `.env` e MinIO no ar |

**Esta rotina nunca treina modelo.** Treinar é operação separada (§3).

O resumo da execução é gravado em `dashboard/data/_ultima_atualizacao.json`
e fica visível na página de qualidade do painel.

---

## 2. Validar

```bash
python -m src.healthcheck                         # PASS / WARN / FAIL por verificação
python -m src.healthcheck --json                  # mesma saída, para automação
python -m pytest -q                               # suíte completa (532 testes)
python scripts/verificar_deploy_dashboard.py      # aptidão para publicação
```

Saída esperada do healthcheck hoje: **13 PASS · 1 WARN · 0 FAIL**. O `WARN`
é o atraso da fonte epidemiológica — estado real do dado, não falha.

`verificar_deploy_dashboard.py` checa sintaxe, imports proibidos em runtime,
caminhos absolutos, segredos literais, artefatos obrigatórios, tamanho
publicado, `.gitignore` e — o mais importante — **privacidade de todos os
artefatos publicados**.

---

## 3. Treinar o modelo (operação controlada, separada)

```bash
python -m src.train_priority_model            # grava artifacts/models/<versao>/
python -m src.generate_priority_artifacts     # backtest + status (não treina)
```

Quando é necessário:

- primeira vez num clone novo (o `.joblib` não é versionado — ver
  `security_and_privacy.md`, §4);
- depois de atualizar o scikit-learn para uma versão maior (o carregamento
  do artefato antigo passa a ser recusado, de propósito);
- nunca como efeito colateral de um refresh de dados.

Depois de treinar, **revisar** o metadado gravado
(`artifacts/models/<versao>/metadata.json`) e reexecutar o healthcheck. Se a
assinatura de features mudou, isso é uma **versão nova** de modelo e exige
nova validação estatística — os números publicados não valem mais.

---

## 4. Rodar o painel localmente

```bash
streamlit run dashboard/app.py
# abre em http://localhost:8501
```

Verificação em navegador real (precisa de Chrome instalado e do painel no
ar; `pip install selenium` sob demanda):

```bash
python scripts/testar_dashboard_navegador.py --url http://localhost:8501 --todos-os-perfis
```

Percorre as 9 páginas em três larguras (1440, 834, 390 px) e **falha** se
alguma página exibir exceção, *stack trace*, seção degradada ou provocar
rolagem horizontal. Grava `reports/product/browser_test_result.json` com
tempos de carregamento.

---

## 5. Verificar a atualidade no painel

Depois de qualquer atualização, confirmar na interface:

1. A faixa **"Atualização dos dados"** aparece no topo de todas as páginas.
2. Ela mostra a semana epidemiológica correta e a data de publicação da
   fonte.
3. A aba **"Período atual"** da página experimental reflete o portão: se o
   dado estiver defasado, ela precisa mostrar o bloqueio, e
   `latest_priority.parquet` **não** deve existir.

---

## 6. Publicar no Streamlit Community Cloud

**Pré-requisitos** (pendências humanas, não técnicas):

- repositório no GitHub com o conteúdo deste projeto;
- conta no Streamlit Community Cloud conectada a esse repositório.

**Configuração do app:**

| Campo | Valor |
|---|---|
| Repository | o repositório deste projeto |
| Branch | `main` |
| Main file path | `dashboard/app.py` |
| Python version | 3.11 ou superior |
| Requirements | detectado automaticamente em `dashboard/requirements.txt` |
| Secrets | **nenhum** — o painel não acessa fonte autenticada |

**O que o painel publicado consome** (tudo versionado, ~3,7 MB):

```
dashboard/data/gold_arboviroses_clima_bairro.parquet   1,36 MB
dashboard/data/bairro_geo.geojson                      2,16 MB
dashboard/data/historical_priority_backtest.parquet    0,14 MB
dashboard/data/_freshness.json                         4 KB
dashboard/data/_priority_status.json                   1 KB
dashboard/data/_evidence_summary.json                  42 KB
dashboard/data/_gold_clima_grade.json                  3 KB
dashboard/data/_profiling_export.json                  1 KB
dashboard/data/_ultima_atualizacao.json                1 KB
```

**O painel não depende em runtime de**: MinIO, moto, API externa,
treinamento, credencial ou caminho absoluto — verificado estaticamente pelo
script de deploy, que **falha** se algum módulo do painel importar `boto3`,
`geopandas`, `sklearn`, `matplotlib` ou `requests`.

---

## 7. Publicação do app técnico de validação

`tools/model_validation_app.py` é uma segunda aplicação Streamlit, voltada
à leitura técnica dos artefatos de validação estatística.

**Decisão: permanece local.** Motivos:

1. O conteúdo técnico dela já está integrado ao painel público, na aba
   "Desempenho histórico" da página experimental — com linguagem adequada a
   gestores e as mesmas ressalvas.
2. Publicar duas URLs com sobreposição de conteúdo aumenta o risco de
   alguém citar a versão técnica fora de contexto.
3. Ela lê `reports/ml/*`, um layout interno que não deve virar contrato
   público.

Se um deploy separado for desejado no futuro, é tecnicamente possível (mesma
receita da §6, apontando `Main file path` para `tools/model_validation_app.py`),
mas exige decisão e credencial humanas.

```bash
streamlit run tools/model_validation_app.py   # uso local
```

---

## 8. Fluxo completo, em uma linha

```
Fonte epidemiológica (CKAN)
        ↓  python -m src.main / ingest_territorio / ingest_climate          [--com-datalake]
Bronze (MinIO)
        ↓  python -m src.transform* / transform_gold_arboviroses_clima      [--com-datalake]
Silver → Gold
        ↓  python -m src.export_dashboard_dataset                           [--com-datalake]
dashboard/data/
        ↓  python -m src.build_climate_grade  (reanálise → Silver em grade)
        ↓  python -m src.enrich_gold_clima_grade  (Gold 1.0 → 1.1)
        ↓  python -m src.generate_freshness
        ↓  python -m src.generate_priority_artifacts  (modelo congelado, sem treinar)
        ↓  python -m src.healthcheck
Streamlit
```

Treino do modelo é uma ramificação lateral e controlada:

```
python -m src.train_priority_model  →  artifacts/models/<versao>/
```

---

## 9. Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| Painel: "Os dados do painel não estão disponíveis" | `gold_...parquet` ausente | `python -m src.update_recife_alerta` |
| Página experimental: "Priorização indisponível" | artefato ausente ou incompatível | `python -m src.train_priority_model` e depois `generate_priority_artifacts` |
| Healthcheck `FAIL` em `modelo:coerencia_projecao` | `latest_priority.parquet` inconsistente com o portão | `python -m src.generate_priority_artifacts` (regenera e remove o artefato indevido) |
| Healthcheck `FAIL` em `gold:legivel` | Parquet corrompido | restaurar do Git (`git checkout -- dashboard/data/`) e reexecutar a atualização |
| Etapa de clima falha | fonte de reanálise fora do ar | reexecutar; se persistir, `--sem-rede` mantém o painel funcionando com o dado anterior |
| `docker compose up` aborta pedindo variável | comportamento **esperado** — credencial do MinIO não definida | preencher `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` no `.env` |
