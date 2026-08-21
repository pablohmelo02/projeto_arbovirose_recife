# Especificação Figma — Recife Alerta

> Documento de especificação visual para um designer reproduzir em Figma.
> **Não é um pedido para gerar um arquivo Figma** — nenhuma ferramenta de
> design foi usada para produzir isto; é texto estruturado, por tela, com
> objetivo, KPIs, gráficos, filtros, textos, estados vazios, avisos e
> interação, como pedido explicitamente nesta etapa do produto.

## 0. Figma ≠ Streamlit

**Figma é visão de produto/experiência futura. Streamlit é a PoC funcional
com dados reais, já implementada e testada (720+ testes automatizados na
suíte do projeto).** As duas coisas não se confundem:

- Tudo o que este documento descreve como comportamento de uma tela **já
  existe e funciona** no Streamlit publicado, salvo quando explicitamente
  marcado `[conceito — não implementado]`.
- Qualquer elemento marcado `[conceito — não implementado]` é uma proposta
  de evolução visual/de experiência que ainda não tem código por trás —
  nunca deve ser apresentado a um stakeholder como algo que já funciona.
- A paleta e os tokens de tipografia usados como semente deste Figma são os
  mesmos já implementados em `dashboard/components/tema.py` — não uma
  identidade nova. Isso é deliberado: reduz o risco de o Figma "prometer"
  uma cara que o produto real não tem.
- **Esta é a identidade visual própria do Recife Alerta, não a identidade
  visual oficial da Prefeitura do Recife** — nenhuma logomarca, brasão ou
  papel timbrado oficial foi usado ou deve ser usado sem autorização
  explícita da Prefeitura. Se o produto for adotado oficialmente, a adoção
  da identidade visual institucional oficial é uma decisão separada, de
  quem tem mandato para autorizá-la — não deste documento.

## 1. Mapeamento tela → página real

O pedido de produto especifica 8 telas; o Streamlit real tem 11 páginas.
Mapeamento explícito (nenhuma tela do Figma corresponde a "nada real"):

| Tela Figma | Página(s) Streamlit reais |
|---|---|
| 01 Home | `1_inicio.py` (Início) — inclui atalhos para as telas 06 e a página "Da informação à ação" |
| 02 Situação Epidemiológica | `2_situacao_epidemiologica.py` |
| 03 Mapa Territorial | `3_mapa_territorial.py` |
| 04 Histórico | `5_evolucao_historica.py` (Evolução histórica) + ranking observado de `4_bairros_prioritarios.py` como aba complementar |
| 05 Clima × Arboviroses | `6_clima.py` (Clima) + `7_clima_dengue.py` (Clima × Arboviroses) consolidadas num único fluxo de 2 telas no Figma (ver §5.5) |
| 06 Projeção 2026 | `10_projecao_2026.py` |
| 07 Priorização Experimental | `8_priorizacao_experimental.py` |
| 08 Qualidade e Transparência | `9_qualidade_limitacoes.py` + a matriz de `11_da_informacao_a_acao.py` (Da informação à ação), apresentada como uma sub-aba de apoio à decisão dentro desta tela |

`4_bairros_prioritarios.py` e `11_da_informacao_a_acao.py` não ganham tela
própria numerada porque o pedido fixou 8 telas; ambas são reais e estão
mapeadas como conteúdo dentro das telas 04 e 08, respectivamente. Um
designer que preferir 10 telas (uma por página real relevante, exceto
`6_clima.py`/`7_clima_dengue.py` que já nascem consolidadas) pode
desdobrar §5.4 e §5.8 em duas telas cada sem contradizer este documento.

## 2. Identidade visual (semente para o Figma)

Fonte da verdade: `dashboard/components/tema.py`. Não uma paleta nova.

### 2.1 Cor

