# Associação clima × arboviroses (2013-2025)

Gerado por `python -m src.generate_climate_arbovirus_report` a partir de `dashboard/data/gold_arboviroses_clima_bairro.parquet`. Todos os números abaixo são reais, calculados por `src/eda/associacao_climatica.py` -- nenhum valor foi estimado ou arredondado à mão.

**Associação observada, nunca causalidade.** Chuva, temperatura e casos de arboviroses podem compartilhar sazonalidade sem existir relação causal direta entre eles. Nenhuma afirmação de causalidade é feita neste documento.

## Metodologia

- **Granularidade: Recife total, nunca bairro/RPA.** A reanálise em grade (ERA5/ERA5-Land, única fonte com cobertura real 2013-2025) resolve só 2 células de precipitação e 3 de temperatura para os 94 bairros (distância mediana de 8,06 km entre bairro e centro da célula) -- qualquer recorte territorial mais fino que a cidade produziria falsa precisão espacial.
- **Defasagem deslocada real**: correlação de Spearman entre a quantidade epidemiológica na semana `t` e a variável climática `t-k` semanas antes, para `k` de 0 a 12 semanas (`src.eda.associacao_climatica.calcular_lags_deslocados`) -- diferente da tabela de janelas cumulativas já publicada no painel (que correlaciona casos com chuva acumulada *até* a própria semana).
- **Casos vs. incidência**: calculados e reportados separadamente. Incidência = casos totais da cidade / população total da cidade no ano × 100.000 -- nunca a soma das incidências por bairro já calculadas.
- **Dessazonalização**: resíduo = valor menos a média histórica de todas as observações da mesma semana epidemiológica (1-53). Compara-se a correlação bruta com a correlação sobre os resíduos -- uma queda grande na versão ajustada sugere que a associação bruta é, em boa parte, sazonalidade compartilhada.
- **Seleção do "melhor" lag**: sempre pelo maior `|correlação de Spearman|` entre os lags com amostra confiável (n ≥ 30) -- nunca pelo menor p-valor.

## Dengue

Série semanal: 679 semanas (2013–2025), 109792 casos totais no período. Incidência disponível: sim.

### Precipitação (mm)

**Casos × Precipitação (mm)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1427 | 0.0002 | 679 | sim |
| 1 | 0.1453 | 0.0001 | 678 | sim |
| 2 | 0.1719 | 0.0000 | 677 | sim |
| 3 | 0.1705 | 0.0000 | 676 | sim |
| 4 | 0.1665 | 0.0000 | 675 | sim |
| 5 | 0.1558 | 0.0000 | 674 | sim |
| 6 | 0.1581 | 0.0000 | 673 | sim |
| 7 | 0.1474 | 0.0001 | 672 | sim |
| 8 | 0.1596 | 0.0000 | 671 | sim |
| 9 | 0.1397 | 0.0003 | 670 | sim |
| 10 | 0.1233 | 0.0014 | 669 | sim |
| 11 | 0.0990 | 0.0105 | 668 | sim |
| 12 | 0.0969 | 0.0122 | 667 | sim |

A maior associação observada ocorreu com 2 semanas de defasagem (Spearman=0.17, n=677), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Precipitação (mm)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1484 | 0.0001 | 679 | sim |
| 1 | 0.1515 | 0.0001 | 678 | sim |
| 2 | 0.1778 | 0.0000 | 677 | sim |
| 3 | 0.1765 | 0.0000 | 676 | sim |
| 4 | 0.1735 | 0.0000 | 675 | sim |
| 5 | 0.1621 | 0.0000 | 674 | sim |
| 6 | 0.1647 | 0.0000 | 673 | sim |
| 7 | 0.1541 | 0.0001 | 672 | sim |
| 8 | 0.1665 | 0.0000 | 671 | sim |
| 9 | 0.1457 | 0.0002 | 670 | sim |
| 10 | 0.1298 | 0.0008 | 669 | sim |
| 11 | 0.1056 | 0.0063 | 668 | sim |
| 12 | 0.1032 | 0.0076 | 667 | sim |

A maior associação observada ocorreu com 2 semanas de defasagem (Spearman=0.18, n=677), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 2) e incidência (lag 2) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × precipitação (mm))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.1427 | -0.0151 | 679 | 679 |
| 1 | 0.1453 | -0.0016 | 678 | 678 |
| 2 | 0.1719 | 0.0141 | 677 | 677 |
| 3 | 0.1705 | 0.0034 | 676 | 676 |
| 4 | 0.1665 | -0.0118 | 675 | 675 |
| 5 | 0.1558 | -0.0171 | 674 | 674 |
| 6 | 0.1581 | -0.0501 | 673 | 673 |
| 7 | 0.1474 | -0.0304 | 672 | 672 |
| 8 | 0.1596 | -0.0336 | 671 | 671 |
| 9 | 0.1397 | -0.0445 | 670 | 670 |
| 10 | 0.1233 | -0.0672 | 669 | 669 |
| 11 | 0.0990 | -0.0592 | 668 | 668 |
| 12 | 0.0969 | -0.0607 | 667 | 667 |

### Temperatura média (°C)

