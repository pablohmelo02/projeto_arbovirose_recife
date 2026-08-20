# Investigação: endpoint automatizável de valores de precipitação do CEMADEN

> Investigação técnica real, feita em 2026-08-19/20, focada exclusivamente
> em descobrir um endpoint automatizável que retorne, por estação real do
> Recife: `id_estacao`, `timestamp`, `precipitacao_mm`. Segue
> `reports/climate_source_analysis/alternative_sources_analysis.md`, que
> havia deixado esse ponto como gap em aberto (só cadastro + status de
> atividade haviam sido confirmados, não valores).

## Objetivo

Confirmar (ou descartar, com evidência) se o CEMADEN pode servir
precipitação atual/histórica de forma automatizada, sem CAPTCHA nem login,
para as estações reais dentro do Recife já identificadas na investigação
anterior.

## Estações de teste

Reobtidas via WFS (`view_pcds_pluviometrica_cemaden`, `uf=PE`, 437
estações) + spatial join real contra `silver_bairro_geo`
(`src.silver.climate_spatial.estacoes_dentro_do_recife`) — confirma as
mesmas 19 estações da investigação anterior. Selecionadas 4 (mais que o
mínimo de 3 pedido), cobrindo regiões diferentes do Recife e incluindo as
de atividade mais recente (`tempo_inatividade` do WFS):

| `codigo_estacao` (WFS) | Nome | `tempo_inatividade` (WFS, dias) | Bairro |
|---|---|---|---|
| `261160620A` | Porto | 0 | Recife (centro) |
| `261160603A` | Dois Irmãos | 0 | Dois Irmãos (zona oeste) |
| `261160609A` | Imbiribeira | 0 | Imbiribeira (zona sul) |
| `261160606A` | Dois Unidos | 2 | Dois Unidos (zona norte) |

## Painel investigado

`https://mapainterativo.cemaden.gov.br/` (painel público oficial). HTML
principal carrega `js/script.js`, que contém as chamadas reais de dados
(`.ajax`) e os endpoints de gráfico por estação clicada no mapa:

```js
function clickPoint(feature) {
    window.open(resources_url+"/graficos/interativo/grafico_CEMADEN.php?idpcd=" + feature.attributes.estacao_id + "&uf=" + feature.attributes.estacao_uf, "_blank");
}
```

com `resources_url = "https://resources.cemaden.gov.br"` (domínio novo,
não testado nas investigações anteriores).

## Scripts JS relevantes

- `https://mapainterativo.cemaden.gov.br/js/script.js` — define
  `resources_url` e os handlers de clique no mapa (`clickPoint`,
  `clickPointGeo`, `clickPointAcqua`, `clickPointHidro`) — cada tipo de
  estação (pluviométrica, geotécnica, nível de rio) abre uma página
  diferente. Para pluviométrica: `grafico_CEMADEN.php`.
- A página retornada por `grafico_CEMADEN.php?idpcd=<id>&uf=PE`
  (`https://resources.cemaden.gov.br/graficos/interativo/grafico_CEMADEN.php`)
  é um app AngularJS que carrega:
  - uma tabela de todas as estações do estado via `getJson2.php?uf=PE`
    (valores atuais + acumulados por janela);
  - um `<iframe src="grafico_pcds.php?idpcd=<id_numerico_sem_sufixo>">`
    com o gráfico interativo real.
- `grafico_pcds.php` (mesma origem) define a URL real da série temporal:

  ```js
  var path = "https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/";
  var geral = [ [0,'chartHorario','horario','Precipitação','mm',null],
                [1,'chartDiario','diario','Precipitação','mm',null] ];
  var idEstacao = url.toString().split("idpcd=")[1].split("&")[0];
  var url = path + geral[0][2] + "/" + idEstacao + "/" + dias;   // horario/{id}/{horas}
  ```

## Endpoints encontrados (todos testados com requisição HTTP real)

| Endpoint | Método | O que retorna |
|---|---|---|
| `https://resources.cemaden.gov.br/graficos/interativo/grafico_CEMADEN.php?idpcd={id}&uf=PE` | GET | Página HTML/Angular (não é a fonte final dos dados, mas revela os dois endpoints abaixo) |
| `https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=PE` | GET | **JSON, 531 registros PE** — 1 linha por estação com `idestacao, uf, codibge, cidade, nomeestacao, ultimovalor, datahoraUltimovalor, acc1hr, acc3hr, acc6hr, acc12hr, acc24hr, acc48hr, acc72hr, acc96hr, tipoestacao, status` |
| `https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/{idEstacao}/{horas}` | GET | **JSON — série horária real de precipitação por estação**, ver exemplo abaixo. **Este é o endpoint-alvo desta investigação.** |
| `https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/diario/{idEstacao}/{dias}` | GET | Estrutura idêntica à horária, mas retornou `"acumulado": [], "data": []` (vazio) em todos os testes (Porto e Imbiribeira, várias janelas) — **não confirmado como funcional** |

