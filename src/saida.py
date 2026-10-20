"""Saídas: planilha Excel, gráficos, mapas e relatório em Markdown."""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap, BoundaryNorm  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from .indices import slug  # noqa: E402

CORES_COMUNS = ["#1a9850", "#fdd835", "#d73027", "#7b1fa2", "#000000"]
CORES_LINHAS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b", "#e377c2"]


# ----------------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------------
def gravar_excel(caminho, abas):
    with pd.ExcelWriter(caminho, engine="openpyxl") as w:
        for nome, df in abas.items():
            if df is None or len(df) == 0:
                df = pd.DataFrame({"aviso": ["sem dados para esta análise"]})
            df.to_excel(w, sheet_name=nome[:31], index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                larg = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, larg + 2), 48)
                for c in col[1:]:
                    if isinstance(c.value, float):
                        c.number_format = "0.000" if abs(c.value) < 10 else "0.0"
            ws.freeze_panes = "A2"


# ----------------------------------------------------------------------------
# Gráficos
# ----------------------------------------------------------------------------
def grafico_series_focos(serie, indices, mascaras, pasta):
    arqs = []
    for reg in mascaras:
        s = serie[serie["região"] == reg]
        x = pd.to_datetime(s["data"])
        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.bar(x, s["focos"], color="#d0d0d0", width=0.8, label="Focos de calor")
        ax.set_ylabel("Focos de calor por dia")
        ax2 = ax.twinx()
        for cor, ind in zip(CORES_LINHAS, indices):
            ax2.plot(x, s[f"{ind.nome} | % área alta"], lw=1.8, color=cor,
                     label=f"{ind.nome} (a partir de {ind.rotulos[ind.k_alta]})")
        ax2.set_ylabel("% da área em classe alta")
        ax2.set_ylim(0, 100)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=False)
        ax.set_title(f"Focos de calor e área em classe alta de perigo – {reg}")
        fig.autofmt_xdate()
        fig.tight_layout()
        nome = pasta / f"a_serie_focos_{slug(reg)}.png"
        fig.savefig(nome, dpi=170)
        plt.close(fig)
        arqs.append(nome)
    return arqs


def grafico_razao(classe, indices, regiao, pasta):
    c = classe[classe["região"] == regiao]
    fig, axs = plt.subplots(1, len(indices), figsize=(4.2 * len(indices), 4), squeeze=False)
    for ax, ind in zip(axs[0], indices):
        ci = c[c["índice"] == ind.nome]
        ax.bar(ci["classe"], ci["razão (% focos / % área)"], color="#c0504d")
        ax.axhline(1, color="k", lw=0.8, ls="--")
        ax.set_title(ind.nome, fontsize=10)
        ax.set_ylabel("razão % focos / % área")
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    fig.suptitle(f"Concentração de focos por classe de perigo – {regiao} (linha tracejada = 1)")
    fig.tight_layout()
    nome = pasta / "a_razao_por_classe.png"
    fig.savefig(nome, dpi=170)
    plt.close(fig)
    return nome


def grafico_comparacao_temporal(serie, indices, mascaras, nome_alto, pasta):
    comuns = [i for i in indices if i.mapa_comum is not None]
    usar_comum = len(comuns) >= 2
    lista = comuns if usar_comum else indices
    regs = list(mascaras)
    fig, axs = plt.subplots(len(regs), 1, figsize=(11, 3.2 * len(regs)), sharex=True, squeeze=False)
    for ax, reg in zip(axs[:, 0], regs):
        s = serie[serie["região"] == reg]
        x = pd.to_datetime(s["data"])
        for cor, ind in zip(CORES_LINHAS, lista):
            col = f"{ind.nome} | % área {nome_alto} (comum)" if usar_comum else f"{ind.nome} | % área alta"
            ax.plot(x, s[col], lw=1.8, color=cor, label=ind.nome)
        ax.set_ylim(0, 100)
        ax.set_ylabel("% da área")
        ax.set_title(reg, fontsize=10, loc="left")
        ax.grid(alpha=0.3)
    axs[0, 0].legend(fontsize=8, frameon=False, ncol=len(lista))
    titulo = f"% da área na classe comum '{nome_alto}'" if usar_comum else "% da área em classe alta (classes próprias)"
    fig.suptitle(f"Comparação temporal entre os índices – {titulo}")
    fig.autofmt_xdate()
    fig.tight_layout()
    nome = pasta / "b_comparacao_temporal.png"
    fig.savefig(nome, dpi=170)
    plt.close(fig)
    return nome


