"""Lê os CSVs da FIRMS de uma plataforma e aplica as etapas 1 e 2, contando o que cada filtro remove."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .. import geo
from ..aggregate import apply_filters
from ..reader import iter_csv
from .clean import drop_nonpositive_frp, duplicate_mask, minute_of_day
from .pixel import modis_vza_from_scan

KEEP = ["lat", "lon", "date", "minute", "platform", "conf", "frp", "scan", "track",
        "daynight", "processing", "vza"]


def in_window(dates: pd.Series, start: str, end: str | None) -> pd.Series:
    ym = dates.dt.to_period("M")
    keep = ym >= pd.Period(start, "M")
    if end is not None:
        keep &= ym <= pd.Period(end, "M")
    return keep


def _filter_chunk(df, platform, start, end, boundary, rep):
    df = df[df["platform"] == platform]
    rep["lidos"] += len(df)
    steps = [
        ("fora_da_janela", lambda d: d[in_window(d["date"], start, end)]),
        # Fluxograma não filtra confiança; só tiramos fontes não vegetais (type ≠ 0) como no resto do projeto.
        ("tipo_nao_vegetacao", lambda d: apply_filters(d, min_conf="low", vegetation_only=True)),
        ("fora_do_brasil", lambda d: geo.clip(d, boundary)),
        ("frp_nao_positivo", drop_nonpositive_frp),
    ]
    for name, step in steps:
        before = len(df)
        df = step(df)
        rep[name] += before - len(df)
    return df


def _drop_nrt_overlap(df: pd.DataFrame) -> pd.DataFrame:
    """NRT só vale depois do último dia do arquivo científico (SP)."""
    sp = df["processing"] == "SP"
    if not sp.any():
        return df
    return df[sp | (df["date"] > df.loc[sp, "date"].max())]


def prepare_platform(paths: Iterable[Path], platform: str, start: str, end: str | None,
                     boundary=None) -> tuple[pd.DataFrame, dict]:
    rep = dict.fromkeys(["lidos", "fora_da_janela", "tipo_nao_vegetacao", "fora_do_brasil",
                         "frp_nao_positivo", "nrt_sobreposto_ao_sp", "duplicatas", "final"], 0)
    parts = [_filter_chunk(c, platform, start, end, boundary, rep) for p in paths for c in iter_csv(p)]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=KEEP), rep

    df = pd.concat(parts, ignore_index=True)
    before = len(df)
    df = _drop_nrt_overlap(df)
    rep["nrt_sobreposto_ao_sp"] = before - len(df)

    df = df.assign(minute=minute_of_day(df["hhmm"]).astype(np.int16))
    df = df.sort_values(["date", "minute"], kind="stable").reset_index(drop=True)
    dup = duplicate_mask(df)
    rep["duplicatas"] = int(dup.sum())
    df = df[~dup]

    is_modis = platform in ("Terra", "Aqua")
    df = df.assign(vza=modis_vza_from_scan(df["scan"]) if is_modis else np.nan,
                   frp=df["frp"].astype("float32"))
    rep["final"] = len(df)
    return df[KEEP].reset_index(drop=True), rep
