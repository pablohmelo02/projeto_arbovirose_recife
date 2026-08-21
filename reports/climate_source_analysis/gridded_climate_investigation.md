# Investigação de fontes climáticas em grade (2013–2025)

**Data:** 2026-08-21 · **Reprodução:** `python -m src.investigate_gridded_climate`
**Artefatos:** `gridded_climate_investigation.json`,
`gridded_climate_cobertura_por_ano.csv`,
`gridded_climate_correlacao_por_bairro.csv`,
`gridded_climate_comparacao_bairro_semana.csv`

## 1. Problema que motivou a investigação

A série epidemiológica do projeto cobre **2013–2025** (679 semanas
epidemiológicas, 94 bairros). A cobertura climática **real, por estação**
existia apenas em 2024–2025 e, mesmo lá, parcial:

| Ano | bairro×semana com estação |
|-----|---------------------------|
| 2013–2023 | 0,00 % |
| 2024 | 26,70 % |
| 2025 | 52,15 % |

Nenhuma das redes de estações investigadas nas etapas anteriores resolve
2013–2023: INMET não tem estação ativa dentro do Recife desde 2020-09-01,
a rede APAC está congelada desde 2024-04-09, a ANA/Hidroweb tem 1 estação
no município e exige autenticação, e o CEMADEN só entrega histórico
automatizável a partir de ~2021 na prática (janela aplicada: 730 dias).

Esta etapa investiga se um produto climático **em grade** (satélite /
reanálise) resolve a dimensão temporal — e, se resolver, com que
limitações.

## 2. Candidatas testadas (requisições HTTP reais)

| Candidata | Acesso | Resolução | Veredito |
|-----------|--------|-----------|----------|
| **ERA5 / ERA5-Land via Open-Meteo Archive** | HTTP público, sem chave, sem CAPTCHA | 0,25° (precip.) / 0,10° (temp.) | **Escolhida** |
| ERA5-Land via CDS/Copernicus direto | exige credencial (`.cdsapirc`) | 0,10° | Não testável neste ambiente |
| CHIRPS 2.0 | diretório público acessível (HTTP 200) | 0,05° | Descartada por custo de ingestão |
| NASA POWER | HTTP público, sem chave, funciona | 0,5° × 0,625° | Descartada por resolução |

**CHIRPS** foi descartada por custo, não por qualidade: o produto diário é
GeoTIFF **global** (um arquivo por dia, ~4.700 arquivos para 2013–2025) e
exigiria uma dependência de leitura raster (GDAL/rasterio) — ecossistema
pesado que o projeto evita deliberadamente. É a melhor candidata para uma
etapa futura com infraestrutura dedicada, por ter 0,05° (~5,5 km).

**NASA POWER** respondeu corretamente (`PRECTOTCORR`, `T2M`, `RH2M`), mas a
célula de 0,5° × 0,625° tem ~55 × 70 km — para uma cidade de 0,18° de
extensão, é pior que ERA5 em todos os aspectos relevantes.

### 2.1 Provenância por variável — medida, não presumida

Achado importante: o provedor **não serve precipitação para o modelo
ERA5-Land** (`precipitation_sum` retorna nulo em toda a janela testada),
apesar de servir temperatura e umidade. Portanto:

| Variável | Modelo | Resolução |
|----------|--------|-----------|
| `precipitacao_mm` | `era5` | 0,25° |
| `temperatura_2m_{mean,min,max}`, `relative_humidity_2m_mean` | `era5_land` | 0,10° |

O modelo "seamless" (que mistura os dois sob um rótulo único) **não é
usado**: o projeto pede um modelo por requisição e registra a origem de
cada variável, para que nenhuma resolução seja atribuída à variável errada.

Fuso horário fixado em `America/Recife` em todas as requisições — o mesmo
referencial de dia-calendário das datas do SINAN e das semanas
epidemiológicas da Gold. Deixar o default (UTC) deslocaria a fronteira do
dia em 3 horas.

## 3. Limitação central: a grade quase não distingue bairros

Os centroides dos 94 bairros ocupam **0,1774° de latitude por 0,1080° de
longitude**. Medido pelas coordenadas que o próprio provedor devolve
(nunca por arredondamento local):

| Grade | Resolução | Células distintas para 94 bairros |
|-------|-----------|-----------------------------------|
| ERA5 (precipitação) | 0,25° | **2** |
| ERA5-Land (temperatura/umidade) | 0,10° | **3** |

Comparação: a Estratégia A com estações CEMADEN usa **16 estações
distintas**, com distância mediana bairro→estação de 1,431 km. Já a
distância mediana do centroide do bairro ao centro da sua célula de grade é
**8,06 km** (máxima 17,29 km).

Consequência medida diretamente no dado: numa mesma semana, os 94 bairros
recebem no máximo **2 valores distintos** de precipitação em grade (mediana
2). Ou seja:

> A fonte em grade informa **quando** chove, não **onde dentro do Recife**.
> Ela é uma covariável temporal quase-municipal, não uma variável
> territorial.

Essa é a conclusão principal — não uma ressalva de rodapé. Qualquer uso
desta fonte tem de assumi-la.

## 4. Validação contra o CEMADEN no período sobreposto

Comparação sobre **as mesmas 3.903 linhas bairro × semana** em que existe
leitura real de estação (2024–2025) e valor em grade.

### 4.1 Concordância no grão bairro × semana