def mapas(datas_sel, indices, comuns, grade, regiao_ras, gdf, focos, nomes_comuns, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    lista = [i for i in indices if i.mapa_comum is not None]
    k = len(nomes_comuns)
    cmap = ListedColormap(CORES_COMUNS[:k])
    norm = BoundaryNorm(np.arange(-0.5, k), k)
    ext = (grade.xmin, grade.xmax, grade.ymin, grade.ymax)
    arqs = []
    fronteira = gdf.dissolve(by="_regiao")
    for _, lin in datas_sel.iterrows():
        d = pd.Timestamp(lin["data"])
        fig, axs = plt.subplots(1, len(lista), figsize=(4.3 * len(lista), 5.2), squeeze=False)
        f = focos[(focos.data == d) & (focos.celula >= 0)]
        f = f[regiao_ras[f.celula.values] > 0]
        for ax, ind in zip(axs[0], lista):
            cc = comuns[ind.nome].get(d)
            if cc is None:
                ax.set_axis_off()
                ax.set_title(f"{ind.nome}\n(sem dado)", fontsize=10)
                continue
            img = np.where((cc >= 0) & (regiao_ras > 0), cc, np.nan).reshape(grade.nlin, grade.ncol)
            ax.imshow(img, extent=ext, cmap=cmap, norm=norm, interpolation="nearest")
            fronteira.boundary.plot(ax=ax, color="k", lw=0.7)
            ax.scatter(f.lon, f.lat, s=1.5, c="k", alpha=0.6, linewidths=0)
            ax.set_xlim(grade.xmin, grade.xmax)
            ax.set_ylim(grade.ymin, grade.ymax)
            ax.set_title(ind.nome, fontsize=10)
            ax.set_xlabel("Longitude", fontsize=8)
            ax.set_ylabel("Latitude", fontsize=8)
            ax.set_aspect("equal")
            ax.tick_params(labelsize=7)
        leg = [Patch(color=CORES_COMUNS[i], label=c) for i, c in enumerate(nomes_comuns)]
        leg.append(plt.Line2D([], [], marker="o", ls="", color="k", ms=3, label="focos do dia"))
        fig.legend(handles=leg, loc="lower center", ncol=k + 1, frameon=False, fontsize=9)
        fig.suptitle(f"{d:%d/%m/%Y} – {lin['grupo']} – {int(lin['focos'])} focos", fontsize=12)
        fig.tight_layout(rect=(0, 0.08, 1, 0.97))
        nome = pasta / f"mapa_{d:%Y%m%d}.png"
        fig.savefig(nome, dpi=150)
        plt.close(fig)
        arqs.append(nome)
    return arqs


# ----------------------------------------------------------------------------
# Relatório Markdown
# ----------------------------------------------------------------------------
def _fmt(v):
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return "–"
        return f"{v:.3f}" if abs(v) < 1 else f"{v:.2f}" if abs(v) < 100 else f"{v:.1f}"
    return str(v)


def tabela_md(df, colunas=None):
    if df is None or len(df) == 0:
        return "_sem dados_\n"
    df = df[colunas] if colunas else df
    cab = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    linhas = ["| " + " | ".join(_fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([cab, sep] + linhas) + "\n"


def relatorio(pasta, ctx):
    p = []
    p.append("# Resultados da avaliação dos índices de perigo\n")
    p.append(f"_Gerado automaticamente em {pd.Timestamp.now():%d/%m/%Y %H:%M}._ "
             "Os números completos estão em `avaliacao.xlsx`.\n")
    if ctx.get("aviso"):
        p.append(f"> **{ctx['aviso']}**\n")
    p.append("## Parâmetros\n")
    p.append(tabela_md(ctx["parametros"]))
    if len(ctx["faltantes"]):
        p.append(f"\n**Dias sem arquivo ou com erro:** {len(ctx['faltantes'])} (ver aba `Arquivos_faltantes`).\n")

    p.append("\n## (a) Desempenho contra os focos de calor\n")
    p.append("Classe alta = a partir da classe indicada. Razão > 1 = a classe concentra mais focos do que "
             "o seu tamanho; SS = skill score (Heidke); POD = detecção; FAR = falso alarme.\n\n")
    p.append(tabela_md(ctx["resumo"]))
    p.append(f"\n![razão por classe]({ctx['img_razao'].name})\n")
    for img in ctx["img_series"]:
        p.append(f"\n![série]({img.name})\n")

    p.append("\n## (b) Comparação temporal entre os índices\n")
    cr = ctx["corr_indices"]
    if len(cr):
        var_pref = [v for v in cr["variável"].unique() if "comum" in v] or list(cr["variável"].unique())
        p.append(f"Correlação de Spearman entre as séries diárias ({var_pref[0]}).\n\n")
        p.append(tabela_md(cr[cr["variável"] == var_pref[0]],
                           ["região", "índice A", "índice B", "n dias", "rho de Spearman", "p-valor"]))
    p.append(f"\n![comparação temporal]({ctx['img_temporal'].name})\n")

    p.append("\n## (c) Comparação espacial nas datas selecionadas\n")
    p.append("### Equivalência de classes\n")
    p.append(tabela_md(ctx["equivalencia"]))
    ds = ctx["datas_sel"]
    if ds is not None and len(ds):
        p.append("\n### Datas selecionadas\n")
        if "p_alto" in ds.attrs:
            p.append(f"Percentis da série diária de focos: P alto = {ds.attrs['p_alto']:.0f} focos, "
                     f"P baixo = {ds.attrs['p_baixo']:.0f} focos.\n\n")
        d2 = ds.copy()
        d2["data"] = pd.to_datetime(d2["data"]).dt.strftime("%d/%m/%Y")
        p.append(tabela_md(d2, ["data", "grupo", "focos", "percentil na série", "atende ao percentil"]))
        conc = ctx["concordancia"]
        if len(conc):
            regiao0 = conc["região"].iloc[0]
            p.append(f"\n### Concordância ({regiao0})\n")
            kcol = [c for c in conc.columns if c.startswith("Kappa ponderado")][0]
            c2 = conc[conc["região"] == regiao0].copy()
            c2["data"] = c2["data"].astype(str)
            p.append(tabela_md(c2, ["data", "par", "células", "% concordância", "Kappa", kcol]))
            p.append("\nResultados por região e matrizes de confusão: abas `Concordancia` e `Matrizes_confusao`.\n")
        p.append("\n### Mapas\n")
        for img in ctx["img_mapas"]:
            p.append(f"\n![mapa](mapas/{img.name})\n")
    (pasta / "RELATORIO.md").write_text("\n".join(p), encoding="utf-8")