**Casos × Temperatura média (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.1075 | 0.0051 | 679 | sim |
| 1 | -0.0888 | 0.0207 | 678 | sim |
| 2 | -0.0649 | 0.0913 | 677 | sim |
| 3 | -0.0454 | 0.2389 | 676 | sim |
| 4 | -0.0107 | 0.7805 | 675 | sim |
| 5 | 0.0187 | 0.6281 | 674 | sim |
| 6 | 0.0394 | 0.3069 | 673 | sim |
| 7 | 0.0726 | 0.0601 | 672 | sim |
| 8 | 0.0935 | 0.0154 | 671 | sim |
| 9 | 0.1238 | 0.0013 | 670 | sim |
| 10 | 0.1595 | 0.0000 | 669 | sim |
| 11 | 0.1883 | 0.0000 | 668 | sim |
| 12 | 0.2037 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.20, n=667), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura média (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.1106 | 0.0039 | 679 | sim |
| 1 | -0.0921 | 0.0164 | 678 | sim |
| 2 | -0.0677 | 0.0785 | 677 | sim |
| 3 | -0.0479 | 0.2135 | 676 | sim |
| 4 | -0.0130 | 0.7358 | 675 | sim |
| 5 | 0.0174 | 0.6521 | 674 | sim |
| 6 | 0.0383 | 0.3208 | 673 | sim |
| 7 | 0.0719 | 0.0624 | 672 | sim |
| 8 | 0.0934 | 0.0155 | 671 | sim |
| 9 | 0.1242 | 0.0013 | 670 | sim |
| 10 | 0.1598 | 0.0000 | 669 | sim |
| 11 | 0.1890 | 0.0000 | 668 | sim |
| 12 | 0.2048 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.20, n=667), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 12) e incidência (lag 12) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura média (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.1075 | 0.1230 | 679 | 679 |
| 1 | -0.0888 | 0.1052 | 678 | 678 |
| 2 | -0.0649 | 0.0994 | 677 | 677 |
| 3 | -0.0454 | 0.0929 | 676 | 676 |
| 4 | -0.0107 | 0.0928 | 675 | 675 |
| 5 | 0.0187 | 0.0913 | 674 | 674 |
| 6 | 0.0394 | 0.0931 | 673 | 673 |
| 7 | 0.0726 | 0.0789 | 672 | 672 |
| 8 | 0.0935 | 0.0732 | 671 | 671 |
| 9 | 0.1238 | 0.0722 | 670 | 670 |
| 10 | 0.1595 | 0.0690 | 669 | 669 |
| 11 | 0.1883 | 0.0589 | 668 | 668 |
| 12 | 0.2037 | 0.0537 | 667 | 667 |

### Temperatura mínima (°C)

**Casos × Temperatura mínima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0778 | 0.0428 | 679 | sim |
| 1 | -0.0580 | 0.1311 | 678 | sim |
| 2 | -0.0371 | 0.3352 | 677 | sim |
| 3 | -0.0139 | 0.7184 | 676 | sim |
| 4 | 0.0181 | 0.6396 | 675 | sim |
| 5 | 0.0535 | 0.1654 | 674 | sim |
| 6 | 0.0746 | 0.0532 | 673 | sim |
| 7 | 0.1027 | 0.0077 | 672 | sim |
| 8 | 0.1254 | 0.0011 | 671 | sim |
| 9 | 0.1595 | 0.0000 | 670 | sim |
| 10 | 0.1854 | 0.0000 | 669 | sim |
| 11 | 0.2047 | 0.0000 | 668 | sim |
| 12 | 0.2221 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.22, n=667), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura mínima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0818 | 0.0332 | 679 | sim |
| 1 | -0.0618 | 0.1078 | 678 | sim |
| 2 | -0.0402 | 0.2962 | 677 | sim |
| 3 | -0.0169 | 0.6618 | 676 | sim |
| 4 | 0.0154 | 0.6889 | 675 | sim |
| 5 | 0.0513 | 0.1834 | 674 | sim |
| 6 | 0.0724 | 0.0603 | 673 | sim |
| 7 | 0.1019 | 0.0082 | 672 | sim |
| 8 | 0.1244 | 0.0012 | 671 | sim |
| 9 | 0.1588 | 0.0000 | 670 | sim |
| 10 | 0.1849 | 0.0000 | 669 | sim |
| 11 | 0.2042 | 0.0000 | 668 | sim |
| 12 | 0.2217 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.22, n=667), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 12) e incidência (lag 12) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura mínima (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.0778 | 0.1089 | 679 | 679 |
| 1 | -0.0580 | 0.0984 | 678 | 678 |
| 2 | -0.0371 | 0.0966 | 677 | 677 |
| 3 | -0.0139 | 0.0932 | 676 | 676 |
| 4 | 0.0181 | 0.0879 | 675 | 675 |
| 5 | 0.0535 | 0.1085 | 674 | 674 |
| 6 | 0.0746 | 0.1009 | 673 | 673 |
| 7 | 0.1027 | 0.0931 | 672 | 672 |
| 8 | 0.1254 | 0.0783 | 671 | 671 |
| 9 | 0.1595 | 0.0790 | 670 | 670 |
| 10 | 0.1854 | 0.0717 | 669 | 669 |
| 11 | 0.2047 | 0.0596 | 668 | 668 |
| 12 | 0.2221 | 0.0538 | 667 | 667 |

### Temperatura máxima (°C)

**Casos × Temperatura máxima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.1088 | 0.0045 | 679 | sim |
| 1 | -0.0954 | 0.0130 | 678 | sim |
| 2 | -0.0711 | 0.0644 | 677 | sim |
| 3 | -0.0605 | 0.1161 | 676 | sim |
| 4 | -0.0291 | 0.4502 | 675 | sim |
| 5 | -0.0135 | 0.7268 | 674 | sim |
| 6 | 0.0058 | 0.8801 | 673 | sim |
| 7 | 0.0383 | 0.3209 | 672 | sim |
| 8 | 0.0625 | 0.1059 | 671 | sim |
| 9 | 0.0936 | 0.0154 | 670 | sim |
| 10 | 0.1276 | 0.0009 | 669 | sim |
| 11 | 0.1543 | 0.0001 | 668 | sim |
| 12 | 0.1688 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.17, n=667), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura máxima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.1119 | 0.0035 | 679 | sim |
| 1 | -0.0986 | 0.0102 | 678 | sim |
| 2 | -0.0740 | 0.0543 | 677 | sim |
| 3 | -0.0632 | 0.1006 | 676 | sim |
| 4 | -0.0314 | 0.4157 | 675 | sim |
| 5 | -0.0153 | 0.6921 | 674 | sim |
| 6 | 0.0045 | 0.9082 | 673 | sim |
| 7 | 0.0371 | 0.3370 | 672 | sim |
| 8 | 0.0620 | 0.1085 | 671 | sim |
| 9 | 0.0935 | 0.0155 | 670 | sim |
| 10 | 0.1273 | 0.0010 | 669 | sim |
| 11 | 0.1545 | 0.0001 | 668 | sim |
| 12 | 0.1695 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.17, n=667), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 12) e incidência (lag 12) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura máxima (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.1088 | 0.1238 | 679 | 679 |
| 1 | -0.0954 | 0.1076 | 678 | 678 |
| 2 | -0.0711 | 0.1079 | 677 | 677 |
| 3 | -0.0605 | 0.0990 | 676 | 676 |
| 4 | -0.0291 | 0.0977 | 675 | 675 |
| 5 | -0.0135 | 0.0943 | 674 | 674 |
| 6 | 0.0058 | 0.1030 | 673 | 673 |
| 7 | 0.0383 | 0.0930 | 672 | 672 |
| 8 | 0.0625 | 0.0979 | 671 | 671 |
| 9 | 0.0936 | 0.1009 | 670 | 670 |
| 10 | 0.1276 | 0.0905 | 669 | 669 |
| 11 | 0.1543 | 0.0708 | 668 | 668 |
| 12 | 0.1688 | 0.0694 | 667 | 667 |

### Umidade relativa (%)

**Casos × Umidade relativa (%)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1710 | 0.0000 | 679 | sim |
| 1 | 0.1708 | 0.0000 | 678 | sim |
| 2 | 0.1782 | 0.0000 | 677 | sim |
| 3 | 0.1825 | 0.0000 | 676 | sim |
| 4 | 0.1682 | 0.0000 | 675 | sim |
| 5 | 0.1602 | 0.0000 | 674 | sim |
| 6 | 0.1569 | 0.0000 | 673 | sim |
| 7 | 0.1410 | 0.0002 | 672 | sim |
| 8 | 0.1325 | 0.0006 | 671 | sim |
| 9 | 0.1101 | 0.0043 | 670 | sim |
| 10 | 0.0923 | 0.0169 | 669 | sim |
| 11 | 0.0690 | 0.0748 | 668 | sim |
| 12 | 0.0546 | 0.1593 | 667 | sim |

A maior associação observada ocorreu com 3 semanas de defasagem (Spearman=0.18, n=676), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Umidade relativa (%)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1742 | 0.0000 | 679 | sim |
| 1 | 0.1744 | 0.0000 | 678 | sim |
| 2 | 0.1817 | 0.0000 | 677 | sim |
| 3 | 0.1861 | 0.0000 | 676 | sim |
| 4 | 0.1721 | 0.0000 | 675 | sim |
| 5 | 0.1636 | 0.0000 | 674 | sim |
| 6 | 0.1608 | 0.0000 | 673 | sim |
| 7 | 0.1448 | 0.0002 | 672 | sim |
| 8 | 0.1362 | 0.0004 | 671 | sim |
| 9 | 0.1131 | 0.0034 | 670 | sim |
| 10 | 0.0958 | 0.0132 | 669 | sim |
| 11 | 0.0724 | 0.0613 | 668 | sim |
| 12 | 0.0575 | 0.1377 | 667 | sim |

A maior associação observada ocorreu com 3 semanas de defasagem (Spearman=0.19, n=676), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 3) e incidência (lag 3) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × umidade relativa (%))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.1710 | -0.0876 | 679 | 679 |
| 1 | 0.1708 | -0.0730 | 678 | 678 |
| 2 | 0.1782 | -0.0551 | 677 | 677 |
| 3 | 0.1825 | -0.0549 | 676 | 676 |
| 4 | 0.1682 | -0.0530 | 675 | 675 |
| 5 | 0.1602 | -0.0532 | 674 | 674 |
| 6 | 0.1569 | -0.0551 | 673 | 673 |
| 7 | 0.1410 | -0.0413 | 672 | 672 |
| 8 | 0.1325 | -0.0369 | 671 | 671 |
| 9 | 0.1101 | -0.0445 | 670 | 670 |
| 10 | 0.0923 | -0.0380 | 669 | 669 |
| 11 | 0.0690 | -0.0374 | 668 | 668 |
| 12 | 0.0546 | -0.0339 | 667 | 667 |

