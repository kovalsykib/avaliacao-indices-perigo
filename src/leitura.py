"""Leitura de dados: grade comum, rasters (GeoTIFF/NetCDF), focos e regiões."""

import glob
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
from rasterio.features import rasterize
from rasterio.transform import from_origin
import geopandas as gpd
import xarray as xr
from pyproj import Transformer

NOMES_LAT = ("lat", "latitude", "y", "LAT", "Latitude")
NOMES_LON = ("lon", "longitude", "x", "LON", "Longitude")
NOMES_TEMPO = ("time", "valid_time", "date", "t", "Time")


# ----------------------------------------------------------------------------
# Grade comum
# ----------------------------------------------------------------------------
class Grade:
    """Grade regular em graus (EPSG:4326)."""

    def __init__(self, xmin, ymin, xmax, ymax, res):
        self.res = res
        self.xmin = np.floor(xmin / res) * res
        self.ymax = np.ceil(ymax / res) * res
        self.ncol = int(np.ceil((xmax - self.xmin) / res))
        self.nlin = int(np.ceil((self.ymax - ymin) / res))
        self.xmax = self.xmin + self.ncol * res
        self.ymin = self.ymax - self.nlin * res
        self.transform = from_origin(self.xmin, self.ymax, res, res)
        self.lon = self.xmin + res * (np.arange(self.ncol) + 0.5)
        self.lat = self.ymax - res * (np.arange(self.nlin) + 0.5)

    @property
    def n(self):
        return self.nlin * self.ncol

    @property
    def bbox(self):
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    def indices(self, lon, lat):
        col = np.floor((np.asarray(lon, float) - self.xmin) / self.res).astype(int)
        lin = np.floor((self.ymax - np.asarray(lat, float)) / self.res).astype(int)
        ok = (col >= 0) & (col < self.ncol) & (lin >= 0) & (lin < self.nlin)
        return np.where(ok, lin * self.ncol + col, -1)


# ----------------------------------------------------------------------------
# Agregação para a grade
# ----------------------------------------------------------------------------
def agregar(val, lon, lat, grade, metodo="media", codigos=None):
    """Agrega pixels de origem (val 2D, lon/lat 1D ou 2D) para a grade.
    Células sem pixel de origem (fonte mais grossa) recebem o vizinho mais próximo."""
    lon2, lat2 = (np.meshgrid(lon, lat) if np.ndim(lon) == 1 else (lon, lat))
    v = np.asarray(val, float).ravel()
    idx = grade.indices(lon2.ravel(), lat2.ravel())
    ok = (idx >= 0) & np.isfinite(v)
    idx, v = idx[ok], v[ok]
    saida = np.full(grade.n, np.nan)
    cont = np.bincount(idx, minlength=grade.n)
    tem = cont > 0
    if metodo == "media":
        soma = np.bincount(idx, weights=v, minlength=grade.n)
        saida[tem] = soma[tem] / cont[tem]
    elif metodo == "moda":
        codigos = list(codigos) if codigos is not None else list(np.unique(v))
        if codigos:
            freq = np.stack([np.bincount(idx, weights=(v == c).astype(float), minlength=grade.n)
                             for c in codigos])
            saida[tem] = np.asarray(codigos, float)[freq[:, tem].argmax(axis=0)]
    else:
        raise ValueError(f"agregacao desconhecida: {metodo}")

    vazias = np.where(~tem)[0]
    if len(vazias) and np.ndim(lon) == 1 and len(lon) > 1 and len(lat) > 1:
        lin_t, col_t = np.divmod(vazias, grade.ncol)
        xt, yt = grade.lon[col_t], grade.lat[lin_t]
        dlon, dlat = lon[1] - lon[0], lat[1] - lat[0]
        j = np.rint((xt - lon[0]) / dlon).astype(int)
        i = np.rint((yt - lat[0]) / dlat).astype(int)
        dentro = (j >= 0) & (j < len(lon)) & (i >= 0) & (i < len(lat))
        # só preenche se o pixel mais próximo está a menos de 1 pixel de distância
        perto = dentro.copy()
        perto[dentro] = (np.abs(lon[j[dentro]] - xt[dentro]) <= abs(dlon)) & \
                        (np.abs(lat[i[dentro]] - yt[dentro]) <= abs(dlat))
        saida[vazias[perto]] = np.asarray(val, float)[i[perto], j[perto]]
    return saida


# ----------------------------------------------------------------------------
# NetCDF
# ----------------------------------------------------------------------------
def _dims(da):
    nlat = next((n for n in NOMES_LAT if n in da.dims), None)
    nlon = next((n for n in NOMES_LON if n in da.dims), None)
    if nlat is None or nlon is None:
        raise ValueError(f"não achei as dimensões de latitude/longitude em {da.dims}")
    ntempo = next((n for n in NOMES_TEMPO if n in da.dims), None)
    return nlat, nlon, ntempo


