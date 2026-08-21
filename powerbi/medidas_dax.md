# Medidas DAX sugeridas

Crie uma tabela de medidas dedicada (Modelagem → Nova Tabela → `Medidas = {}`)
e cole as fórmulas abaixo nela, em vez de anexar todas a
`fact_epidemiologia_semanal` — mantém o modelo organizado e evita medida
implícita.

## Casos e volume

```dax
Casos = SUM(fact_epidemiologia_semanal[casos])

Casos (4 semanas) =
CALCULATE(
    [Casos],
    DATESINPERIOD(
        dim_tempo[semana_epi_data_inicio],
        MAX(dim_tempo[semana_epi_data_inicio]),
        -28,
        DAY
    )
)

Casos período anterior =
CALCULATE([Casos], DATEADD(dim_tempo[semana_epi_data_inicio], -7, DAY))

Variação % =
VAR Atual = [Casos]
VAR Anterior = [Casos período anterior]
RETURN
    IF(
        ISBLANK(Anterior) || Anterior = 0,
        BLANK(),
        DIVIDE(Atual - Anterior, Anterior)
    )
```

## População e incidência — nunca somar população repetida por semana

`populacao_bairro_ano` está gravada em **toda linha semanal** de
`fact_epidemiologia_semanal` (mesmo valor repetido nas ~52-53 linhas do
ano) — se você fizer `SUM(populacao_bairro_ano)` num visual com o tempo no
eixo, o resultado soma o mesmo valor várias vezes. Use `AVERAGE` (todas as
linhas do mesmo bairro/ano têm o mesmo valor, então a média é igual ao
valor real) ou, melhor, agregue num contexto sem a dimensão de tempo:

```dax
População =
CALCULATE(
    AVERAGE(fact_epidemiologia_semanal[populacao_bairro_ano]),
    VALUES(dim_bairro[codigo_bairro])
)

Incidência por 100 mil =
VAR Casos_ = [Casos]
VAR Pop_ = [População]
RETURN
    IF(ISBLANK(Pop_) || Pop_ = 0, BLANK(), DIVIDE(Casos_, Pop_) * 100000)
```

**Nunca** `AVERAGE(fact_epidemiologia_semanal[incidencia_100k])` como
"incidência do período" — isso tira a média de taxas semanais já
calculadas, que não é a mesma coisa que casos-do-período/população (o
erro clássico de "não somar taxas" citado no pedido original, na direção
inversa: aqui é "não tirar média de taxas", mesmo princípio).

```dax
Incidência 4 semanas =
VAR Casos4s = [Casos (4 semanas)]
VAR Pop_ = [População]
RETURN
    IF(ISBLANK(Pop_) || Pop_ = 0, BLANK(), DIVIDE(Casos4s, Pop_) * 100000)
```

## Ranking

```dax
Ranking casos =
RANKX(ALL(dim_bairro[codigo_bairro]), [Casos], , DESC, DENSE)

Ranking incidência =
RANKX(ALL(dim_bairro[codigo_bairro]), [Incidência por 100 mil], , DESC, DENSE)
```

## Contexto temporal

```dax
Última semana disponível =
CALCULATE(
    MAX(dim_tempo[id_semana_epi]),
    ALL(dim_tempo)
)

Casos (última semana) =
CALCULATE([Casos], dim_tempo[id_semana_epi] = [Última semana disponível])
```

## Priorização experimental (usar com a mesma cautela do dashboard)

```dax
Score de priorização (candidato v1) =
AVERAGE(fact_priorizacao_backtest[score_prioridade])
```

**Nunca** crie uma medida chamada "Probabilidade de surto" ou formate
`score_prioridade`/`ranking` como percentual de confiança — são posição
relativa dentro do backtest retrospectivo do candidato congelado, não uma
previsão operacional (mesma regra do dashboard, `CLAUDE.md` §11 e
`reports/ml/dengue_ranking_evidence_validation.md`). Se publicar um
relatório com esta tabela, inclua o mesmo aviso do app técnico:
"Validação experimental — não representa ferramenta operacional de
previsão".