## Zika

Série semanal: 679 semanas (2013–2025), 7160 casos totais no período. Incidência disponível: sim.

### Precipitação (mm)

**Casos × Precipitação (mm)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1202 | 0.0017 | 679 | sim |
| 1 | 0.1197 | 0.0018 | 678 | sim |
| 2 | 0.1201 | 0.0017 | 677 | sim |
| 3 | 0.1103 | 0.0041 | 676 | sim |
| 4 | 0.1355 | 0.0004 | 675 | sim |
| 5 | 0.1388 | 0.0003 | 674 | sim |
| 6 | 0.1269 | 0.0010 | 673 | sim |
| 7 | 0.1402 | 0.0003 | 672 | sim |
| 8 | 0.1493 | 0.0001 | 671 | sim |
| 9 | 0.1461 | 0.0001 | 670 | sim |
| 10 | 0.1341 | 0.0005 | 669 | sim |
| 11 | 0.0915 | 0.0181 | 668 | sim |
| 12 | 0.0949 | 0.0142 | 667 | sim |

A maior associação observada ocorreu com 8 semanas de defasagem (Spearman=0.15, n=671), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Precipitação (mm)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1215 | 0.0015 | 679 | sim |
| 1 | 0.1226 | 0.0014 | 678 | sim |
| 2 | 0.1222 | 0.0014 | 677 | sim |
| 3 | 0.1123 | 0.0034 | 676 | sim |
| 4 | 0.1377 | 0.0003 | 675 | sim |
| 5 | 0.1421 | 0.0002 | 674 | sim |
| 6 | 0.1303 | 0.0007 | 673 | sim |
| 7 | 0.1438 | 0.0002 | 672 | sim |
| 8 | 0.1514 | 0.0001 | 671 | sim |
| 9 | 0.1494 | 0.0001 | 670 | sim |
| 10 | 0.1395 | 0.0003 | 669 | sim |
| 11 | 0.0968 | 0.0123 | 668 | sim |
| 12 | 0.0996 | 0.0101 | 667 | sim |