def _escolher_variavel(ds, variavel, caminho):
    if variavel:
        if variavel not in ds.data_vars:
            raise ValueError(f"{caminho}: variável '{variavel}' não existe. "
                             f"Variáveis disponíveis: {list(ds.data_vars)}")
        return variavel
    cands = [v for v in ds.data_vars if ds[v].ndim >= 2]
    if not cands:
        raise ValueError(f"{caminho}: nenhuma variável 2D encontrada")
    return cands[0]


def _recortar(da, nlat, nlon, bbox):
    """Recorta à bbox, convertendo longitudes 0–360 para −180–180 se preciso."""
    lon = da[nlon].values
    if np.nanmax(lon) > 180:
        da = da.assign_coords({nlon: ((da[nlon] + 180) % 360) - 180}).sortby(nlon)
    xmin, ymin, xmax, ymax = bbox
    lat = da[nlat].values
    fatia_lat = slice(ymax, ymin) if lat[0] > lat[-1] else slice(ymin, ymax)
    return da.sel({nlon: slice(xmin, xmax), nlat: fatia_lat})


def _limpar(da, val, nodata):
    if nodata is not None:
        val[val == nodata] = np.nan
    for chave in ("_FillValue", "missing_value"):
        fv = da.attrs.get(chave, da.encoding.get(chave))
        if fv is not None:
            val[val == fv] = np.nan
    return val


def ler_netcdf_dia(caminho, variavel, bbox, nodata=None):
    """NetCDF de um dia → (val 2D, lon 1D, lat 1D)."""
    with xr.open_dataset(caminho, decode_times=False) as ds:
        var = _escolher_variavel(ds, variavel, caminho)
        da = ds[var]
        nlat, nlon, _ = _dims(da)
        for d in da.dims:
            if d not in (nlat, nlon):
                da = da.isel({d: 0})
        da = _recortar(da, nlat, nlon, bbox).transpose(nlat, nlon)
        val = _limpar(da, da.values.astype("float64"), nodata)
        return val, da[nlon].values.astype(float), da[nlat].values.astype(float)


def ler_netcdf_multidia(arquivos, variavel, bbox, nodata=None, fuso_horas=0):
    """Um ou mais NetCDF com dimensão de tempo → {Timestamp(dia): (val, lon, lat)}."""
    saida = {}
    for caminho in arquivos:
        with xr.open_dataset(caminho) as ds:
            var = _escolher_variavel(ds, variavel, caminho)
            da = ds[var]
            nlat, nlon, ntempo = _dims(da)
            if ntempo is None:
                raise ValueError(f"{caminho}: sem dimensão de tempo; use {{data}} no padrão do nome")
            for d in da.dims:
                if d not in (nlat, nlon, ntempo):
                    da = da.isel({d: 0})
            da = _recortar(da, nlat, nlon, bbox).transpose(ntempo, nlat, nlon)
            tempos = pd.to_datetime(da[ntempo].values) + pd.Timedelta(hours=fuso_horas)
            vals = da.values.astype("float64")
            lon, lat = da[nlon].values.astype(float), da[nlat].values.astype(float)
            for t, v in zip(tempos, vals):
                saida[t.normalize()] = (_limpar(da, v.copy(), nodata), lon, lat)
    return saida


# ----------------------------------------------------------------------------
# GeoTIFF
# ----------------------------------------------------------------------------
def ler_geotiff(caminho, bbox, nodata=None, banda=1):
    with rasterio.open(caminho) as src:
        crs = src.crs
        geo = crs is None or crs.to_epsg() == 4326
        if not geo:
            t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            xs, ys = t.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
            b = (min(xs), min(ys), max(xs), max(ys))
        else:
            b = bbox
        jan = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
        val = src.read(banda, window=jan, boundless=True, fill_value=src.nodata if src.nodata is not None else 0)
        val = val.astype("float64")
        tr = src.window_transform(jan)
        nd = nodata if nodata is not None else src.nodata
        if nd is not None:
            val[val == nd] = np.nan
        if geo and tr.b == 0 and tr.d == 0:
            lon = tr.c + (np.arange(val.shape[1]) + 0.5) * tr.a
            lat = tr.f + (np.arange(val.shape[0]) + 0.5) * tr.e
            return val, lon, lat
        lin, col = np.mgrid[0:val.shape[0], 0:val.shape[1]]
        x = tr.c + (col + 0.5) * tr.a + (lin + 0.5) * tr.b
        y = tr.f + (col + 0.5) * tr.d + (lin + 0.5) * tr.e
        if not geo:
            x, y = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return val, x, y