| Token | Valor | Uso |
|---|---|---|
| `COR_INSTITUCIONAL` | `#1f4e79` | Estrutura, ênfase neutra, elementos "observado" |
| `COR_INSTITUCIONAL_CLARA` | `#2e6da4` | Variação de ênfase (barras secundárias, eixo secundário) |
| `COR_TEXTO` | `#1b2631` | Texto principal (contraste ≥ 4,5:1 verificado sobre `#ffffff` e `#f4f6f7`) |
| `COR_TEXTO_SUAVE` | `#5b6b7b` | Texto secundário, legendas, notas de cartão |
| `COR_FUNDO_SUAVE` | `#f4f6f7` | Fundo de sidebar, fundo de faixa de atualização |
| `COR_BORDA` | `#dde3e8` | Bordas de cartão, divisores |
| `COR_ATENCAO` / `COR_ATENCAO_FUNDO` | `#b9770e` / `#fdf6e3` | Etiqueta e avisos do modo **experimental** (modelo de priorização) |
| `COR_DENGUE` | `#a93226` | Reservada **exclusivamente** à série de dengue nos gráficos — nunca reaproveitada para outro sentido |
| `COR_PROJECAO` / `COR_PROJECAO_FUNDO` | `#5b4b8a` / `#f1eef9` | Etiqueta e elementos do modo **projeção estatística** (Projeção 2026), visualmente distinta de "experimental" |

**Regra inegociável, testada no código real:** nenhuma escala
verde-amarelo-vermelho de "risco" em lugar nenhum. A validação estatística
do modelo experimental não sustenta categorizar risco, e cor de semáforo
comunicaria exatamente essa categorização proibida. Um designer que
proponha uma paleta de risco está, por definição, fora do escopo deste
produto.

### 2.2 Tipografia e espaçamento

- H1: 1,85rem, peso 650, usado uma vez por tela (título da página).
- H2: 1,25rem, peso 620, início de cada seção principal.
- H3: 1,05rem, peso 600, subseções.
- Corpo/subtítulo: ~0,97rem, `COR_TEXTO_SUAVE`, largura máxima 78 caracteres
  por linha (legibilidade, não decoração).
- Uma "régua" de 3px × 56px, `COR_INSTITUCIONAL`, sob todo H1 — assinatura
  visual mínima, não decorativa.
- Espaçamento de bloco: `st.divider()` entre seções principais — no Figma,
  equivalente a um espaçamento vertical generoso + linha fina `COR_BORDA`
  (nunca uma sombra pesada ou cartão all-around para simular divisão).

### 2.3 Componentes-base

- **Cartão de KPI**: fundo branco, borda 1px `COR_BORDA`, raio 8px,
  título em maiúsculas pequenas (`COR_TEXTO_SUAVE`), valor grande
  (1,55rem, `COR_TEXTO`), nota explicativa sempre visível abaixo (nunca só
  em tooltip — um gestor não deve precisar passar o mouse para entender o
  número). Máximo 4 cartões por linha.
- **Etiqueta de natureza do conteúdo** (canto do H1): "Dados observados"
  (azul), "Experimental" (âmbar), "Projeção estatística" (roxo) — as três
  são mutuamente exclusivas por tela.
- **Faixa de atualização dos dados**: barra com borda esquerda de 4px na
  cor institucional (ou âmbar se em atenção), sempre no topo de toda tela,
  nunca omitida.
- Acessibilidade: nenhuma informação depende só de cor — tendência,
  status, observado/projetado e conclusivo/inconclusivo sempre também em
  texto ou padrão de preenchimento (hachurado). Contraste de texto ≥ 4,5:1.
  Tabelas com rótulos completos, nunca sigla sem legenda.

### 2.4 Responsividade

Breakpoint real já implementado: `900px`. Abaixo dele, título reduz para
1,5rem, cartões reduzem para 1,3rem de valor, padding lateral cai para
0,8rem. Tabelas largas rolam dentro do próprio contêiner, nunca a página
inteira. `[conceito — não implementado]`: breakpoint dedicado de tablet
(entre 900px e 1200px) com grade de 2 colunas para cartões em vez de
empilhamento total — hoje o CSS só tem um breakpoint.

---

## 3. Telas

Cada tela segue: Objetivo · KPIs · Gráficos · Filtros · Textos · Estados
vazios · Avisos · Interação.

### 3.1 Tela 01 — Home

**Objetivo.** Responder em poucos segundos: até quando os dados vão, qual
agravo estou vendo, quantos casos, qual a incidência, a tendência, quais
territórios olhar primeiro, e como chegar à Projeção 2026 e à Priorização
Experimental. **Não é um relatório técnico** — é a tela de entrada
orientada à decisão (ver §4).

