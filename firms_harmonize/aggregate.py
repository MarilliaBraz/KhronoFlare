"""Filtros idênticos para os dois sensores e contagem por célula × mês × plataforma."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from . import geo
from .reader import iter_csv

KEYS = ["platform", "processing", "ym", "cy", "cx"]


def apply_filters(df: pd.DataFrame, min_conf: str = "nominal",
                  vegetation_only: bool = True) -> pd.DataFrame:
    """Mantém confiança >= min_conf e, quando o produto informa, só type 0 (vegetação).

    O guia MODIS (§8.4.2) recomenda descartar a classe 'baixa' para reduzir alarmes falsos;
    aplicamos a mesma regra aos dois sensores. Dados NRT não trazem `type`, então nesses
    casos nada é removido por tipo (limitação documentada).
    """
    order = {"low": 0, "nominal": 1, "high": 2}
    keep = df["conf"].map(order).fillna(-1) >= order[min_conf]
    if vegetation_only:
        keep &= df["type"].isna() | (df["type"] == 0)
    return df[keep]


def count_chunk(df: pd.DataFrame, res: float) -> pd.DataFrame:
    cy, cx = geo.cell_index(df["lat"], df["lon"], res)
    tmp = pd.DataFrame({
        "platform": df["platform"].to_numpy(),
        "processing": df["processing"].to_numpy(),
        "ym": df["date"].dt.strftime("%Y-%m").to_numpy(),
        "cy": cy, "cx": cx,
    })
    return tmp.groupby(KEYS, observed=True).size().rename("n").reset_index()


def aggregate_frames(frames: Iterable[pd.DataFrame], res: float = 0.25, boundary=None,
                     **filter_kw) -> pd.DataFrame:
    parts = []
    for df in frames:
        df = geo.clip(apply_filters(df, **filter_kw), boundary)
        if len(df):
            parts.append(count_chunk(df, res))
    if not parts:
        return pd.DataFrame(columns=[*KEYS, "n"])
    return pd.concat(parts).groupby(KEYS, observed=True)["n"].sum().reset_index()


def aggregate_files(paths: Iterable[Path], res: float = 0.25, boundary=None, **filter_kw):
    def frames():
        for p in paths:
            print(f"  lendo {p.name} ...", flush=True)
            yield from iter_csv(p)
    return aggregate_frames(frames(), res=res, boundary=boundary, **filter_kw)


def resolve_processing(counts: pd.DataFrame) -> pd.DataFrame:
    """Para cada plataforma e mês, usa SP quando existir; senão, NRT.

    O SP termina num fim de mês e o NRT começa no dia seguinte, então a precedência mensal
    não mistura os dois dentro do mesmo mês.
    """
    if counts.empty:
        return counts.drop(columns="processing", errors="ignore")
    sp_months = set(map(tuple, counts.loc[counts.processing == "SP", ["platform", "ym"]]
                        .drop_duplicates().to_numpy()))
    is_nrt_dup = counts.processing.eq("NRT") & pd.Series(
        [(p, m) in sp_months for p, m in zip(counts.platform, counts.ym)], index=counts.index)
    out = counts[~is_nrt_dup]
    return out.groupby(["platform", "ym", "cy", "cx"])["n"].sum().reset_index()
