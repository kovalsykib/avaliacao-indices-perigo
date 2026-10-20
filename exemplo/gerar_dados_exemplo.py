#!/usr/bin/env python3
"""
Gera dados SIMULADOS (não reais!) para testar o programa.

Cria em exemplo/dados/, nos mesmos formatos esperados para os dados reais:
  regioes_simuladas.geojson                      duas regiões fictícias (Chaco / Oriental)
  indice_proposto/indice_AAAAMMDD.tif            classes 1-4, GeoTIFF 0,1° (como export do GEE)
  inpe/INPE_FireRiskModel_2.2_FireRisk_AAAAMMDD.nc   RF 0-1, NetCDF diário 0,05°
  gwis/fwi_ago_set_2025.nc                       FWI, NetCDF único com vários dias (como o EWDS),
                                                 longitude 0–360, dimensão valid_time
  gwis/climatologia/fwi_climatologia.nc          FWI de ago–set 2000–2024 (para o ranking)
  focos/focos_simulados.csv                      formato BDQueimadas (hora UTC)

Uso:  python exemplo/gerar_dados_exemplo.py
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import xarray as xr
import rasterio
from rasterio.transform import from_origin

rng = np.random.default_rng(42)
pasta = Path(__file__).resolve().parent / "dados"
for sub in ("indice_proposto", "inpe", "gwis/climatologia", "focos"):
    (pasta / sub).mkdir(parents=True, exist_ok=True)

XMIN, XMAX, YMIN, YMAX = -62.7, -54.2, -27.7, -19.2
dias = pd.date_range("2025-08-01", "2025-09-30")

chaco = [[-62.6, -19.3], [-58.2, -19.3], [-57.6, -22.0], [-57.6, -25.3], [-58.6, -27.2],
         [-62.6, -22.4], [-62.6, -19.3]]
oriental = [[-58.2, -19.3], [-54.3, -22.5], [-54.6, -26.0], [-55.8, -27.6], [-58.6, -27.2],
            [-57.6, -25.3], [-57.6, -22.0], [-58.2, -19.3]]
(pasta / "regioes_simuladas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"regiao": "Chaco"}, "geometry": {"type": "Polygon", "coordinates": [chaco]}},
    {"type": "Feature", "properties": {"regiao": "Oriental"}, "geometry": {"type": "Polygon", "coordinates": [oriental]}},
]}))


def secura(lon, lat, t, ano_extra=0.0):
    oeste = (lon - XMAX) / (XMIN - XMAX)
    onda = 0.5 + 0.5 * np.sin(2 * np.pi * t / 9.0 + 0.6 * lon) * np.cos(2 * np.pi * t / 23.0)
    return np.clip(0.35 * oeste + 0.45 * onda + t / len(dias) * 0.25 + ano_extra
                   + 0.08 * rng.standard_normal(np.shape(lon)), 0, 1)


def grade(res, x0=XMIN, y1=YMAX):
    return np.arange(x0 + res / 2, XMAX, res), np.arange(y1 - res / 2, YMIN, -res)


# Focos (Poisson, taxa crescente com a secura)
lonf, latf = grade(0.05)
LF, AF = np.meshgrid(lonf, latf)
linhas = []
for t, d in enumerate(dias):
    n = rng.poisson(0.0004 * np.exp(6.0 * secura(LF, AF, t - 0.7)))
    for ii, jj in zip(*np.nonzero(n)):
        for _ in range(n[ii, jj]):
            ts = d + pd.Timedelta(hours=int(rng.choice([4, 5, 16, 17, 18])), minutes=int(rng.integers(0, 60)))
            linhas.append({"DataHora": ts.strftime("%Y/%m/%d %H:%M:%S"), "Satelite": "AQUA_M-T",
                           "Pais": "Paraguai", "Latitude": round(AF[ii, jj] + rng.uniform(-.025, .025), 4),
                           "Longitude": round(LF[ii, jj] + rng.uniform(-.025, .025), 4)})
focos = pd.DataFrame(linhas)
pd.concat([focos, focos.sample(frac=0.1, random_state=1).assign(Satelite="NPP-375")]).to_csv(
    pasta / "focos" / "focos_simulados.csv", index=False)

lon10, lat10 = grade(0.1)
lon05, lat05 = grade(0.05)
lon25, lat25 = grade(0.25, x0=XMIN - 0.125, y1=YMAX + 0.125)
L25, A25 = np.meshgrid(lon25, lat25)
fwi_dias = []
for t, d in enumerate(dias):
    tag = d.strftime("%Y%m%d")
    L, A = np.meshgrid(lon10, lat10)
    cls = np.digitize(secura(L, A, t), [0.35, 0.55, 0.72]) + 1
    with rasterio.open(pasta / "indice_proposto" / f"indice_{tag}.tif", "w", driver="GTiff",
                       height=cls.shape[0], width=cls.shape[1], count=1, dtype="uint8", crs="EPSG:4326",
                       transform=from_origin(XMIN, YMAX, 0.1, 0.1), nodata=0) as dst:
        dst.write(cls.astype("uint8"), 1)
    L, A = np.meshgrid(lon05, lat05)
    rf = np.clip(secura(L, A, t) * 1.1 - 0.02, 0, 1).astype("float32")
    xr.Dataset({"rf": (("time", "lat", "lon"), rf[None])}, coords={"time": [0], "lat": lat05, "lon": lon05}
               ).to_netcdf(pasta / "inpe" / f"INPE_FireRiskModel_2.2_FireRisk_{tag}.nc")
    fwi_dias.append(np.clip(80 * secura(L25, A25, t) ** 1.5, 0, None))

fwi = np.stack(fwi_dias).astype("float32")
fwi = np.delete(fwi, 45, axis=0)                       # simula um dia faltante (15/09)
tempos = np.delete(dias.values, 45) + np.timedelta64(12, "h")
lon360 = lon25 % 360                                   # longitudes 0–360, como alguns downloads globais
xr.Dataset({"fwinx": (("valid_time", "latitude", "longitude"), fwi)},
           coords={"valid_time": tempos, "latitude": lat25, "longitude": lon360}
           ).to_netcdf(pasta / "gwis" / "fwi_ago_set_2025.nc")

# Climatologia: ago–set de 2000 a 2024
blocos, tt = [], []
for ano in range(2000, 2025):
    extra = rng.normal(-0.05, 0.08)
    for t, d in enumerate(pd.date_range(f"{ano}-08-01", f"{ano}-09-30")):
        blocos.append(np.clip(80 * secura(L25, A25, t, extra) ** 1.5, 0, None))
        tt.append(d + pd.Timedelta(hours=12))
xr.Dataset({"fwinx": (("valid_time", "latitude", "longitude"), np.stack(blocos).astype("float32"))},
           coords={"valid_time": tt, "latitude": lat25, "longitude": lon360}
           ).to_netcdf(pasta / "gwis" / "climatologia" / "fwi_climatologia.nc")
print(f"Dados simulados gravados em {pasta} ({len(focos)} focos)")