A maior associação observada ocorreu com 8 semanas de defasagem (Spearman=0.15, n=671), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 8) e incidência (lag 8) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × precipitação (mm))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.1202 | 0.0385 | 679 | 679 |
| 1 | 0.1197 | 0.0574 | 678 | 678 |
| 2 | 0.1201 | 0.0427 | 677 | 677 |
| 3 | 0.1103 | 0.0391 | 676 | 676 |
| 4 | 0.1355 | 0.0581 | 675 | 675 |
| 5 | 0.1388 | 0.0371 | 674 | 674 |
| 6 | 0.1269 | 0.0387 | 673 | 673 |
| 7 | 0.1402 | 0.0262 | 672 | 672 |
| 8 | 0.1493 | 0.0322 | 671 | 671 |
| 9 | 0.1461 | 0.0183 | 670 | 670 |
| 10 | 0.1341 | -0.0022 | 669 | 669 |
| 11 | 0.0915 | -0.0305 | 668 | 668 |
| 12 | 0.0949 | -0.0274 | 667 | 667 |

### Temperatura média (°C)

**Casos × Temperatura média (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0214 | 0.5775 | 679 | sim |
| 1 | -0.0082 | 0.8315 | 678 | sim |
| 2 | 0.0112 | 0.7703 | 677 | sim |
| 3 | 0.0212 | 0.5829 | 676 | sim |
| 4 | 0.0275 | 0.4762 | 675 | sim |
| 5 | 0.0409 | 0.2889 | 674 | sim |
| 6 | 0.0542 | 0.1598 | 673 | sim |
| 7 | 0.0542 | 0.1607 | 672 | sim |
| 8 | 0.0657 | 0.0892 | 671 | sim |
| 9 | 0.0824 | 0.0330 | 670 | sim |
| 10 | 0.1053 | 0.0064 | 669 | sim |
| 11 | 0.1341 | 0.0005 | 668 | sim |
| 12 | 0.1424 | 0.0002 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.14, n=667), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura média (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0236 | 0.5394 | 679 | sim |
| 1 | -0.0114 | 0.7675 | 678 | sim |
| 2 | 0.0083 | 0.8286 | 677 | sim |
| 3 | 0.0182 | 0.6366 | 676 | sim |
| 4 | 0.0240 | 0.5328 | 675 | sim |
| 5 | 0.0374 | 0.3329 | 674 | sim |
| 6 | 0.0503 | 0.1928 | 673 | sim |
| 7 | 0.0506 | 0.1903 | 672 | sim |
| 8 | 0.0621 | 0.1082 | 671 | sim |
| 9 | 0.0781 | 0.0434 | 670 | sim |
| 10 | 0.1004 | 0.0093 | 669 | sim |
| 11 | 0.1294 | 0.0008 | 668 | sim |
| 12 | 0.1380 | 0.0004 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.14, n=667), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 12) e incidência (lag 12) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura média (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.0214 | 0.0493 | 679 | 679 |
| 1 | -0.0082 | 0.0565 | 678 | 678 |
| 2 | 0.0112 | 0.0609 | 677 | 677 |
| 3 | 0.0212 | 0.0454 | 676 | 676 |
| 4 | 0.0275 | 0.0397 | 675 | 675 |
| 5 | 0.0409 | 0.0399 | 674 | 674 |
| 6 | 0.0542 | 0.0428 | 673 | 673 |
| 7 | 0.0542 | 0.0293 | 672 | 672 |
| 8 | 0.0657 | 0.0440 | 671 | 671 |
| 9 | 0.0824 | 0.0342 | 670 | 670 |
| 10 | 0.1053 | 0.0568 | 669 | 669 |
| 11 | 0.1341 | 0.0781 | 668 | 668 |
| 12 | 0.1424 | 0.0789 | 667 | 667 |

### Temperatura mínima (°C)

**Casos × Temperatura mínima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.0240 | 0.5326 | 679 | sim |
| 1 | 0.0332 | 0.3884 | 678 | sim |
| 2 | 0.0519 | 0.1770 | 677 | sim |
| 3 | 0.0548 | 0.1544 | 676 | sim |
| 4 | 0.0607 | 0.1149 | 675 | sim |
| 5 | 0.0807 | 0.0361 | 674 | sim |
| 6 | 0.0952 | 0.0135 | 673 | sim |
| 7 | 0.0979 | 0.0111 | 672 | sim |
| 8 | 0.1045 | 0.0067 | 671 | sim |
| 9 | 0.1265 | 0.0010 | 670 | sim |
| 10 | 0.1428 | 0.0002 | 669 | sim |
| 11 | 0.1755 | 0.0000 | 668 | sim |
| 12 | 0.1738 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 11 semanas de defasagem (Spearman=0.18, n=668), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura mínima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.0201 | 0.6015 | 679 | sim |
| 1 | 0.0289 | 0.4523 | 678 | sim |
| 2 | 0.0481 | 0.2109 | 677 | sim |
| 3 | 0.0504 | 0.1907 | 676 | sim |
| 4 | 0.0559 | 0.1466 | 675 | sim |
| 5 | 0.0756 | 0.0497 | 674 | sim |
| 6 | 0.0899 | 0.0197 | 673 | sim |
| 7 | 0.0934 | 0.0155 | 672 | sim |
| 8 | 0.0989 | 0.0104 | 671 | sim |
| 9 | 0.1209 | 0.0017 | 670 | sim |
| 10 | 0.1375 | 0.0004 | 669 | sim |
| 11 | 0.1699 | 0.0000 | 668 | sim |
| 12 | 0.1678 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 11 semanas de defasagem (Spearman=0.17, n=668), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 11) e incidência (lag 11) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura mínima (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.0240 | 0.0909 | 679 | 679 |
| 1 | 0.0332 | 0.0949 | 678 | 678 |
| 2 | 0.0519 | 0.0879 | 677 | 677 |
| 3 | 0.0548 | 0.0670 | 676 | 676 |
| 4 | 0.0607 | 0.0532 | 675 | 675 |
| 5 | 0.0807 | 0.0785 | 674 | 674 |
| 6 | 0.0952 | 0.0913 | 673 | 673 |
| 7 | 0.0979 | 0.0968 | 672 | 672 |
| 8 | 0.1045 | 0.0875 | 671 | 671 |
| 9 | 0.1265 | 0.0766 | 670 | 670 |
| 10 | 0.1428 | 0.1026 | 669 | 669 |
| 11 | 0.1755 | 0.1127 | 668 | 668 |
| 12 | 0.1738 | 0.1271 | 667 | 667 |

### Temperatura máxima (°C)

**Casos × Temperatura máxima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0367 | 0.3400 | 679 | sim |
| 1 | -0.0290 | 0.4509 | 678 | sim |
| 2 | -0.0117 | 0.7617 | 677 | sim |
| 3 | 0.0008 | 0.9833 | 676 | sim |
| 4 | 0.0037 | 0.9226 | 675 | sim |
| 5 | 0.0117 | 0.7622 | 674 | sim |
| 6 | 0.0270 | 0.4842 | 673 | sim |
| 7 | 0.0241 | 0.5324 | 672 | sim |
| 8 | 0.0444 | 0.2508 | 671 | sim |
| 9 | 0.0597 | 0.1229 | 670 | sim |
| 10 | 0.0870 | 0.0245 | 669 | sim |
| 11 | 0.1102 | 0.0043 | 668 | sim |
| 12 | 0.1216 | 0.0017 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.12, n=667), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura máxima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0383 | 0.3184 | 679 | sim |
| 1 | -0.0315 | 0.4127 | 678 | sim |
| 2 | -0.0142 | 0.7116 | 677 | sim |
| 3 | -0.0016 | 0.9661 | 676 | sim |
| 4 | 0.0009 | 0.9812 | 675 | sim |
| 5 | 0.0092 | 0.8124 | 674 | sim |
| 6 | 0.0241 | 0.5324 | 673 | sim |
| 7 | 0.0216 | 0.5755 | 672 | sim |
| 8 | 0.0417 | 0.2809 | 671 | sim |
| 9 | 0.0560 | 0.1478 | 670 | sim |
| 10 | 0.0823 | 0.0334 | 669 | sim |
| 11 | 0.1058 | 0.0062 | 668 | sim |
| 12 | 0.1176 | 0.0024 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.12, n=667), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 12) e incidência (lag 12) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura máxima (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.0367 | 0.0336 | 679 | 679 |
| 1 | -0.0290 | 0.0323 | 678 | 678 |
| 2 | -0.0117 | 0.0463 | 677 | 677 |
| 3 | 0.0008 | 0.0476 | 676 | 676 |
| 4 | 0.0037 | 0.0307 | 675 | 675 |
| 5 | 0.0117 | 0.0241 | 674 | 674 |
| 6 | 0.0270 | 0.0356 | 673 | 673 |
| 7 | 0.0241 | 0.0092 | 672 | 672 |
| 8 | 0.0444 | 0.0410 | 671 | 671 |
| 9 | 0.0597 | 0.0431 | 670 | 670 |
| 10 | 0.0870 | 0.0572 | 669 | 669 |
| 11 | 0.1102 | 0.0587 | 668 | 668 |
| 12 | 0.1216 | 0.0682 | 667 | 667 |

### Umidade relativa (%)

**Casos × Umidade relativa (%)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.0902 | 0.0187 | 679 | sim |
| 1 | 0.0869 | 0.0236 | 678 | sim |
| 2 | 0.0785 | 0.0412 | 677 | sim |
| 3 | 0.0814 | 0.0344 | 676 | sim |
| 4 | 0.0954 | 0.0132 | 675 | sim |
| 5 | 0.0859 | 0.0258 | 674 | sim |
| 6 | 0.0832 | 0.0309 | 673 | sim |
| 7 | 0.0945 | 0.0142 | 672 | sim |
| 8 | 0.1060 | 0.0060 | 671 | sim |
| 9 | 0.0819 | 0.0340 | 670 | sim |
| 10 | 0.0756 | 0.0507 | 669 | sim |
| 11 | 0.0337 | 0.3839 | 668 | sim |
| 12 | 0.0346 | 0.3716 | 667 | sim |

A maior associação observada ocorreu com 8 semanas de defasagem (Spearman=0.11, n=671), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Umidade relativa (%)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.0891 | 0.0202 | 679 | sim |
| 1 | 0.0865 | 0.0243 | 678 | sim |
| 2 | 0.0780 | 0.0424 | 677 | sim |
| 3 | 0.0813 | 0.0346 | 676 | sim |
| 4 | 0.0955 | 0.0130 | 675 | sim |
| 5 | 0.0866 | 0.0245 | 674 | sim |
| 6 | 0.0839 | 0.0295 | 673 | sim |
| 7 | 0.0948 | 0.0140 | 672 | sim |
| 8 | 0.1062 | 0.0059 | 671 | sim |
| 9 | 0.0837 | 0.0302 | 670 | sim |
| 10 | 0.0781 | 0.0435 | 669 | sim |
| 11 | 0.0356 | 0.3588 | 668 | sim |
| 12 | 0.0371 | 0.3392 | 667 | sim |

A maior associação observada ocorreu com 8 semanas de defasagem (Spearman=0.11, n=671), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 8) e incidência (lag 8) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × umidade relativa (%))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.0902 | -0.0073 | 679 | 679 |
| 1 | 0.0869 | -0.0056 | 678 | 678 |
| 2 | 0.0785 | -0.0029 | 677 | 677 |
| 3 | 0.0814 | 0.0179 | 676 | 676 |
| 4 | 0.0954 | 0.0411 | 675 | 675 |
| 5 | 0.0859 | 0.0359 | 674 | 674 |
| 6 | 0.0832 | 0.0419 | 673 | 673 |
| 7 | 0.0945 | 0.0483 | 672 | 672 |
| 8 | 0.1060 | 0.0620 | 671 | 671 |
| 9 | 0.0819 | 0.0519 | 670 | 670 |
| 10 | 0.0756 | 0.0344 | 669 | 669 |
| 11 | 0.0337 | 0.0017 | 668 | 668 |
| 12 | 0.0346 | 0.0244 | 667 | 667 |

