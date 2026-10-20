/* Worker da calculadora: roda o Python (Pyodide) fora da tela principal. */
/* global loadPyodide, importScripts */

let py = null;
const ARQUIVOS_PY = ["rodar.py", "src/__init__.py", "src/leitura.py", "src/indices.py", "src/analises.py",
  "src/saida.py", "src/pagina.py", "src/web.py", "exemplo/gerar_dados_exemplo.py"];

const enviar = (tipo, dados = {}) => postMessage({ tipo, ...dados });
const log = (texto) => enviar("log", { texto });

async function iniciar({ indexURL, baseCodigo, rodas }) {
  importScripts(indexURL + "pyodide.js");
  enviar("etapa", { texto: "Carregando o Python no navegador…" });
  py = await loadPyodide({ indexURL });
  py.setStdout({ batched: (t) => log(t) });
  py.setStderr({ batched: (t) => { if (!/Warning|warn\(/.test(t)) log(t); } });
  enviar("etapa", { texto: "Carregando bibliotecas (rasterio, geopandas, netCDF4…). Na primeira vez leva cerca de 1 minuto." });
  await py.loadPackage(["numpy", "pandas", "scipy", "matplotlib", "xarray", "netcdf4", "rasterio",
    "geopandas", "pyyaml", "micropip"], { messageCallback: () => {} });
  const micropip = py.pyimport("micropip");
  await micropip.install(rodas && rodas.length ? rodas : ["openpyxl"]);
  enviar("etapa", { texto: "Carregando o programa…" });
  for (const caminho of ARQUIVOS_PY) {
    const resp = await fetch(baseCodigo + caminho, { cache: "no-cache" });
    if (!resp.ok) throw new Error(`Não encontrei ${caminho} (${resp.status})`);
    const destino = "/app/" + caminho;
    py.FS.mkdirTree(destino.substring(0, destino.lastIndexOf("/")));
    py.FS.writeFile(destino, await resp.text());
  }
  py.runPython(`
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/app")
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg")
from src import web
`);
  enviar("pronto");
}

function limparPasta(pasta) {
  const FS = py.FS;
  try {
    const st = FS.analyzePath(pasta);
    if (!st.exists) return;
    for (const nome of FS.readdir(pasta)) {
      if (nome === "." || nome === "..") continue;
      const p = pasta + "/" + nome;
      if (FS.isDir(FS.stat(p).mode)) { limparPasta(p); FS.rmdir(p); } else FS.unlink(p);
    }
  } catch (e) { /* ignora */ }
}

async function escrever(arquivo, destino) {
  py.FS.mkdirTree(destino.substring(0, destino.lastIndexOf("/")));
  const buf = new Uint8Array(await arquivo.arrayBuffer());
  py.FS.writeFile(destino, buf);
}

async function inspecionar({ id, tipoArq: tipo, arquivos, campo }) {
  try {
    const pasta = "/tmp/inspecao/" + id;
    limparPasta(pasta);
    for (const a of arquivos) await escrever(a, `${pasta}/${a.name}`);
    let caminho = `${pasta}/${arquivos[0].name}`;
    if (tipo === "regioes") {
      const shp = arquivos.find((a) => /\.shp$/i.test(a.name));
      if (shp) caminho = `${pasta}/${shp.name}`;
    }
    const fn = tipo === "netcdf" ? "inspecionar_netcdf" : "inspecionar_regioes";
    const args = tipo === "netcdf" ? `r"${caminho}"` : `r"${caminho}", ${campo ? JSON.stringify(campo) : "None"}`;
    const r = py.runPython(`web.${fn}(${args})`);
    if (tipo === "netcdf") limparPasta(pasta);
    enviar("inspecao", { id, resultado: JSON.parse(r) });
  } catch (e) {
    enviar("inspecao", { id, erro: String(e.message || e).split("\n").filter(Boolean).slice(-1)[0] });
  }
}

async function calcular({ config, grupos }) {
  try {
    limparPasta("/dados");
    limparPasta("/trabalho");
    // 1) regiões primeiro (definem a área de recorte)
    enviar("etapa", { texto: "Gravando as regiões…" });
    const reg = grupos.find((g) => g.chave === "regioes");
    for (const a of reg.arquivos) await escrever(a, `/dados/regioes/${a.name}`);
    const bbox = JSON.parse(py.runPython(
      `import json; json.dumps(web.bbox_trabalho(r"${config.regioes.arquivo}", ${config.grade.resolucao}))`));
    // 2) demais arquivos
    for (const g of grupos) {
      if (g.chave === "regioes") continue;
      let i = 0;
      for (const a of g.arquivos) {
        i += 1;
        if (i === 1 || i % 5 === 0 || i === g.arquivos.length)
          enviar("etapa", { texto: `Lendo ${g.rotulo}: ${i} de ${g.arquivos.length} arquivo(s)…` });
        const destino = `${g.pasta}/${a.name}`;
        const grande = /\.nc4?$/i.test(a.name) && a.size > 15e6;
        if (grande) {
          const tmp = `/tmp/bruto_${a.name}`;
          await escrever(a, tmp);
          py.FS.mkdirTree(g.pasta);
          py.runPython(`web.recortar(r"${tmp}", r"${destino}", ${g.variavel ? JSON.stringify(g.variavel) : "None"}, ${JSON.stringify(bbox)})`);
        } else {
          await escrever(a, destino);
        }
      }
    }
    enviar("etapa", { texto: "Calculando as análises (a), (b) e (c)… isso pode levar alguns minutos." });
    await new Promise((r) => setTimeout(r, 30));
    const r = JSON.parse(py.runPython(`web.executar(${JSON.stringify(JSON.stringify(config))})`));
    const pagina = new TextDecoder().decode(py.FS.readFile(r.pagina));
    const zip = py.FS.readFile(r.zip);
    const excel = py.FS.readFile(r.excel);
    const cfgYaml = new TextDecoder().decode(py.FS.readFile(r.config));
    enviar("resultado", { pagina, zip, excel, cfgYaml }, [zip.buffer, excel.buffer]);
  } catch (e) {
    const msg = String(e.message || e);
    const linhas = msg.split("\n").filter((l) => l.trim());
    const util = linhas.filter((l) => /Error|Erro|não|nenhum|Nenhum|SystemExit/.test(l)).slice(-2);
    enviar("erro", { texto: (util.length ? util : linhas.slice(-1)).join("\n"), detalhe: msg });
  }
}

async function exemplo() {
  try {
    enviar("etapa", { texto: "Gerando dados simulados…" });
    py.runPython(`
import runpy, sys
sys.argv = ["gerar"]
runpy.run_path("/app/exemplo/gerar_dados_exemplo.py", run_name="__main__")
`);
    const base = "/app/exemplo/dados";
    const ler = (pasta) => py.FS.readdir(pasta).filter((n) => n !== "." && n !== ".." && !py.FS.isDir(py.FS.stat(pasta + "/" + n).mode))
      .map((n) => ({ nome: n, dados: py.FS.readFile(pasta + "/" + n) }));
    const pacote = {
      regioes: ler(base).filter((f) => /\.geojson$/.test(f.nome)),
      focos: ler(base + "/focos"),
      indice_proposto: ler(base + "/indice_proposto"),
      inpe: ler(base + "/inpe"),
      gwis: ler(base + "/gwis"),
      climatologia: ler(base + "/gwis/climatologia"),
    };
    enviar("exemplo", { pacote });
  } catch (e) {
    enviar("erro", { texto: "Falha ao gerar o exemplo: " + String(e.message || e).split("\n").slice(-2).join(" ") });
  }
}

let fila = Promise.resolve();
onmessage = (ev) => {
  const m = ev.data;
  fila = fila.then(async () => {
    try {
      if (m.tipo === "iniciar") await iniciar(m);
      else if (m.tipo === "inspecionar") await inspecionar(m);
      else if (m.tipo === "calcular") await calcular(m);
      else if (m.tipo === "exemplo") await exemplo();
    } catch (e) {
      enviar("erro", { texto: String(e.message || e).split("\n").slice(-3).join("\n") });
    }
  });
};
