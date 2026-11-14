from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from firms_harmonize import aggregate as agg
from firms_harmonize import firecal, geo, harmonize
from firms_harmonize.reader import iter_csv, modis_conf_class, normalize

FIX = Path(__file__).parent / "fixtures"


# ---------- leitura ----------

def test_modis_conf_thresholds_follow_user_guide_table_11():
    s = pd.Series([0, 29, 30, 79, 80, 100])
    assert list(modis_conf_class(s)) == ["low", "low", "nominal", "nominal", "high", "high"]


def test_reads_real_api_samples():
    v = next(iter_csv(FIX / "viirs_noaa20_nrt_sample.csv"))
    m = next(iter_csv(FIX / "modis_nrt_sample.csv"))
    assert set(v.platform) == {"NOAA20"} and set(v.sensor) == {"VIIRS"}
    assert set(m.platform) <= {"Terra", "Aqua"} and set(m.sensor) == {"MODIS"}
    assert set(v.processing) == {"NRT"} and set(m.processing) == {"NRT"}
    assert v.conf.isin(["low", "nominal", "high"]).all()
    assert v.hhmm.str.len().eq(4).all()        # 306 -> "0306"
    assert v.type.isna().all()                  # NRT não traz type


def test_archive_style_columns_with_type_and_short_satellite_codes():
    raw = pd.DataFrame({
        "latitude": [-10.0, -10.0], "longitude": [-50.0, -50.0], "brightness": [320, 330],
        "scan": [1, 1], "track": [1, 1], "acq_date": ["2010-08-01", "2010-08-02"],
        "acq_time": [1330, 1340], "satellite": ["A", "T"], "instrument": ["MODIS"] * 2,
        "confidence": [85, 40], "version": ["6.1", "6.1"], "bright_t31": [300, 300],
        "frp": [10.0, 5.0], "daynight": ["D", "D"], "type": [0, 2]})
    n = normalize(raw)
    assert list(n.platform) == ["Aqua", "Terra"]
    assert list(n.processing) == ["SP", "SP"]
    assert list(n.type) == [0, 2]


def test_unknown_satellite_fails_loudly():
    raw = pd.read_csv(FIX / "viirs_noaa20_nrt_sample.csv").head(2).assign(satellite="XYZ")
    with pytest.raises(ValueError, match="desconhecido"):
        normalize(raw)


# ---------- filtros e agregação ----------

def _pts(n, platform, ym, lat=-10.1, lon=-50.1, conf="nominal", typ=pd.NA, proc="SP"):
    return pd.DataFrame({
        "lat": [lat] * n, "lon": [lon] * n, "date": pd.to_datetime([f"{ym}-15"] * n),
        "hhmm": ["1330"] * n, "sensor": ["VIIRS" if platform not in ("Terra", "Aqua") else "MODIS"] * n,
        "platform": [platform] * n, "conf": [conf] * n, "frp": [1.0] * n, "daynight": ["D"] * n,
        "type": pd.array([typ] * n, dtype="Int64"), "processing": [proc] * n})


def test_filters_drop_low_confidence_and_static_sources():
    df = pd.concat([_pts(3, "Aqua", "2015-08"), _pts(2, "Aqua", "2015-08", conf="low"),
                    _pts(4, "Aqua", "2015-08", typ=2), _pts(1, "Aqua", "2015-08", typ=0)])
    assert len(agg.apply_filters(df)) == 4


def test_clip_removes_points_outside_polygon():
    df = pd.concat([_pts(3, "Aqua", "2015-08"), _pts(2, "Aqua", "2015-08", lat=-33.8, lon=-70.8)])
    poly = box(-74, -30, -34, 6)
    shapely_geom = poly
    import shapely
    shapely.prepare(shapely_geom)
    assert len(geo.clip(df, shapely_geom)) == 3


def test_sp_takes_precedence_over_nrt_in_same_month():
    df = pd.concat([_pts(5, "NOAA20", "2026-07", proc="SP"), _pts(7, "NOAA20", "2026-07", proc="NRT"),
                    _pts(9, "NOAA20", "2026-08", proc="NRT")])
    c = agg.resolve_processing(agg.aggregate_frames([df]))
    got = c.groupby("ym")["n"].sum().to_dict()
    assert got == {"2026-07": 5, "2026-08": 9}