# ----------------------------------------------------------------------------
# Download (ex.: RF do INPE direto do dataserver)
# ----------------------------------------------------------------------------
def baixar(url, destino, tentativas=3):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "avaliacao-indices-perigo"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
            tmp.replace(destino)
            return True
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) == 404:
                return False
            time.sleep(3 * (i + 1))
    if tmp.exists():
        tmp.unlink()
    return False


def recortar_netcdf(origem, destino, variavel, bbox):
    """Salva só a área de estudo (economiza espaço no cache)."""
    with xr.open_dataset(origem, decode_times=False) as ds:
        var = _escolher_variavel(ds, variavel, origem)
        da = ds[var]
        nlat, nlon, _ = _dims(da)
        da = _recortar(da, nlat, nlon, bbox).load()
    da.to_dataset(name=var).to_netcdf(destino)


# ----------------------------------------------------------------------------
# Focos de calor
# ----------------------------------------------------------------------------
def ler_focos(cfg, grade, inicio, fim):
    arquivos = sorted(glob.glob(cfg["arquivo"]))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum arquivo de focos encontrado em: {cfg['arquivo']}")
    partes = [pd.read_csv(a, sep=cfg.get("separador", ","), encoding=cfg.get("codificacao", "utf-8"),
                          decimal=cfg.get("decimal", "."), low_memory=False) for a in arquivos]
    df = pd.concat(partes, ignore_index=True)
    obrig = [cfg["coluna_data"], cfg["coluna_lat"], cfg["coluna_lon"]] + \
            ([cfg["coluna_hora"]] if cfg.get("coluna_hora") else [])
    for c in obrig:
        if c not in df.columns:
            raise ValueError(f"Coluna '{c}' não encontrada no CSV de focos. Colunas: {list(df.columns)}")
    for col, valores in (cfg.get("filtro") or {}).items():
        if col not in df.columns:
            raise ValueError(f"Coluna do filtro '{col}' não existe no CSV de focos. Colunas: {list(df.columns)}")
        valores = valores if isinstance(valores, list) else [valores]
        df = df[df[col].astype(str).isin([str(v) for v in valores])]
    fmt = cfg.get("formato_data")
    datas = pd.to_datetime(df[cfg["coluna_data"]].astype(str), format=fmt) if fmt else \
        pd.to_datetime(df[cfg["coluna_data"]].astype(str), format="mixed")
    if cfg.get("coluna_hora"):  # ex.: FIRMS acq_time = HHMM
        hhmm = df[cfg["coluna_hora"]].astype(int)
        datas = datas + pd.to_timedelta(hhmm // 100, unit="h") + pd.to_timedelta(hhmm % 100, unit="m")
    datas = datas + pd.to_timedelta(cfg.get("fuso_horas", 0), unit="h")
    out = pd.DataFrame({"data": datas.dt.normalize().values,
                        "lat": pd.to_numeric(df[cfg["coluna_lat"]]).values,
                        "lon": pd.to_numeric(df[cfg["coluna_lon"]]).values})
    out = out[(out.data >= inicio) & (out.data <= fim + pd.Timedelta(days=1))].copy()
    out["celula"] = grade.indices(out.lon.values, out.lat.values)
    return out


# ----------------------------------------------------------------------------
# Regiões
# ----------------------------------------------------------------------------
def ler_regioes(cfg):
    arqs = sorted(glob.glob(cfg["arquivo"]))
    if not arqs:
        raise FileNotFoundError(f"Arquivo de regiões não encontrado: {cfg['arquivo']}")
    gdf = gpd.read_file(arqs[0], layer=cfg.get("camada")) if cfg.get("camada") else gpd.read_file(arqs[0])
    gdf = gdf.to_crs(4326) if gdf.crs is not None else gdf.set_crs(4326)
    campo = cfg.get("campo")
    if campo:
        nomes = gdf[campo].astype(str)
        agrupar = cfg.get("agrupar") or {}
        mapa = {str(v): reg for reg, lista in agrupar.items() for v in lista}
        resto = cfg.get("demais")
        nomes = nomes.map(lambda n: mapa.get(n, resto if (resto and agrupar) else n))
    else:
        nomes = pd.Series([cfg.get("nome_total", "Total")] * len(gdf))
    gdf = gdf.assign(_regiao=nomes.values)
    return gdf


def rasterizar_regioes(gdf, grade, todas_tocadas=False):
    regioes = sorted(gdf["_regiao"].unique())
    cod = {r: i + 1 for i, r in enumerate(regioes)}
    shapes = [(geom, cod[n]) for geom, n in zip(gdf.geometry, gdf["_regiao"])]
    ras = rasterize(shapes, out_shape=(grade.nlin, grade.ncol), transform=grade.transform,
                    fill=0, dtype="int32", all_touched=todas_tocadas).ravel()
    return ras, regioes, cod
