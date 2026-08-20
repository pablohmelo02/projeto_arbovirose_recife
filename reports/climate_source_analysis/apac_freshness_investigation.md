# Investigação: por que a rede APAC (PCDs) aparenta não ter leituras após 2024-04-09

> Investigação técnica real, feita em 2026-08-19, motivada pelo resultado do
> mapeamento Silver `bairro -> estação climática` (Estratégia A):
> `0/94 bairros associados`, porque as 299 estações APAC candidatas foram
> todas excluídas pelo critério de atividade (`LIMIAR_DIAS_ESTACAO_ATIVA=90`
> em `src/silver/schema_climate_bairro.py`).

## Problema

`filtrar_estacoes_elegiveis()` excluiu 100% das estações APAC como
"inativas" (última leitura há mais de 90 dias). Antes de relaxar esse
critério, era preciso determinar **por que** a rede parece parada: rede
real desatualizada, endpoint errado/legado, bug de parsing, ou semântica
incorreta do campo de data.

## Hipótese inicial

Qualquer uma das causas A-E listadas na seção de classificação abaixo era
plausível a priori — em particular, "endpoint legado" (B) parecia razoável,
já que o cliente usa uma URL sob o diretório `PainelMapaGoogle`, nome que
sugere um painel antigo (baseado em Google Maps), enquanto o site atual da
APAC já usa OpenLayers.

## Metodologia

1. Preservar o estado já ingerido (Bronze/Silver no `moto.server`), sem
   reingestão.
2. Analisar os timestamps brutos do instantâneo APAC já armazenado no
   Bronze (`bronze/recife/clima/apac/pcd/ingestion=20260819T234911Z/pcds.json`,
   299 estações).
3. Reler o código de parsing (`src/silver/climate.py::transformar_diario_apac`
   e `_parsear_data_apac`) para confirmar campo/formato/timezone usados.
4. Consultar a fonte **ao vivo**, agora, e comparar byte a byte com o que já
   está no Bronze.
5. Investigar o site público atual da APAC (`www.apac.pe.gov.br/monitoramento`)
   e o JavaScript do painel de mapa vigente, para descobrir se ele ainda usa
   o mesmo backend/endpoint que o nosso cliente (`apac_client.py`).
6. Buscar evidência pública (notícias) de pane/mudança na rede.

## Dados Bronze analisados

299 pontos (estações PCD), campo usado: `"Data último dado"` (formato
`DD-MM-AAAA`, ex.: `"14-03-2018"`), mais `"Hora último dado"` e `"24 Horas"`
(acumulado de chuva).

- Parsing: **299/299 sucesso**, 0 falhas, 0 nulos. O formato `DD-MM-AAAA` é
  inequívoco nas amostras (ex.: dia `14` não pode ser mês) — não há indício
  de troca dia/mês.
- Timestamp mínimo bruto: `2015-01-23` (estação 1280, Jaqueira).
- Timestamp máximo bruto: `2024-04-09` (múltiplas estações).
- 98 timestamps distintos no total.
- Distribuição por ano: `{2015:1, 2016:2, 2017:1, 2018:4, 2019:5, 2020:4,
  2021:9, 2022:24, 2023:24, 2024:225}`.
- **Achado central**: **157 das 299 estações (52,5%) têm o mesmíssimo dia
  `2024-04-09` como última leitura**, com **horas distintas e plausíveis**
  nesse dia (`08:20`, `08:30`, `08:40`, `08:50`, `09:00`, `09:10`, `04:50`,
  `05:00`, `06:30` — 9 horários diferentes, não um valor fixo/artificial).
  Mais 18 estações têm última leitura em `2024-04-08`. Ou seja, ~58% da rede
  parou de transmitir na mesma janela de ~2 dias.
- O restante (~42%) morreu de forma dispersa ao longo de 2015-2024 — isso é
  consistente com degradação individual gradual, já conhecida do projeto.

Isso não é compatível com falha individual e independente de cada PCD
(o que produziria uma cauda suave de datas de morte); é compatível com um
evento sistêmico que atingiu a maior parte da rede de uma vez, em cima de
uma degradação gradual pré-existente.

## Consulta online atual (ao vivo, nesta sessão)

