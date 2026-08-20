# Fontes climáticas alternativas: CEMADEN e ANA/Hidroweb (comparativo com INMET/APAC)

> Investigação técnica real, feita em 2026-08-19, motivada pelo resultado da
> investigação de atualidade da APAC
> (`reports/climate_source_analysis/apac_freshness_investigation.md`):
> `0/94 bairros` cobertos porque a rede PCD da APAC está com dados
> congelados desde 2024-04-09. Objetivo: descobrir a melhor fonte
> alternativa/complementar de precipitação atual para Recife — **sem
> implementar nada ainda**, só reunir evidência para decisão.

## Metodologia

Duas investigações paralelas e independentes (uma por CEMADEN, outra por
ANA/Hidroweb), cada uma fazendo requisições HTTP reais contra os endpoints
candidatos (não confiando em documentação de terceiros), seguidas de:

1. Contagem separada de estações **cadastradas** → **com coordenada
   válida** → **com dado real acessado** → **ativas** (buckets de idade da
   última leitura) → **ativas dentro do Recife**.
2. Spatial join geométrico real contra `silver_bairro_geo` (94 bairros,
   `src/silver/climate_spatial.py::estacoes_dentro_do_recife`) — nunca por
   campo textual de município.
3. Diagnóstico exploratório da Estratégia A (`src/silver/climate_bairro.py`,
   usado só em memória, **nada persistido em Silver**, nenhum arquivo do
   pipeline alterado): cobertura simulada dos 94 bairros, nº de estações
   distintas, distância mediana/p90/p95/máxima.

Nenhum cliente definitivo (`cemaden_client.py`, `ana_client.py`) foi criado.
Nenhum schema oficial foi alterado. Nenhuma integração foi conectada ao
pipeline. A suíte de testes permanece intacta (verificado antes e depois:
156/156).

## CEMADEN — resultados

**Endpoints testados**:

| Endpoint | Status | Formato | Observação |
|---|---|---|---|
| `sjc.salvar.cemaden.gov.br/...` (legado, referenciado em JS antigo) | Falha de DNS | — | Morto |
| `mapainterativo.cemaden.gov.br` | 200 | HTML | Painel público ativo |
| `gsc.cemaden.gov.br/geoserver/cemaden_dev/wfs` (GetCapabilities) | 200 | XML | GeoServer real, 395 feature types |
| `.../wfs?...typeName=cemaden_dev:view_pcds_pluviometrica_cemaden&outputFormat=application/json` | 200 | GeoJSON | **4449 estações Brasil, 437 em PE** — cadastro + status de atividade (`tempo_inatividade`) |
| `.../wfs?...typeName=cemaden_dev:precipitacao_bacia_24` | 200 | GeoJSON | Camada de precipitação **agregada por bacia hidrográfica** (não por estação) — testada agora: `dt_acc_24` mais recente encontrada = **2017-06-05**, ou seja, também congelada/abandonada, e de qualquer forma inadequada para granularidade de bairro |
| `mapainterativo.cemaden.gov.br/download/download_form.php` + `getperiodos.php` + `getcidades.php` | 200 | HTML/JSON | Download histórico mensal, anos **2011-2026** disponíveis, Recife = município `5550` |
| `.../download/download_file.php` (download real) | Bloqueado | — | **CAPTCHA de imagem (Securimage)** antes de qualquer download |
| `.../graficos/interativo/grafico_CEMADEN.php?idpcd=` (série por estação, legado) | 404 | — | Endpoint não existe mais no caminho atual |

**Estações — cadastro vs. dado vs. ativo** (obrigatório separar):

- Cadastradas (tipo pluviométrica, Brasil): 4449 · PE: **437**.
- Com coordenada válida: 437/437 (100%).
- Com **valor de precipitação real acessado**: **0** (o único layer de
  valores encontrado, `precipitacao_bacia_24`, é agregado por bacia, está
  congelado desde 2017, e não serve para granularidade de bairro).
- Com metadado de atividade (`tempo_inatividade`, dias desde a última
  leitura, campo nativo do próprio dataset CEMADEN): **sim, para as 437**.