# ---------- harmonização ----------

def _synthetic_counts(k_true_by_month, years=range(2003, 2025), cells=((-40, -200), (-41, -201))):
    """Contagens em que SNPP = k(mês) × Aqua, Aqua = 1,5 × Terra e NOAA20 = 0,9 × SNPP."""
    rng = np.random.default_rng(0)
    rows = []
    for y in years:
        for m in range(1, 13):
            ym = f"{y}-{m:02d}"
            for cy, cx in cells:
                aqua = int(rng.integers(50, 150))
                rows += [("Aqua", ym, cy, cx, aqua),
                         ("Terra", ym, cy, cx, round(aqua / 1.5)),
                         ("SNPP", ym, cy, cx, round(aqua * k_true_by_month[m])),
                         ("NOAA20", ym, cy, cx, round(aqua * k_true_by_month[m] * 0.9))]
    return pd.DataFrame(rows, columns=["platform", "ym", "cy", "cx", "n"])


K_TRUE = {m: 3.0 + 0.2 * m for m in range(1, 13)}  # fator varia com a estação


def test_calibration_recovers_known_seasonal_factor():
    counts = _synthetic_counts(K_TRUE)
    ft = harmonize.calibrate(counts, "Aqua", "SNPP")
    t = ft.table[ft.table.level == "1deg"].set_index("month")["k"]
    for m, k in K_TRUE.items():
        assert t.loc[m].mean() == pytest.approx(k, rel=0.01)


def test_fallback_to_coarser_level_when_counts_are_small():
    counts = _synthetic_counts(K_TRUE)
    ft = harmonize.calibrate(counts, "Aqua", "SNPP", min_count=10**9)  # nenhuma unidade passa
    assert set(ft.table.level) == {"brasil_geral"}
    k, lvl = ft.lookup(np.array([-40]), np.array([-200]), np.array([8]))
    assert lvl[0] == "brasil_geral" and 3.0 < k[0] < 5.5


def test_series_uses_snpp_observed_and_converts_others_to_snpp_units():
    counts = _synthetic_counts(K_TRUE, years=range(2001, 2027))
    series, _ = harmonize.build_series(counts)
    by_origin = series.groupby("origin").ym.agg(["min", "max"])
    assert by_origin.loc["SNPP", "min"] == "2012-02"
    assert by_origin.loc["Aqua", "max"] == "2012-01"
    assert by_origin.loc["Terra", "max"] == "2002-07"
    assert by_origin.loc["NOAA20", "min"] == "2026-11"
    # Aqua convertido deve reproduzir SNPP sintético (k conhecido)
    aq = series[(series.origin == "Aqua") & (series.ym == "2010-08")]
    raw = counts[(counts.platform == "Aqua") & (counts.ym == "2010-08")].n.to_numpy()
    assert aq.value.to_numpy() == pytest.approx(raw * K_TRUE[8], rel=0.02)
    # Terra passa por Terra→Aqua→SNPP
    te = series[(series.origin == "Terra")]
    assert te.factor_level.str.contains(">").all()


def test_validation_beats_uncorrected_baseline():
    counts = _synthetic_counts(K_TRUE)
    rep = harmonize.validate(counts)
    nat = rep["brasil_mensal"]
    assert nat["pred_hier"]["mape_pct"] < nat["pred_nat"]["mape_pct"] < nat["pred_raw"]["mape_pct"]
    assert abs(nat["pred_hier"]["vies_pct"]) < 2


# ---------- calendário ----------

def test_calendar_median_excludes_current_year_and_flags_anomaly():
    s = pd.DataFrame({
        "ym": ["2020-08", "2021-08", "2022-08", "2023-08"],
        "cy": 0, "cx": 0, "value": [100.0, 200.0, 300.0, 600.0], "origin": "SNPP"})
    c = firecal.calendar(s)
    aug23 = c[(c.year == 2023) & (c.month == 8)].iloc[0]
    assert aug23.mediana == 200 and aug23.anomalia_pct == pytest.approx(200)
    assert aug23.percentil == 100
    # meses sem foco no meio do período viram 0, não ficam vazios
    assert c[(c.year == 2021) & (c.month == 1)].value.iloc[0] == 0
