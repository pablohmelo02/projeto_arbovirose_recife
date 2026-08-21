# Segurança e privacidade

**Escopo:** aplicação web pública (Streamlit), pipeline de dados e
artefatos publicados. Documento de auditoria, não de marketing.

**Nenhuma certificação, conformidade formal ou auditoria externa é
reivindicada.** Este é o resultado de uma revisão interna, com as
ferramentas e evidências listadas abaixo.

---

## 1. Superfície de dados

| Camada | Contém | Publicada? |
|---|---|---|
| Bronze | CSV bruto do SINAN — **registro individual**, com campos potencialmente identificáveis | **Não.** Vive só no Data Lake local/MinIO. |
| Silver | dado normalizado, ainda no grão de notificação | **Não.** |
| Gold | agregado `bairro × semana epidemiológica × agravo` | **Sim** (é o dataset do painel) |
| Território | geometria oficial dos 94 bairros (dado público) | Sim |
| Clima | leitura de estação e reanálise em grade, por célula/estação | Sim (agregado por bairro × semana) |
| Artefatos de ML | ranking por bairro × semana, score relativo | Sim |
| Modelo treinado (`.joblib`) | pesos do classificador | **Não versionado** (ver §4) |

A menor unidade de qualquer coisa publicada é **bairro × semana**. Não
existe, em nenhum artefato publicado, linha que se refira a uma pessoa.

---

## 2. Privacidade — verificação, não confiança

Três barreiras independentes:

1. **Na exportação** (`src/export_dashboard_dataset.py`): a Gold é
   verificada contra uma lista de colunas potencialmente identificáveis e a
   exportação **aborta** se encontrar alguma. O resultado da verificação é
   gravado em `dashboard/data/_profiling_export.json` a cada execução — não
   depende de memória de quem rodou.
2. **Nos portões de qualidade** (`src/quality_gates.py::validar_dataset_publicavel`):
   o mesmo critério, disponível para qualquer artefato.
3. **Na verificação de deploy** (`scripts/verificar_deploy_dashboard.py`):
   varre **todos** os Parquet de `dashboard/data/` e as propriedades do
   GeoJSON, procurando 19 nomes de coluna identificáveis
   (`id_notificacao`, `nome`, `cpf`, `cns`, `data_nascimento`, `endereco`,
   `telefone`, `email`, `prontuario`, `latitude_paciente`, …).

**Resultado da última execução:** nenhum achado. 2 Parquet e 1 GeoJSON
verificados.

Barreira adicional no log: o filtro de redação
(`src/logging_config.py::FiltroRedacao`) mascara padrões de CPF e de CNS
mesmo que alguém, por acidente, tente registrar uma linha de Bronze.

---

## 3. Segredos

### Auditoria realizada

| Verificação | Resultado |
|---|---|
| Arquivo sensível versionado (`.env`, `secrets.toml`, `.pem`, `.key`, `credentials*`) | **Nenhum.** Só `.env.example` (placeholders). |
| Padrões de credencial conhecida no código versionado (`AKIA…`, `ghp_…`, `sk-…`, `xox…`, chave privada PEM, `AIza…`) | **Nenhum.** |
| URL com `usuario:senha@host` | **Nenhuma.** |
| Atribuição literal de senha/token/api_key | **Nenhuma.** |
| Histórico do Git (todos os commits, arquivos adicionados e conteúdo de blobs) | **Nenhum segredo jamais commitado.** |

### Correções aplicadas nesta revisão

- **`.env.example` tinha defaults fracos** (`MINIO_ACCESS_KEY=admin`,
  `MINIO_SECRET_KEY=admin123`). Substituídos por placeholders explícitos
  (`DEFINA_UMA_CHAVE_SECRETA_FORTE`). O risco não era o arquivo em si: era
  alguém copiar o `.env.example` para `.env` e subir um serviço com senha
  previsível.
- **`docker-compose.yml` tinha os mesmos defaults** via
  `${MINIO_ACCESS_KEY:-admin}`. Agora usa `${MINIO_ACCESS_KEY:?...}`, que
  **aborta** o Compose se a variável não estiver definida.
- **MinIO escutava em todas as interfaces.** Portas restritas a
  `127.0.0.1` — o Data Lake de desenvolvimento não precisa estar exposto na
  rede local.

### Onde os segredos devem viver

- Local: `.env` (ignorado pelo Git).
- Deploy do painel: **nenhum segredo é necessário** — o painel não acessa
  fonte autenticada nem banco. Se um dia precisar, `.streamlit/secrets.toml`
  (também ignorado).