- Ativas dentro do Recife (spatial join real): **19 estações** fisicamente
  dentro do polígono do município — 18 rotuladas `cidade=RECIFE` no
  cadastro + 1 rotulada `PAULISTA` mas geometricamente dentro do bairro
  Guabiraba (confirma, de novo, que o campo textual de município não é
  confiável).
- Dessas 19, aplicando o mesmo limiar do projeto (`tempo_inatividade<=90
  dias`): **15/19 elegíveis**. Distribuição bruta das 19: 3 com 0 dias, 1
  com 2 dias, 4 entre 19-25 dias, 7 entre 63-71 dias, 3 entre 118-244 dias,
  1 com 1851 dias (morta).
- Buckets de atividade, todas as 437 de PE: `≤1d: 69 | ≤7d: 40 | ≤30d: 125
  | ≤90d: 76 | >90d: 127`.
- Nomes/coordenadas das estações em Recife **coincidem com os mesmos nomes
  já documentados na rede PCD da APAC** (Ibura, Dois Unidos, Guabiraba,
  Alto do Mandu etc.) — forte indício de que CEMADEN monitora o **mesmo
  hardware físico** que a APAC, mas com um sinal de atividade mais recente
  e aparentemente confiável do que o endpoint direto da APAC.

**Histórico**: existe (2011-2026, download mensal por município), mas
bloqueado por CAPTCHA de imagem — **não automatizável de forma simples**;
exigiria intervenção manual recorrente ou infraestrutura de
CAPTCHA-solving, que não deve ser implementada sem autorização explícita.

**Variáveis e frequência**: o layer de descoberta
(`view_pcds_pluviometrica_cemaden`) só expõe `codestacao, nome, latitude,
longitude, cidade, uf, tipo, tempo_inatividade` — cadastro + status, **não
o valor de chuva em si**. O único layer de valores encontrado é agregado
por bacia e está congelado desde 2017. **Não foi encontrado, nesta rodada,
um endpoint de observações de precipitação por estação em tempo real** (o
antigo está 404). Outros layers do mesmo GeoServer
(`view_pcds_agrometeorologica_cemaden`, `view_pcds_hidrologicas_cemaden`)
não foram investigados — ficam como próximo passo técnico, não como
suposição.

**Qualidade**: cadastro limpo (0 duplicidade de `codestacao`, 0 coordenada
inválida, 0 nulo).

**Diagnóstico da Estratégia A (simulado, não persistido)**:

- Todas as 437 candidatas PE (ignorando atividade): **94/94 bairros**, 23
  estações distintas, distância mediana **1,31 km**, p90 2,64 km, p95 2,82
  km, máxima 3,64 km.
- Só as 310 elegíveis (`tempo_inatividade<=90`, mesmo limiar do projeto):
  **94/94 bairros**, 18 estações distintas, distância mediana **1,41 km**,
  p90 2,68 km, p95 2,91 km, máxima 5,37 km (o bairro Guabiraba passa a usar
  uma estação mais distante quando a estação local fica inelegível).

**Estabilidade**: registro de estações + atividade — **Boa** (GET puro,
sem auth, GeoJSON padrão OGC WFS, estável em chamadas repetidas). Histórico
mensal — **Frágil** (CAPTCHA). Série de observações em tempo real por
estação — **Inviável** com o que foi encontrado (endpoint antigo morto,
substituto não identificado).

## ANA / Hidroweb — resultados

**Endpoints testados**:

| Endpoint | Método | Status | Formato | Observação |
|---|---|---|---|---|
| `ana.gov.br/hidrowebservico/*` | GET | 200, mas redireciona para página institucional genérica | HTML | Domínio antigo migrado, não é mais serviço de API |
| `telemetriaws1.ana.gov.br/ServiceANA.asmx` (`HidroInventario`, `HidroSerieHistorica`, http/https) | GET | **Timeout em 4 tentativas** (schemes/métodos diferentes) | — | SOAP legado, amplamente citado pela comunidade (ex. pacote `hydrobr`), **hoje inacessível** |
| `www.snirh.gov.br/hidroweb/rest/api/{documento/convencionais, listaEstacoes, documento, usuario/autentica}` | GET/POST | **401 em todas as variações** testadas (querystring, Basic auth, header custom) | JSON | `"Token de Autenticação da API Inexistente ou mal Formatado"` — **exige cadastro de usuário + login**, nenhum modo anônimo |
| `www.snirh.gov.br/hidroweb/` (SPA) | GET | 200 | HTML/Angular | Só a casca do app; dado real vem da API acima |
| `dadosabertos.ana.gov.br` (ArcGIS Hub + `dcat-us` + `v3/datasets`) | GET | 200 | JSON | Público, sem auth — catálogo de datasets de terceiros, pouco relevante |
| `www.snirh.gov.br/arcgis/rest/services` (raiz + pastas) | GET | 200 | JSON (Esri) | **Público, sem auth** — servidor ArcGIS oficial real |
| `SGH/REDE_HIDROMETEOROLOGICA_NACIONAL/MapServer/{0,8,9}` | GET (`/query`) | 200 | JSON | **Cadastro nacional funciona bem**, com filtro por estado |
| `Telemetria_BH/ESTACOES_TELEMETRICAS` e `MEDICOES_TELEMETRICAS/MapServer` | GET | 200 | JSON | **Service definition vazia** (`layers: [], tables: []`) — órfã, sem dado real |

**Estações — cadastro vs. dado vs. ativo**:

- Cadastradas em PE: **43 pluviométricas + 42 telemétricas = 85** (sem
  sobreposição de código). 0 climatológicas em PE (sem temperatura/umidade
  possível por esta fonte, em Recife).
- Com coordenada válida: 85/85 (100%).
- Com **valor de precipitação real acessado**: **0** — SOAP morto, REST
  exige login, serviço de medições telemétricas vazio/quebrado.
- "Ativas" por leitura real: **não determinável** com os endpoints
  públicos testados. O campo `ULTIMAATUALIZACAO` do cadastro (2014-11-17 a
  2015-04-01 para as pluviométricas de PE) é **metadado de edição do
  registro cadastral**, não data de leitura de campo — não deve ser
  confundido com atividade real (mesmo erro que este projeto já evitou na
  investigação da APAC).
- Dentro do polígono do Recife (spatial join real): **1 estação** —
  código `834017`, "RECIFE / AFOGADOS", bairro Afogados (`codigo_bairro
  =779`).

**Histórico**: reputação pública de ser o mais longo do Brasil (décadas) —
**não confirmado tecnicamente**, nenhuma série foi de fato baixada (SOAP
morto, REST bloqueado por login). Requer criação de conta/login no portal
Hidroweb para obter token — não tentado (fora de escopo desta rodada
exploratória).

**Variáveis**: pluviométrica convencional = só precipitação, diária por
convenção pública (não confirmado empiricamente). Sem estação
climatológica em PE → sem temperatura/umidade nesta fonte para Recife.

**Diagnóstico da Estratégia A (simulado, não persistido, só cadastro —
sem nenhuma garantia de dado real por trás)**: **94/94 bairros
"cobertos"**, mas com só **2 estações distintas** (`834017` usada em 89
bairros, `835048` em 5) — distância mediana **5,45 km**, p90 8,24 km, p95
9,22 km, máxima 11,19 km (bairro Passarinho). Densidade geométrica muito
inferior à APAC/CEMADEN, e isso é só cadastro — sem confirmação de que
haja dado real por trás.

**Estabilidade**: **Inviável** no estado atual para uso automatizado sem
login — único caminho de dado real é a API REST nova, que exige conta de
usuário registrado (não é um ajuste técnico pequeno). SOAP legado morto.
Telemetria com service definition quebrada. Só o cadastro ArcGIS é robusto
e público, mas cadastro não é dado climático.

## Comparação final