## GeoServer

Não foi necessário aprofundar além do já documentado
(`view_pcds_pluviometrica_cemaden` = cadastro; `precipitacao_bacia_24` =
agregado por bacia, congelado desde 2017) — o endpoint de valores reais
encontrado está em um sistema totalmente diferente
(`mapservices.cemaden.gov.br`, um serviço REST Java/Spring aparente, não
GeoServer/WFS).

## Histórico / CAPTCHA

**Achado principal**: o CAPTCHA do `download_form.php` protege apenas
**um mecanismo de exportação em lote/relatório formatado** — não é a única
via de acesso a dados históricos. Existe um **backend técnico separado,
legítimo e sem CAPTCHA** (`mapservices.cemaden.gov.br`) que serve a mesma
informação (ou mais) usada pelo próprio painel público para desenhar o
gráfico interativo. Isso responde diretamente à pergunta (a) vs (b) da
investigação: **(b)** — o CAPTCHA protege a interface do formulário de
download, não a consulta de dados em si; existe outro caminho técnico
legítimo (usado pelo próprio site) que não passa por ele.

Testado o parâmetro `horas` do endpoint `horario/{id}/{horas}` com valores
crescentes:

| `horas` | Resultado |
|---|---|
| 23 | 2 dias de dados horários |
| 168 (7 dias) | 8 dias de dados horários |
| 720 (30 dias) | ~31 dias de dados horários |
| **8760 (365 dias)** | **366 dias de dados horários, 200 OK, ~16 MB de resposta** |

Não há limite de janela detectado até 1 ano — **não testado além disso**
(não fazia parte do critério mínimo, e evitar carga desnecessária no
servidor público).

## Testes realizados e resultados (4 estações reais do Recife)

Todas retornaram `estacao.codEstacao` **idêntico** ao `codigo_estacao` do
WFS, confirmando definitivamente a correspondência entre o `idEstacao`
numérico (usado pela API de valores) e o `codestacao` alfanumérico (usado
pelo cadastro WFS):

| Estação (WFS) | `idEstacao` (API) | `codEstacao` confirmado | Última leitura não-nula (janela de 23h) | Valores 24h não-nulos (exemplos, mm) |
|---|---|---|---|---|
| Porto | 6846 | `261160620A` ✓ | sim — até `20/08/2026 1h` | 1.0, 0.4, 0.6, 0.8, 1.2, 0.2 ... |
| Dois Irmãos | 3006 | `261160603A` ✓ | sim (poucos valores, maioria 0.0) | 0.0, 0.0, 0.0 |
| Imbiribeira | 3257 | `261160609A` ✓ | sim — série densa | 0.6, 0.79, 0.59, 0.2, 0.4, 0.59 ... |
| Dois Unidos | 3254 | `261160606A` ✓ | **não** — todos os valores da janela de 23h vieram `null` | — |

**Achado de qualidade importante**: Dois Unidos aparecia com
`tempo_inatividade=2` dias no cadastro WFS (sugerindo estação bem ativa),
mas o próprio `getJson2.php` mostra sua última leitura real em
`08/07/2026` (mais de um mês antes da consulta) e o endpoint horário não
retornou nenhum valor na janela recente testada. **O campo
`tempo_inatividade` do cadastro WFS não é totalmente confiável como proxy
de atividade real** — precisa ser cruzado com o dado de valor em si
(`datahoraUltimovalor` do `getJson2.php` ou os próprios registros não-nulos
do `horario/`), não usado isoladamente. Isso é relevante para uma futura
integração: **o critério de elegibilidade não deve confiar cegamente no
campo de metadado de atividade do cadastro** — deve validar contra a série
real, como o projeto já faz para a APAC.

## Exemplo real de payload/resposta

Requisição:
```
GET https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/6846/23
```