## Chikungunya

Série semanal: 679 semanas (2013–2025), 39552 casos totais no período. Incidência disponível: sim.

### Precipitação (mm)

**Casos × Precipitação (mm)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.0854 | 0.0261 | 679 | sim |
| 1 | 0.0874 | 0.0228 | 678 | sim |
| 2 | 0.1050 | 0.0063 | 677 | sim |
| 3 | 0.1155 | 0.0026 | 676 | sim |
| 4 | 0.1446 | 0.0002 | 675 | sim |
| 5 | 0.1509 | 0.0001 | 674 | sim |
| 6 | 0.1509 | 0.0001 | 673 | sim |
| 7 | 0.1624 | 0.0000 | 672 | sim |
| 8 | 0.1621 | 0.0000 | 671 | sim |
| 9 | 0.1667 | 0.0000 | 670 | sim |
| 10 | 0.1701 | 0.0000 | 669 | sim |
| 11 | 0.1531 | 0.0001 | 668 | sim |
| 12 | 0.1578 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 10 semanas de defasagem (Spearman=0.17, n=669), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Precipitação (mm)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.0885 | 0.0211 | 679 | sim |
| 1 | 0.0910 | 0.0178 | 678 | sim |
| 2 | 0.1085 | 0.0047 | 677 | sim |
| 3 | 0.1191 | 0.0019 | 676 | sim |
| 4 | 0.1477 | 0.0001 | 675 | sim |
| 5 | 0.1546 | 0.0001 | 674 | sim |
| 6 | 0.1537 | 0.0001 | 673 | sim |
| 7 | 0.1656 | 0.0000 | 672 | sim |
| 8 | 0.1648 | 0.0000 | 671 | sim |
| 9 | 0.1694 | 0.0000 | 670 | sim |
| 10 | 0.1732 | 0.0000 | 669 | sim |
| 11 | 0.1568 | 0.0000 | 668 | sim |
| 12 | 0.1608 | 0.0000 | 667 | sim |

