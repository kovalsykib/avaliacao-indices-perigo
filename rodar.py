#!/usr/bin/env python3
"""
Avaliação de índices de perigo de incêndio – programa principal.

Uso:
    python rodar.py config.yaml

Lê os índices diários (GeoTIFF/NetCDF), os focos de calor e as regiões
definidos no arquivo de configuração e gera, na pasta de saída:
    avaliacao.xlsx   todas as tabelas
    RELATORIO.md     resumo com tabelas e figuras (abre direto no GitHub)
    *.png            gráficos;  mapas/*.png  mapas das datas selecionadas
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src import leitura as L
from src import analises as A
from src import saida as S
from src import pagina as P
from src.indices import Indice, slug


def main(caminho_cfg):
    cfg_path = Path(caminho_cfg).resolve()
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    base = cfg_path.parent

    def caminho(p):
        return p if Path(str(p)).is_absolute() else str(base / str(p))

    inicio, fim = pd.Timestamp(cfg["periodo"]["inicio"]), pd.Timestamp(cfg["periodo"]["fim"])
    dias = pd.date_range(inicio, fim, freq="D")
    res = float(cfg["grade"]["resolucao"])
    saida = Path(caminho(cfg["saida"]["pasta"]))
    saida.mkdir(parents=True, exist_ok=True)
    cache = Path(caminho(cfg.get("cache", "cache")))
    min_focos = int(cfg["focos"].get("min_focos_celula", 1))
    so_comuns = bool(cfg.get("somente_dias_comuns", True))
    ce = cfg.get("comparacao_espacial") or {}
    nomes_comuns = [str(c) for c in ce.get("classes", ["Baixo", "Moderado", "Alto"])]

    # ---------------- regiões e grade
    rcfg = dict(cfg["regioes"])
    rcfg["arquivo"] = caminho(rcfg["arquivo"])
    gdf = L.ler_regioes(rcfg)
    b = gdf.total_bounds
    grade = L.Grade(b[0] - res, b[1] - res, b[2] + res, b[3] + res, res)
    reg_ras, regioes, cod = L.rasterizar_regioes(gdf, grade, rcfg.get("todas_celulas_tocadas", False))
    nome_total = rcfg.get("nome_total", "Total")
    mascaras = {nome_total: reg_ras > 0}
    if len(regioes) > 1:
        mascaras.update({r: reg_ras == cod[r] for r in regioes})
    print(f"Grade {grade.nlin}x{grade.ncol} de {res}°; {int((reg_ras > 0).sum())} células na área. "
          f"Regiões: {', '.join(mascaras)}")

    # ---------------- focos
    fcfg = dict(cfg["focos"])
    fcfg["arquivo"] = caminho(fcfg["arquivo"])
    focos = L.ler_focos(fcfg, grade, inicio, fim)
    print(f"Focos lidos (período + 1 dia): {len(focos)}")
    um = pd.Timedelta(days=1)
    focos_dia = {}
    for d in list(dias) + [fim + um]:
        f = focos[(focos.data == d) & (focos.celula >= 0)]
        focos_dia[d] = np.bincount(f.celula.values, minlength=grade.n)
    tem_dia_seguinte = bool((focos.data == fim + um).any())
    if not tem_dia_seguinte:
        focos_dia.pop(fim + um)

    # ---------------- índices
    indices = [Indice(ic, caminho, cache, nomes_comuns) for ic in cfg["indices"]]
    valores, classes, comuns, faltantes = {}, {}, {}, []
    for ind in indices:
        print(f"Lendo {ind.nome}...", flush=True)
        valores[ind.nome] = ind.carregar(dias, grade, faltantes)
        classes[ind.nome] = {d: ind.classificar(v) for d, v in valores[ind.nome].items()}
        comuns[ind.nome] = {d: ind.comum(c) for d, c in classes[ind.nome].items()} if ind.mapa_comum is not None else {}
        print(f"  {len(valores[ind.nome])} de {len(dias)} dias")

    dias_ok = {i.nome: set(valores[i.nome]) for i in indices}
    if so_comuns:
        inter = set.intersection(*dias_ok.values()) if dias_ok else set()
        dias_ok = {k: inter for k in dias_ok}
    dias_validos = sorted(set.union(*dias_ok.values())) if dias_ok else []
    print(f"Dias usados: {len(dias_validos)}" + (" (comuns a todos os índices)" if so_comuns else ""))
    if not dias_validos:
        sys.exit("Nenhum dia com dados para todos os índices. Veja Arquivos_faltantes / nomes dos arquivos.")

    # ---------------- (a)
    t_classe, t_cont, resumo = A.desempenho(indices, classes, focos_dia, mascaras, dias_ok, min_focos)
    nome_alto = nomes_comuns[-1]
    serie = A.series(dias, indices, valores, classes, comuns, focos_dia, mascaras, dias_ok, nome_alto)
    corr_f = A.correlacoes_focos(serie, indices, mascaras)
    for rot, dfz in (("mesmo dia", "Spearman % área alta (mesmo dia)"),
                     ("focos do dia seguinte", "Spearman % área alta (dia seguinte)")):
        sel = corr_f[(corr_f["variável do índice"] == "% área alta") & (corr_f["defasagem"] == rot)]
        resumo = resumo.merge(sel[["índice", "região", "rho de Spearman"]].rename(columns={"rho de Spearman": dfz}),
                              on=["índice", "região"], how="left")

    # ---------------- (b)
    corr_i = A.correlacoes_entre_indices(serie, indices, mascaras, nome_alto)

    # ---------------- (c)
    equiv = pd.DataFrame({"classe comum": nomes_comuns})
    for ind in indices:
        if ind.mapa_comum is not None:
            equiv[ind.nome] = [", ".join(r for k, r in enumerate(ind.rotulos) if ind.mapa_comum[k] == i)
                               for i in range(len(nomes_comuns))]
    datas_sel, conc, matr, faltam_datas = None, pd.DataFrame(), pd.DataFrame(), []
    conc_d, conc_r, img_conc = pd.DataFrame(), pd.DataFrame(), {}
    img_mapas = []
    com_comum = [i for i in indices if i.mapa_comum is not None]
    if ce and len(com_comum) >= 2:
        ce = dict(ce)
        ce.setdefault("regiao_selecao", nome_total)
        datas_sel, faltam_datas = A.selecionar_datas(serie, ce, dias_validos)
        referencia = ce.get("referencia", com_comum[0].nome)
        pesos = ce.get("kappa_pesos", "linear")
        datas_ts = [pd.Timestamp(d) for d in datas_sel["data"]]
        conc, matr = A.concordancia(datas_ts, indices, comuns, mascaras, nomes_comuns, referencia, pesos)
        img_mapas = S.mapas(datas_sel, indices, comuns, grade, reg_ras, gdf, focos, nomes_comuns, saida / "mapas")
        if ce.get("todos_os_dias", True):
            conc_d, conc_r = A.concordancia_diaria(dias_validos, indices, comuns, mascaras, nomes_comuns,
                                                   referencia, pesos, serie, ce["regiao_selecao"])
            for reg in mascaras:
                img_conc[reg] = S.grafico_concordancia_diaria(conc_d, reg, saida)
        print(f"Datas selecionadas: {', '.join(pd.to_datetime(datas_sel['data']).dt.strftime('%d/%m').tolist())}")

    # ---------------- parâmetros
    par = [("período", f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"), ("dias usados", len(dias_validos)),
           ("resolução da grade (°)", res), ("células na área de estudo", int((reg_ras > 0).sum())),
           ("célula-dia com fogo = nº de focos ≥", min_focos),
           ("fuso aplicado aos focos (h)", fcfg.get("fuso_horas", 0)),
           ("filtro dos focos", str(fcfg.get("filtro") or "nenhum")),
           ("focos na área de estudo (dias usados)", int(sum(focos_dia[d][reg_ras > 0].sum() for d in dias_validos))),
           ("somente dias comuns a todos os índices", "sim" if so_comuns else "não")]
    for ind in indices:
        par.append((f"{ind.nome}: classes", ind.descricao_classes()))
        par.append((f"{ind.nome}: classe alta", f"a partir de {ind.rotulos[ind.k_alta]}"))
        if ind.tipo == "percentil":
            par.append((f"{ind.nome}: climatologia", f"{ind.n_clima} dias, {ind.anos_clima[0]}–{ind.anos_clima[1]}"))
    if ce:
        par.append(("Kappa ponderado: pesos", ce.get("kappa_pesos", "linear")))
    if faltam_datas:
        par.append(("datas manuais sem dados", ", ".join(map(str, faltam_datas))))
    parametros = pd.DataFrame(par, columns=["parâmetro", "valor"])
    falt = pd.DataFrame(faltantes) if faltantes else pd.DataFrame([{"índice": "-", "data": "-", "problema": "nenhum"}])

    # ---------------- gravação
    ds_x = None
    if datas_sel is not None:
        ds_x = datas_sel.copy()
        ds_x["data"] = pd.to_datetime(ds_x["data"]).dt.date
        ds_x = ds_x[["data", "grupo", "focos", "percentil na série", "atende ao percentil"]]
    S.gravar_excel(saida / "avaliacao.xlsx", {
        "Resumo": resumo, "a_Focos_por_classe": t_classe, "a_Contingencia": t_cont,
        "a_Correlacoes_focos": corr_f, "b_Correlacao_entre_indices": corr_i,
        "Serie_diaria": serie, "c_Equivalencia_classes": equiv, "c_Datas_selecionadas": ds_x,
        "c_Concordancia_resumo": conc_r, "c_Concordancia_diaria": conc_d,
        "c_Concordancia_datas": conc, "c_Matrizes_confusao": matr,
        "Parametros": parametros, "Arquivos_faltantes": falt})
    img_series = S.grafico_series_focos(serie, indices, mascaras, saida)
    img_razao = S.grafico_razao(t_classe, indices, nome_total, saida)
    for reg in mascaras:
        S.grafico_razao(t_classe, indices, reg, saida, f"a_razao_por_classe_{slug(reg)}.png")
    img_temp = S.grafico_comparacao_temporal(serie, indices, mascaras, nome_alto, saida)
    S.relatorio(saida, {"parametros": parametros, "faltantes": faltantes, "resumo": resumo,
                        "img_razao": img_razao, "img_series": img_series, "corr_indices": corr_i,
                        "img_temporal": img_temp, "equivalencia": equiv, "datas_sel": datas_sel,
                        "concordancia": conc, "img_mapas": img_mapas, "aviso": cfg.get("aviso_relatorio"),
                        "conc_resumo": conc_r, "img_conc_diaria": img_conc.get(nome_total)})
    mapas_pg = []
    if datas_sel is not None:
        for _, lin in datas_sel.sort_values("data").iterrows():
            d = pd.Timestamp(lin["data"])
            mapas_pg.append({"data": str(d.date()), "rotulo": f"{d:%d/%m/%Y}", "grupo": lin["grupo"],
                             "focos": int(lin["focos"]), "arquivo": f"mapa_{d:%Y%m%d}.png"})
    P.gerar(saida, {
        "titulo": cfg.get("titulo", "Avaliação dos índices de perigo de incêndio"),
        "aviso": cfg.get("aviso_relatorio"), "periodo": f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}",
        "regioes": list(mascaras), "indices": [i.nome for i in indices], "mapas": mapas_pg,
        "resumo": resumo, "classe": t_classe, "cont": t_cont, "corr_f": corr_f, "corr_i": corr_i,
        "equiv": equiv, "datas": ds_x, "conc": conc, "matr": matr, "param": parametros, "falt": falt,
        "conc_r": conc_r, "conc_d": conc_d,
        "limites_atividade": conc_r.attrs.get("limites") if len(conc_r) else None,
        "img_conc": {r: (p.name if p else None) for r, p in img_conc.items()},
        "embutir": bool(cfg.get("pagina_embutida", False))})
    print(f"Pronto. Resultados em: {saida}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python rodar.py config.yaml")
    main(sys.argv[1])