- `.streamlit/config.toml` **é** versionado: contém só tema e opções de
  servidor, nenhum segredo.

---

## 4. Desserialização e o artefato de modelo

Carregar um pickle executa código. Mitigações:

1. O **painel público não carrega modelo nenhum** — lê apenas Parquet e
   JSON já calculados. Nenhuma superfície pública desserializa objeto
   arbitrário.
2. O `.joblib` **não é versionado** (`.gitignore`). Ele é gerado localmente
   por `python -m src.train_priority_model` e reconstruído em segundos. Isso
   remove o binário da distribuição e evita que um artefato adulterado
   chegue a alguém via `git clone`.
3. O caminho do artefato **nunca vem de entrada de usuário**:
   `src/ml/artifacts.py::caminho_artefato` valida o identificador contra um
   padrão restrito (`^[a-z0-9_]+$`) **e** contra uma lista permitida de
   versões conhecidas. Testes cobrem `../fora`, `c:/windows`, nome com
   espaço e versão desconhecida.
4. Ao carregar, a compatibilidade é validada (assinatura de features, versão
   do schema da Gold, versão maior do scikit-learn). Incompatibilidade
   **levanta exceção**; o produto mostra indisponibilidade em vez de um
   ranking aparentemente válido.

---

## 5. Validação de entrada na interface

Todo valor vindo de widget é tratado como não confiável
(`dashboard/utils/validacao.py`):

- **Domínio real, não lista fixa**: agravo, RPA, bairro, ano e semana são
  validados contra os valores que **existem no dataset carregado** — não
  contra uma constante do código, que poderia divergir do dado.
- **Semana epidemiológica**: validada contra os pares `(ano, semana)` que
  realmente existem (não basta `1 ≤ semana ≤ 53`: nem todo ano tem 53
  semanas).
- **K do ranking**: restrito a `{5, 10, 15, 20}` — os únicos valores para os
  quais existe evidência publicada.
- **Intervalo de anos**: inteiros, ordem corrigida, dentro do mínimo/máximo
  reais.
- **Estado vazio, ano inválido, dataset ausente, bairro sem dado, zero
  casos, clima ausente**: todos tratados com mensagem explícita, nunca com
  exceção vazando.

Nada na interface monta SQL, executa código, importa módulo por nome ou
compõe caminho de arquivo a partir de texto do usuário. As fontes do painel
são **três arquivos fixos** declarados em `dashboard/utils/data_loader.py`.

---

## 6. Sistema de arquivos

- Nenhum parâmetro de usuário chega a uma operação de arquivo.
- Os artefatos vêm de caminhos derivados de `__file__`, não de configuração.
- Escrita sempre atômica (`src/utils/io_atomico.py`): temporário no mesmo
  diretório → validação → `os.replace`. Um processo interrompido não deixa
  artefato meio escrito.

---

## 7. Dependências

`pip-audit` (2.10.1) contra os dois arquivos de requisitos:

| Arquivo | Resultado |
|---|---|
| `dashboard/requirements.txt` (**superfície publicada**) | **Nenhuma vulnerabilidade conhecida.** |
| `requirements.txt` (pipeline completo) | **Nenhuma vulnerabilidade conhecida** após a correção abaixo. |

**Vulnerabilidade encontrada e corrigida:** `pytest 8.4.2` —
`PYSEC-2026-1845`, corrigida em 9.0.3. A faixa foi elevada para
`pytest>=9.0.3,<10` e a suíte completa (532 testes) foi reexecutada com
sucesso na versão nova. Severidade prática baixa (dependência apenas de
desenvolvimento, ausente da superfície publicada), corrigida de todo modo.

O `dashboard/requirements.txt` é deliberadamente mínimo — 5 pacotes
(`streamlit`, `plotly`, `statsmodels`, `pandas`, `pyarrow`). Ele **não**
inclui `geopandas`/GDAL, `boto3`, `moto`, `scikit-learn`, `matplotlib` nem
`requests`, e a verificação de deploy **falha** se algum módulo do painel
passar a importar um deles.

Nova dependência introduzida nesta etapa: **nenhuma** em runtime.
`selenium`, `pip-audit` e `bandit` são ferramentas de verificação,
instaladas sob demanda e fora dos dois arquivos de requisitos.

---

## 8. Análise estática (bandit 1.9.4)

Varredura de `src/`, `dashboard/`, `scripts/`, `tools/` — 18.419 linhas.

| Momento | Achados | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| Antes | 6 | 0 | 1 | 5 |
| Depois | **3** | **0** | **0** | 3 |

### Corrigidos