A maior associação observada ocorreu com 10 semanas de defasagem (Spearman=0.17, n=669), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 10) e incidência (lag 10) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × precipitação (mm))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.0854 | 0.0652 | 679 | 679 |
| 1 | 0.0874 | 0.0809 | 678 | 678 |
| 2 | 0.1050 | 0.0928 | 677 | 677 |
| 3 | 0.1155 | 0.0869 | 676 | 676 |
| 4 | 0.1446 | 0.0964 | 675 | 675 |
| 5 | 0.1509 | 0.1000 | 674 | 674 |
| 6 | 0.1509 | 0.0862 | 673 | 673 |
| 7 | 0.1624 | 0.0932 | 672 | 672 |
| 8 | 0.1621 | 0.0815 | 671 | 671 |
| 9 | 0.1667 | 0.0892 | 670 | 670 |
| 10 | 0.1701 | 0.0741 | 669 | 669 |
| 11 | 0.1531 | 0.0701 | 668 | 668 |
| 12 | 0.1578 | 0.0609 | 667 | 667 |

### Temperatura média (°C)

**Casos × Temperatura média (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0859 | 0.0253 | 679 | sim |
| 1 | -0.0855 | 0.0260 | 678 | sim |
| 2 | -0.0787 | 0.0406 | 677 | sim |
| 3 | -0.0824 | 0.0323 | 676 | sim |
| 4 | -0.0758 | 0.0490 | 675 | sim |
| 5 | -0.0647 | 0.0931 | 674 | sim |
| 6 | -0.0510 | 0.1866 | 673 | sim |
| 7 | -0.0342 | 0.3758 | 672 | sim |
| 8 | -0.0189 | 0.6241 | 671 | sim |
| 9 | -0.0031 | 0.9368 | 670 | sim |
| 10 | 0.0205 | 0.5970 | 669 | sim |
| 11 | 0.0509 | 0.1888 | 668 | sim |
| 12 | 0.0741 | 0.0559 | 667 | sim |

A maior associação observada ocorreu com 0 semanas de defasagem (Spearman=-0.09, n=679), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura média (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0867 | 0.0238 | 679 | sim |
| 1 | -0.0866 | 0.0242 | 678 | sim |
| 2 | -0.0796 | 0.0384 | 677 | sim |
| 3 | -0.0833 | 0.0303 | 676 | sim |
| 4 | -0.0766 | 0.0467 | 675 | sim |
| 5 | -0.0656 | 0.0889 | 674 | sim |
| 6 | -0.0517 | 0.1805 | 673 | sim |
| 7 | -0.0350 | 0.3645 | 672 | sim |
| 8 | -0.0195 | 0.6146 | 671 | sim |
| 9 | -0.0037 | 0.9242 | 670 | sim |
| 10 | 0.0195 | 0.6146 | 669 | sim |
| 11 | 0.0498 | 0.1985 | 668 | sim |
| 12 | 0.0731 | 0.0592 | 667 | sim |

A maior associação observada ocorreu com 0 semanas de defasagem (Spearman=-0.09, n=679), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 0) e incidência (lag 0) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura média (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.0859 | 0.0643 | 679 | 679 |
| 1 | -0.0855 | 0.0462 | 678 | 678 |
| 2 | -0.0787 | 0.0511 | 677 | 677 |
| 3 | -0.0824 | 0.0344 | 676 | 676 |
| 4 | -0.0758 | 0.0271 | 675 | 675 |
| 5 | -0.0647 | 0.0242 | 674 | 674 |
| 6 | -0.0510 | 0.0212 | 673 | 673 |
| 7 | -0.0342 | 0.0203 | 672 | 672 |
| 8 | -0.0189 | 0.0124 | 671 | 671 |
| 9 | -0.0031 | 0.0076 | 670 | 670 |
| 10 | 0.0205 | 0.0194 | 669 | 669 |
| 11 | 0.0509 | 0.0332 | 668 | 668 |
| 12 | 0.0741 | 0.0409 | 667 | 667 |

### Temperatura mínima (°C)

**Casos × Temperatura mínima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0612 | 0.1113 | 679 | sim |
| 1 | -0.0606 | 0.1151 | 678 | sim |
| 2 | -0.0611 | 0.1123 | 677 | sim |
| 3 | -0.0569 | 0.1396 | 676 | sim |
| 4 | -0.0516 | 0.1809 | 675 | sim |
| 5 | -0.0326 | 0.3977 | 674 | sim |
| 6 | -0.0264 | 0.4936 | 673 | sim |
| 7 | 0.0042 | 0.9131 | 672 | sim |
| 8 | 0.0163 | 0.6736 | 671 | sim |
| 9 | 0.0309 | 0.4240 | 670 | sim |
| 10 | 0.0575 | 0.1374 | 669 | sim |
| 11 | 0.0847 | 0.0286 | 668 | sim |
| 12 | 0.1085 | 0.0050 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.11, n=667), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura mínima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0632 | 0.0997 | 679 | sim |
| 1 | -0.0626 | 0.1034 | 678 | sim |
| 2 | -0.0627 | 0.1030 | 677 | sim |
| 3 | -0.0585 | 0.1285 | 676 | sim |
| 4 | -0.0531 | 0.1679 | 675 | sim |
| 5 | -0.0341 | 0.3763 | 674 | sim |
| 6 | -0.0284 | 0.4627 | 673 | sim |
| 7 | 0.0023 | 0.9532 | 672 | sim |
| 8 | 0.0145 | 0.7078 | 671 | sim |
| 9 | 0.0293 | 0.4491 | 670 | sim |
| 10 | 0.0554 | 0.1523 | 669 | sim |
| 11 | 0.0826 | 0.0328 | 668 | sim |
| 12 | 0.1063 | 0.0060 | 667 | sim |

A maior associação observada ocorreu com 12 semanas de defasagem (Spearman=0.11, n=667), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 12) e incidência (lag 12) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura mínima (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.0612 | 0.0667 | 679 | 679 |
| 1 | -0.0606 | 0.0567 | 678 | 678 |
| 2 | -0.0611 | 0.0486 | 677 | 677 |
| 3 | -0.0569 | 0.0429 | 676 | 676 |
| 4 | -0.0516 | 0.0348 | 675 | 675 |
| 5 | -0.0326 | 0.0490 | 674 | 674 |
| 6 | -0.0264 | 0.0377 | 673 | 673 |
| 7 | 0.0042 | 0.0499 | 672 | 672 |
| 8 | 0.0163 | 0.0373 | 671 | 671 |
| 9 | 0.0309 | 0.0353 | 670 | 670 |
| 10 | 0.0575 | 0.0491 | 669 | 669 |
| 11 | 0.0847 | 0.0509 | 668 | 668 |
| 12 | 0.1085 | 0.0584 | 667 | 667 |

### Temperatura máxima (°C)

**Casos × Temperatura máxima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0942 | 0.0141 | 679 | sim |
| 1 | -0.0972 | 0.0113 | 678 | sim |
| 2 | -0.0862 | 0.0250 | 677 | sim |
| 3 | -0.0938 | 0.0147 | 676 | sim |
| 4 | -0.0911 | 0.0179 | 675 | sim |
| 5 | -0.0824 | 0.0325 | 674 | sim |
| 6 | -0.0710 | 0.0657 | 673 | sim |
| 7 | -0.0520 | 0.1779 | 672 | sim |
| 8 | -0.0439 | 0.2559 | 671 | sim |
| 9 | -0.0227 | 0.5568 | 670 | sim |
| 10 | -0.0007 | 0.9851 | 669 | sim |
| 11 | 0.0278 | 0.4734 | 668 | sim |
| 12 | 0.0482 | 0.2137 | 667 | sim |

A maior associação observada ocorreu com 1 semana de defasagem (Spearman=-0.10, n=678), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Temperatura máxima (°C)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | -0.0951 | 0.0132 | 679 | sim |
| 1 | -0.0982 | 0.0105 | 678 | sim |
| 2 | -0.0873 | 0.0230 | 677 | sim |
| 3 | -0.0948 | 0.0137 | 676 | sim |
| 4 | -0.0921 | 0.0167 | 675 | sim |
| 5 | -0.0834 | 0.0305 | 674 | sim |
| 6 | -0.0718 | 0.0627 | 673 | sim |
| 7 | -0.0531 | 0.1695 | 672 | sim |
| 8 | -0.0447 | 0.2479 | 671 | sim |
| 9 | -0.0235 | 0.5436 | 670 | sim |
| 10 | -0.0019 | 0.9618 | 669 | sim |
| 11 | 0.0267 | 0.4911 | 668 | sim |
| 12 | 0.0473 | 0.2228 | 667 | sim |

A maior associação observada ocorreu com 1 semana de defasagem (Spearman=-0.10, n=678), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 1) e incidência (lag 1) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × temperatura máxima (°c))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | -0.0942 | 0.0490 | 679 | 679 |
| 1 | -0.0972 | 0.0345 | 678 | 678 |
| 2 | -0.0862 | 0.0469 | 677 | 677 |
| 3 | -0.0938 | 0.0318 | 676 | 676 |
| 4 | -0.0911 | 0.0237 | 675 | 675 |
| 5 | -0.0824 | 0.0269 | 674 | 674 |
| 6 | -0.0710 | 0.0277 | 673 | 673 |
| 7 | -0.0520 | 0.0340 | 672 | 672 |
| 8 | -0.0439 | 0.0238 | 671 | 671 |
| 9 | -0.0227 | 0.0308 | 670 | 670 |
| 10 | -0.0007 | 0.0368 | 669 | 669 |
| 11 | 0.0278 | 0.0426 | 668 | 668 |
| 12 | 0.0482 | 0.0514 | 667 | 667 |

