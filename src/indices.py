"""Índices de perigo: leitura diária, classificação e classes comuns."""

import glob
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from . import leitura as L


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_").lower()


def preencher(padrao, data):
    return (padrao.replace("{data}", data.strftime("%Y%m%d"))
            .replace("{ano}", data.strftime("%Y")).replace("{mes}", data.strftime("%m"))
            .replace("{dia}", data.strftime("%d")).replace("{doy}", data.strftime("%j")))


TEM_DATA = ("{data}", "{ano}", "{mes}", "{dia}", "{doy}")


class Indice:
    def __init__(self, cfg, caminho, cache_dir, classes_comuns_nomes=None):
        self.cfg = cfg
        self.nome = cfg["nome"]
        self.id = slug(self.nome)
        self.padrao = caminho(cfg["arquivos"]) if cfg.get("arquivos") else None
        self.download = cfg.get("download")
        self.cache = Path(cache_dir) / self.id
        self.variavel = cfg.get("variavel")
        self.nodata = cfg.get("nodata")
        self.fuso = cfg.get("fuso_horas", 0)
        self.tipo = cfg.get("tipo", "continuo")
        self.rotulos = [str(r) for r in cfg["rotulos"]]
        nr = len(self.rotulos)
        if self.tipo == "continuo":
            self.limites = np.asarray(cfg["limites"], float)
            if len(self.limites) != nr - 1:
                raise ValueError(f"{self.nome}: 'limites' precisa de {nr - 1} valores para {nr} rótulos")
            self.agregacao = cfg.get("agregacao", "media")
        elif self.tipo == "classes":
            self.codigos = list(cfg["codigos"])
            if len(self.codigos) != nr:
                raise ValueError(f"{self.nome}: 'codigos' e 'rotulos' devem ter o mesmo tamanho")
            self.agregacao = cfg.get("agregacao", "moda")
        elif self.tipo == "percentil":
            self.percentis = np.asarray(cfg["limites_percentis"], float)
            if len(self.percentis) != nr - 1:
                raise ValueError(f"{self.nome}: 'limites_percentis' precisa de {nr - 1} valores")
            self.climatologia = caminho(cfg["climatologia"])
            self.meses_clima = cfg.get("meses_climatologia")
            self.agregacao = cfg.get("agregacao", "media")
            self.limiares_celula = None
        else:
            raise ValueError(f"{self.nome}: tipo deve ser 'continuo', 'classes' ou 'percentil'")
        alta = str(cfg.get("classe_alta_a_partir_de", self.rotulos[-1]))
        if alta not in self.rotulos:
            raise ValueError(f"{self.nome}: classe_alta_a_partir_de='{alta}' não está em {self.rotulos}")
        self.k_alta = self.rotulos.index(alta)

        # Classes comuns (para a comparação entre índices)
        self.mapa_comum = None
        cc = cfg.get("classes_comuns")
        if cc and classes_comuns_nomes:
            mapa = {}
            for i, nome_c in enumerate(classes_comuns_nomes):
                for r in cc.get(nome_c, []) or []:
                    if str(r) not in self.rotulos:
                        raise ValueError(f"{self.nome}: classes_comuns usa '{r}', que não está em {self.rotulos}")
                    mapa[self.rotulos.index(str(r))] = i
            faltam = [r for k, r in enumerate(self.rotulos) if k not in mapa]
            if faltam:
                raise ValueError(f"{self.nome}: classes {faltam} não foram associadas a nenhuma classe comum")
            self.mapa_comum = np.array([mapa[k] for k in range(nr)])

    # ------------------------------------------------------------------ leitura
    def carregar(self, dias, grade, log):
        """Retorna {dia: valores na grade}. Registra faltas em log (lista)."""
        cods = self.codigos if self.tipo == "classes" else None
        out = {}
        if self.padrao and not any(t in self.padrao for t in TEM_DATA):
            # Arquivo(s) com vários dias (ex.: download do Copernicus/EWDS)
            arqs = sorted(glob.glob(self.padrao))
            if not arqs:
                for d in dias:
                    log.append({"índice": self.nome, "data": d.date(), "problema": f"nenhum arquivo em {self.padrao}"})
                return out
            try:
                todos = L.ler_netcdf_multidia(arqs, self.variavel, grade.bbox, self.nodata, self.fuso)
            except Exception as e:  # noqa: BLE001
                log.append({"índice": self.nome, "data": "-", "problema": f"erro de leitura: {e}"})
                return out
            for d in dias:
                if d in todos:
                    out[d] = L.agregar(*todos[d], grade, self.agregacao, cods)
                else:
                    log.append({"índice": self.nome, "data": d.date(), "problema": "dia ausente no(s) arquivo(s)"})
        else:
            for d in dias:
                arq = self._arquivo_dia(d, grade, log)
                if arq is None:
                    continue
                try:
                    if arq.lower().endswith((".nc", ".nc4", ".netcdf")):
                        v = L.ler_netcdf_dia(arq, self.variavel, grade.bbox, self.nodata)
                    else:
                        v = L.ler_geotiff(arq, grade.bbox, self.nodata)
                    out[d] = L.agregar(*v, grade, self.agregacao, cods)
                except Exception as e:  # noqa: BLE001
                    log.append({"índice": self.nome, "data": d.date(), "problema": f"erro de leitura: {e}"})
        if self.tipo == "percentil":
            self._preparar_percentis(grade, log)
        return out

    def _arquivo_dia(self, d, grade, log):
        if self.padrao:
            achados = sorted(glob.glob(preencher(self.padrao, d)))
            if achados:
                return achados[0]
        if self.download:
            url = preencher(self.download, d)
            destino = self.cache / Path(url).name
            if destino.exists():
                return str(destino)
            bruto = destino.with_suffix(".bruto" + destino.suffix)
            if L.baixar(url, bruto):
                try:
                    L.recortar_netcdf(bruto, destino, self.variavel, grade.bbox)
                    bruto.unlink()
                    return str(destino)
                except Exception as e:  # noqa: BLE001
                    log.append({"índice": self.nome, "data": d.date(), "problema": f"baixado, mas erro ao recortar: {e}"})
                    return str(bruto)
            log.append({"índice": self.nome, "data": d.date(), "problema": f"não foi possível baixar {url}"})
            return None
        log.append({"índice": self.nome, "data": d.date(), "problema": "arquivo não encontrado"})
        return None

    def _preparar_percentis(self, grade, log):
        arqs = sorted(glob.glob(self.climatologia))
        if not arqs:
            raise FileNotFoundError(f"{self.nome}: nenhum arquivo de climatologia em {self.climatologia}")
        serie = L.ler_netcdf_multidia(arqs, self.variavel, grade.bbox, self.nodata, self.fuso)
        if self.meses_clima:
            serie = {d: v for d, v in serie.items() if d.month in self.meses_clima}
        pilha = np.stack([L.agregar(*v, grade, self.agregacao) for v in serie.values()])
        self.n_clima = pilha.shape[0]
        self.anos_clima = (min(serie).year, max(serie).year)
        import warnings
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            self.limiares_celula = np.nanpercentile(pilha, self.percentis, axis=0)  # (k, n)

    # ------------------------------------------------------------ classificação
    def classificar(self, valores):
        """Classe (0..n-1) de cada célula; -1 sem dado."""
        cls = np.full(valores.shape, -1, int)
        ok = np.isfinite(valores)
        if self.tipo == "continuo":
            cls[ok] = np.digitize(valores[ok], self.limites)
        elif self.tipo == "classes":
            mapa = {c: i for i, c in enumerate(self.codigos)}
            cls[ok] = [mapa.get(int(round(v)), -1) for v in valores[ok]]
        else:
            thr = self.limiares_celula
            ok &= np.all(np.isfinite(thr), axis=0)
            cls[ok] = (valores[ok][None, :] >= thr[:, ok]).sum(axis=0)
        return cls

    def comum(self, cls):
        """Converte classes próprias em classes comuns (0..k-1); -1 sem dado."""
        if self.mapa_comum is None:
            return None
        out = np.full(cls.shape, -1, int)
        ok = cls >= 0
        out[ok] = self.mapa_comum[cls[ok]]
        return out

    def descricao_classes(self):
        if self.tipo == "continuo":
            lim = list(self.limites)
            partes = []
            for k, r in enumerate(self.rotulos):
                if k == 0:
                    partes.append(f"{r} (< {lim[0]:g})")
                elif k == len(self.rotulos) - 1:
                    partes.append(f"{r} (≥ {lim[-1]:g})")
                else:
                    partes.append(f"{r} ({lim[k - 1]:g} a {lim[k]:g})")
            return "; ".join(partes)
        if self.tipo == "classes":
            return "; ".join(f"{r} (código {c})" for r, c in zip(self.rotulos, self.codigos))
        p = list(self.percentis)
        partes = []
        for k, r in enumerate(self.rotulos):
            if k == 0:
                partes.append(f"{r} (< P{p[0]:g})")
            elif k == len(self.rotulos) - 1:
                partes.append(f"{r} (≥ P{p[-1]:g})")
            else:
                partes.append(f"{r} (P{p[k - 1]:g} a P{p[k]:g})")
        return "; ".join(partes)