Resposta (200 OK, JSON):
```json
{
  "horarios": ["2h","3h","4h","5h","6h","7h","8h","9h","10h","11h","12h","13h","14h","15h","16h","17h","18h","19h","20h","21h","22h","23h","0h","1h"],
  "estacao": {
    "idEstacao": 6846,
    "nome": "Porto",
    "latitude": -8.054,
    "longitude": -34.873,
    "status": "ENABLED",
    "codEstacao": "261160620A",
    "idMunicipio": {"idMunicipio": 5550, "cidade": "RECIFE", "uf": "PE", "codibge": 2611606, "id": 5550},
    "idRede": {"idRede": 11, "nome": "Centro Nacional de Monitoramento e Alertas de Desastres Naturais", "sigla": "CEMADEN", "status": "ENABLED", "id": 11},
    "idTipoestacao": {"idTipoestacao": 1, "descricao": "Pluviométrica", "id": 1},
    "offset": null, "cotaAtencao": null, "cotaAlerta": null, "cotaTransbordamento": null, "id": 6846
  },
  "datas": ["19/08/2026", "20/08/2026"],
  "acumulados": [
    [1.0, 0.0, 0.4, 0.6, 0.6, 0.6, 0.0, 0.0, 0.8, 1.2, 0.2, 0.2, null, null, null, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, null, null],
    [null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, 0.0, 0.0]
  ]
}
```

Complementar (tabela de status atual, todas as estações de PE):
```
GET https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=PE
```
```json
{
  "idestacao": 6846,
  "uf": "PE",
  "codibge": 2611606,
  "cidade": "RECIFE",
  "nomeestacao": "Porto",
  "ultimovalor": 0,
  "datahoraUltimovalor": "20/08/26 00:50",
  "acc1hr": "-", "acc3hr": "-", "acc6hr": "-",
  "acc12hr": 0.2, "acc24hr": 5.6, "acc48hr": null, "acc72hr": null, "acc96hr": null,
  "tipoestacao": 1, "status": 0
}
```

## Mapeamento semântico dos campos

| Campo | Significado |
|---|---|
| `estacao.idEstacao` | **id_estacao** — id numérico interno do CEMADEN, ponte confirmada 1:1 com `codEstacao` (o `codestacao` do cadastro WFS) |
| `datas[i]` + `horarios[j]` (endpoint `horario/`) | **timestamp** — dia calendário + hora do dia; junto formam a hora exata do acumulado |
| `acumulados[i][j]` (endpoint `horario/`) | **precipitacao_mm** — милímetros acumulados **naquela hora específica** (não é total corrido nem outra janela) |
| `datahoraUltimovalor` (`getJson2.php`) | timestamp da última transmissão real recebida daquela estação, formato `DD/MM/AA HH:MM` |
| `ultimovalor` (`getJson2.php`) | valor mm do último registro individual (leitura pontual mais recente, não acumulado) |
| `acc1hr`/`acc3hr`/`acc6hr`/`acc12hr`/`acc24hr`/`acc48hr`/`acc72hr`/`acc96hr` (`getJson2.php`) | acumulados em janelas móveis nomeadas explicitamente pelo próprio campo — **nunca confundir uma janela com outra**, mesma regra já aplicada ao INMET/APAC neste projeto |

## Unidade e janela temporal

**Confirmado**: milímetros (`mm`), rótulo `'medida':'mm'` explícito no
array `geral` do JS do painel (não vem no payload da API em si, mas é o
mesmo rótulo usado pela própria interface oficial para exibir esses
números ao usuário). Cada posição do array `acumulados` no endpoint
`horario/` representa o acumulado **daquela hora isolada** (não uma soma
corrida) — inferido pela variação hora a hora dos valores (ex.: 1.0, 0.0,
0.4, 0.6... não monotônico, logo não é acumulado desde um ponto fixo).

## Frequência real

A granularidade de base da telemetria (`getJson2.php`, campo
`datahoraUltimovalor`) mostrou, entre estações distintas na mesma consulta,
timestamps como `00:10`, `00:20`, `00:30`, `00:40`, `00:50`, `01:00` —
consistente com um ciclo de transmissão de **~10 minutos** por estação
(não confirmado como fixo/universal — não foi coletada uma série de
leituras individuais de 10 em 10 minutos da mesma estação para provar
isso). O endpoint `horario/` **agrega essa telemetria em baldes de 1
hora** — essa agregação é a granularidade oficial exposta pela API testada.

## Atualidade

- Estação Porto: última hora com valor não-nulo = `20/08/2026, 1h`.
  Consulta feita em torno de `2026-08-20 01:xx` (hora não confirmada, sem
  fuso explícito no payload). Data do sistema/ambiente é `2026-08-19`.
