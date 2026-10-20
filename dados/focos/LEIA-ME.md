# Focos de calor

Coloque aqui o(s) CSV de focos exportados do **BDQueimadas** (INPE) para o Paraguai,
cobrindo o período de estudo **e o dia seguinte ao último dia** (para a análise com defasagem).

- Pode ser um ou vários arquivos `.csv` (todos são lidos).
- Confira em `config.yaml` (seção `focos`) os nomes das colunas de data, latitude, longitude e satélite.
- Datas do BDQueimadas estão em UTC; o programa converte para o horário local (`fuso_horas: -3`).