Reconsultado `https://barramento.apac.pe.gov.br/.../ServicoMonitoramentoPCDs.php`
diretamente (não via cache/Bronze), ~40 minutos depois da ingestão:

- 299 pontos retornados (mesma contagem).
- Mínimo e máximo idênticos: `2015-01-23` / `2024-04-09`.
- Mesma distribuição de datas (`2024-04-09`: 157 ocorrências).
- Estação de teste (`id=1190`, Caruaru): **valor idêntico, byte a byte**
  (`14-03-2018`, `08:10`, `24h=0.62`) nas duas consultas.

**Conclusão direta**: o endpoint está servindo um conjunto de dados
estático/congelado — não há telemetria nova chegando a essa API, pelo menos
não desde abril de 2024.

## Endpoints investigados

Buscando se o site atual da APAC usa outro backend:

- `https://www.apac.pe.gov.br/monitoramento` (painel atual) carrega o
  módulo `modules/mod_painel_mapa/` — Angular + **OpenLayers**
  (`ol.js`), não mais o antigo `PainelMapaGoogle` (baseado em Google Maps).
  Isso levantou a hipótese de endpoint legado (categoria B).
- Porém, `modules/mod_painel_mapa/assets/js/services.js` (o serviço Angular
  que o painel *atual* usa para buscar dados) chama
  `Service.servicoMapa()` → `GET
  https://barramento.apac.pe.gov.br/.../PainelMapaGoogle/ServicoMapa.php?mapeamento=1/`
  — ou seja, **o backend `PainelMapaGoogle` (mesmo diretório do nosso
  cliente) continua sendo o backend oficial**, só o frontend visual mudou.
- Consultei `ServicoMapa.php?mapeamento=1/` (o registro de mapeamentos do
  painel atual) e ele lista explicitamente:

  ```json
  "3": {
    "titulo": "ACUMULADO DE CHUVAS(mm) EM 24 HORAS",
    "servico": "https://barramento.apac.pe.gov.br:443/BarramentoServicosApac/Servicos/Site/PainelMapaGoogle/ServicoMonitoramentoPCDs.php",
    "nome": "Coleta de Dados (PCDs)"
  }
  ```

  **Esse é exatamente o endpoint usado por `apac_client.py`.** O painel
  público vigente da APAC, hoje, referencia esse mesmo script como fonte
  oficial de "Coleta de Dados (PCDs)".

Isso **descarta a hipótese de endpoint legado/errado (categoria B)**: não
existe um endpoint mais novo sendo usado pelo site que estejamos deixando
de consultar — é o mesmo.

Também listados nesse registro (não investigados a fundo, fora do escopo
desta rodada): RADAR (`ServicoMonitoramentoRADAR.php`), Modelo WRF, Modelo
ETA, Barragens, NDVI — nenhum é a fonte de precipitação por PCD.

## Evidência pública

Busca por notícias sobre pane/mudança na rede de telemetria da APAC não
retornou nenhum relato específico de uma falha em abril de 2024. Encontrada
uma notícia (fonte secundária, não oficial) sobre a APAC ter lançado "uma
nova ferramenta de monitoramento de chuvas" e um "Banco Estadual de
Precipitação Preenchida" — mas não foi possível confirmar data exata,
relação causal com o `ServicoMonitoramentoPCDs.php`, nem acessar a URL
`/chuvas` citada (retornou HTTP 404 no site atual). **Marcado como hipótese
não confirmada, não como fato.**

## Validação do significado do campo

`"Data último dado"` (chave do JSON, junto com `"Hora último dado"` e
valores em janelas de `15 Minutos` até `24 Horas`) é semanticamente
inequívoco: é a data/hora da última transmissão de dado recebida daquela
PCD, não uma data de cadastro ou manutenção — coerente com o próprio nome
do campo e com a estrutura de janelas de acumulado (`15min`...`24h`) que só
fazem sentido como leituras de telemetria, não como metadado estático. Não
há campo de "status" ou "situação" separado na resposta.

## Hipóteses de erro de parsing testadas e descartadas

- Inversão dia/mês: descartada — formato `DD-MM-AAAA` é usado de forma
  consistente e inequívoca em toda a amostra (dia > 12 aparece com
  frequência).
