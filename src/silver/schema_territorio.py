"""Contrato canônico da Silver territorial (`silver_bairro_geo`).

Definido a partir da inspeção real do recurso "Limites dos Bairros - 2023"
(dataset CKAN `mapas-de-limites-e-divisoes-territoriais`, formato GeoJSON),
não de suposição. Achados que sustentam este desenho:

- O GeoJSON não declara `crs` explicitamente. Pela RFC 7946 (spec do
  GeoJSON), a ausência de `crs` significa WGS84 (EPSG:4326) por padrão — e
  isso bate com os valores reais das coordenadas (longitude ~-34.9,
  latitude ~-8.08, compatível com Recife) e com a detecção automática do
  geopandas (`gdf.crs` -> `EPSG:4326`). Portanto o CRS original é
  **EPSG:4326**, verificado por três ângulos independentes, não presumido.
- Todas as 94 features são `Polygon` (nenhuma `MultiPolygon` encontrada).
- `CBAIRRCODI` (código do bairro) e `EBAIRRNOME` (nome) são 94/94 não-nulos
  e únicos — chave natural confiável.
- `CRPAAACODI` (código da RPA — Região Político-Administrativa, Recife tem
  6) e `CMICROCODI` (microrregião dentro da RPA) são 94/94 não-nulos,
  valores plausíveis (1-6 e 1-3 respectivamente) — mantidos como referência.
- `EBAIRRNOMEOF` é o nome em formatação "oficial" (ex.: "Curado", enquanto
  `EBAIRRNOME` é "CURADO") — mantido separado para exibição/mapas.
- Campos `VBAIRROID`, `CEMPRECODI`, `AUSUACMATR`, `EBAIRRLINK` e
  `TBAIRRSULAT` são 100% nulos em todas as 94 features — descartados.
- `TBAIRRULAT` (93/94 não-nulo, parece um timestamp epoch em ms) tem
  semântica não confirmada — não há metadado/dicionário de dados publicado
  para este recurso — por isso NÃO foi incluído no contrato (não inventamos
  o que ele significa).
- A área embutida na fonte (`DB2GSE.ST_Area(SHAPE)`) bate quase exatamente
  com a área recalculada aqui via reprojeção para SIRGAS2000/UTM 25S
  (EPSG:31985) — ex.: Curado = 8.255.773,76 m² na fonte vs 8.255.774 m²
  recalculado — o que valida a escolha de EPSG:31985 para cálculo de área. A
  soma de todas as áreas (~220 km²) também bate com a área real do
  Recife (~218-220 km²).

CRS utilizados nesta etapa:

- **CRS original**: EPSG:4326 (verificado, não presumido).
- **CRS usado em cálculos** (área e centroide): EPSG:31985 (SIRGAS 2000 /
  UTM zone 25S) — CRS métrico oficial brasileiro apropriado para a
  longitude do Recife. Área nunca é calculada diretamente em EPSG:4326.
- **CRS final de armazenamento**: EPSG:4326 (para interoperabilidade com
  GeoPandas/mapas/GeoJSON — é o que a geometria do Parquet final carrega).
"""
from __future__ import annotations

CRS_ORIGINAL = "EPSG:4326"
CRS_CALCULO_METRICO = "EPSG:31985"  # SIRGAS 2000 / UTM zone 25S
CRS_ARMAZENAMENTO = "EPSG:4326"

TIPOS_GEOMETRIA_ESPERADOS = ("Polygon", "MultiPolygon")

# Campos de negócio do contrato canônico, na ordem gravada no GeoParquet.
COLUNAS_SILVER_BAIRRO_GEO = (
    "codigo_bairro",
    "nome_bairro",
    "nome_bairro_oficial",
    "codigo_rpa",
    "codigo_microrregiao",
    "crs",
    "area_km2",
    "centroide_lat",
    "centroide_lon",
    "geometry",
    "_source_resource_id",
    "_ingestion_run_id",
    "_processed_at",
)
