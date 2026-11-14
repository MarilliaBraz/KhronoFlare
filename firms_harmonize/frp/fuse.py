"""Etapas 7 e 8 do fluxograma: fusão do FRP e saída diária no pixel MODIS.

Cada foco do Aqua (2002-08 em diante) recebe um FRP em "escala S-NPP VIIRS":
  * `viirs`: o pixel tem par válido (passo 3, não anômalo) → soma do FRP VIIRS dentro da pegada;
  * `modis_cal`: sem par, ou par anômalo pelo IQR (tipicamente fogo visto só em parte pelo VIIRS)
    → FRP MODIS calibrado pelo modelo final (passo 5, versão B).
Focos vistos só pelo VIIRS ficam de fora para a série ser comparável antes e depois de 2012.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import Calibration

KEY = ["date", "minute", "lat", "lon"]
FUSED_COLUMNS = ["date", "minute", "daynight", "lat", "lon", "scan", "track", "vza",
                 "frp_modis", "frp_harm", "fonte"]


def fuse(aqua: pd.DataFrame, pairs: pd.DataFrame, cal: Calibration) -> pd.DataFrame:
    """Uma linha por foco do Aqua, na ordem de entrada, com `frp_harm` e `fonte`."""
    valid = pairs.loc[~pairs["outlier"].astype(bool), [*KEY, "frp_viirs"]]
    if valid.duplicated(KEY).any():
        raise ValueError("par duplicado: o mesmo pixel MODIS aparece em mais de um par")
    merged = aqua.reset_index(drop=True).merge(valid, on=KEY, how="left", validate="many_to_one")
    has_pair = merged["frp_viirs"].notna().to_numpy()
    calibrated = cal.predict(merged["frp"], merged["vza"])
    return pd.DataFrame({
        **{c: merged[c].to_numpy() for c in ["date", "minute", "daynight", "lat", "lon", "scan", "track", "vza"]},
        "frp_modis": merged["frp"].to_numpy(float),
        "frp_harm": np.where(has_pair, merged["frp_viirs"].to_numpy(float), calibrated),
        "fonte": np.where(has_pair, "viirs", "modis_cal"),
    })[FUSED_COLUMNS]


def annual_totals(fused: pd.DataFrame) -> pd.DataFrame:
    """Resumo por ano: focos, ΣFRP original e harmonizado (MW), mediana e fração vinda do VIIRS."""
    g = fused.assign(viirs=fused["fonte"].eq("viirs")).groupby(fused["date"].dt.year)
    return pd.DataFrame({
        "focos": g.size(),
        "frp_modis_total": g["frp_modis"].sum(),
        "frp_harm_total": g["frp_harm"].sum(),
        "frp_harm_mediana": g["frp_harm"].median(),
        "frac_viirs": g["viirs"].mean(),
    }).rename_axis("ano").reset_index()
