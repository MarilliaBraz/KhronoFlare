"""Leitura dos CSVs do FIRMS (Archive Download ou Area API) num esquema único.

Esquema padronizado:
    lat, lon, date (datetime64), hhmm (str 'HHMM' UTC), sensor ('MODIS'|'VIIRS'),
    platform ('Terra'|'Aqua'|'SNPP'|'NOAA20'|'NOAA21'), conf ('low'|'nominal'|'high'),
    frp (MW), daynight ('D'|'N'), type (Int, <NA> quando o produto não informa),
    processing ('SP'|'NRT')
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

COLUMNS = ["lat", "lon", "date", "hhmm", "sensor", "platform", "conf",
           "frp", "daynight", "type", "processing"]

_PLATFORM = {
    # MODIS
    "terra": "Terra", "t": "Terra", "aqua": "Aqua", "a": "Aqua",
    # VIIRS (a API usa N, N20, N21; arquivos antigos podem trazer 1/2 ou J1/J2)
    "n": "SNPP", "npp": "SNPP", "snpp": "SNPP", "suomi npp": "SNPP", "suomi-npp": "SNPP",
    "n20": "NOAA20", "1": "NOAA20", "j1": "NOAA20", "noaa-20": "NOAA20", "noaa20": "NOAA20",
    "n21": "NOAA21", "2": "NOAA21", "j2": "NOAA21", "noaa-21": "NOAA21", "noaa21": "NOAA21",
}
_VIIRS_CONF = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal",
               "h": "high", "high": "high"}


def modis_conf_class(values: pd.Series) -> pd.Series:
    """Confiança MODIS 0-100 → classe (guia MODIS C6/C6.1, Tabela 11):
    0 ≤ C < 30 baixa; 30 ≤ C < 80 nominal; 80 ≤ C ≤ 100 alta."""
    c = pd.to_numeric(values, errors="coerce")
    out = np.select([c < 30, c < 80, c <= 100], ["low", "nominal", "high"], default="")
    return pd.Series(out, index=values.index).replace("", pd.NA)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Converte um DataFrame cru do FIRMS para o esquema padronizado."""
    cols = {c.lower(): c for c in df.columns}
    if "bright_ti4" in cols:
        sensor = "VIIRS"
    elif "brightness" in cols:
        sensor = "MODIS"
    else:
        raise ValueError(f"Colunas não reconhecidas como MODIS nem VIIRS: {list(df.columns)}")
    g = lambda name: df[cols[name]]  # noqa: E731

    platform = g("satellite").astype(str).str.strip().str.lower().map(_PLATFORM)
    if platform.isna().any():
        unknown = sorted(g("satellite").astype(str)[platform.isna()].unique())[:5]
        raise ValueError(f"Satélite desconhecido em {sensor}: {unknown}")

    if sensor == "MODIS":
        conf = modis_conf_class(g("confidence"))
    else:
        conf = g("confidence").astype(str).str.strip().str.lower().map(_VIIRS_CONF)

    version = g("version").astype(str) if "version" in cols else pd.Series("", index=df.index)
    processing = np.where(version.str.contains("RT", case=False), "NRT", "SP")

    typ = (pd.to_numeric(g("type"), errors="coerce").astype("Int64")
           if "type" in cols else pd.Series(pd.NA, index=df.index, dtype="Int64"))

    out = pd.DataFrame({
        "lat": pd.to_numeric(g("latitude"), errors="coerce"),
        "lon": pd.to_numeric(g("longitude"), errors="coerce"),
        "date": pd.to_datetime(g("acq_date"), errors="coerce"),
        "hhmm": pd.to_numeric(g("acq_time"), errors="coerce").astype("Int64")
                  .astype(str).str.zfill(4),
        "sensor": sensor,
        "platform": platform.values,
        "conf": conf.values,
        "frp": pd.to_numeric(g("frp"), errors="coerce") if "frp" in cols else np.nan,
        "daynight": g("daynight").astype(str).str.strip().str.upper() if "daynight" in cols else pd.NA,
        "type": typ.values,
        "processing": processing,
    })
    return out.dropna(subset=["lat", "lon", "date"])[COLUMNS]


def iter_csv(path: Path, chunksize: int = 500_000) -> Iterator[pd.DataFrame]:
    """Lê um CSV do FIRMS em blocos, já padronizados. Aceita .csv e .csv.gz."""
    for chunk in pd.read_csv(path, chunksize=chunksize, low_memory=False):
        if len(chunk):
            yield normalize(chunk)


def find_csvs(folder: Path) -> list[Path]:
    return sorted([*folder.rglob("*.csv"), *folder.rglob("*.csv.gz")])
