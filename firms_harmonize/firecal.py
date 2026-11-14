"""Calendário de atividade de queimadas (ano × mês) a partir da série harmonizada."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import geo


def select_region(series: pd.DataFrame, res: float, bbox=None, geom=None) -> pd.DataFrame:
    """Filtra células cujo centro está no retângulo (oeste, sul, leste, norte) e/ou no polígono."""
    lat, lon = geo.cell_center(series.cy, series.cx, res)
    keep = np.ones(len(series), bool)
    if bbox is not None:
        w, s, e, n = bbox
        keep &= (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    if geom is not None:
        import shapely
        keep &= shapely.contains_xy(geom, lon, lat)
    return series[keep]


def monthly_totals(series: pd.DataFrame) -> pd.DataFrame:
    t = series.groupby("ym").agg(value=("value", "sum"),
                                 origin=("origin", lambda s: "/".join(sorted(set(s)))))
    full = pd.period_range(series.ym.min(), series.ym.max(), freq="M").astype(str)
    t = t.reindex(full)
    t["value"] = t["value"].fillna(0.0)  # mês dentro do período sem nenhum foco = 0
    t.index.name = "ym"
    return t.reset_index()


def calendar(series: pd.DataFrame, current_year: int | None = None) -> pd.DataFrame:
    """Tabela longa: ano, mês, valor, mediana histórica do mês, anomalia e percentil.

    A mediana e o percentil usam todos os anos exceto `current_year`: o ano corrente é
    parcial e fica fora da referência, como faz o INPE em "Situação Atual".
    """
    t = monthly_totals(series)
    t["year"] = t.ym.str[:4].astype(int)
    t["month"] = t.ym.str[5:7].astype(int)
    current_year = current_year or int(t.year.max())
    ref = t[t.year != current_year]
    stats = ref.groupby("month")["value"].agg(
        mediana="median", p10=lambda v: v.quantile(.1), p90=lambda v: v.quantile(.9))
    t = t.join(stats, on="month")
    t["anomalia_pct"] = np.where(t.mediana > 0, (t.value / t.mediana - 1) * 100, np.nan)
    t["percentil"] = [
        float((ref.loc[ref.month == m, "value"] < v).mean() * 100) if (ref.month == m).any() else np.nan
        for m, v in zip(t.month, t.value)]
    return t[["year", "month", "ym", "value", "origin", "mediana", "p10", "p90",
              "anomalia_pct", "percentil"]]


def grid(cal: pd.DataFrame) -> pd.DataFrame:
    """Matriz ano × mês (para o heatmap 'calendário em chamas')."""
    return cal.pivot(index="year", columns="month", values="value").round(0)