### Umidade relativa (%)

**Casos × Umidade relativa (%)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1011 | 0.0084 | 679 | sim |
| 1 | 0.1148 | 0.0028 | 678 | sim |
| 2 | 0.1258 | 0.0010 | 677 | sim |
| 3 | 0.1435 | 0.0002 | 676 | sim |
| 4 | 0.1668 | 0.0000 | 675 | sim |
| 5 | 0.1638 | 0.0000 | 674 | sim |
| 6 | 0.1760 | 0.0000 | 673 | sim |
| 7 | 0.1784 | 0.0000 | 672 | sim |
| 8 | 0.1771 | 0.0000 | 671 | sim |
| 9 | 0.1764 | 0.0000 | 670 | sim |
| 10 | 0.1732 | 0.0000 | 669 | sim |
| 11 | 0.1626 | 0.0000 | 668 | sim |
| 12 | 0.1519 | 0.0001 | 667 | sim |

A maior associação observada ocorreu com 7 semanas de defasagem (Spearman=0.18, n=672), mas isso representa associação histórica, não causalidade.

**Incidência (100 mil hab.) × Umidade relativa (%)**

| Defasagem (semanas) | Spearman | p-valor | n | Confiável (n≥30) |
|---|---|---|---|---|
| 0 | 0.1026 | 0.0075 | 679 | sim |
| 1 | 0.1163 | 0.0024 | 678 | sim |
| 2 | 0.1279 | 0.0009 | 677 | sim |
| 3 | 0.1451 | 0.0002 | 676 | sim |
| 4 | 0.1676 | 0.0000 | 675 | sim |
| 5 | 0.1656 | 0.0000 | 674 | sim |
| 6 | 0.1773 | 0.0000 | 673 | sim |
| 7 | 0.1794 | 0.0000 | 672 | sim |
| 8 | 0.1781 | 0.0000 | 671 | sim |
| 9 | 0.1775 | 0.0000 | 670 | sim |
| 10 | 0.1743 | 0.0000 | 669 | sim |
| 11 | 0.1641 | 0.0000 | 668 | sim |
| 12 | 0.1535 | 0.0001 | 667 | sim |

