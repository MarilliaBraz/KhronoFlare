"""FRP harmonizado por município IBGE → harmonized_mun.json.

Compara o mesmo recorte de dias em todos os anos (ex.: 1–13 de novembro), para que um
mês ainda incompleto tenha anomalia honesta. Fonte: frp_fused.parquet (focos do Aqua com
FRP na escala S-NPP VIIRS), única série de FRP comparável antes e depois de 2012.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

NATIONAL_KEY = "*"
ROUND = 1


def load_municipalities(malhas_dir: Path) -> tuple[list[str], np.ndarray]:
    """Lê as malhas por UF (GeoJSON com `codarea`) e devolve códigos + geometrias."""
    codes: list[str] = []
    geoms: list = []
    for path in sorted(malhas_dir.glob("*.json")):
        fc = json.loads(path.read_text(encoding="utf-8"))
        for feat in fc["features"]:
            codes.append(str(feat["properties"]["codarea"]))
            geoms.append(shapely.geometry.shape(feat["geometry"]))
    return codes, np.array(geoms, dtype=object)


def assign_municipality(lat: np.ndarray, lon: np.ndarray, codes: list[str],
                        geoms: np.ndarray) -> np.ndarray:
    """Código IBGE do município que contém cada ponto (None fora de todos)."""
    points = shapely.points(lon, lat)
    tree = shapely.STRtree(geoms)
    pt_idx, poly_idx = tree.query(points, predicate="within")
    out = np.full(len(points), None, dtype=object)
    # Ponto na divisa de dois municípios: fica com o primeiro, sem contar em dobro.
    first = pd.Series(poly_idx).groupby(pt_idx).first()
    out[first.index.to_numpy()] = np.asarray(codes, dtype=object)[first.to_numpy()]
    return out


def window_mask(dates: pd.Series, data_end: date) -> pd.Series:
    """Focos de 1 até `data_end.day` do mês de `data_end`, em qualquer ano."""
    return (dates.dt.month == data_end.month) & (dates.dt.day <= data_end.day)


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, ROUND)


def _stats(values_by_year: pd.Series, current_year: int, ref_years: list[int]) -> dict:
    """Mesmo critério do firecal.calendar: referência = todos os anos menos o corrente.

    Ano sem foco no município conta como 0 (não some da mediana).
    """
    full = values_by_year.reindex([*ref_years, current_year], fill_value=0.0)
    cur = float(full[current_year])
    ref = full.loc[ref_years]
    med = float(ref.median()) if len(ref) else None
    anom = (cur / med - 1) * 100 if med else None  # mediana 0 → sem anomalia, não +∞
    pct = float((ref < cur).mean() * 100) if len(ref) else None
    return {"frpHarm": _round(cur), "value": _round(cur), "mediana": _round(med),
            "anomalia_pct": _round(anom), "percentil": _round(pct)}


def window_stats(df: pd.DataFrame, data_end: date,
                 all_ids: list[str] | None = None) -> dict[str, dict]:
    """`df` com colunas mun, year, frp_harm (já recortado na janela) → byId.

    `all_ids`: municípios a incluir mesmo sem foco (FRP 0). Sem isso, a UI cairia no
    fallback "*" e mostraria o total do Brasil como se fosse do município.
    """
    current_year = data_end.year
    ref_years = sorted(int(y) for y in df["year"].unique() if y != current_year)
    ym = f"{current_year}-{data_end.month:02d}"
    by_id: dict[str, dict] = {}
    totals = df.dropna(subset=["mun"]).groupby(["mun", "year"])["frp_harm"].sum()
    for mun, series in totals.groupby(level=0):
        by_id[str(mun)] = {**_stats(series.droplevel(0), current_year, ref_years), "ym": ym}
    empty = pd.Series(dtype=float)
    for mun in all_ids or []:
        if mun not in by_id:
            by_id[mun] = {**_stats(empty, current_year, ref_years), "ym": ym}
    national = df.groupby("year")["frp_harm"].sum()
    by_id[NATIONAL_KEY] = {**_stats(national, current_year, ref_years), "ym": ym}
    return by_id


def build_payload(fused_path: Path, malhas_dir: Path, data_end: date, generated: str) -> dict:
    fused = pd.read_parquet(fused_path, columns=["date", "lat", "lon", "frp_harm"])
    win = fused[window_mask(fused["date"], data_end)].copy()
    codes, geoms = load_municipalities(malhas_dir)
    win["mun"] = assign_municipality(win["lat"].to_numpy(), win["lon"].to_numpy(), codes, geoms)
    win["year"] = win["date"].dt.year
    by_id = window_stats(win, data_end, all_ids=codes)
    years = sorted(int(y) for y in win["year"].unique())
    print(f"  janela {data_end.month:02d}/01–{data_end.day:02d}: {len(win)} focos, "
          f"{win['mun'].notna().mean():.1%} dentro de município, "
          f"{win['mun'].nunique()} de {len(codes)} municípios com foco")
    return {
        "kind": "harmonized-mun",
        "generated": generated,
        "window": {"month": data_end.month, "day_start": 1, "day_end": data_end.day,
                   "years": [years[0], years[-1]] if years else None},
        "source": "frp_fused (Aqua MODIS, FRP na escala S-NPP VIIRS), soma em MW",
        "byId": by_id,
    }
