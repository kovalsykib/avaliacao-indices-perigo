"""Página web de resultados (index.html), publicada pelo GitHub Pages."""

import base64
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .indices import slug


def _registros(df, colunas=None):
    if df is None or len(df) == 0:
        return {"colunas": [], "linhas": []}
    df = df[colunas] if colunas else df
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%d/%m/%Y")
    linhas = []
    for r in df.itertuples(index=False):
        lin = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                lin.append(None if np.isnan(v) else float(v))
            elif isinstance(v, (np.integer,)):
                lin.append(int(v))
            else:
                lin.append(v if isinstance(v, (int, float)) else str(v))
        linhas.append(lin)
    return {"colunas": [str(c) for c in df.columns], "linhas": linhas}


def _src(pasta, nome, embutir):
    """Caminho relativo da imagem, ou data URI se a página deve ser autocontida."""
    if not nome:
        return None
    if not embutir:
        return nome
    arq = Path(pasta) / nome
    if not arq.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(arq.read_bytes()).decode()


def gerar(pasta, ctx, nome_arquivo="index.html"):
    pasta = Path(pasta)
    regioes = ctx["regioes"]
    emb = bool(ctx.get("embutir"))
    mapas = []
    for m in ctx["mapas"]:
        m = dict(m)
        m["src"] = _src(pasta, f"mapas/{m['arquivo']}", emb)
        mapas.append(m)
    lim = ctx.get("limites_atividade")
    excel = "avaliacao.xlsx"
    if emb and (pasta / excel).exists():
        excel = ("data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,"
                 + base64.b64encode((pasta / excel).read_bytes()).decode())
    dados = {
        "titulo": ctx.get("titulo", "Avaliação dos índices de perigo de incêndio"),
        "aviso": ctx.get("aviso") or "",
        "gerado": f"{pd.Timestamp.now():%d/%m/%Y %H:%M}",
        "periodo": ctx["periodo"],
        "regioes": regioes,
        "indices": ctx["indices"],
        "excel": excel,
        "limites": [float(lim[0]), float(lim[1])] if lim is not None else None,
        "img": {
            "serie": {r: _src(pasta, f"a_serie_focos_{slug(r)}.png", emb) for r in regioes},
            "razao": {r: _src(pasta, f"a_razao_por_classe_{slug(r)}.png", emb) for r in regioes},
            "temporal": _src(pasta, "b_comparacao_temporal.png", emb),
            "conc": {r: _src(pasta, n, emb) for r, n in (ctx.get("img_conc") or {}).items()},
        },
        "mapas": mapas,
        "t": {k: _registros(ctx.get(v)) for k, v in {
            "resumo": "resumo", "classe": "classe", "cont": "cont", "corr_f": "corr_f", "corr_i": "corr_i",
            "equiv": "equiv", "datas": "datas", "conc": "conc", "matr": "matr", "param": "param",
            "falt": "falt", "conc_r": "conc_r", "conc_d": "conc_d"}.items()},
    }
    html = MODELO.replace("__DADOS__", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/"))
    (pasta / nome_arquivo).write_text(html, encoding="utf-8")
    return pasta / nome_arquivo


MODELO = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Avaliação dos índices de perigo</title>
<style>
:root{
  --bg:#f7f7f4; --surface:#ffffff; --surface-2:#f0efe9; --text:#1d1f1c; --muted:#5f645c;
  --line:#dddcd3; --accent:#b4441c; --accent-soft:#f6e3da; --ok:#2e7d4f; --warn:#9a6a00; --warn-soft:#fbf1d3;
  --shadow:0 1px 2px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.04);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#151614; --surface:#1e201d; --surface-2:#262924; --text:#ecece6; --muted:#a3a89e;
    --line:#353831; --accent:#ec8a5e; --accent-soft:#3a261c; --ok:#6cc08f; --warn:#e3b54a; --warn-soft:#3a3018;
    --shadow:none;
  }
}
:root[data-theme="dark"]{
  --bg:#151614; --surface:#1e201d; --surface-2:#262924; --text:#ecece6; --muted:#a3a89e;
  --line:#353831; --accent:#ec8a5e; --accent-soft:#3a261c; --ok:#6cc08f; --warn:#e3b54a; --warn-soft:#3a3018;
  --shadow:none;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
header{padding:28px 0 8px}
h1{font-size:clamp(1.35rem,2.6vw,1.9rem);margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0}
.aviso{background:var(--warn-soft);color:var(--warn);border:1px solid var(--warn);border-radius:10px;padding:10px 14px;margin:14px 0 0;font-weight:600}
.barra{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:5;background:var(--bg);padding:12px 0;border-bottom:1px solid var(--line);margin-top:12px}
nav{display:flex;flex-wrap:wrap;gap:4px}
nav button{border:1px solid transparent;background:none;color:var(--muted);padding:7px 12px;border-radius:8px;cursor:pointer;font:inherit;font-weight:600}
nav button[aria-selected="true"]{background:var(--surface);color:var(--text);border-color:var(--line);box-shadow:var(--shadow)}
.ctrl{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--surface)}
.seg button{border:0;background:none;color:var(--muted);padding:6px 12px;font:inherit;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--accent);color:#fff}
a.btn{display:inline-block;text-decoration:none;background:var(--text);color:var(--bg);padding:7px 12px;border-radius:8px;font-weight:600}
section{display:none;padding:18px 0 40px}
section.ativo{display:block}
h2{font-size:1.2rem;margin:22px 0 6px}
h3{font-size:1rem;margin:18px 0 6px}
p.nota{color:var(--muted);margin:4px 0 10px;max-width:80ch}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow);margin:10px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.kpi h4{margin:0 0 8px;font-size:.95rem}
.kpi dl{display:grid;grid-template-columns:1fr auto;gap:2px 10px;margin:0}
.kpi dt{color:var(--muted)} .kpi dd{margin:0;font-variant-numeric:tabular-nums;font-weight:600;text-align:right}
.tabela{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:var(--surface-2);font-weight:600;position:sticky;top:0}
td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.destaque td{background:var(--accent-soft)}
tr:last-child td{border-bottom:0}
figure{margin:10px 0}
figure img{width:100%;height:auto;border-radius:10px;border:1px solid var(--line);background:#fff}
.datas{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.datas button{border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit}
.datas button[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-soft);font-weight:600}
.datas small{display:block;color:var(--muted);font-size:.75rem}
details.card summary{cursor:pointer;font-weight:600}
details.card .tabela{margin-top:10px}
.vazio{color:var(--muted);font-style:italic;padding:10px}
@media (max-width:700px){.barra{position:static}}
footer{color:var(--muted);font-size:.85rem;padding:20px 0 40px;border-top:1px solid var(--line)}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1 id="titulo"></h1>
  <p class="sub" id="sub"></p>
  <div class="aviso" id="aviso" hidden></div>
</header>

<div class="barra">
  <nav role="tablist" id="abas"></nav>
  <div class="ctrl">
    <span class="sub">Região:</span>
    <div class="seg" id="regioes"></div>
    <a class="btn" id="baixar-excel" href="avaliacao.xlsx" download="avaliacao.xlsx">Baixar Excel</a>
  </div>
</div>

<section id="s-resumo">
  <h2>Resumo por índice</h2>
  <p class="nota">Desempenho de cada índice contra os focos de calor na região selecionada.
  Razão &gt; 1 indica que a classe alta concentra mais focos do que o seu tamanho; o skill score (SS)
  desconta os acertos ao acaso.</p>
  <div class="kpis" id="kpis"></div>
  <h3>Tabela-resumo</h3>
  <div class="tabela" id="t-resumo"></div>
</section>

<section id="s-a">
  <h2>(a) Desempenho contra os focos de calor</h2>
  <h3>Focos por classe</h3>
  <p class="nota">Um bom índice tem razão crescente da classe mais baixa para a mais alta.</p>
  <figure><img id="img-razao" alt="Razão % focos / % área por classe"></figure>
  <div class="tabela" id="t-classe"></div>
  <h3>Tabela de contingência (célula-dia)</h3>
  <p class="nota">Previsto alto = classe igual ou acima do limiar; com fogo = célula com focos no dia.
  A linha destacada é o limiar principal de cada índice.</p>
  <div class="tabela" id="t-cont"></div>
  <h3>Relação temporal com os focos</h3>
  <figure><img id="img-serie" alt="Série diária de focos e área em classe alta"></figure>
  <div class="tabela" id="t-corrf"></div>
</section>

<section id="s-b">
  <h2>(b) Comparação temporal entre os índices</h2>
  <p class="nota">Séries diárias da área na classe comum mais alta e correlação de Spearman entre os pares.</p>
  <figure><img id="img-temporal" alt="Comparação temporal entre os índices"></figure>
  <div class="tabela" id="t-corri"></div>
</section>

<section id="s-c">
  <h2>(c) Comparação espacial</h2>
  <h3>Concordância em todos os dias</h3>
  <p class="nota" id="nota-tercis">Concordância entre os mapas reclassificados nas classes comuns, calculada em cada dia
  do período. Os dias são separados em terços pela série de focos (baixa, média e alta atividade de fogo).</p>
  <figure id="fig-conc"><img id="img-conc" alt="Concordância espacial diária e por nível de atividade"></figure>
  <div class="tabela" id="t-concr"></div>
  <details class="card"><summary>Ver a concordância de cada dia</summary><div class="tabela" id="t-concd"></div></details>
  <h3>Mapas das datas ilustrativas</h3>
  <p class="nota">Datas de maiores e menores registros de focos, usadas como ilustração. As conclusões devem se
  apoiar na concordância de todos os dias, acima.</p>
  <div class="datas" id="botoes-datas"></div>
  <figure><img id="img-mapa" alt="Mapas lado a lado"></figure>
  <h3>Concordância nas datas ilustrativas</h3>
  <div class="tabela" id="t-conc"></div>
  <h3>Matriz de confusão da data escolhida</h3>
  <div class="tabela" id="t-matr"></div>
  <h3>Datas selecionadas</h3>
  <div class="tabela" id="t-datas"></div>
  <h3>Equivalência de classes</h3>
  <div class="tabela" id="t-equiv"></div>
</section>

<section id="s-param">
  <h2>Parâmetros da análise</h2>
  <p class="nota">Use estas informações para descrever o método.</p>
  <div class="tabela" id="t-param"></div>
  <h3>Arquivos faltantes ou com erro</h3>
  <div class="tabela" id="t-falt"></div>
</section>

<footer id="rodape"></footer>
</div>

<script>
const D = __DADOS__;
let regiao = D.regioes[0];
let dataMapa = D.mapas.length ? D.mapas[0].data : null;

const fmt = v => {
  if (v === null || v === undefined || v === "") return "–";
  if (typeof v !== "number") return v;
  if (Number.isInteger(v)) return v.toLocaleString("pt-BR");
  const a = Math.abs(v);
  const d = a < 1 ? 3 : a < 100 ? 2 : 1;
  return v.toLocaleString("pt-BR", {minimumFractionDigits: d, maximumFractionDigits: d});
};
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function filtrar(t, filtros, colunas) {
  if (!t.colunas.length) return {colunas: [], linhas: []};
  let linhas = t.linhas;
  for (const [col, val] of Object.entries(filtros)) {
    const i = t.colunas.indexOf(col);
    if (i >= 0) linhas = linhas.filter(l => String(l[i]) === String(val));
  }
  let cols = t.colunas;
  if (colunas) {
    const idx = colunas.map(c => t.colunas.indexOf(c)).filter(i => i >= 0);
    cols = idx.map(i => t.colunas[i]);
    linhas = linhas.map(l => idx.map(i => l[i]));
  }
  return {colunas: cols, linhas};
}

function tabela(id, t, opc = {}) {
  const el = document.getElementById(id);
  if (!t.linhas.length) { el.innerHTML = '<div class="vazio">Sem dados.</div>'; return; }
  const iDest = opc.destaque ? t.colunas.indexOf(opc.destaque) : -1;
  let h = "<table><thead><tr>" + t.colunas.map(c => `<th>${esc(c)}</th>`).join("") + "</tr></thead><tbody>";
  for (const l of t.linhas) {
    const cls = iDest >= 0 && l[iDest] === "sim" ? ' class="destaque"' : "";
    h += `<tr${cls}>` + l.map(v => `<td${typeof v === "number" ? ' class="n"' : ""}>${esc(fmt(v))}</td>`).join("") + "</tr>";
  }
  el.innerHTML = h + "</tbody></table>";
}

function kpis() {
  const t = filtrar(D.t.resumo, {"região": regiao});
  const c = t.colunas;
  const g = (l, n) => l[c.indexOf(n)];
  document.getElementById("kpis").innerHTML = t.linhas.map(l => `
    <div class="card kpi"><h4>${esc(g(l, "índice"))}</h4><dl>
      <dt>Classe alta</dt><dd>${esc(String(g(l, "classe alta")).replace("a partir de ", "≥ "))}</dd>
      <dt>Razão na classe alta</dt><dd>${fmt(g(l, "razão na classe alta"))}</dd>
      <dt>Skill score</dt><dd>${fmt(g(l, "skill score (SS)"))}</dd>
      <dt>POD / FAR (%)</dt><dd>${fmt(g(l, "POD (%)"))} / ${fmt(g(l, "FAR (%)"))}</dd>
      <dt>Spearman (dia seguinte)</dt><dd>${fmt(g(l, "Spearman % área alta (dia seguinte)"))}</dd>
    </dl></div>`).join("") || '<div class="vazio">Sem dados.</div>';
}

function desenhar() {
  const r = {"região": regiao};
  kpis();
  tabela("t-resumo", filtrar(D.t.resumo, r));
  tabela("t-classe", filtrar(D.t.classe, r));
  tabela("t-cont", filtrar(D.t.cont, r), {destaque: "limiar principal"});
  tabela("t-corrf", filtrar(D.t.corr_f, r));
  tabela("t-corri", filtrar(D.t.corr_i, r));
  tabela("t-conc", filtrar(D.t.conc, r));
  tabela("t-concr", filtrar(D.t.conc_r, r));
  tabela("t-concd", filtrar(D.t.conc_d, r));
  const ic = D.img.conc[regiao];
  document.getElementById("fig-conc").hidden = !ic;
  if (ic) document.getElementById("img-conc").src = ic;
  tabela("t-equiv", D.t.equiv);
  tabela("t-datas", D.t.datas);
  tabela("t-param", D.t.param);
  tabela("t-falt", D.t.falt);
  document.getElementById("img-razao").src = D.img.razao[regiao];
  document.getElementById("img-serie").src = D.img.serie[regiao];
  document.getElementById("img-temporal").src = D.img.temporal;
  desenharMapa();
}

function desenharMapa() {
  const box = document.getElementById("botoes-datas");
  if (!D.mapas.length) { box.innerHTML = '<div class="vazio">Sem datas selecionadas.</div>'; return; }
  box.innerHTML = D.mapas.map(m => `<button aria-pressed="${m.data === dataMapa}" data-d="${m.data}">
      ${esc(m.rotulo)}<small>${esc(m.grupo)} · ${fmt(m.focos)} focos</small></button>`).join("");
  box.querySelectorAll("button").forEach(b => b.onclick = () => { dataMapa = b.dataset.d; desenharMapa(); });
  const m = D.mapas.find(x => x.data === dataMapa);
  document.getElementById("img-mapa").src = m.src;
  tabela("t-matr", filtrar(D.t.matr, {"região": regiao, "data": m.data}));
}

const ABAS = [["s-resumo", "Resumo"], ["s-a", "(a) Desempenho"], ["s-b", "(b) Temporal"],
              ["s-c", "(c) Espacial"], ["s-param", "Parâmetros"]];
function mostrar(id) {
  document.querySelectorAll("section").forEach(s => s.classList.toggle("ativo", s.id === id));
  document.querySelectorAll("#abas button").forEach(b => b.setAttribute("aria-selected", b.dataset.s === id));
  try { localStorage.setItem("aba", id); } catch (e) {}
}

document.getElementById("titulo").textContent = D.titulo;
document.getElementById("sub").textContent = `Período: ${D.periodo} · Índices: ${D.indices.join(", ")}`;
if (D.aviso) { const a = document.getElementById("aviso"); a.hidden = false; a.textContent = D.aviso; }
document.getElementById("baixar-excel").href = D.excel;
if (D.limites) document.getElementById("nota-tercis").textContent +=
  ` Limites: baixa ≤ ${fmt(Math.round(D.limites[0]))} focos; média ≤ ${fmt(Math.round(D.limites[1]))}; alta acima disso.`;
document.getElementById("rodape").textContent = `Gerado automaticamente em ${D.gerado}.`;
document.getElementById("abas").innerHTML = ABAS.map(([id, n]) =>
  `<button role="tab" data-s="${id}">${n}</button>`).join("");
document.querySelectorAll("#abas button").forEach(b => b.onclick = () => mostrar(b.dataset.s));
document.getElementById("regioes").innerHTML = D.regioes.map(r =>
  `<button aria-pressed="${r === regiao}" data-r="${esc(r)}">${esc(r)}</button>`).join("");
document.querySelectorAll("#regioes button").forEach(b => b.onclick = () => {
  regiao = b.dataset.r;
  document.querySelectorAll("#regioes button").forEach(x => x.setAttribute("aria-pressed", x === b));
  desenhar();
});
let inicial = "s-resumo";
try { inicial = localStorage.getItem("aba") || inicial; } catch (e) {}
if (!document.getElementById(inicial)) inicial = "s-resumo";
mostrar(inicial);
desenhar();
</script>
</body>
</html>
"""