A maior associação observada ocorreu com 7 semanas de defasagem (Spearman=0.18, n=672), mas isso representa associação histórica, não causalidade.

**Casos vs. incidência**: o lag de maior associação coincide entre casos (lag 7) e incidência (lag 7) -- resultado consistente entre as duas quantidades.

**Bruta vs. ajustada por sazonalidade (casos × umidade relativa (%))**

| Defasagem (semanas) | Spearman bruta | Spearman ajustada | n (bruta) | n (ajustada) |
|---|---|---|---|---|
| 0 | 0.1011 | -0.0266 | 679 | 679 |
| 1 | 0.1148 | -0.0162 | 678 | 678 |
| 2 | 0.1258 | -0.0174 | 677 | 677 |
| 3 | 0.1435 | -0.0008 | 676 | 676 |
| 4 | 0.1668 | 0.0130 | 675 | 675 |
| 5 | 0.1638 | 0.0178 | 674 | 674 |
| 6 | 0.1760 | 0.0290 | 673 | 673 |
| 7 | 0.1784 | 0.0305 | 672 | 672 |
| 8 | 0.1771 | 0.0285 | 671 | 671 |
| 9 | 0.1764 | 0.0308 | 670 | 670 |
| 10 | 0.1732 | 0.0264 | 669 | 669 |
| 11 | 0.1626 | 0.0119 | 668 | 668 |
| 12 | 0.1519 | 0.0120 | 667 | 667 |

## Limitações

- Granularidade Recife total apenas; a fonte de clima não sustenta análise por bairro/RPA (ver Metodologia).
- Correlação, mesmo com amostra confiável (n ≥ 30) e ajustada por sazonalidade, não é prova de causalidade -- outras variáveis (comportamento humano, capacidade de vigilância, outros fatores climáticos) variam juntas e não são controladas aqui.
- A reanálise em grade subestima a chuva medida por estação em cerca de 29% (ver CLAUDE.md §19.1) -- a magnitude da correlação com precipitação pode estar distorcida por esse viés de medição, mesmo que o sinal (positivo/negativo) permaneça informativo.
- A dessazonalização usada aqui é descritiva (média histórica por semana epidemiológica, sem fronteira de treino/teste) -- adequada para uma análise exploratória de associação histórica, não para uso como feature de um modelo preditivo.
- Quando o lag de maior associação reportado for exatamente 12 semanas (o limite testado), isso não significa que a semana 12 é o pico real -- a maior associação pode estar fora da janela testada (0-12 semanas). Ver, por exemplo, temperatura média × casos de dengue abaixo, onde a correlação ainda está subindo em módulo na semana 12.
