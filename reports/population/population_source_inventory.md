# Inventário de fontes de população por bairro do Recife

Investigação sistemática (não limitada a Censo 2010/2022) das fontes
oficiais/institucionais de população por bairro do Recife, 2010-2025.
Metodologia: pesquisa web + verificação direta (download real, filtragem,
soma e comparação contra totais municipais oficiais) — nenhum valor deste
relatório foi aceito só por aparecer numa busca; todos os marcados como
`alta` confiança foram baixados e conferidos nesta sessão.

## Tabela de checkpoints

| ano | fonte | tipo | cobertura_bairros | populacao_total | observado_ou_estimado | automatizavel | qualidade |
|---|---|---|---|---|---|---|---|
| 2010 | IBGE Censo 2010 (via CIEVS/Sesau Recife) | censo observado | 94/94 | 1.537.704 | observado | não (PDF, extraído nesta sessão) | alta — soma bate exatamente com o total oficial (SIDRA tabela 202) |
| 2011-2016 | CIEVS/Sesau Recife, "População 2010 a 2017" (dez/2017) | estimativa institucional (partilha proporcional fixa do Censo 2010 sobre projeções IBGE) | 94/94 | ver série completa abaixo | estimado | não (mesmo PDF) | média-alta — método simples, mas institucional e documentado; validado por reconciliação (ver seção "Reconciliação") |
| 2017 | idem CIEVS | estimativa institucional | 94/94 | 1.633.697 (município) | estimado | não | média-alta — usado também como checkpoint de validação cruzada (seção "Validação") |
| 2011-2021 (municipal) | IBGE Estimativas de População (SIDRA, tabela 6579) | estimativa oficial | município (não bairro) | ver série completa | estimado | sim (API) | alta |
| 2018-2021 (por bairro) | reconstrução própria deste projeto (CAGR 2017→2022 por bairro + reconciliação ao total municipal oficial) | estimativa intercensitária derivada | 94/94 | reconciliada ano a ano | estimado (não publicado por nenhuma fonte) | sim (código deste projeto) | média — sem checkpoint oficial nesse intervalo; MAPE estimado por validação cruzada ≈ 10,8% (ver seção "Validação") |
| 2022 | IBGE Censo 2022, "Agregados por Bairro" | censo observado | 94/94 | 1.488.920 | observado | sim (FTP público, ZIP ~700 KB) | alta — soma bate exatamente com o total oficial (SIDRA tabela 9514) |
| 2023 | sem publicação oficial (ano de transição pós-Censo) | — | — | interpolação geométrica 2022↔2024 (1.537.520) | estimado (município apenas) | sim (interpolação documentada) | baixa-média — não é dado publicado, é uma ponte para um único ano |
| 2024-2025 (municipal) | IBGE Estimativas de População (SIDRA, tabela 6579), pós-Censo | estimativa oficial | município (não bairro) | 1.587.707 / 1.588.376 | estimado | sim (API) | alta |
| 2023-2025 (por bairro) | projeção pós-censo deste projeto (participação do Censo 2022 escalada pelo total municipal oficial do ano) | projeção | 94/94 | reconciliada ano a ano | projetado | sim (código deste projeto) | média — nenhum checkpoint futuro existe para validar |

Fontes investigadas e **descartadas/não usadas como checkpoint primário**,
por completude:

- **CONDEPE/FIDEM (Base de Dados do Estado)**: publica apenas estimativas
  municipais (repasse do IBGE), sem granularidade de bairro — redundante
  com a série SIDRA já usada.
- **ESIG/Prefeitura do Recife, "Perfil dos Bairros"**: existe e cobre os 94
  bairros com dados do Censo 2010, mas como 94 páginas HTML individuais
  (sem CSV/tabela consolidada) — mais custoso de extrair de forma
  auditável que o documento CIEVS, que já publica a mesma origem (Censo
  2010) em formato tabular único. Não usado como fonte primária; pode
  servir de validação cruzada independente em trabalho futuro.
- **Anuário Estatístico de Pernambuco (CONDEPE/FIDEM)**: cobertura por
  bairro não confirmada como compatível com a divisão atual de 94 bairros.
