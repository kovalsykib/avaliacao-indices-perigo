"""Análises: (a) desempenho contra focos, (b) comparação temporal, (c) comparação espacial."""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


# ----------------------------------------------------------------------------
# Métricas
# ----------------------------------------------------------------------------
def metricas_contingencia(a, b, c, d):
    N = a + b + c + d
    G = a + d
    H = ((a + b) * (a + c) + (c + d) * (b + d)) / N if N else np.nan
    return {
        "a (alto, com fogo)": a, "b (alto, sem fogo)": b,
        "c (não alto, com fogo)": c, "d (não alto, sem fogo)": d, "N": N,
        "% sucesso": 100 * G / N if N else np.nan,
        "acertos ao acaso (H)": H,
        "skill score (SS)": (G - H) / (N - H) if N and N != H else np.nan,
        "POD (%)": 100 * a / (a + c) if (a + c) else np.nan,
        "FAR (%)": 100 * b / (a + b) if (a + b) else np.nan,
    }


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 3 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
        return n, np.nan, np.nan
    r, p = spearmanr(x[ok], y[ok])
    return n, float(r), float(p)


def kappa_ponderado(matriz, pesos="linear"):
    """Kappa de Cohen ponderado a partir da matriz de confusão k×k."""
    m = np.asarray(matriz, float)
    k = m.shape[0]
    N = m.sum()
    if N == 0:
        return np.nan, np.nan, np.nan
    i, j = np.indices((k, k))
    if pesos == "quadratico":
        w = 1 - ((i - j) / (k - 1)) ** 2
    elif pesos == "nenhum":
        w = (i == j).astype(float)
    else:
        w = 1 - np.abs(i - j) / (k - 1)
    p = m / N
    esperado = np.outer(p.sum(1), p.sum(0))
    po, pe = (w * p).sum(), (w * esperado).sum()
    kw = (po - pe) / (1 - pe) if pe < 1 else np.nan
    # Kappa simples (sem peso) também
    po0, pe0 = np.trace(p), np.trace(esperado)
    k0 = (po0 - pe0) / (1 - pe0) if pe0 < 1 else np.nan
    return 100 * po0, k0, kw


# ----------------------------------------------------------------------------
# (a) Desempenho contra os focos
# ----------------------------------------------------------------------------
def desempenho(indices, classes, focos_dia, mascaras, dias_ok, min_focos):
    linhas_classe, linhas_cont, resumo = [], [], []
    for ind in indices:
        nc = len(ind.rotulos)
        for reg, m in mascaras.items():
            area, nf = np.zeros(nc), np.zeros(nc)
            cls_all, fogo_all = [], []
            for d in sorted(dias_ok[ind.nome]):
                cls = classes[ind.nome][d]
                ok = m & (cls >= 0)
                c, f = cls[ok], focos_dia[d][ok]
                area += np.bincount(c, minlength=nc)
                nf += np.bincount(c, weights=f, minlength=nc)
                cls_all.append(c)
                fogo_all.append(f >= min_focos)
            ta, tf = area.sum(), nf.sum()
            for k in range(nc):
                pa = 100 * area[k] / ta if ta else np.nan
                pf = 100 * nf[k] / tf if tf else np.nan
                linhas_classe.append({
                    "índice": ind.nome, "região": reg, "classe": ind.rotulos[k],
                    "células-dia": int(area[k]), "% da área": pa, "focos": int(nf[k]), "% dos focos": pf,
                    "razão (% focos / % área)": pf / pa if pa else np.nan,
                    "focos por 1000 células-dia": 1000 * nf[k] / area[k] if area[k] else np.nan})
            if not cls_all:
                continue
            cls_all, fogo_all = np.concatenate(cls_all), np.concatenate(fogo_all)
            for k in range(1, nc):
                alto = cls_all >= k
                met = metricas_contingencia(int((alto & fogo_all).sum()), int((alto & ~fogo_all).sum()),
                                            int((~alto & fogo_all).sum()), int((~alto & ~fogo_all).sum()))
                linhas_cont.append({"índice": ind.nome, "região": reg,
                                    "previsto alto = classe ≥": ind.rotulos[k],
                                    "limiar principal": "sim" if k == ind.k_alta else "", **met})
                if k == ind.k_alta:
                    pa = 100 * area[k:].sum() / ta if ta else np.nan
                    pf = 100 * nf[k:].sum() / tf if tf else np.nan
                    resumo.append({"índice": ind.nome, "região": reg, "classe alta": f"a partir de {ind.rotulos[k]}",
                                   "dias": len(dias_ok[ind.nome]), "% área em classe alta": pa,
                                   "% focos em classe alta": pf, "razão na classe alta": pf / pa if pa else np.nan,
                                   "% sucesso": met["% sucesso"], "skill score (SS)": met["skill score (SS)"],
                                   "POD (%)": met["POD (%)"], "FAR (%)": met["FAR (%)"]})
    return pd.DataFrame(linhas_classe), pd.DataFrame(linhas_cont), pd.DataFrame(resumo)