| Critério | INMET | APAC | CEMADEN | ANA |
|---|---|---|---|---|
| Histórico | Sim — ZIP anual funcional, horário, Brasil inteiro, desde a fundação de cada estação | Não (só instantâneo acumulado desde que o projeto começou a rodar) | Existe (2011-2026, mensal), mas **CAPTCHA-gated** | Reputado o mais longo do Brasil — **não confirmado tecnicamente** |
| Tempo real/atual | Instável (API `apitempo` 500/502) | Estruturalmente sim, mas **congelado desde 2024-04-09** | Registro de **atividade real e atualizada** (`tempo_inatividade`); **valor de chuva não confirmado** neste endpoint | Não confirmado — nenhum dado real obtido |
| Frequência | Horária | Janelas 15min-24h (dado congelado) | Não confirmada (falta endpoint de observações) | Diária por convenção — não confirmado |
| Precipitação | Sim | Sim (congelada) | Não confirmado neste endpoint | Não confirmado (nenhum dado obtido) |
| Temperatura | Sim | Não (rede só pluviômetros) | Não confirmado | Não (0 estações climatológicas em PE) |
| Umidade | Sim | Não | Não confirmado | Não (0 estações climatológicas em PE) |
| Estações PE | 12 (ativas na ingestão real desta sessão) | 299 | 437 | 43 pluviométricas + 42 telemétricas = 85 |
| Estações Recife (spatial join real) | 0 | 22 (`reports/climate_spatial/summary.json`, baseline anterior; a Estratégia A usou 27 como "mais próxima" para os 94 bairros, número diferente por natureza — nem toda estação mais próxima de um bairro está fisicamente dentro dele) | 19 | 1 |
| Estações ativas Recife (≤90 dias) | 0 | 0 (congelado) | **15/19** | não confirmado (nenhum dado de leitura real obtido) |
| Cobertura dos 94 bairros | 0/94 | 0/94 oficial · 94/94 em diagnóstico ignorando idade | **94/94** (mesmo só com as 310 elegíveis ≤90d) | 94/94 só por proximidade de cadastro (2 estações, sem dado confirmado) |
| Distância mediana | N/A | 1,1 km (diagnóstico) | 1,41 km (só elegíveis) / 1,31 km (todas) | 5,45 km |
| Distância máxima | N/A | 3,64 km | 5,37 km (só elegíveis) / 3,64 km (todas) | 11,19 km |
| API/download automatizável | Sim (ZIP, sem auth) | Sim (JSON, sem auth) — dado congelado | Registro: sim (WFS, sem auth) · Histórico: não (CAPTCHA) · Observações: endpoint não encontrado | Não (REST exige login; SOAP morto; telemetria quebrada) |
| Estabilidade | Boa (histórico) / Frágil (tempo real) | Boa (tecnicamente) mas dado morto | Boa (registro) / Frágil (histórico) / Inviável (observações, não encontrado) | Inviável (sem login) |
| Principais problemas | Zero estação ativa em Recife | Dados congelados desde 2024-04-09 | Falta confirmar endpoint de **valores** de precipitação; histórico com CAPTCHA | Autenticação obrigatória; telemetria quebrada; baixíssima densidade em Recife |

## Opções arquiteturais avaliadas (não implementadas)

**Opção 1 — INMET (histórico) + CEMADEN (alta resolução atual)**: a mais
promissora pelas evidências coletadas — mesma densidade espacial excelente
que a APAC (porque é literalmente a mesma rede física de PCDs), com sinal
de atividade real e recente, sem autenticação para descoberta. **Risco
conhecido e não resolvido**: ainda não identificamos o endpoint que entrega
o *valor* de precipitação por estação (só cadastro + status de atividade).
Sem isso, esta opção não pode virar código.

**Opção 2 — INMET (histórico) + ANA (complemento espacial)**: fraca.
Apenas 1 estação ANA cai dentro do Recife, sem dado real confirmado, e a
API que teria dado real exige login. Cobertura simulada por proximidade é
6-10x pior (em distância) que APAC/CEMADEN.

**Opção 3 — INMET + CEMADEN + ANA combinadas**: prematura. Somar a ANA
agora adicionaria complexidade (autenticação, baixa densidade, dado não
confirmado) sem benefício claro sobre a Opção 1.

**Opção 4 — manter APAC só como catálogo espacial/histórico congelado +
usar outra rede para dado atual**: viável como fallback conceitual — a
APAC continua sendo a melhor fonte *documentada* de nomes/coordenadas de
PCDs em Recife, mesmo com o feed atual congelado; se ela voltar a
atualizar, o pipeline já existente (Estratégia A) funciona sem mudança de
código.

