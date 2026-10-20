# Avaliação de índices de perigo de incêndio – Paraguai

Este repositório compara índices diários de perigo de incêndio com os focos de calor, de forma automática:

- o **índice proposto**, calculado no Google Earth Engine a partir do GFS e do IMERG;
- o **Risco de Fogo (RF) do INPE**;
- o **FWI do GWIS/CEMS**, em ranking por percentis.

Há duas formas de usar:

1. **Calculadora on-line (mais simples):** abra `https://SEU_USUARIO.github.io/NOME_DO_REPOSITORIO/`, selecione os arquivos do seu computador, ajuste o formulário e clique em **Calcular**. Os resultados aparecem na própria página, com download do Excel e de um .zip. **Os arquivos não saem do seu computador:** tudo é processado no navegador.
2. **Automação no GitHub:** coloque os arquivos nas pastas de `dados/`, e o GitHub roda as análises sozinho e publica os resultados em [`resultados/RELATORIO.md`](resultados/RELATORIO.md).

As duas usam o **mesmo programa** e dão os mesmos números. Veja um exemplo do resultado, feito com dados simulados, em [`resultados_exemplo/RELATORIO.md`](resultados_exemplo/RELATORIO.md).

---

## O que é calculado

### (a) Desempenho contra os focos de calor (todos os dias do período)
Os três índices são avaliados pela mesma referência externa, os focos. Os cálculos saem para o Paraguai, o **Chaco** e a **Região Oriental**:
- **Focos por classe:** % da área, % dos focos e **razão % focos ÷ % área** em cada classe. Um bom índice concentra os focos nas classes altas (razão > 1).
- **Tabela de contingência** por célula-dia ("previsto alto" × "com fogo"), com **% de sucesso**, **skill score** (Heidke, como na avaliação da FMA), **POD** e **FAR**, para cada limiar de classe.
- **Relação temporal:** correlação de **Spearman** entre a série diária de focos (no mesmo dia e no dia seguinte) e a % da área em classe alta ou o valor médio do índice.

### (b) Comparação temporal entre os índices
- As séries diárias da % da área na classe comum "Alto", por região, num mesmo gráfico.
- A correlação de Spearman entre cada par de índices.

### (c) Comparação espacial
- **Concordância em todos os dias (principal):** % de concordância e Kappa ponderado entre os mapas reclassificados, calculados em **cada dia** do período. Os dias são separados em terços pela série de focos (baixa, média e alta atividade de fogo), com mediana, quartis, série diária e boxplot por grupo. As conclusões devem se apoiar aqui, e não em poucas datas.
- **Datas ilustrativas, para os mapas:** pelos extremos da série de focos (maiores e menores registros por mês), comparados aos percentis P90 e P10, **sem dias consecutivos**, com o número de focos de cada data. Também dá para informar as datas manualmente.
- **Classes comuns:** os três índices reclassificados em Baixo, Moderado e Alto, com a **tabela de equivalência** explícita. Ela é definida em `config.yaml` e precisa ser justificada no trabalho.
- **Concordância:** mapas lado a lado (com os focos do dia), **matriz de confusão**, **% de concordância**, **Kappa** e **Kappa ponderado** para cada par (índice proposto × INPE, índice proposto × GWIS), em cada data e no conjunto.

Todos os índices são agregados para uma **grade comum de 0,25°**:
- índices contínuos: média dos pixels de cada célula;
- índices já em classes: a classe mais frequente na célula.

---

## Calculadora on-line

O endereço é `https://SEU_USUARIO.github.io/NOME_DO_REPOSITORIO/`. Para ativar, uma única vez, faça **Settings → Pages → Source: GitHub Actions** e rode **Actions → Rodar análise → Run workflow**.

1. **Teste primeiro:** o botão *"Preencher com dados simulados"* carrega um exemplo completo. Depois clique em **Calcular**.
2. **Passo 1, área e período:** o limite do Paraguai (GeoJSON do GADM, ou shapefile selecionando .shp, .shx, .dbf e .prj juntos) e os polígonos que formam o Chaco.
3. **Passo 2, focos:** o CSV do BDQueimadas. As colunas e os satélites aparecem para escolher.
4. **Passo 3, índices:** os arquivos de cada índice. Dá para selecionar vários arquivos ou a pasta inteira. O padrão do nome (com a data) e a variável do NetCDF são preenchidos sozinhos. Também se definem as classes, a classe alta e a classe comum de cada classe.
5. **Passos 4 e 5:** as regras da comparação espacial, e então **Calcular**.

Algumas observações:
- **Primeira abertura:** o navegador baixa o Python e as bibliotecas, o que leva cerca de 1 minuto. Depois fica em cache.
- **RF do INPE:** na calculadora, os arquivos do INPE precisam ser baixados antes, porque o navegador não consegue buscá-los sozinho no servidor do INPE. Arquivos grandes são recortados para a área de estudo durante a leitura.
- **Navegador:** use Chrome, Edge ou Firefox atualizados, num computador. Com os dois meses completos (~550 MB do INPE), espere alguns minutos.
- **Configuração:** o botão *"Baixar configuração"* gera um `config.yaml` com tudo o que foi usado, para registrar no método.

## Como usar no GitHub (automação)

