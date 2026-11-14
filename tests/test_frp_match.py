import numpy as np
import pandas as pd
import pytest

from firms_harmonize.frp.match import PAIR_COLUMNS, match_pairs, outlier_mask

KM_LON_EQ, KM_LAT = 111.32, 110.574


def _modis(rows):
    """rows: (date, minute, lat, lon, scan, track, frp[, daynight])"""
    rows = [r if len(r) == 8 else (*r, "D") for r in rows]
    df = pd.DataFrame(rows, columns=["date", "minute", "lat", "lon", "scan", "track", "frp", "daynight"])
    return df.assign(date=pd.to_datetime(df["date"]), platform="Aqua", vza=0.0)


def _viirs(rows):
    """rows: (date, minute, lat, lon, frp[, daynight])"""
    rows = [r if len(r) == 6 else (*r, "D") for r in rows]
    df = pd.DataFrame(rows, columns=["date", "minute", "lat", "lon", "frp", "daynight"])
    return df.assign(date=pd.to_datetime(df["date"]), platform="SNPP", scan=0.4, track=0.4)


def _east(km):
    return km / KM_LON_EQ


def _north(km):
    return km / KM_LAT


D = "2015-08-01"


def test_viirs_inside_footprint_at_same_minute_forms_a_pair():
    p = match_pairs(_modis([(D, 1000, 0, 0, 1.0, 1.0, 20.0)]), _viirs([(D, 1000, 0, _east(0.2), 7.0)]))
    assert len(p) == 1
    assert p.iloc[0][["frp_modis", "frp_viirs", "n_viirs"]].tolist() == [20.0, 7.0, 1]
    assert list(p.columns) == PAIR_COLUMNS


def test_all_viirs_inside_the_same_modis_pixel_are_summed():
    p = match_pairs(_modis([(D, 1000, 0, 0, 1.0, 1.0, 20.0)]),
                    _viirs([(D, 1000, 0, _east(0.2), 7.0), (D, 1001, _north(-0.3), 0, 5.0)]))
    assert p.iloc[0]["frp_viirs"] == pytest.approx(12.0) and p.iloc[0]["n_viirs"] == 2


def test_footprint_is_scan_east_west_by_track_north_south():
    m = _modis([(D, 1000, 0, 0, 4.0, 2.0, 20.0)])
    inside = match_pairs(m, _viirs([(D, 1000, 0, _east(1.5), 7.0)]))     # 1,5 < 4/2
    outside = match_pairs(m, _viirs([(D, 1000, _north(1.5), 0, 7.0)]))   # 1,5 > 2/2
    assert len(inside) == 1 and outside.empty


def test_viirs_outside_footprint_does_not_pair():
    p = match_pairs(_modis([(D, 1000, 0, 0, 1.0, 1.0, 20.0)]), _viirs([(D, 1000, 0, _east(0.6), 7.0)]))
    assert p.empty


@pytest.mark.parametrize("dt, expected", [(5, 1), (-5, 1), (6, 0), (-6, 0)])
def test_time_difference_limit_is_five_minutes(dt, expected):
    p = match_pairs(_modis([(D, 1000, 0, 0, 1.0, 1.0, 20.0)]), _viirs([(D, 1000 + dt, 0, 0, 7.0)]))
    assert len(p) == expected


def test_different_date_or_overpass_does_not_pair():
    m = _modis([(D, 1000, 0, 0, 1.0, 1.0, 20.0)])
    assert match_pairs(m, _viirs([("2015-08-02", 1000, 0, 0, 7.0)])).empty
    assert match_pairs(m, _viirs([(D, 1000, 0, 0, 7.0, "N")])).empty


def test_viirs_in_two_overlapping_footprints_counts_only_for_the_closest():
    m = _modis([(D, 1000, 0, 0, 2.0, 2.0, 20.0), (D, 1000, 0, _east(1.0), 2.0, 2.0, 30.0)])
    p = match_pairs(m, _viirs([(D, 1000, 0, _east(0.7), 7.0)]))   # dentro dos dois, mais perto do 2º
    assert len(p) == 1 and p.iloc[0]["frp_modis"] == 30.0
    assert p["frp_viirs"].sum() == pytest.approx(7.0)            # sem contagem dupla


def test_reports_time_difference_and_keeps_modis_geometry():
    p = match_pairs(_modis([(D, 1000, -10, -50, 1.0, 1.0, 20.0)]), _viirs([(D, 1003, -10, -50, 7.0)]))
    row = p.iloc[0]
    assert row["dt_min"] == 3 and row["lat"] == -10 and row["scan"] == 1.0 and row["vza"] == 0.0