- Timezone: o campo não traz timezone explícito; não há evidência de que
  isso explique uma defasagem de **anos**.
- Timestamp Unix mal tratado, string parcialmente parseada, fallback
  silencioso, data default: nenhuma falha de parsing ocorreu (299/299
  sucesso), e o valor batido é idêntico entre consulta ao vivo e Bronze —
  não é um artefato do nosso parsing.
- Cache do lado do cliente: descartado — a consulta ao vivo foi feita
  diretamente ao endpoint, sem cache local, e reproduziu os mesmos valores
  que o Bronze já tinha.

## Diagnóstico isolado: cobertura ignorando SOMENTE a idade da estação

**Não persistido em Silver — puramente exploratório, fora do pipeline
oficial.** Rodei `calcular_estacao_representativa_por_bairro` diretamente
sobre as 299 estações APAC (todas com coordenada válida), sem aplicar
`filtrar_estacoes_elegiveis`:

- **Cobertura: 94/94 bairros (100%)**, usando **27 estações distintas**.
- Distância: média 1,23 km | mediana 1,106 km | p90 2,273 km | p95 2,519 km
  | máxima 3,636 km (bairro PAU FERRO) | mínima 0,109 km.
- 20/94 bairros têm estação fisicamente dentro do próprio polígono.
- Idade das estações efetivamente escolhidas para os 94 bairros (última
  leitura real): 2 em 2018, 13 em 2021, 6 em 2023, **73 em 2024** — das
  quais 25 caem exatamente no dia do "evento" (`2024-04-09`).

**Leitura**: a cobertura espacial da rede PCD dentro do Recife é excelente
(distâncias sub-4km, mediana ~1km) — a Estratégia A funcionaria muito bem
*se* a rede estivesse ativa. O problema não é de desenho geométrico, é
100% de atualidade temporal dos dados.

## Classificação final

**A — Rede APAC realmente desatualizada**, com uma nuance adicional
verificável: não é uma desatualização puramente gradual/individual — há
evidência de um evento concentrado (~58% da rede parou de transmitir em
2024-04-08/09) somado a uma cauda de mortes individuais mais antigas
(2015-2024). A causa raiz exata do evento de 2024-04-09 (falha de
infraestrutura de coleta, migração de sistema do lado da APAC, corte de
comunicação, etc.) **não foi confirmada** — é hipótese em aberto, não fato.

Descartadas com evidência direta:
- **B (endpoint legado)** — descartada: o próprio painel público vigente da
  APAC referencia o mesmo endpoint como fonte oficial de PCDs.
- **C (bug no nosso pipeline)** — descartada: parsing 100% correto, consulta
  ao vivo reproduz exatamente o que está no Bronze.
- **D (semântica incorreta do timestamp)** — descartada: o campo
  significa inequivocamente "última leitura transmitida".

## Recomendação

Não relaxar `LIMIAR_DIAS_ESTACAO_ATIVA` — o filtro está correto e é a rede
que está com problema, não o critério. Como a rede é geometricamente
excelente mas temporalmente morta:

1. **Curto prazo**: manter a Estratégia A como está (0/94 é o resultado
   correto e honesto dado o estado real da fonte). Não fabricar cobertura.
2. **Investigar diretamente com a APAC** (fora do escopo técnico deste
   pipeline) se a rede de PCDs tem previsão de voltar a operar, ou se a
   "nova ferramenta de monitoramento" mencionada na busca por notícias
   (não confirmada tecnicamente aqui) é um substituto oficial — isso exige
   contato institucional ou mais investigação de endpoints do site,
   não implementação de código agora.
3. **Não implementar uma nova fonte climática ainda** — nenhuma alternativa
   (CEMADEN, ANA/Hidroweb, outra rede) foi avaliada tecnicamente nesta
   rodada; isso ficaria para uma investigação futura explicitamente
   autorizada.
4. Se, no futuro, uma nova consulta à APAC mostrar timestamps recentes
   novamente (rede voltou), a Estratégia A já está pronta para funcionar
   sem nenhuma mudança de código — o pipeline é exatamente o que deveria
   rodar quando a fonte se recuperar.