# ----------------------------------------------------------------------------
# Séries diárias
# ----------------------------------------------------------------------------
def series(dias, indices, valores, classes, comuns, focos_dia, mascaras, dias_ok, nome_alto_comum):
    linhas = []
    um_dia = pd.Timedelta(days=1)
    for d in dias:
        for reg, m in mascaras.items():
            lin = {"data": d.date(), "região": reg, "focos": int(focos_dia[d][m].sum()),
                   "focos dia seguinte": int(focos_dia[d + um_dia][m].sum()) if (d + um_dia) in focos_dia else np.nan}
            for ind in indices:
                usar = d in dias_ok[ind.nome]
                v = valores[ind.nome].get(d) if usar else None
                cls = classes[ind.nome].get(d) if usar else None
                ok = (m & (cls >= 0)) if cls is not None else None
                tem = ok is not None and ok.any()
                lin[f"{ind.nome} | valor médio"] = float(np.nanmean(v[ok])) if tem else np.nan
                lin[f"{ind.nome} | % área alta"] = 100 * float((cls[ok] >= ind.k_alta).mean()) if tem else np.nan
                if ind.mapa_comum is not None:
                    cc = comuns[ind.nome].get(d) if usar else None
                    lin[f"{ind.nome} | % área {nome_alto_comum} (comum)"] = (
                        100 * float((cc[ok] == ind.mapa_comum.max()).mean()) if tem else np.nan)
            linhas.append(lin)
    return pd.DataFrame(linhas)