def test_empty_inputs_return_empty_frame_with_columns():
    p = match_pairs(_modis([]), _viirs([]))
    assert p.empty and list(p.columns) == PAIR_COLUMNS

# ---------- etapa 5: remoção de pares anômalos pelo IQR ----------

def _pairs(ratios, vza):
    ratios = np.asarray(ratios, dtype=float)
    return pd.DataFrame({"frp_modis": 10.0, "frp_viirs": 10.0 * ratios, "vza": vza}).set_axis(
        range(100, 100 + len(ratios)))


def _spread(n, center=1.0):
    return center * np.exp(np.linspace(-0.3, 0.3, n))   # razões em torno do centro


def test_iqr_flags_extreme_high_and_low_ratios_only():
    p = _pairs([*_spread(20), 100.0, 0.001], vza=5.0)
    mask = outlier_mask(p)
    assert list(np.flatnonzero(mask)) == [20, 21]


def test_iqr_keeps_everything_when_there_are_no_outliers():
    assert not outlier_mask(_pairs(_spread(30), vza=25.0)).any()


def test_iqr_limits_are_computed_per_vza_bin():
    # 100 pares ≈ 1 no nadir e 30 pares ≈ 0,01 na borda: juntos, os da borda seriam anômalos
    p = _pairs([*_spread(100), *_spread(30, center=0.01)], vza=[5.0] * 100 + [65.0] * 30)
    assert not outlier_mask(p).any()
    assert outlier_mask(p, bin_width=None)[100:].all()   # sem faixas: os 30 caem fora


def test_iqr_flags_pairs_without_vza_or_with_nonpositive_frp():
    p = _pairs([*_spread(20), 1.0, 1.0], vza=[10.0] * 21 + [np.nan])
    p.iloc[20, p.columns.get_loc("frp_viirs")] = 0.0
    assert list(np.flatnonzero(outlier_mask(p))) == [20, 21]

# ---------- robustez ----------

def test_one_modis_pixel_without_scan_does_not_block_the_others():
    m = _modis([(D, 1000, 0, 0, 1.0, 1.0, 20.0), (D, 1000, 1, 1, np.nan, 1.0, 30.0)])
    p = match_pairs(m, _viirs([(D, 1000, 0, _east(0.2), 7.0), (D, 1000, 1, 1, 5.0)]))
    assert len(p) == 1 and p.iloc[0]["frp_modis"] == 20.0


def test_group_where_every_modis_pixel_lacks_scan_yields_no_pairs():
    m = _modis([(D, 1000, 0, 0, np.nan, 1.0, 20.0)])
    assert match_pairs(m, _viirs([(D, 1000, 0, 0, 7.0)])).empty


def test_iqr_limits_can_come_from_reference_rows_only():
    # 20 pares de referência ≈ 1 e 20 pares fora da referência ≈ 0,01 na mesma faixa
    p = _pairs([*_spread(20), *_spread(20, center=0.01)], vza=5.0)
    ref = np.r_[np.ones(20, bool), np.zeros(20, bool)]
    assert not outlier_mask(p).any()                         # com todos, o IQR é largo
    assert outlier_mask(p, reference=ref)[20:].all()          # só com a referência, os outros saem
    assert not outlier_mask(p, reference=ref)[:20].any()


def test_bin_without_reference_rows_uses_global_reference_limits():
    p = _pairs([*_spread(20), 0.001, 1.0], vza=[5.0] * 20 + [65.0, 65.0])
    ref = np.r_[np.ones(20, bool), False, False]
    assert list(outlier_mask(p, reference=ref)[20:]) == [True, False]


def test_empty_reference_fails_loudly():
    with pytest.raises(ValueError, match="referência"):
        outlier_mask(_pairs(_spread(10), vza=5.0), reference=np.zeros(10, bool))



def test_bin_with_too_few_reference_pairs_uses_global_limits():
    # 100 pares ≈ 1 no nadir; só 10 pares ≈ 0,01 na borda: poucos para limites próprios
    p = _pairs([*_spread(100), *_spread(10, center=0.01)], vza=[5.0] * 100 + [65.0] * 10)
    assert outlier_mask(p)[100:].all()                       # mínimo padrão (30) → limites globais
    assert not outlier_mask(p, min_per_bin=5)[100:].any()    # com mínimo 5 a faixa tem limites próprios