- **Hipótese razoável sobre fuso**: se os timestamps da API forem UTC, e o
  Recife usa horário local BRT (UTC−3), então `2026-08-20 01:00 UTC`
  equivale a `2026-08-19 22:00 BRT` — compatível com a data do sistema
  (`2026-08-19`). **Não confirmado com um campo de fuso explícito no
  payload** (o campo `offset` da estação veio `null` em todos os testes) —
  registrado como hipótese razoável, não fato.
- Em qualquer leitura (UTC ou local), a defasagem é de **horas, não de
  centenas de dias** como na APAC — os dados são genuinamente atuais.
- Repetição da consulta (`getJson2.php`) duas vezes com 20s de intervalo
  retornou o mesmo timestamp para Porto (`20/08/26 00:50`) — esperado dado
  o intervalo curto frente a um ciclo de ~10 min; não é evidência de dado
  congelado, é consistente com a granularidade observada.

## Estabilidade

- 200 OK em todas as chamadas realizadas (getJson2, grafico_CEMADEN,
  grafico_pcds, horario em 5 janelas diferentes, diario em 2 janelas).
- Tempo de resposta: ~0,7-0,9s para `getJson2.php` (531 registros); rápido
  também para `horario/` mesmo na janela de 1 ano (~16 MB, sem timeout).
- **Sem cookie, sem sessão, sem header além de `User-Agent` genérico.**
- Sem paginação nem limite de tamanho detectado até 1 ano de janela
  horária.
- `diario/` sempre retornou estrutura vazia (`"acumulado": [], "data":
  []`) nas estações e janelas testadas — não é erro HTTP, é ausência de
  dado nessa variante específica; **não confiável, não confirmado como
  funcional**.

## Limitações desta investigação

- Frequência de 10 minutos é inferida por comparação entre estações
  diferentes numa mesma consulta, não por uma série real de uma única
  estação amostrada em minutos — não foi coletada evidência direta disso.
- Fuso horário não confirmado por campo explícito — inferido por
  aritmética plausível.
- Endpoint `diario/` não funcionou em nenhum teste — pode ser um recurso
  não populado, um parâmetro incorreto, ou simplesmente não usado por este
  conjunto de estações; não investigado a fundo (fora do escopo mínimo,
  já que `horario/` supre a necessidade e pode ser agregado para diário no
  próprio pipeline, como já feito para o INMET).
- Não foi verificado se há um limite de taxa (rate limit) documentado —
  só testado com poucas chamadas moderadas.
- Autenticação/CORS: o próprio JS do painel usa `crossDomain: true` — a
  API aceita chamadas de origem diferente, o que facilita uso programático
  fora do navegador (nenhuma barreira de CORS observada via `requests`).

## Classificação final

**A — Endpoint funcional encontrado.** Critério mínimo superado: 3+
estações reais do Recife (testadas 4), cada uma com `id_estacao` real
(confirmado 1:1 contra o cadastro oficial via `codEstacao`), `timestamp`
real (hora a hora, até a hora mais recente disponível) e
`precipitacao_mm` real e plausível (não nulo, não constante, coerente
entre estações vizinhas). Não é CAPTCHA-gated, não exige login, não exige
sessão/cookie.

## Recomendação técnica

**Sim — o CEMADEN pode ser usado como fonte automatizada de precipitação,
tanto para dados atuais quanto para histórico**, com uma ressalva:

- **Atual**: automatizável, confirmado, sem bloqueio. `getJson2.php` dá o
  status mais recente de todas as estações de uma vez (útil para o filtro
  de elegibilidade); `horario/{id}/{horas}` dá a série real por estação.
- **Histórico**: automatizável **via este endpoint REST** (`horario/`,
  testado até 1 ano de profundidade, sem CAPTCHA) — **não** via o
  formulário de download mencionado na investigação anterior (esse
  continua CAPTCHA-gated e não deve ser usado). Ou seja, o histórico
  "difícil" documentado antes tinha uma alternativa mais simples que não
  havia sido encontrada ainda.
- **Ressalva de qualidade**: o campo `tempo_inatividade` do cadastro WFS
  (usado na investigação anterior para a simulação de elegibilidade) **não
  deve ser usado sozinho** como critério de atividade numa futura
  integração oficial — o caso "Dois Unidos" mostrou uma estação marcada
  como recém-ativa no cadastro, mas sem dado real recente na série. Uma
  futura Estratégia A/CEMADEN precisaria validar elegibilidade contra a
  própria série de valores (como já é feito para a APAC), não contra esse
  metadado.
- **Ainda não implementado**: nenhum cliente oficial, nenhum schema, nada
  conectado ao pipeline — conforme pedido, esta etapa parou na validação.