def correlacoes_focos(serie, indices, mascaras):
    linhas = []
    for ind in indices:
        for reg in mascaras:
            s = serie[serie["região"] == reg]
            for var in ("valor médio", "% área alta"):
                for rot, col_f in (("mesmo dia", "focos"), ("focos do dia seguinte", "focos dia seguinte")):
                    n, r, p = spearman(s[f"{ind.nome} | {var}"], s[col_f])
                    linhas.append({"índice": ind.nome, "região": reg, "variável do índice": var,
                                   "defasagem": rot, "n dias": n, "rho de Spearman": r, "p-valor": p})
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# (b) Comparação temporal entre os índices
# ----------------------------------------------------------------------------
def correlacoes_entre_indices(serie, indices, mascaras, nome_alto_comum):
    linhas = []
    for reg in mascaras:
        s = serie[serie["região"] == reg]
        for i, a in enumerate(indices):
            for b in indices[i + 1:]:
                variaveis = [("valor médio", "valor médio"), ("% área alta", "% área alta (classe própria)")]
                if a.mapa_comum is not None and b.mapa_comum is not None:
                    variaveis.append((f"% área {nome_alto_comum} (comum)", f"% área {nome_alto_comum} (classe comum)"))
                for var, rot in variaveis:
                    n, r, p = spearman(s[f"{a.nome} | {var}"], s[f"{b.nome} | {var}"])
                    linhas.append({"região": reg, "índice A": a.nome, "índice B": b.nome, "variável": rot,
                                   "n dias": n, "rho de Spearman": r, "p-valor": p})
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# (c) Seleção de datas e comparação espacial
# ----------------------------------------------------------------------------
def selecionar_datas(serie, cfg, dias_validos):
    reg = cfg.get("regiao_selecao")
    s = serie[serie["região"] == reg] if reg else serie[serie["região"] == serie["região"].iloc[0]]
    s = s[s["data"].isin([d.date() for d in dias_validos])].copy()
    s["data"] = pd.to_datetime(s["data"])
    s["percentil na série"] = s["focos"].rank(pct=True) * 100

    manuais = cfg.get("datas")
    if isinstance(manuais, list) and manuais:
        alvo = pd.to_datetime([str(x) for x in manuais])
        out = s[s["data"].isin(alvo)].copy()
        out["grupo"] = "definida manualmente"
        out["atende ao percentil"] = ""
        faltam = [d.date() for d in alvo if d not in set(out["data"])]
        return out.sort_values("data"), faltam

    p_alto = np.percentile(s["focos"], cfg.get("percentil_alto", 90))
    p_baixo = np.percentile(s["focos"], cfg.get("percentil_baixo", 10))
    n = int(cfg.get("n_por_grupo", 2))
    gap = int(cfg.get("intervalo_minimo_dias", 3))
    grupos_mes = [s] if not cfg.get("por_mes", True) else [g for _, g in s.groupby(s["data"].dt.to_period("M"))]
    escolhidas = []

    def livre(d):
        return all(abs((d - e).days) >= gap for e in escolhidas)

    sel = []
    for g in grupos_mes:
        for grupo, asc, lim, cmp in (("maiores registros", False, p_alto, np.greater_equal),
                                     ("menores registros", True, p_baixo, np.less_equal)):
            cand = g.sort_values(["focos", "data"], ascending=[asc, True])
            k = 0
            for _, lin in cand.iterrows():
                if k >= n:
                    break
                if livre(lin["data"]):
                    escolhidas.append(lin["data"])
                    sel.append({**lin.to_dict(), "grupo": grupo,
                                "atende ao percentil": "sim" if cmp(lin["focos"], lim) else "não"})
                    k += 1
    out = pd.DataFrame(sel).sort_values("data")
    out.attrs["p_alto"], out.attrs["p_baixo"] = p_alto, p_baixo
    return out, []


def concordancia(datas, indices, comuns, mascaras, nomes_comuns, referencia, pesos):
    k = len(nomes_comuns)
    ref = next(i for i in indices if i.nome == referencia)
    outros = [i for i in indices if i.nome != referencia and i.mapa_comum is not None]
    linhas, matrizes = [], []
    for reg, m in mascaras.items():
        for o in outros:
            total = np.zeros((k, k))
            for d in list(datas) + [None]:
                if d is None:
                    mat, rot_data = total, "todas as datas"
                else:
                    a, b = comuns[ref.nome].get(d), comuns[o.nome].get(d)
                    if a is None or b is None:
                        continue
                    ok = m & (a >= 0) & (b >= 0)
                    mat = np.zeros((k, k))
                    np.add.at(mat, (a[ok], b[ok]), 1)
                    total += mat
                    rot_data = str(d.date())
                pc, k0, kw = kappa_ponderado(mat, pesos)
                linhas.append({"região": reg, "data": rot_data, "par": f"{ref.nome} × {o.nome}",
                               "células": int(mat.sum()), "% concordância": pc,
                               "Kappa": k0, f"Kappa ponderado ({pesos})": kw,
                               **{f"% área {c} em A": 100 * mat[i].sum() / mat.sum() if mat.sum() else np.nan
                                  for i, c in enumerate(nomes_comuns)},
                               **{f"% área {c} em B": 100 * mat[:, i].sum() / mat.sum() if mat.sum() else np.nan
                                  for i, c in enumerate(nomes_comuns)}})
                for i, ca in enumerate(nomes_comuns):
                    lin = {"região": reg, "data": rot_data, "índice A (linhas)": ref.nome,
                           "índice B (colunas)": o.nome, "classe em A": ca}
                    for j, cb in enumerate(nomes_comuns):
                        lin[f"B = {cb}"] = int(mat[i, j])
                    lin["total da linha"] = int(mat[i].sum())
                    matrizes.append(lin)
    return pd.DataFrame(linhas), pd.DataFrame(matrizes)