**KPIs** (linha de 4 cartões, real): Casos nas últimas 4 semanas · Incidência
(100 mil hab.) no período (com nota "sem base" quando a população do ano
não está disponível) · Variação sobre as 4 semanas anteriores (com a
tendência também escrita em texto, nunca só pela cor da variação) · Bairros
em alta (contagem sobre o total).

**Gráficos.** Série semanal de casos do agravo selecionado (barras =
observado semana a semana; linha = média móvel de 4 semanas — as duas
juntas, nunca a suavização isolada).

**Filtros.** Seletor de agravo (Dengue/Zika/Chikungunya/Todas as
arboviroses), sem recorte geográfico nesta tela (a Home é sempre Recife
inteiro; o recorte territorial vive nas telas 02/03/04).

**Textos (reais, verbatim onde fixos).** Subtítulo da página: *"Plataforma
de inteligência epidemiológica e priorização territorial para apoiar ações
preventivas contra arboviroses nos 94 bairros do Recife. Todos os números
desta página são observados — o que os registros oficiais mostram, sem
projeção."* Expander "Perguntas que o Recife Alerta ajuda a responder"
(tabela pergunta → onde responder, 11 linhas reais, incluindo linhas para
Clima × Arboviroses, Projeção 2026 e Da informação à ação).

**Estados vazios.** Se a tabela analítica principal não estiver publicada:
mensagem de indisponibilidade acionável, nunca stack trace. Se não houver
série suficiente para o gráfico: aviso "Sem série temporal para o recorte
carregado" em vez de gráfico vazio. Se o módulo experimental de
priorização estiver ausente: aviso específico, o resto da Home continua.