| Achado | Correção |
|---|---|
| `B113` requisição sem timeout garantido (`InmetClient`) | O construtor agora **rejeita** timeout ausente/não positivo, e o timeout por chamada é validado. Uma requisição sem timeout pode travar o pipeline indefinidamente se a fonte aceitar a conexão e nunca responder. |
| `B101` uso de `assert` para invariante de experimento | Convertido em `raise ValueError` explícito — a verificação sobrevive a `python -O`. |
| `B607` processo iniciado por caminho parcial (`git`) | O executável passou a ser resolvido com `shutil.which` e invocado pelo caminho absoluto, com `shell=False`. |

### Remanescentes, investigados e aceitos

| Achado | Avaliação |
|---|---|
| `B105` "possible hardcoded password: 'PASS'" em `src/healthcheck.py` | **Falso positivo.** `PASS` é o rótulo de status do healthcheck. Não corrigido de propósito — renomear uma constante correta para agradar a um verificador pioraria o código. |
| `B404` import de `subprocess` | Informativo. Único uso: `git rev-parse HEAD` para registrar o commit no metadado do modelo. |
| `B603` chamada de subprocesso | Lista de argumentos fixa, sem entrada de usuário, caminho absoluto, `shell=False`, `timeout=15`, `check=False`. Aceito e documentado no código. |

---

## 9. Log

- **Formato**: texto legível por padrão; JSON por linha com
  `RECIFE_ALERTA_LOG_JSON=1`.
- **Conteúdo obrigatório por fonte**: registros obtidos, registros
  rejeitados **por motivo**, data máxima, duração.
- **Redação automática** (`FiltroRedacao`): chaves sensíveis
  (`secret_key`, `access_key`, `password`, `token`, `authorization`,
  `api_key`, …), credencial embutida em URL, padrão de CPF e de CNS. O
  filtro atua sobre a **mensagem já formatada**, portanto cobre o caso real
  de vazamento — o valor sensível vindo de um argumento de formatação, não
  da string literal. Testado.
- **Nada é engolido**: uma etapa que falha registra o erro com *traceback* e
  propaga.

---

## 10. Erro na interface

Nenhum *stack trace* chega ao usuário público. Cada seção de página é
isolada por uma fronteira de erro (`dashboard/components/erros.py`): se ela
falhar, mostra "Não foi possível carregar esta análise. Os demais módulos do
painel continuam disponíveis", registra o detalhe técnico no log do servidor,
e a página continua. O teste de navegador **falha** se essa mensagem
aparecer — ou seja, degradação silenciosa é tratada como defeito, não como
resiliência bem-sucedida.

---

## 11. Ameaças principais e mitigação

| Ameaça | Impacto | Mitigação | Risco residual |
|---|---|---|---|
| Vazamento de dado pessoal do SINAN via painel | Alto | Bronze/Silver nunca publicados; 3 barreiras de verificação; redação no log | **Baixo** — depende de a Gold continuar agregada, o que é verificado a cada exportação |
| Commit acidental de credencial | Alto | `.gitignore` abrangente; auditoria de histórico limpa; sem defaults fracos; verificação no script de deploy | **Baixo** |
| Execução de código via pickle adulterado | Alto | Painel não carrega modelo; `.joblib` não versionado; caminho validado contra lista permitida | **Baixo** |
| Dependência vulnerável | Médio | `pip-audit` nos dois arquivos; superfície publicada com 5 pacotes | **Baixo**, mas requer reexecução periódica |
| Interpretação errada do score como probabilidade | **Médio-alto** | Probabilidade nunca publicada; score é posto relativo; avisos em toda página experimental; tabela de claims | **Médio** — é risco de comunicação, não técnico |
| Dado desatualizado lido como atual | Médio | Faixa de atualização em toda página; portão da projeção; healthcheck | **Baixo** |
| Serviço MinIO exposto | Médio | Portas em `127.0.0.1`; credencial obrigatória | **Baixo** (ambiente de desenvolvimento) |
| Indisponibilidade da fonte durante atualização | Baixo | Retentativa com espera crescente; falha explícita; artefato anterior preservado | **Baixo** |

---

## 12. Limitações desta revisão

- Não houve teste de intrusão, revisão de terceiros nem análise de
  composição de software além do `pip-audit`.
- A varredura de segredos cobre padrões conhecidos; um segredo com formato
  incomum passaria.
- `bandit` é análise estática: não detecta falha de lógica de autorização
  (irrelevante aqui, pois o painel não tem autenticação nem multi-tenancy —
  e **não deve ter**, por decisão de escopo).
- O painel é público por natureza: não há controle de acesso, e nenhum é
  necessário, porque todo o conteúdo é derivado de dado público agregado.
