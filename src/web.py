"""Funções de apoio para a calculadora no navegador (Pyodide)."""

import io
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import xarray as xr
import yaml

from . import leitura as L


def inspecionar_netcdf(caminho):
    """Lista as variáveis com 2+ dimensões e as dimensões de um NetCDF."""
    with xr.open_dataset(caminho, decode_times=False) as ds:
        vars_ = [{"nome": v, "dims": list(ds[v].dims), "forma": list(ds[v].shape),
                  "descricao": str(ds[v].attrs.get("long_name", ds[v].attrs.get("standard_name", "")))}
                 for v in ds.data_vars if ds[v].ndim >= 2]
        tempo = next((d for d in L.NOMES_TEMPO if d in ds.dims), None)
        n_tempo = int(ds.sizes[tempo]) if tempo else 1
    return json.dumps({"variaveis": vars_, "n_tempo": n_tempo})


def inspecionar_regioes(caminho, campo=None):
    import geopandas as gpd
    gdf = gpd.read_file(caminho)
    campos = [c for c in gdf.columns if c != "geometry"]
    valores = []
    if campo and campo in gdf.columns:
        valores = sorted(map(str, gdf[campo].dropna().unique()))
    elif campos:
        candidato = next((c for c in campos if c.upper() in ("NAME_1", "NOMBRE", "NOME", "REGIAO", "REGION")), campos[0])
        campo = candidato
        valores = sorted(map(str, gdf[campo].dropna().unique()))
    b = gdf.to_crs(4326).total_bounds if gdf.crs is not None else gdf.total_bounds
    return json.dumps({"campos": campos, "campo": campo, "valores": valores,
                       "n": int(len(gdf)), "bbox": [float(x) for x in b]})


def bbox_trabalho(caminho_regioes, res):
    import geopandas as gpd
    gdf = gpd.read_file(caminho_regioes)
    gdf = gdf.to_crs(4326) if gdf.crs is not None else gdf
    b = gdf.total_bounds
    g = L.Grade(b[0] - res, b[1] - res, b[2] + res, b[3] + res, res)
    return [g.xmin, g.ymin, g.xmax, g.ymax]


def recortar(origem, destino, variavel, bbox):
    """Recorta um NetCDF grande à área de estudo e apaga o original (economiza memória)."""
    try:
        L.recortar_netcdf(origem, destino, variavel or None, tuple(bbox))
        os.remove(origem)
        return "ok"
    except Exception as e:  # noqa: BLE001
        os.replace(origem, destino)
        return f"não recortado ({e})"


def executar(config_json, pasta_trabalho="/trabalho"):
    """Roda a análise completa e devolve os caminhos dos produtos."""
    import rodar
    cfg = json.loads(config_json)
    cfg["pagina_embutida"] = True
    trab = Path(pasta_trabalho)
    trab.mkdir(parents=True, exist_ok=True)
    caminho_cfg = trab / "config.yaml"
    caminho_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    rodar.main(str(caminho_cfg))
    saida = Path(cfg["saida"]["pasta"])
    if not saida.is_absolute():
        saida = trab / saida
    # zip com tudo (página relativa + imagens + Excel + config)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(saida.rglob("*")):
            if arq.is_file():
                z.write(arq, f"resultados/{arq.relative_to(saida)}")
        z.write(caminho_cfg, "config.yaml")
    zip_path = trab / "resultados.zip"
    zip_path.write_bytes(buf.getvalue())
    return json.dumps({"pagina": str(saida / "index.html"), "zip": str(zip_path),
                       "excel": str(saida / "avaliacao.xlsx"), "config": str(caminho_cfg)})