**Avisos.** Nenhum aviso permanente fixo nesta tela além da faixa de
atualização — a Home é dado observado, sem ressalva de modelo. O bloco do
módulo experimental (coluna direita) carrega sua própria ressalva
("Resultados retrospectivos... não representam previsão oficial da
Prefeitura do Recife") sempre que exibido.

**Interação.** Trocar o agravo no filtro recalcula título, KPIs, série e
tabela "Onde olhar primeiro" na mesma tela (sem navegação). Dois blocos de
atalho levam a "Projeção 2026" e "Da informação à ação". `[conceito — não
implementado]`: um "hero" com resumo em uma frase gerada dinamicamente
(ex.: *"Dengue: X casos nas últimas 4 semanas, Y% acima do mesmo período do
ano anterior"*) acima da linha de cartões — hoje a leitura textual mais
próxima disso é o parágrafo de "Onde olhar primeiro", não um resumo de
uma frase no topo.

### 3.2 Tela 02 — Situação Epidemiológica

**Objetivo.** *"Como a dengue (ou o agravo escolhido) está evoluindo?"* —
leitura observada, comparável ano a ano e agravo a agravo.

**KPIs** (5 cartões reais): Casos no recorte · Casos nas últimas 4 semanas
· Incidência (100 mil hab.) no período recente · Variação sobre o período
anterior · Bairros com pelo menos 1 caso (de 94).

**Gráficos.** (a) Série semanal — por agravo único (barra + média móvel) ou,
quando "Todas as arboviroses" está selecionado, uma série por agravo lado a
lado (nunca somadas na mesma linha, porque a soma não é uma série com
sentido epidemiológico próprio); (b) comparação sazonal entre anos, uma
curva por ano, ano em destaque escolhível, destacado em vermelho; (c)
total por ano (barras); (d) comparação entre os 3 agravos em escalas
separadas (dengue tem volume muito maior — forçar a mesma escala tornaria
zika/chikungunya ilegíveis).

**Filtros.** Agravo (incl. "Todas as arboviroses"), intervalo de anos,
recorte territorial (Recife inteiro / uma RPA / um bairro).

**Textos.** Caption fixo sob os KPIs: *"Incidência = casos da janela
dividido pela população total da cidade no ano de referência, vezes
100.000 — uma única divisão sobre os totais, nunca a soma das incidências
por bairro."* Nota de fonte ao final: *"Fonte: Portal de Dados Abertos do
Recife (CKAN), casos notificados ao SINAN. Notificação é compulsória,
portanto ausência de notificação numa semana é lida como zero caso — não
como dado faltante. Subnotificação permanece um risco conhecido e não é
corrigida por este painel."*

**Estados vazios.** Recorte sem nenhum registro → aviso e interrupção da
tela antes de tentar desenhar qualquer gráfico.

**Avisos.** Nenhum aviso de ressalva de modelo (tela 100% observada).

**Interação.** Trocar o "ano em destaque" do gráfico sazonal realça uma
curva sem recarregar os outros gráficos. Trocar o recorte territorial
(RPA/bairro) refiltra todos os gráficos da tela simultaneamente.

### 3.3 Tela 03 — Mapa Territorial

**Objetivo.** *"Onde há maior concentração/intensidade/crescimento de
casos?"* — leitura espacial dos 94 bairros.

**KPIs.** Nenhum cartão de KPI dedicado — o "indicador" desta tela é a
própria escala do mapa; a tabela de detalhe por bairro concentra os
números.

**Gráficos.** Mapa coroplético dos 94 bairros com seletor de métrica
(Casos acumulados no período · Casos nas últimas 4 semanas · Incidência
/100k · Incidência móvel 4 semanas /100k · Crescimento recente % ·
Razão contra o histórico do bairro · Densidade populacional). Escala de
cor **sequencial** (mais escuro = valor mais alto) — nunca categórica de
risco. Hover mostra RPA, tendência (em texto) e casos recentes. Tabela de
detalhe por bairro, ordenável pela métrica ativa, com colunas de população
usada e tipo de população (Censo observado vs. reconstruída/projetada).

**Filtros.** Agravo (incl. "Todas as arboviroses" — soma de casos válida
para o mapa; incidência/densidade recalculadas corretamente por
`total_arboviroses`, nunca por soma de taxas), intervalo de anos. Sem
recorte territorial nesta tela (ela É o recorte territorial).

**Textos.** Legenda de ajuda por métrica (ex.: para incidência móvel:
*"Soma dos casos das últimas 4 semanas dividida pela população do bairro,
× 100.000 — nunca a soma de taxas semanais já calculadas."*). Nota sobre
tipo de população sempre visível quando a métrica depende de população:
anos de Censo (2010, 2022) vs. estimativa intercensitária/projeção
pós-Censo.

**Estados vazios.** Geometria dos bairros ausente → aviso explícito e a
tabela de detalhe substitui o mapa (a tela continua útil sem o desenho).
Nenhum bairro com valor calculável para a métrica escolhida → aviso
específico em vez de mapa vazio.

**Avisos.** Aviso fixo quando a métrica é incidência: *"Taxas de curto
prazo podem variar fortemente em bairros de menor população: um único caso
a mais ou a menos muda a incidência de forma desproporcional. Os valores
não são ocultados para nenhum bairro."*

**Interação.** Trocar a métrica no seletor redesenha mapa e tabela juntos,
mantendo o mesmo recorte de agravo/ano. Ordenar a tabela por outra coluna
não afeta o mapa. `[conceito — não implementado]`: clicar num bairro do
mapa para abrir um painel lateral com a série histórica só daquele bairro
— hoje o drill-down é só via o seletor de bairro na barra lateral de
outras telas (02, 04, 05), não um clique direto no mapa desta tela.

### 3.4 Tela 04 — Histórico

**Objetivo.** *"Qual o comportamento sazonal? Que anos foram atípicos?
Quais territórios concentram a carga histórica? Quais bairros merecem
priorização segundo o que já foi observado (sem modelo)?"*

**KPIs** (4 cartões, tela `5_evolucao_historica.py`): Período coberto · Casos
no período · Ano de maior volume (com a mediana anual do período como
referência) · Pico sazonal médio (semana epidemiológica).

**Gráficos.** Série longa completa com média móvel; totais por ano com
métrica alternável (Casos / Incidência por 100 mil hab. / População);
sazonalidade média por semana epidemiológica (com o número de anos-base
visível no hover); todos os anos sobrepostos com um ano em destaque
selecionável; tabela pivô de casos por RPA e ano; ranking dos 15 bairros
com maior carga histórica acumulada.

Complementar nesta tela (conteúdo real de `4_bairros_prioritarios.py`, aqui
como uma segunda aba "Priorização observada"): 4 rankings **distintos e
nunca combinados** — maior volume recente, maior incidência, maior
crescimento, maior desvio contra o próprio histórico sazonal — cada um com
tamanho de lista selecionável (5/10/15/20/94) e, para incidência, aviso de
instabilidade quando a população do bairro é pequena.

**Filtros.** Agravo (incl. "Todas"), intervalo de anos, recorte territorial
completo (Recife / RPA / bairro).

**Textos.** Leitura textual gerada a partir do dado real, nunca narrada de
memória: *"No recorte selecionado, o ano de maior volume foi **{ano}**
({casos} casos)... O pico sazonal médio ocorre em torno da semana
epidemiológica **{semana}**."* Caption: *"O critério de 'ano de alta' é
objetivo e está no código desta página (fator sobre a mediana anual do
próprio recorte) — nenhum ano é destacado por escolha editorial."*

**Estados vazios.** Métrica anual sem valor calculável no recorte → aviso
em vez de gráfico vazio.

**Avisos.** Nenhum de modelo (100% observado). Caption explicando que
comparação por RPA é volume absoluto, não incidência (RPAs têm tamanhos
diferentes).

**Interação.** Trocar a métrica anual (rádio) redesenha só aquele gráfico.
Trocar o "ano em destaque" da sobreposição realça uma curva. Trocar o
critério de ranking (aba de priorização observada) reordena a lista sem
tocar nos gráficos históricos.

### 3.5 Tela 05 — Clima × Arboviroses

Consolidação de duas páginas reais (`6_clima.py` + `7_clima_dengue.py`) —
proposital: a primeira estabelece a confiabilidade das fontes climáticas
antes de a segunda usá-las para associação. No Figma, pode ser um fluxo de
2 sub-telas ou uma tela com duas seções âncora.

**Objetivo.** *"Existe associação histórica entre chuva/temperatura e os
casos? As fontes climáticas disponíveis são confiáveis, e para quê
exatamente?"*

**KPIs** (sub-tela "Cobertura", 4 cartões reais): % de linhas com reanálise
em grade · % de linhas com estação física · células de grade de
precipitação para os 94 bairros (hoje: poucas — o número real está em
`reports/climate_source_analysis/`, não fixado aqui para não descasar do
dado ao vivo) · estações distintas usadas.

**Gráficos.**
- Cobertura por ano: reanálise × estação (barras agrupadas).
- Série da reanálise em grade: precipitação (barra) + temperatura média
  (linha), eixo duplo.
- Sazonalidade climática média por semana epidemiológica: chuva (barra) +
  umidade relativa (linha), eixo duplo.
- Série de estações físicas (só no período coberto) + mapa de calor de
  disponibilidade das estações no tempo.
- Concordância entre as duas fontes (correlação, razão de volume captado).
- **Aba "Janelas cumulativas"** (metodologia legada, preservada): correlação
  entre casos e chuva acumulada retrospectivamente em janelas de 7/14/21/28
  dias (estação) ou 1–4 semanas (grade) — barra + tabela com n de
  observações.
- **Aba "Defasagem real (lag)"** (nova, item 4-9 do pedido): seletor de
  variável climática (precipitação, temperatura média/mínima/máxima,
  umidade) e de quantidade epidemiológica (casos ou incidência); série
  clima + epidemiológica sobreposta; barra de correlação de Spearman por
  defasagem deslocada real `t` × `t-k`, k = 0 a 12 semanas, com tabela de
  p-valor e n de observações; frase-resumo automática ("A maior associação
  observada ocorreu com X semanas de defasagem... mas isso representa
  associação histórica, não causalidade").
- **Aba "Bruta vs. ajustada por sazonalidade"** (nova, item 6): duas barras
  por defasagem — correlação bruta e correlação após remover a média
  histórica da própria semana epidemiológica de cada série.

**Filtros.** Página Clima: agravo incl. "Todas", ano, recorte territorial.
Página Clima × Arboviroses: **agravo sem a opção "Todas"** — Dengue, Zika
ou Chikungunya sempre um de cada vez, porque a defasagem/sazonalidade é
específica de cada agravo e somar os três não produziria uma associação
com significado único. Sem recorte territorial nesta segunda página — a
análise é sempre Recife total (a reanálise em grade só resolve poucas
células para os 94 bairros; qualquer recorte mais fino produziria falsa
precisão espacial).

**Textos (avisos fixos, verbatim).** *"O painel usa duas fontes climáticas
com naturezas diferentes... Elas aparecem separadas e nunca são somadas ou
substituídas uma pela outra."* (Clima) · *"Associação não é causalidade.
Uma correlação entre variável climática e casos não significa que o clima
cause o aumento de casos, nem permite prever casos a partir do clima. As
séries podem compartilhar a mesma sazonalidade anual, o que sozinho produz
correlação."* (Clima × Arboviroses, aviso permanente no topo).

**Estados vazios.** Bloco em grade ausente → cartão mostra "indisponível"
em vez de quebrar a tela. Nenhuma linha com valor climático no
recorte/fonte escolhidos → aviso específico por seção, sem interromper as
demais seções da tela.

**Avisos.** O aviso de não-causalidade é permanente (não fecha, não é
dismissable) nesta tela. Nota adicional ao final: leitura honesta de que o
clima, testado em experimento controlado, não melhorou o modelo
experimental de priorização na faixa validada (Top-5).

**Interação.** As 3 abas da segunda sub-tela trocam de conteúdo sem
recarregar o filtro de agravo. Seletor de variável climática e de
casos/incidência recalculam gráfico + tabela + frase-resumo juntos.

### 3.6 Tela 06 — Projeção 2026

**Objetivo.** *"O que esperar de 2026, por agravo, com que incerteza — sem
confundir com dado observado nem com a priorização territorial
experimental?"*

**KPIs** (3 cartões reais): Semana de maior valor esperado (SE/2026) ·
Casos esperados na semana de pico · Média sazonal histórica das mesmas
semanas (comparação, não meta).

**Gráficos.** Um único gráfico central: série observada 2013–2025 (linha
sólida, cor da série do agravo) + projeção 2026 (linha **tracejada**, cor
institucional roxa/`COR_PROJECAO`) + faixas sombreadas de intervalo de
previsão de 80% e 95% (nunca uma única linha). A diferenciação
observado/projetado usa **três sinais redundantes, nunca só cor**: estilo
de linha (sólida vs. tracejada), nome explícito da série no rótulo/legenda
("Observado (2013-2025)" / "Projetado 2026") e a etiqueta "Projeção
estatística" no cabeçalho da própria tela. Tabela de desempenho do
backtest do modelo escolhido (MAE, RMSE, MASE, semana de pico
observada/prevista, erro de timing em semanas, erro de magnitude do pico) —
uma linha por ano de teste (2023, 2024, 2025).

**Filtros.** Agravo, **sem a opção "Todas"** (cada agravo tem processo/
sazonalidade próprios; a soma dos três não é uma série válida para
baselines/ETS). Sem recorte territorial (Recife total apenas — nenhuma
projeção por bairro/RPA é publicada, por instabilidade).

**Textos (aviso permanente, verbatim exato do código real).**
> *"Projeção estatística baseada nos dados históricos disponíveis até
> 2025. Não representa casos observados em 2026 nem previsão oficial da
> Prefeitura do Recife."*

Seção "Metodologia" (texto real, parametrizado por agravo): baselines
obrigatórios (seasonal naive, média histórica da mesma semana, tendência +
sazonalidade) + 1 método adicional (ETS/Holt-Winters) — nunca deep
learning, nunca AutoML; seleção pela mediana do MASE em 3 dobras de
backtest walk-forward (2023, 2024, 2025), desempate pelo erro de timing do
pico, **nunca escolhido olhando 2026**. Seção "Limitações" (texto real):
ausência de caso observado de 2026 em qualquer fonte oficial verificada;
ausência de incidência 2026 (sem estimativa municipal oficial do IBGE);
granularidade Recife-total apenas; instabilidade estrutural em anos
atípicos.

**Estados vazios.** Artefato de projeção ainda não gerado nesta publicação
→ aviso acionável ("rode `python -m src.generate_forecast_artifacts`"),
resto do painel continua. Agravo sem histórico suficiente → aviso
específico daquele agravo, sem impedir a troca para outro.

**Avisos.** O aviso permanente acima nunca é ocultável. Etiqueta "Projeção
estatística" no cabeçalho (roxa) — deliberadamente diferente da etiqueta
"Experimental" (âmbar) da tela 07, para que as duas nunca sejam confundidas
mentalmente.

**Interação.** Trocar o agravo recalcula gráfico, KPIs, metodologia e
tabela de backtest juntos (cada agravo pode ter um modelo vencedor
diferente — isso é esperado e mostrado, não escondido). `[conceito — não
implementado]`: um controle para alternar a visão entre "casos" e
"incidência" nesta tela — hoje a Projeção 2026 é sempre em casos (não há
incidência 2026 disponível, por ausência de estimativa populacional
municipal oficial).

### 3.7 Tela 07 — Priorização Experimental

**Objetivo.** *"Onde olhar primeiro, com recursos operacionais restritos,
segundo um modelo estatístico — e com que confiabilidade real, faixa por
faixa?"* Dengue apenas.

**KPIs** (variam por aba). Aba backtest: Bairros priorizados (Top-K) ·
Acertos · Falsos alertas · Episódios perdidos. Aba "período atual" (quando
bloqueada): Último período publicado · Atraso em relação a hoje ·
Situação do módulo ("somente backtest"). Aba desempenho: recall por K com
IC 95%, antecedência mediana (semanas), taxas ≥2 e ≥3 semanas de
antecedência, sobreposição (Jaccard) do Top-10 entre semanas consecutivas.

**Gráficos.** Ranking navegável por semana de decisão passada (backtest),
com trajetória de um bairro escolhido antes/decisão/desfecho; recall por K
(5/10/15/20) com barras de erro (IC 95%, modelo × regras simples); ganho do
modelo sobre a melhor regra simples por K (preenchido = conclusivo,
**hachurado + rótulo textual** = inconclusivo, nunca só cor);
distribuição de antecedência (lead time); tabela de desempenho por RPA;
tabela de recall para início genuíno vs. recaída; tabela de recall para
grandes episódios vs. todos; tabela de custo operacional por K.

**Filtros.** **Nenhum seletor de agravo nesta tela** — o modelo é
dengue-only por construção (target/features treinados só para dengue).
Seletor de semana de decisão (backtest) e de K (5/10/15/20).

**Textos (fixos, verbatim).**
> *"Priorização experimental atualmente validada apenas para dengue."*

> *"Módulo experimental. Resultados retrospectivos e sinais de priorização
> não substituem avaliação epidemiológica nem representam previsão oficial
> da Prefeitura do Recife."*

Leitura honesta por faixa de K (texto real, uma frase por K): Top-5 =
"faixa com ganho robusto" (única com IC que não cruza zero); Top-10 =
"ganho não conclusivo"; Top-15 = "regras simples são competitivas"; Top-20
= "regra simples é melhor". **Score de prioridade nunca é chamado de
probabilidade** — é posição relativa 0–100 dentro da própria semana.

**Estados vazios.** Artefato de estado ausente → priorização totalmente
indisponível, mensagem explícita, resto do painel funciona. Backtest não
disponível/modelo não validado para o período → mesma lógica. Portão de
atualidade fechado → aba "período atual" mostra por quê, nunca mostra um
ranking desatualizado disfarçado de atual.

**Avisos.** Etiqueta "Experimental" (âmbar) no cabeçalho. Bloco de
limitações fixo ao final da tela (7 itens reais: ganho só em Top-5,
variação entre anos/RPAs, pior desempenho no cenário mais relevante —
início genuíno —, instabilidade semana a semana da lista, maioria das
priorizações sem episódio subsequente, nenhuma demonstração de redução de
incidência/internação, riscos de subnotificação/mudança de padrão).

**Interação.** Trocar a semana de decisão (backtest) atualiza ranking,
cartões e a trajetória do bairro escolhido. Trocar K muda a leitura textual
junto com a lista — nunca um sem o outro. As 3 abas (backtest / período
atual / desempenho) são independentes entre si.

### 3.8 Tela 08 — Qualidade e Transparência

**Objetivo.** *"Até onde os dados sustentam cada afirmação do painel? O que
pode e o que não pode ser dito a partir deles? Como cada pergunta
operacional da Prefeitura se conecta a uma decisão apoiada — nunca
executada automaticamente?"*

**KPIs.** Cobertura epidemiológica (linhas na tabela analítica, período,
bairros, casos notificados); cobertura climática (% reanálise, % estação,
células de grade, estações distintas); módulo experimental (período
avaliado, disponibilidade do período atual, modelo treinado até).

**Gráficos.** Tabela de atualidade por conjunto de dados (com regra
objetiva de limiar de atraso); gráfico de cobertura dupla por ano
(reanálise × estação); matriz de correlação exploratória clima × casos
(só observações com clima real, identificadores nunca entram como
variável numérica); tabela de proveniência de artefatos publicados
(obrigatório/presente/tamanho); tabela pergunta → indicador → decisão
apoiada (9 linhas reais, de `11_da_informacao_a_acao.py`).

**Filtros.** Nenhum — esta tela é sempre sobre o dataset completo, para
que a leitura de qualidade não dependa de um recorte que poderia escondê-la.

**Textos (a tabela "o que pode e o que não pode ser afirmado" é real,
verbatim, 12 linhas)** — amostra: *"Prevê surtos" → **Não** → "O produto
ordena prioridades relativas; não estima ocorrência nem magnitude."*
*"Reduz a incidência de dengue" → **Não** → "Não foi medido e não poderia
ser, com os dados disponíveis."* *"Fornece um ranking experimental de
priorização" → **Sim, com ressalva** → "Retrospectivo, experimental, não é
previsão oficial."* Bloco fixo "Riscos conhecidos que o painel não
corrige" (subnotificação, atraso de publicação, mudança de padrão
epidemiológico, mudanças climáticas, capacidade operacional, ausência de
população — **nota**: este último item do texto real está desatualizado
frente ao estado atual do produto, que passou a calcular incidência via
população reconstruída desde a Gold 1.2; ver observação de manutenção no
rodapé deste documento). Bloco "Esta plataforma apoia, prioriza, informa e
contextualiza. Ela NÃO ordena equipes automaticamente, NÃO substitui
avaliação epidemiológica, NÃO garante redução de casos/internações e NÃO
diagnostica surto. Toda decisão final é humana." (real, de
`11_da_informacao_a_acao.py`).

**Estados vazios.** Módulo experimental indisponível → seção de cobertura
do modelo mostra aviso, resto da tela (qualidade epidemiológica/climática)
continua. Manifest da reanálise ausente → nota de resolução da grade
simplesmente não aparece, sem quebrar a tela.

**Avisos.** Esta é a tela que existe justamente para conter avisos — não
tem aviso "extra" além do que já está descrito nos Textos acima.

**Interação.** Tela primariamente de leitura; a única interação real é a
navegação entre as 7 seções via scroll/sumário. `[conceito — não
implementado]`: um sumário lateral fixo (sticky) com âncoras para as 7
seções — hoje a navegação dentro da tela é scroll simples, sem sumário
fixo.

---

## 4. Home orientada à decisão (item 25)

A Home **não deve parecer relatório técnico**. O que já é real hoje:
freshness sempre visível no topo (faixa de atualização, comum a toda
tela do produto, não exclusiva da Home); agravo selecionável; casos e
incidência do período recente; tendência (variação % com sinal textual
explícito, nunca só cor); principais territórios ("onde olhar primeiro",
tabela com posição, casos, variação, tendência e — quando disponível —
incidência móvel); acesso direto à Projeção 2026 e à página "Da informação
à ação"; acesso ao estado do módulo experimental (disponível/só backtest).

`[conceito — não implementado]`: agrupar os 3 modos do produto (observado
/ projeção / experimental) como três "portais" visuais distintos logo
abaixo da linha de KPIs da Home (hoje eles são acessíveis via dois blocos
de texto + a navegação lateral padrão, não um componente de portal
dedicado). `[conceito — não implementado]`: indicador visual de
"frescor" em selo compacto ao lado do título (hoje o frescor vive só na
faixa de atualização já existente, não duplicado como selo).

---

## 5. Nota de manutenção (não é parte da especificação visual)

Ao revisar os textos reais para este documento, foi encontrada uma
inconsistência textual que não é responsabilidade desta tarefa corrigir,
mas que um leitor deste documento deveria saber: `9_qualidade_limitacoes.py`
ainda contém a frase "**Incidência por 100 mil habitantes não é calculada**
em nenhuma página" — isso deixou de ser verdade nesta mesma etapa do
produto (Home, Situação Epidemiológica e Mapa Territorial passaram a
calcular e mostrar incidência via a população reconstruída da Gold 1.2).
Esta especificação Figma já reflete o estado **atual e correto** (com
incidência disponível), não o texto desatualizado da página em si.
