"""Exportador do Khronoflare: mês parcial no calendário e FRP harmonizado por município."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import shapely

TOOLS = Path(__file__).resolve().parent.parent / "firms-angular" / "tools"
sys.path.insert(0, str(TOOLS))  # export_for_web importa mun_join do mesmo diretório


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


efw = _load("export_for_web")
mj = _load("mun_join")
NOV_13 = date(2026, 11, 13)


def _row(year, month, anom=10.0):
    return {"year": year, "month": month, "ym": f"{year}-{month:02d}", "value": 1.0,
            "anomalia_pct": anom, "percentil": 50.0}


# ---------- mês parcial ----------

def test_latest_month_is_partial_when_data_ends_before_month_end():
    rows = [_row(2026, 10), _row(2026, 11)]
    out = efw.mark_partial_month(rows, NOV_13)
    assert out[1]["partial"] is True
    assert out[1]["anomalia_pct"] is None and out[1]["percentil"] is None
    assert "partial" not in out[0] and out[0]["anomalia_pct"] == 10.0


def test_complete_month_is_left_untouched():
    rows = [_row(2026, 10)]
    assert efw.mark_partial_month(rows, date(2026, 10, 31)) == rows


def test_mark_partial_does_not_mutate_input():
    rows = [_row(2026, 11)]
    efw.mark_partial_month(rows, date(2026, 11, 2))
    assert "partial" not in rows[0] and rows[0]["anomalia_pct"] == 10.0


# ---------- município ----------

def test_window_mask_keeps_same_days_of_the_month_in_every_year():
    d = pd.Series(pd.to_datetime(
        ["2010-11-01", "2010-11-13", "2010-11-14", "2010-10-05", "2026-11-13"]))
    assert mj.window_mask(d, NOV_13).tolist() == [True, True, False, False, True]


def test_assign_municipality_uses_polygon_and_returns_none_outside():
    codes = ["111", "222"]
    geoms = np.array([shapely.box(0, 0, 1, 1), shapely.box(2, 0, 3, 1)], dtype=object)
    out = mj.assign_municipality(np.array([0.5, 0.5, 0.5]), np.array([0.5, 2.5, 5.0]), codes, geoms)
    assert out.tolist() == ["111", "222", None]


def test_window_stats_counts_missing_years_as_zero_and_computes_anomaly():
    # Município A: 2024=10, 2025 sem foco (0), 2026=30 → mediana(10, 0)=5, anomalia +500 %
    df = pd.DataFrame({"mun": ["A", "A", "B"], "year": [2024, 2026, 2025],
                       "frp_harm": [10.0, 30.0, 4.0]})
    a = mj.window_stats(df, NOV_13)["A"]
    assert a["frpHarm"] == 30.0 and a["mediana"] == 5.0
    assert a["anomalia_pct"] == pytest.approx(500.0)
    assert a["percentil"] == 100.0 and a["ym"] == "2026-11"


def test_window_stats_leaves_anomaly_empty_when_median_is_zero():
    df = pd.DataFrame({"mun": ["B", "C"], "year": [2025, 2026], "frp_harm": [4.0, 7.0]})
    by_id = mj.window_stats(df, NOV_13)
    assert by_id["C"]["mediana"] == 0.0 and by_id["C"]["anomalia_pct"] is None
    assert by_id["B"]["frpHarm"] == 0.0  # sem foco em 2026 → 0, não ausente


def test_municipality_without_fire_gets_zero_entry_instead_of_national_fallback():
    df = pd.DataFrame({"mun": ["A"], "year": [2026], "frp_harm": [5.0]})
    by_id = mj.window_stats(df, NOV_13, all_ids=["A", "Z"])
    assert by_id["Z"]["frpHarm"] == 0.0 and by_id["Z"]["anomalia_pct"] is None
    assert by_id["A"]["frpHarm"] == 5.0


def test_window_stats_national_entry_includes_points_outside_municipalities():
    df = pd.DataFrame({"mun": ["A", None], "year": [2026, 2026], "frp_harm": [1.0, 2.0]})
    assert mj.window_stats(df, NOV_13)["*"]["frpHarm"] == 3.0