| Métrica | Valor |
|---------|-------|
| n (bairro × semana) | 3.903 |
| Pearson | **0,6084** |
| Spearman | 0,5507 |
| MAE | 17,614 mm |
| RMSE | 35,504 mm |
| Viés médio (grade − estação) | **−5,684 mm** |
| Média grade / média estação | 14,218 / 19,901 mm |
| Razão dos totais | **0,7144** |
| Concordância "semana chuvosa" (≥ 20 mm) | 83,58 % |
| Recall de "semana chuvosa" real | 64,21 % |

Leitura honesta: a grade **subestima sistematicamente** a chuva medida pelo
pluviômetro — captura ~71 % do volume total e perde ~36 % das semanas
chuvosas (≥ 20 mm) que a estação registrou. Isso é o comportamento
esperado de reanálise numa faixa costeira com convecção local intensa: o
modelo suaviza extremos.

### 4.2 Concordância na série agregada da cidade

| Métrica | Valor |
|---------|-------|
| n (semanas) | 72 |
| Pearson | **0,7787** |
| Spearman | **0,8626** |

A concordância sobe bastante quando se compara a série temporal da cidade
em vez de cada bairro isolado — exatamente o que a limitação da §3 prevê.

### 4.3 Concordância por bairro

71 bairros com ≥ 10 semanas comparáveis:

| Métrica | Pearson |
|---------|---------|
| Mediana | **0,7123** |
| Máximo | 0,7915 |
| Mínimo | **−0,0022** |

O mínimo praticamente nulo mostra que existe ao menos um bairro onde a
grade não acompanha nada do que o pluviômetro associado mediu — mais uma
evidência de que a grade não substitui o sensor onde o sensor existe.

## 5. Cobertura obtida

Depois da incorporação (`python -m src.enrich_gold_clima_grade`), na Gold de
191.478 linhas:

| Ano | com clima em grade | com clima de estação |
|-----|--------------------|----------------------|
| 2013–2023 | **100 %** | 0 % |
| 2024 | 100 % | 26,70 % |
| 2025 | 100 % | 52,15 % |

Total: **100 % das linhas** passam a ter precipitação, temperatura e
umidade em grade — contra 6,1151 % com clima de estação antes desta etapa.
As colunas de estação **não foram alteradas**: verificado que todas as 31
colunas pré-existentes da Gold permanecem idênticas valor a valor (só
`versao_schema_gold` mudou de `1.0` para `1.1`, e foram acrescentadas 15
colunas novas).

## 6. Variáveis incorporadas (11 de conteúdo + 4 de rastreabilidade)

`precipitacao_semana_grade_mm`, `precipitacao_2s_grade_mm`,
`precipitacao_3s_grade_mm`, `precipitacao_4s_grade_mm`,
`temperatura_media_grade_c`, `temperatura_minima_grade_c`,
`temperatura_maxima_grade_c`, `umidade_relativa_media_grade_pct`,
`dias_validos_precipitacao_grade_semana`,
`dias_validos_temperatura_grade_semana`, `cobertura_grade_semana` —
mais `fonte_clima_grade`, `celula_grade_precipitacao`,
`celula_grade_temperatura` e `_grade_processed_at`.

Notas de honestidade:

- `temperatura_minima_grade_c` é a **menor mínima diária da semana** (não a
  média das mínimas); simétrico para a máxima.
- `umidade_relativa_media_grade_pct` **não é derivada** por este projeto —
  vem pronta do ERA5-Land. Nenhuma fórmula psicrométrica foi aplicada.
- Acumulados de 2/3/4 semanas são janelas móveis de 14/21/28 dias
  terminando em `semana_epi_data_fim` da própria linha (regra de leakage
  idêntica à da camada de estação, com teste adversarial dedicado).
- `missing ≠ 0` preservado: semana sem dia válido fica `None` nos valores e
  `0` nos contadores de dias válidos.

## 7. Classificação e recomendação

**Classificação: B — utilizável com limitações.**

Utilizável para:

- descrever a **sazonalidade climática** de 2013–2025 (a série temporal que
  o projeto simplesmente não tinha);
- oferecer uma covariável climática temporal a um experimento de ML
  controlado;
- contextualizar a página *Clima × Dengue* sem restringi-la a 2024–2025.

**Não** utilizável para:

- afirmar diferença climática **entre bairros** (2 valores distintos por
  semana entre 94 bairros);
- substituir a estação onde existe estação (subestima 29 % do volume e
  perde 36 % das semanas chuvosas);
- ser chamada de "estação meteorológica do bairro" em qualquer texto.

**Recomendação aplicada:** incorporada à Gold como bloco de colunas
separado (`*_grade_*`), coexistindo com as colunas de estação, e submetida
ao experimento controlado de ML descrito em
`reports/ml/dengue_ranking_clima_experiment.md`. A expectativa *a priori*,
derivada da §3, é de ganho nulo ou marginal num produto que é um **ranking
entre bairros na mesma semana** — uma variável quase constante entre
bairros não tem como discriminá-los. O experimento existe para medir isso,
não para confirmar uma intuição.

## 8. Pendências humanas

- **CHIRPS (0,05°)** é a próxima candidata natural se um dia houver
  infraestrutura para ingestão raster: daria ~11 células em vez de 2, o que
  ainda é pouco, mas mensuravelmente melhor.
- **ERA5-Land via CDS direto** requer uma conta Copernicus (gratuita). Com
  credencial, valeria testar se o CDS serve precipitação ERA5-Land a 0,10°
  (o que o provedor intermediário não serve).
- Nenhuma das duas é necessária para o produto atual funcionar.
