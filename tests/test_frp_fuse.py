import numpy as np
import pandas as pd
import pytest

from firms_harmonize.frp.calibrate import Calibration
from firms_harmonize.frp.fuse import FUSED_COLUMNS, annual_totals, fuse

CAL = Calibration(a=0.0, b=1.0, c=0.0, smearing=0.5, n=1)   # FRP calibrado = metade do MODIS


def _aqua(rows):
    """rows: (date, minute, lat, lon, frp, vza)"""
    df = pd.DataFrame(rows, columns=["date", "minute", "lat", "lon", "frp", "vza"])
    return df.assign(date=pd.to_datetime(df["date"]), daynight="D", scan=1.0, track=1.0, platform="Aqua")


def _pairs(rows):
    """rows: (date, minute, lat, lon, frp_viirs, outlier)"""
    df = pd.DataFrame(rows, columns=["date", "minute", "lat", "lon", "frp_viirs", "outlier"])
    return df.assign(date=pd.to_datetime(df["date"]))


AQUA = _aqua([("2015-08-01", 1000, -10.0, -50.0, 40.0, 5.0),
              ("2015-08-01", 1000, -10.1, -50.1, 30.0, 5.0),
              ("2015-08-02", 1000, -11.0, -51.0, 20.0, 5.0),
              ("2005-08-02", 1000, -12.0, -52.0, 10.0, 5.0)])


def test_matched_pixel_uses_the_viirs_sum():
    f = fuse(AQUA, _pairs([("2015-08-01", 1000, -10.0, -50.0, 33.0, False)]), CAL)
    assert f.loc[0, "frp_harm"] == 33.0 and f.loc[0, "fonte"] == "viirs"


def test_unmatched_pixel_uses_the_calibrated_modis():
    f = fuse(AQUA, _pairs([("2015-08-01", 1000, -10.0, -50.0, 33.0, False)]), CAL)
    assert f.loc[1:, "frp_harm"].tolist() == pytest.approx([15.0, 10.0, 5.0])
    assert set(f.loc[1:, "fonte"]) == {"modis_cal"}


def test_outlier_pair_falls_back_to_calibrated_modis():
    f = fuse(AQUA, _pairs([("2015-08-01", 1000, -10.0, -50.0, 1.0, True)]), CAL)
    assert f.loc[0, "frp_harm"] == pytest.approx(20.0) and f.loc[0, "fonte"] == "modis_cal"


def test_keeps_every_aqua_pixel_in_order_with_fixed_columns():
    f = fuse(AQUA, _pairs([]), CAL)
    assert len(f) == len(AQUA) and list(f.columns) == FUSED_COLUMNS
    assert f["frp_modis"].tolist() == AQUA["frp"].tolist()


def test_duplicate_pair_key_fails_loudly():
    dup = _pairs([("2015-08-01", 1000, -10.0, -50.0, 33.0, False)] * 2)
    with pytest.raises(ValueError, match="duplicad"):
        fuse(AQUA, dup, CAL)


def test_annual_totals():
    f = fuse(AQUA, _pairs([("2015-08-01", 1000, -10.0, -50.0, 33.0, False)]), CAL)
    t = annual_totals(f).set_index("ano")
    assert t.loc[2015, "focos"] == 3 and t.loc[2005, "focos"] == 1
    assert t.loc[2015, "frp_modis_total"] == pytest.approx(90.0)
    assert t.loc[2015, "frp_harm_total"] == pytest.approx(33.0 + 15.0 + 10.0)
    assert t.loc[2015, "frac_viirs"] == pytest.approx(1 / 3)
    assert t.loc[2005, "frp_harm_mediana"] == pytest.approx(5.0)
    assert np.isclose(t.loc[2005, "frac_viirs"], 0.0)
