# Regiões

Limite do Paraguai com as regiões de análise. A configuração padrão usa os
**departamentos do GADM** (`gadm41_PRY_1.json`, de gadm.org → Paraguay → GeoJSON nível 1)
e agrupa Alto Paraguay, Boquerón e Presidente Hayes como **Chaco**; os demais como **Oriental**.

Também serve um shapefile (envie todos os arquivos: .shp, .shx, .dbf, .prj) ou GeoPackage
com uma coluna de região — ajuste `campo` e `agrupar` em `config.yaml`.