def concordancia_diaria(dias, indices, comuns, mascaras, nomes_comuns, referencia, pesos, serie, regiao_grupos):
    """Concordância espacial (classes comuns) em TODOS os dias válidos, com os dias
    separados em terços pela série de focos (baixa / média / alta atividade)."""
    k = len(nomes_comuns)
    ref = next(i for i in indices if i.nome == referencia)
    outros = [i for i in indices if i.nome != referencia and i.mapa_comum is not None]
    s = serie[serie["região"] == regiao_grupos].set_index("data")["focos"]
    s = s[[d.date() for d in dias if d.date() in s.index]]
    q1, q2 = np.percentile(s.values, [100 / 3, 200 / 3]) if len(s) else (np.nan, np.nan)

    def grupo(n):
        return "baixa atividade" if n <= q1 else ("média atividade" if n <= q2 else "alta atividade")

    linhas, mats = [], {}
    for reg, m in mascaras.items():
        for o in outros:
            for d in dias:
                a, b = comuns[ref.nome].get(d), comuns[o.nome].get(d)
                if a is None or b is None:
                    continue
                ok = m & (a >= 0) & (b >= 0)
                mat = np.zeros((k, k))
                np.add.at(mat, (a[ok], b[ok]), 1)
                pc, k0, kw = kappa_ponderado(mat, pesos)
                g = grupo(s.get(d.date(), np.nan))
                linhas.append({"região": reg, "data": str(d.date()), "par": f"{ref.nome} × {o.nome}",
                               "focos (série de seleção)": int(s.get(d.date(), 0)), "grupo de atividade": g,
                               "células": int(mat.sum()), "% concordância": pc, "Kappa": k0,
                               f"Kappa ponderado ({pesos})": kw})
                for chave in ((reg, o.nome, g), (reg, o.nome, "todos os dias")):
                    mats[chave] = mats.get(chave, 0) + mat
    diaria = pd.DataFrame(linhas)
    kcol = f"Kappa ponderado ({pesos})"
    resumo = []
    ordem = ["baixa atividade", "média atividade", "alta atividade", "todos os dias"]
    if len(diaria):
        for (reg, par), g in diaria.groupby(["região", "par"], sort=False):
            for grp in ordem:
                gg = g if grp == "todos os dias" else g[g["grupo de atividade"] == grp]
                if not len(gg):
                    continue
                outro = par.split(" × ", 1)[1]
                pc_ag, _, kw_ag = kappa_ponderado(mats[(reg, outro, grp)], pesos)
                resumo.append({"região": reg, "par": par, "grupo de atividade": grp, "dias": len(gg),
                               "focos: mín–máx": f"{gg['focos (série de seleção)'].min()}–{gg['focos (série de seleção)'].max()}",
                               "% concordância (mediana)": gg["% concordância"].median(),
                               f"{kcol} – mediana": gg[kcol].median(),
                               f"{kcol} – P25": gg[kcol].quantile(.25),
                               f"{kcol} – P75": gg[kcol].quantile(.75),
                               f"{kcol} – mín": gg[kcol].min(), f"{kcol} – máx": gg[kcol].max(),
                               "% concordância (todos os pixels-dia)": pc_ag,
                               f"{kcol} (todos os pixels-dia)": kw_ag})
    resumo = pd.DataFrame(resumo)
    resumo.attrs["limites"] = (q1, q2)
    return diaria, resumo
