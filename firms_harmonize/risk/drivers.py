"""Fatores externos do modelo de mês crítico (passos 2 e 3).

ONI (Oceanic Niño Index, NOAA CPC): anomalia da temperatura do mar no Niño 3.4, em médias móveis de
três meses (DJF, JFM, ...). O ano da linha é o do mês central (NDJ 2009 = nov/2009–jan/2010).
Cada trimestre é indexado pelo **último** mês: a variável do mês t usa o trimestre que termina em t,
porque o trimestre centrado em t já inclui t+1, que é o mês do alvo.

Biomas (IBGE, "Biomas_5000mil.zip", 1:5.000.000, SIRGAS 2000 em graus ≈ WGS84 dos focos): a API de
malhas do IBGE não tem biomas, então o shapefile vem do geoftp oficial. Só os 6 biomas terrestres
entram; cada célula recebe o bioma do seu centro ou, se o centro cair fora (mar, vãos), o mais próximo.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import shapefile
import shapely
from shapely.geometry import shape

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
_SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                  "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}


def parse_oni(text: str) -> pd.DataFrame:
    """Texto do arquivo da NOAA → DataFrame (ym_fim, oni), em ordem e sem meses repetidos."""
    try:
        raw = pd.read_csv(io.StringIO(text), sep=r"\s+")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise ValueError(f"arquivo ONI ilegível: {e}") from None
    if not {"SEAS", "YR", "ANOM"} <= set(raw.columns) or raw.empty:
        raise ValueError(f"arquivo ONI sem as colunas SEAS, YR e ANOM: {list(raw.columns)[:5]}")
    center = raw["SEAS"].map(_SEASON_CENTER)
    if center.isna().any():
        raise ValueError(f"trimestre desconhecido no arquivo ONI: {raw.loc[center.isna(), 'SEAS'].iloc[0]}")
    ym_center = pd.PeriodIndex.from_fields(year=raw["YR"].astype(int), month=center.astype(int), freq="M")
    out = pd.DataFrame({"ym_fim": ym_center + 1, "oni": pd.to_numeric(raw["ANOM"], errors="raise")})
    out = out.sort_values("ym_fim").reset_index(drop=True)
    if out["ym_fim"].duplicated().any():
        raise ValueError("arquivo ONI com trimestre repetido")
    return out


def read_oni(path: Path) -> pd.DataFrame:
    return parse_oni(Path(path).read_text())


def fetch_oni(dest: Path, session: requests.Session | None = None, url: str = ONI_URL,
              timeout: int = 60) -> Path:
    """Baixa o ONI, valida e só então grava em `dest` (nunca salva uma página de erro)."""
    r = (session or requests.Session()).get(url, timeout=timeout)
    r.raise_for_status()
    parse_oni(r.text)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(r.text)
    return dest


def add_oni(panel: pd.DataFrame, oni: pd.DataFrame) -> pd.DataFrame:
    """`oni_atual`: trimestre que termina em t; `oni_3m`: média dos trimestres que terminam em t−2..t."""
    s = oni.set_index("ym_fim")["oni"]
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    three = s.rolling(3, min_periods=3).mean()
    ym = pd.PeriodIndex(panel["ym"], freq="M")
    atual, media = s.reindex(ym).to_numpy(), three.reindex(ym).to_numpy()
    missing = np.isnan(atual) | np.isnan(media)
    if missing.any():
        meses = sorted({str(m) for m in ym[missing]})
        raise ValueError(f"ONI ausente para {len(meses)} mês(es) do painel, ex.: {meses[:3]}")
    return panel.assign(oni_atual=atual, oni_3m=media)


# ---------- biomas ----------

BIOMES_URL = ("https://geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/biomas/vetores/"
              "Biomas_5000mil.zip")
BIOME_CODES = {"AMZ": "Amazônia", "CAAT": "Caatinga", "CER": "Cerrado",
               "MAT": "Mata Atlântica", "PMP": "Pampa", "PTN": "Pantanal"}


def read_biomes(zip_path: Path) -> dict:
    """Zip do IBGE → {código: geometria shapely}, só com os biomas terrestres."""
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("arquivo de biomas não é um zip válido") from None
    with z:
        bases = [n[:-4] for n in z.namelist() if n.lower().endswith(".shp")]
        if not bases:
            raise ValueError("zip de biomas sem arquivo .shp")
        reader = shapefile.Reader(shp=io.BytesIO(z.read(bases[0] + ".shp")),
                                  dbf=io.BytesIO(z.read(bases[0] + ".dbf")), encoding="latin-1")
    fields = [f[0] for f in reader.fields[1:]]
    if "COD_BIOMA" not in fields:
        raise ValueError(f"shapefile de biomas sem o campo COD_BIOMA: {fields}")
    out = {}
    for rec, shp in zip(reader.records(), reader.shapes()):
        code = str(rec["COD_BIOMA"]).strip()
        if code in BIOME_CODES:
            out[code] = shapely.make_valid(shape(shp.__geo_interface__))
    if not out:
        raise ValueError("shapefile sem nenhum bioma terrestre conhecido")
    return out


def fetch_biomes(dest: Path, session: requests.Session | None = None, url: str = BIOMES_URL,
                 timeout: int = 120) -> Path:
    """Baixa o zip de biomas, valida e só então grava em `dest`."""
    r = (session or requests.Session()).get(url, timeout=timeout)
    r.raise_for_status()
    dest = Path(dest)
    tmp = dest.with_suffix(".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(r.content)
    try:
        read_biomes(tmp)
    except ValueError:
        tmp.unlink()
        raise
    tmp.replace(dest)
    return dest


def assign_biome(cells: pd.DataFrame, biomes: dict, res: float) -> pd.DataFrame:
    """Bioma do centro de cada célula; fora de todos, o bioma mais próximo (marcado)."""
    lat = (cells["cy"].to_numpy() + 0.5) * res
    lon = (cells["cx"].to_numpy() + 0.5) * res
    codes = np.full(len(cells), "", dtype=object)
    for code, geom in biomes.items():
        inside = shapely.contains_xy(geom, lon, lat) & (codes == "")
        codes[inside] = code
    outside = codes == ""
    if outside.any():
        points = shapely.points(lon[outside], lat[outside])
        names = list(biomes)
        dist = np.column_stack([shapely.distance(points, biomes[c]) for c in names])
        codes[outside] = np.array(names, dtype=object)[np.argmin(dist, axis=1)]
    return cells.assign(bioma=codes, bioma_por_proximidade=outside)


def add_biome(panel: pd.DataFrame, biomes: dict, res: float) -> pd.DataFrame:
    """`bioma` e uma coluna 0/1 por bioma (`bioma_AMZ`, ...), iguais em todos os meses da célula."""
    cells = assign_biome(panel[["cy", "cx"]].drop_duplicates(), biomes, res)
    out = panel.merge(cells[["cy", "cx", "bioma"]], on=["cy", "cx"], how="left")
    return out.assign(**{f"bioma_{c}": out["bioma"].eq(c).astype(int) for c in BIOME_CODES})
