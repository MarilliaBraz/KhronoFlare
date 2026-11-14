"""Recorte espacial e grade regular."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

IBGE_BRASIL_URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
                   "?formato=application/vnd.geo+json&qualidade=intermediaria")


def load_boundary(path: Path):
    """Lê um GeoJSON (FeatureCollection, Feature ou Geometry) e devolve uma geometria preparada."""
    gj = json.loads(Path(path).read_text())
    if gj.get("type") == "FeatureCollection":
        geom = unary_union([shape(f["geometry"]) for f in gj["features"]])
    elif gj.get("type") == "Feature":
        geom = shape(gj["geometry"])
    else:
        geom = shape(gj)
    shapely.prepare(geom)
    return geom


def fetch_boundary_ibge(dest: Path) -> Path:
    """Baixa o contorno oficial do Brasil da API de malhas do IBGE."""
    import requests
    r = requests.get(IBGE_BRASIL_URL, timeout=120)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    load_boundary(dest)  # valida
    return dest


def clip(df: pd.DataFrame, geom) -> pd.DataFrame:
    if geom is None or df.empty:
        return df
    inside = shapely.contains_xy(geom, df["lon"].to_numpy(), df["lat"].to_numpy())
    return df[inside]


def cell_index(lat: pd.Series, lon: pd.Series, res: float) -> tuple[np.ndarray, np.ndarray]:
    """Índices inteiros (cy, cx) da célula de grade de lado `res` graus."""
    return (np.floor(lat.to_numpy() / res).astype(np.int32),
            np.floor(lon.to_numpy() / res).astype(np.int32))


def cell_center(cy, cx, res: float) -> tuple[np.ndarray, np.ndarray]:
    return (np.asarray(cy) + 0.5) * res, (np.asarray(cx) + 0.5) * res