## Cuidados arquiteturais para múltiplas fontes (se combinadas no futuro)

Registrado para quando a decisão de combinar fontes for tomada — não
resolvido agora: diferenças de frequência (horária INMET vs. janelas APAC
vs. desconhecida CEMADEN vs. diária ANA), diferença de fuso/horário de
corte de "dia calendário", unidades e janelas de acumulado (não misturar
`15min`/`1h`/`24h` como se fossem a mesma grandeza — mesma regra já
aplicada em `agregar_diario_inmet`), estações duplicadas entre redes
(CEMADEN e APAC parecem monitorar o **mesmo hardware físico** em Recife —
uma futura combinação precisa decidir prioridade de fonte por estação, não
apenas somar contagens), e a distinção `0 mm` vs. ausência (regra já
inegociável do projeto, `CLAUDE.md` §5).

## Classificação e recomendação

- **INMET**: **PRIMÁRIA** (mantido — única fonte com histórico realmente
  funcional; decisão já tomada e não revisitada aqui).
- **APAC**: **RESERVA** (rebaixada de "complementar" para "reserva" nesta
  sessão — a rede continua sendo a melhor cobertura espacial conhecida
  para Recife, mas o feed atual está congelado desde 2024-04-09 sem
  confirmação de quando ou se voltará; não descartada, porque o pipeline
  já está pronto para usá-la de novo sem nenhuma mudança de código caso
  volte a atualizar).
- **CEMADEN**: **COMPLEMENTAR (condicional)** — a candidata mais forte
  encontrada nesta rodada: mesma densidade espacial da APAC, sinal de
  atividade real e recente (15/19 estações elegíveis em Recife pelo
  limiar atual do projeto), API de descoberta estável e sem
  autenticação. **Condicional** porque o endpoint de valores de
  precipitação por estação ainda não foi confirmado — é um item de
  investigação técnica adicional, pequeno e focado, antes de qualquer
  implementação.
- **ANA/Hidroweb**: **RESERVA** — única fonte com estação fisicamente
  dentro do Recife além da APAC/CEMADEN, e autoridade histórica nacional
  por reputação, mas hoje inviável sem criação de conta/token, com
  densidade espacial muito inferior mesmo se o acesso for resolvido.

### Qual fonte devemos implementar em seguida?

**CEMADEN.** Critérios, na ordem pedida:

1. **Cobertura espacial no Recife**: a melhor das três alternativas
   avaliadas — 19 estações fisicamente dentro do município (via spatial
   join real), distância mediana simulada de 1,3-1,4 km, comparável à
   própria APAC (porque é a mesma rede física).
2. **Atualidade**: única fonte, das três avaliadas, com evidência real e
   recente de atividade (`tempo_inatividade`) — 15/19 estações do Recife
   dentro do limiar de 90 dias já usado pelo projeto.
3. **Histórico**: existe (2011-2026), mas gated por CAPTCHA — pior que
   INMET, mas não pior que ANA (que não pôde nem ser confirmada).
4. **Qualidade**: cadastro limpo, sem duplicidade nem coordenada inválida.
5. **Automatização**: a única, das três alternativas, com um endpoint de
   descoberta público, estável e sem autenticação (WFS/GeoJSON) — ANA
   exige login, APAC (o endpoint atual) está morto.
6. **Estabilidade**: Boa para descoberta/atividade; ainda não avaliável
   para os valores em si (gap conhecido).
7. **Compatibilidade arquitetural**: encaixa exatamente no papel que a
   APAC ocupava (fonte de alta densidade espacial para Recife, sem
   histórico em lote fácil) — não exige redesenho da Estratégia A.

**Antes de implementar**, o próximo passo técnico (pequeno, focado, não é
esta etapa) é confirmar o endpoint real de valores de precipitação por
estação no GeoServer do CEMADEN (candidatos não investigados:
`view_pcds_agrometeorologica_cemaden`, `view_pcds_hidrologicas_cemaden`,
ou um serviço de observações em separado do registro de estações) — sem
isso, CEMADEN oferece ótimo cadastro e sinal de atividade, mas nenhum
valor de chuva utilizável ainda.