1. **Coloque os dados** nas pastas abaixo. Pelo navegador: abra a pasta → **Add file → Upload files**. Cada pasta tem um `LEIA-ME.md` explicando o formato.

   | Pasta | O que colocar |
   |---|---|
   | `dados/regioes/` | Limite do Paraguai (ex.: `gadm41_PRY_1.json` do GADM) |
   | `dados/focos/` | CSV de focos do BDQueimadas (período + 1 dia) |
   | `dados/indice_proposto/` | GeoTIFFs do GEE, `indice_AAAAMMDD.tif` |
   | `dados/gwis/` | NetCDF do FWI (EWDS/Copernicus) |
   | `dados/gwis/climatologia/` | NetCDF do FWI de vários anos (para o ranking) |
   | `dados/inpe/` | **Opcional:** o RF do INPE é baixado automaticamente |

2. **Confira o `config.yaml`:** os nomes das colunas do CSV de focos, o nome da variável nos NetCDF, as classes e as equivalências. Para editar no navegador, abra o arquivo e clique no lápis.
3. **Aguarde a análise.** Na aba **Actions** aparece a execução "Rodar análise", que leva poucos minutos. Ela roda de novo sempre que algo muda em `dados/` ou no `config.yaml`.
4. **Veja os resultados** na pasta `resultados/`:
   - `RELATORIO.md`: tabelas e figuras, legível direto no GitHub;
   - `avaliacao.xlsx`: todas as tabelas (abas `Resumo`, `a_…`, `b_…`, `c_…`, `Parametros`, `Arquivos_faltantes`);
   - `*.png` e `mapas/*.png`: gráficos e mapas.

### Página de resultados (site)

Cada execução também publica os resultados da pasta `dados/` como **página web**, em `https://SEU_USUARIO.github.io/NOME_DO_REPOSITORIO/resultados/`. Ela tem as abas Resumo, (a), (b), (c) e Parâmetros, o filtro por região, os mapas por data e um botão para baixar o Excel. A calculadora fica na raiz do mesmo endereço.

Para ativar, uma única vez: **Settings → Pages → Build and deployment → Source: GitHub Actions**. Na próxima execução, o endereço aparece em Settings → Pages e no resumo da execução, na aba Actions.

> Em repositório público, a página também é pública. Se os resultados ainda não puderem ser divulgados, deixe o repositório privado. Em conta gratuita, porém, o GitHub Pages só funciona em repositórios públicos.

**Para testar antes de ter os dados:** na aba **Actions**, clique em **Rodar análise → Run workflow**, marque *"Rodar com os dados SIMULADOS"* e confirme.

> Se a publicação dos resultados falhar com erro de permissão, vá em **Settings → Actions → General → Workflow permissions** e marque **Read and write permissions**.

## Como usar no computador ou no Google Colab

```bash
pip install -r requirements.txt
python exemplo/gerar_dados_exemplo.py          # dados simulados, para testar
python rodar.py exemplo/config_exemplo.yaml    # resultados em resultados_exemplo/
python rodar.py config.yaml                    # com os dados reais
```

No Windows, se `rasterio` ou `geopandas` não instalarem com pip, use o Anaconda:
`conda install -c conda-forge rasterio geopandas xarray netcdf4 pyproj scipy openpyxl pyyaml matplotlib`.

---

## Onde obter os dados

- **Focos:** BDQueimadas (INPE) → filtrar por país Paraguai e pelo período → exportar CSV. Use o satélite de referência (`AQUA_M-T`) para manter a série consistente.
- **RF do INPE:** baixado automaticamente de `dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/observado/risco_fogo/`. Ele é NetCDF diário, com grade de ~1 km e valores de 0 a 1.
- **FWI (GWIS/CEMS):** EWDS do Copernicus, conjunto *Fire danger indices historical data* (`cems-fire-historical-v1`), reanálise ERA5, grade de 0,25°, em NetCDF. O cadastro é gratuito e a licença é CC-BY. Baixe a área do Paraguai (N −19, O −63, S −28, L −54) para o período do estudo e, para a climatologia, os mesmos meses de vários anos.
- **Regiões:** GADM → Paraguay → nível 1 (departamentos), em GeoJSON.

## Cuidados na interpretação

- **% de sucesso:** sozinha, ela engana, porque é inflada pelos acertos "sem fogo, sem perigo". Use o **skill score**.
- **Tamanho da célula:** os resultados dependem da grade (0,25°) e de quantos focos fazem uma célula contar como "com fogo". Declare as duas escolhas no método; elas estão na aba `Parametros`.
- **RF do INPE:** a versão atual usa **IMERG + GFS**, as mesmas fontes do índice proposto. Parte da semelhança entre os dois vem dos dados de entrada.
- **FWI em ranking:** cada dia é comparado à climatologia do próprio pixel. As classes absolutas do GWIS foram calibradas para a Europa e podem ser incluídas como índice adicional no `config.yaml`.
- **Poucas datas:** a concordância em poucas datas extremas tende a sair maior do que no período todo, porque nos extremos os índices concordam mais. Por isso as datas selecionadas servem só como ilustração.
- **Datas da análise (c):** se não houver dias acima de P90 ou abaixo de P10 suficientes num mês, o programa escolhe os mais extremos disponíveis e marca **"atende ao percentil: não"**.

## Estrutura

```
config.yaml                 configuração da análise com os dados reais
rodar.py                    programa principal (gera também resultados/index.html)
app/                        calculadora on-line (index.html + worker.js, Pyodide)
src/                        leitura dos dados, análises e saídas
dados/                      dados de entrada (você adiciona)
resultados/                 gerado automaticamente
exemplo/                    gerador de dados simulados + configuração de exemplo
resultados_exemplo/         resultado do exemplo
.github/workflows/          automação do GitHub Actions
```

Licença MIT. Ao usar, cite o repositório.
