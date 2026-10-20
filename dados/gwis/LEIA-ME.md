# FWI do GWIS / CEMS

Baixe no EWDS do Copernicus o conjunto **"Fire danger indices historical data from the
Copernicus Emergency Management Service"** (`cems-fire-historical-v1`):

- Product type: **reanalysis** · Variable: **Fire weather index** · formato **NetCDF** (grade regular 0,25°)
- Período: os dias do estudo (ex.: agosto e setembro de 2025)
- Área (sub-região): Norte −19, Oeste −63, Sul −28, Leste −54

Coloque o(s) `.nc` nesta pasta (pode ser um único arquivo com todos os dias).

Para o **ranking em percentis**, baixe também a climatologia (mesma variável, mesmos meses,
por exemplo 1995–2024) e coloque em `climatologia/`.

Confira o nome da variável no arquivo (ex.: `fwinx`) e ajuste `variavel` em `config.yaml`.