- Agregadores secundários (Wikipédia, imprensa): usados apenas como pista
  inicial, nunca como fonte citável — não aparecem na tabela acima.

## Como cada arquivo foi obtido (proveniência completa)

Todos os brutos estão versionados em `data/bronze/populacao/`, cada um com
um manifest/campo de proveniência interno (URL, data de extração, método,
verificação de integridade):

- `cievs_populacao_bairro_2010_2017.json` — extraído do PDF
  "População do Recife: Censo Demográfico 2010 e Projeções 2010 a 2017"
  (Secretaria de Saúde do Recife/CIEVS, dez/2017,
  <https://cievsrecife.files.wordpress.com/2017/11/populac3a7c3a3o-2010-a-2017-uvepi1.pdf>).
  A Tabela 25 (páginas 30-32 do PDF) não é reconhecida como tabela
  estruturada por extratores automáticos (`pdfplumber.extract_tables`
  falha nela) — foi extraída por regex sobre o texto bruto
  (`pdfplumber.extract_text`), numa sessão manual única, com duas
  verificações de integridade: (1) soma das 94 linhas de bairro +
  "Bairro Ignorado" bate com a linha "Total" publicada em todos os 8 anos
  (diferença ≤ 4 pessoas em 1,5-1,6 milhão — arredondamento da própria
  fonte, não erro de transcrição); (2) soma dos 8 subtotais de Distrito
  Sanitário + "Bairro Ignorado" bate **exatamente** (diferença 0) com o
  Total em todos os anos.
- `censo2022_ibge_bairro_recife.csv` — filtrado de
  `Agregados_por_bairros_basico_BR_20260520.zip`, produto oficial do IBGE
  Censo 2022 ("Agregados por Setores Censitários — Agregados por Bairro"),
  baixado de
  `ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/`.
  Filtro `CD_MUN=2611606` (Recife) devolve exatamente 94 linhas; soma de
  `v0001` (população) = 1.488.920, idêntica ao total municipal oficial
  (SIDRA tabela 9514).
- `estimativas_municipais_ibge.json` — IBGE/SIDRA, tabelas 202 (Censo
  2010), 6579 (estimativas anuais 2011-2021 e 2024-2025) e 9514 (Censo
  2022), via `apisidra.ibge.gov.br`.

`src/ingestion/population_ingestion.py` automatiza o re-download das duas
fontes automatizáveis (Censo 2022 e SIDRA); o documento CIEVS não é
reparseado automaticamente (ver docstring do módulo para o motivo).

## Cobertura de bairros: 94/94 em ambos os checkpoints reais

Nenhuma das fontes de população publica o `codigo_bairro` interno de
`silver_bairro_geo`. O join foi feito por nome normalizado (maiúsculo, sem
acento, sem pontuação) mais exatamente duas correções pontuais
documentadas — nunca fuzzy matching:

| fonte | grafia na fonte | grafia oficial (`silver_bairro_geo`) |
|---|---|---|
| CIEVS 2010-2017 | "Alto Sta Teresinha" | "ALTO SANTA TEREZINHA" |
| IBGE Censo 2022 | "Sítio dos Pintos - São Brás" | "SITIO DOS PINTOS" |

Depois dessas duas correções, **94/94 bairros casam em ambas as fontes**,
sem nenhuma discrepância residual (`discrepancias_join_cievs` e
`discrepancias_join_censo2022`, calculadas a cada execução da Silver, estão
vazias — ver `data/silver/populacao_bairro_ano/_manifest.json`).

## Reconciliação contra o total municipal oficial

Para cada ano, a soma dos 94 bairros foi comparada ao total municipal
oficial do IBGE (ver `reconciliacao_por_ano` no manifest da Silver):

- **2010-2017**: a soma dos bairros publicados pela CIEVS fica
  consistentemente **~0,65% abaixo** do total municipal oficial — a
  própria fonte tem uma categoria separada "Bairro Ignorado" (pessoas não
  atribuídas a nenhum bairro específico, ~10 mil pessoas) que não está
  distribuída entre os 94 bairros. Isso não foi "corrigido" — os valores da
  CIEVS são usados como publicados, sem reescalar, porque não há como saber
  a que bairros essas ~10 mil pessoas pertenceriam.
- **2018-2021** (reconstrução própria): reconciliado ativamente — diferença
  final entre 0 e 3 pessoas em ~1,6 milhão (arredondamento de `int`).
- **2022**: diferença 0 (Censo observado, sem necessidade de reconciliação).
- **2023-2025**: reconciliado ativamente — diferença entre 0 e 7 pessoas.

## Validação cruzada (reconstrução sem o checkpoint de 2017)

Para avaliar se o método de reconstrução (CAGR por bairro + reconciliação
municipal) seria confiável nos anos 2018-2021 — onde não existe nenhum
checkpoint real para comparar — o mesmo método foi aplicado a 2010→2022
**sem usar o checkpoint de 2017**, e o resultado em 2017 foi comparado
contra o valor real publicado pela CIEVS:

- **MAE**: ≈ 886 pessoas por bairro
- **MAPE**: ≈ 10,8%
- **Bias médio**: +112 pessoas (leve superestimação)
- **Pior caso**: bairro 515 (Mangabeira), erro percentual ≈ 211% — um
  bairro muito pequeno (955 habitantes em 2010) com trajetória de
  crescimento irregular que uma extrapolação CAGR simples não captura.

**Leitura honesta**: um erro típico de ~11% é real e não deve ser escondido
— os anos 2018-2021 (reconstruídos sem checkpoint) devem ser tratados como
`ESTIMATIVA_INTERCENSITARIA` com essa margem de incerteza implícita, nunca
como equivalentes a um censo. Bairros muito pequenos ou com trajetória
atípica (ver seção seguinte) são os que mais sofrem esse erro.

## Áreas atípicas (não suavizadas)

`identificar_areas_atipicas` (em `src/population/reconstruction.py`) marca
bairros pequenos (< 1.000 habitantes em 2022), com crescimento 2010→2022
acima de 50% ou com redução populacional — 72 dos 94 bairros caem em pelo
menos uma dessas categorias (a lista completa está em
`data/silver/populacao_bairro_ano/_manifest.json` → `areas_atipicas`).
Casos notáveis:

- **Redução populacional mais acentuada**: PEIXINHOS (-41,7%), APIPUCOS
  (-24,5%), CAJUEIRO (-23,1%), COELHOS (-22,4%) — consistente com
  esvaziamento de bairros centrais/industriais do Recife entre os dois
  Censos, um fenômeno urbano real, não um artefato de dado.
- Nenhum valor foi suavizado ou descartado por parecer estranho — todos
  entram na série publicada como estão.

## Método de projeção pós-Censo escolhido (2023-2025)

Três métodos foram comparados (participação de 2022 fixa; extrapolação da
tendência longa 2010-2022; extrapolação da tendência recente 2017-2022),
medindo a dispersão da taxa de crescimento implícita entre bairros como
proxy de estabilidade — critério declarado antes de olhar o resultado.
**Participação de 2022 fixa** foi escolhido (dispersão ≈ 0, por construção:
é matematicamente idêntico a distribuir o crescimento municipal oficial
proporcionalmente à participação 2022 — os métodos "A" e "D" do pedido
original são o mesmo método, ver docstring de
`comparar_metodos_pos_censo`). Isso é o método mais conservador possível: não
extrapola nenhuma tendência específica de bairro, só aplica a trajetória
municipal já oficial e observada. Ver
`reports/population/population_incidence_integration.md` para a discussão
completa e os números dos métodos alternativos.

## Limitações declaradas

1. Nenhum checkpoint oficial por bairro existe entre 2017 e 2022, nem depois
   de 2022 — os anos correspondentes são reconstrução/projeção deste
   projeto, marcados como tal (`tipo_valor`), nunca apresentados como dado
   observado.
2. A reconstrução 2018-2021 tem MAPE ≈ 11% medido por validação cruzada —
   não é precisão de censo.
3. O documento CIEVS usa "Alto Sta Teresinha"/"Pau-Ferro" e outras grafias
   ligeiramente diferentes da grafia oficial atual — resolvido por
   normalização + 2 correções documentadas, não fuzzy matching.
4. Não foi possível confirmar cobertura por bairro em CONDEPE/FIDEM nem no
   Anuário Estatístico de Pernambuco compatível com a divisão de 94
   bairros — não usados.
