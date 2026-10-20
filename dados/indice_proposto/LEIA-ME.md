# Índice proposto (Google Earth Engine)

Um GeoTIFF por dia, com o nome `indice_AAAAMMDD.tif` (ex.: `indice_20250801.tif`),
em EPSG:4326, com o **código da classe** (1 = Baixo, 2 = Leve, 3 = Moderado, 4 = Alto)
e 0 como "sem dado". Exemplo de exportação no GEE:

```javascript
Export.image.toDrive({
  image: indiceDoDia.toByte(),          // classes 1–4
  description: 'indice_' + data,        // data no formato AAAAMMDD
  fileNamePrefix: 'indice_' + data,
  region: paraguai.geometry(),
  scale: 11132,                         // ~0,1°
  crs: 'EPSG:4326',
  maxPixels: 1e9
});
```

Se exportar o valor contínuo em vez da classe, ajuste `tipo` e `limites` em `config.yaml`.
