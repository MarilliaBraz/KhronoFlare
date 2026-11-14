import numpy as np
import pandas as pd

from firms_harmonize.frp.clean import drop_nonpositive_frp, duplicate_mask, minute_of_day
from firms_harmonize.frp.prepare import prepare_platform

KM_LON_EQ = 111.32


def _fires(rows):
    """rows: (platform, date, hhmm, lat, lon, scan, track, frp)"""
    df = pd.DataFrame(rows, columns=["platform", "date", "hhmm", "lat", "lon", "scan", "track", "frp"])
    df["date"] = pd.to_datetime(df["date"])
    return df

# ---------- etapa 1: FRP ≤ 0 ----------

def test_drop_nonpositive_frp_removes_zero_negative_and_missing():
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 1, 1, f) for f in (5.0, 0.0, -1.0, np.nan, 0.1)])
    assert list(drop_nonpositive_frp(df).frp) == [5.0, 0.1]


def test_minute_of_day():
    assert list(minute_of_day(pd.Series(["0000", "0130", "1345", "2359"]))) == [0, 90, 825, 1439]

# ---------- etapa 2: duplicatas (Δt ≤ 1 min e sobreposição > 30 %) ----------

def test_duplicate_keeps_the_pixel_closest_to_nadir():
    df = _fires([("Aqua", "2015-08-01", "1330", -10, -50, 2.0, 1.2, 30.0),
                 ("Aqua", "2015-08-01", "1331", -10, -50, 1.0, 1.0, 20.0)])
    assert list(duplicate_mask(df)) == [True, False]


def test_small_overlap_is_not_a_duplicate():
    shift = 0.8 / KM_LON_EQ                        # 1×1 km deslocados 0,8 km → 20 % de sobreposição
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0),
                 ("Aqua", "2015-08-01", "1330", 0, shift, 1.0, 1.0, 10.0)])
    assert not duplicate_mask(df).any()


def test_overlap_above_30_percent_is_a_duplicate_and_ties_keep_the_first_row():
    shift = 0.5 / KM_LON_EQ                        # 50 % de sobreposição, mesmo scan
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0),
                 ("Aqua", "2015-08-01", "1330", 0, shift, 1.0, 1.0, 12.0)])
    assert list(duplicate_mask(df)) == [False, True]


def test_two_minutes_apart_is_not_a_duplicate():
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0),
                 ("Aqua", "2015-08-01", "1332", 0, 0, 1.0, 1.0, 10.0)])
    assert not duplicate_mask(df).any()


def test_different_platform_or_date_is_not_a_duplicate():
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0),
                 ("SNPP", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0),
                 ("Aqua", "2015-08-02", "1330", 0, 0, 1.0, 1.0, 10.0)])
    assert not duplicate_mask(df).any()


def test_chain_of_three_identical_keeps_exactly_one():
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0)] * 3)
    assert list(duplicate_mask(df)) == [False, True, True]


def test_mask_follows_row_order_with_non_default_index():
    df = _fires([("Aqua", "2015-08-01", "1330", 0, 0, 3.0, 1.5, 10.0),
                 ("Aqua", "2015-08-02", "1330", 5, 5, 1.0, 1.0, 10.0),
                 ("Aqua", "2015-08-01", "1330", 0, 0, 1.0, 1.0, 10.0)]).set_axis([10, 7, 3])
    assert list(duplicate_mask(df)) == [True, False, False]

# ---------- preparo a partir dos CSVs ----------

def _csv(path, rows, satellite):
    cols = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
            "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type"]
    df = pd.DataFrame([(lat, lon, 320, sc, tr, d, t, satellite, "MODIS", 50, ver, 300, frp, "D", typ)
                       for lat, lon, sc, tr, d, t, frp, typ, ver in rows], columns=cols)
    df.to_csv(path, index=False)
    return path


def test_prepare_platform_applies_window_type_frp_and_duplicate_filters(tmp_path):
    arch = _csv(tmp_path / "fire_archive_M-C61_1.csv", [
        (-10, -50, 1.0, 1.0, "2012-01-31", 1330, 9.0, 0, "6.1"),    # antes da janela
        (-10, -50, 1.0, 1.0, "2012-02-01", 1330, 9.0, 0, "6.1"),    # fica
        (-10, -50, 2.0, 1.2, "2012-02-01", 1331, 8.0, 0, "6.1"),    # duplicata do anterior
        (-11, -51, 1.0, 1.0, "2012-02-02", 1330, 0.0, 0, "6.1"),    # FRP = 0
        (-12, -52, 1.0, 1.0, "2012-02-03", 1330, 9.0, 2, "6.1"),    # fonte estática
        (-13, -53, 1.0, 1.0, "2012-02-04", 1330, 9.0, 0, "6.1"),    # fica
    ], "Aqua")
    nrt = _csv(tmp_path / "fire_nrt_M-C61_1.csv", [
        (-13, -53, 1.0, 1.0, "2012-02-04", 1330, 9.0, 0, "6.1NRT"), # já coberto pelo arquivo SP
        (-14, -54, 1.0, 1.0, "2012-02-05", 1330, 9.0, 0, "6.1NRT"), # fica (depois do fim do SP)
    ], "Aqua")
    df, rep = prepare_platform([arch, nrt], "Aqua", start="2012-02", end=None)
    assert list(df.date.dt.strftime("%d")) == ["01", "04", "05"]
    assert {"minute", "vza"} <= set(df.columns)
    assert rep["lidos"] == 8
    assert rep["fora_da_janela"] == 1 and rep["tipo_nao_vegetacao"] == 1
    assert rep["frp_nao_positivo"] == 1 and rep["nrt_sobreposto_ao_sp"] == 1
    assert rep["duplicatas"] == 1 and rep["final"] == 3


def test_prepare_platform_ignores_other_platforms_and_respects_end(tmp_path):
    arch = _csv(tmp_path / "fire_archive_M-C61_1.csv", [
        (-10, -50, 1.0, 1.0, "2012-02-01", 1030, 9.0, 0, "6.1"),
        (-10, -50, 1.0, 1.0, "2012-03-01", 1330, 9.0, 0, "6.1"),
    ], "Terra")
    df, rep = prepare_platform([arch], "Aqua", start="2012-02", end="2012-02")
    assert df.empty and rep["final"] == 0
