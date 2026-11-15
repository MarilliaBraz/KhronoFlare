import pytest
import numpy as np
import pandas as pd

from firms_harmonize.risk.panel import FEATURES, add_history, add_target, aggregate_cells, build_panel, complete_panel

FEATURES_HIST = ["n_lag0", "n_lag1", "n_lag2", "frp_lag0", "frp_lag1", "frp_lag2", "n_mesmo_mes_ano_ant", "n_12m"]


def _fused(rows):
    """rows: (date, lat, lon, frp_harm)"""
    df = pd.DataFrame(rows, columns=["date", "lat", "lon", "frp_harm"])
    return df.assign(date=pd.to_datetime(df["date"]))


# ---------- agregação e painel completo ----------

def test_aggregate_sums_fires_by_cell_and_month():
    f = _fused([("2010-08-01", -10.1, -50.1, 10.0), ("2010-08-20", -10.4, -50.4, 5.0),
                ("2010-09-01", -10.1, -50.1, 1.0), ("2010-08-01", -9.9, -50.1, 2.0)])
    a = aggregate_cells(f, res=0.5, start="2010-01", end="2010-12").set_index(["cy", "cx", "ym"])
    assert a.loc[(-21, -101, pd.Period("2010-08", "M")), ["n", "frp"]].tolist() == [2, 15.0]
    assert a.loc[(-21, -101, pd.Period("2010-09", "M")), "n"] == 1
    assert a.loc[(-20, -101, pd.Period("2010-08", "M")), "n"] == 1      # −9,9° cai na célula de cima


def test_aggregate_ignores_dates_outside_the_period():
    f = _fused([("2009-12-31", -10.1, -50.1, 10.0), ("2010-01-01", -10.1, -50.1, 3.0)])
    a = aggregate_cells(f, res=0.5, start="2010-01", end="2010-12")
    assert a["n"].sum() == 1 and a["frp"].sum() == 3.0


def test_complete_panel_fills_months_without_fire_with_zero():
    f = _fused([("2010-03-05", -10.1, -50.1, 10.0)])
    p = complete_panel(aggregate_cells(f, res=0.5, start="2010-01", end="2010-12"), "2010-01", "2010-12")
    assert len(p) == 12 and p["n"].sum() == 1 and p.loc[p["n"] == 0, "frp"].eq(0).all()
    assert list(p["ym"]) == list(pd.period_range("2010-01", "2010-12", freq="M"))

# ---------- histórico e alvo ----------

def _two_cells(months=36, seed=0):
    rng = np.random.default_rng(seed)
    ym = pd.period_range("2004-01", periods=months, freq="M")
    rows = []
    for cy, cx in [(0, 0), (1, 1)]:
        n = rng.integers(0, 5, months)
        rows.append(pd.DataFrame({"cy": cy, "cx": cx, "ym": ym, "n": n, "frp": n * 10.0}))
    return pd.concat(rows, ignore_index=True)


def test_history_uses_the_same_cell_and_past_months_only():
    p = _two_cells()
    h = add_history(p).set_index(["cy", "cx", "ym"])
    raw = p.set_index(["cy", "cx", "ym"])
    t = pd.Period("2005-06", "M")
    for cell in [(0, 0), (1, 1)]:
        row = h.loc[(*cell, t)]
        assert row["n_lag0"] == raw.loc[(*cell, t), "n"]
        assert row["n_lag1"] == raw.loc[(*cell, t - 1), "n"]
        assert row["n_lag2"] == raw.loc[(*cell, t - 2), "n"]
        assert row["n_mesmo_mes_ano_ant"] == raw.loc[(*cell, t - 11), "n"]   # alvo é t+1
        window = pd.period_range(t - 11, t, freq="M")
        assert row["n_12m"] == sum(raw.loc[(*cell, m), "n"] for m in window)
        assert row["alvo_n"] == raw.loc[(*cell, t + 1), "n"]
        assert row["mes_alvo"] == 7 and row["ano_alvo"] == 2005


def test_history_drops_rows_without_full_past_or_future():
    h = add_history(_two_cells(months=36))
    per_cell = h.groupby(["cy", "cx"]).size()
    assert (per_cell == 36 - 11 - 1).all()        # 11 meses sem histórico de 12 meses e o último sem alvo


def test_features_do_not_change_when_the_future_changes():
    p = _two_cells()
    t = pd.Period("2005-06", "M")
    fut = p.copy()
    fut.loc[fut["ym"] > t, ["n", "frp"]] = 999
    a = add_history(p).set_index(["cy", "cx", "ym"]).loc[pd.IndexSlice[:, :, t], FEATURES_HIST]
    b = add_history(fut).set_index(["cy", "cx", "ym"]).loc[pd.IndexSlice[:, :, t], FEATURES_HIST]
    pd.testing.assert_frame_equal(a, b)


def test_target_percentile_comes_from_train_years_only():
    h = add_history(_two_cells(months=48))
    train = (2004, 2005)
    a = add_target(h, train_years=train)
    changed = h.copy()
    changed.loc[changed["ano_alvo"] > 2005, "alvo_frp"] *= 100
    b = add_target(changed, train_years=train)
    np.testing.assert_allclose(a["frp_p75"], b["frp_p75"])
    np.testing.assert_allclose(a["p_fogo"], b["p_fogo"])


def test_critical_month_is_above_p75_and_has_fire():
    h = add_history(_two_cells(months=48))
    t = add_target(h, train_years=(2004, 2005))
    expected = (t["alvo_frp"] > t["frp_p75"]) & (t["alvo_frp"] > 0)
    assert t["y_critico"].tolist() == expected.astype(int).tolist()
    assert set(FEATURES) <= set(t.columns)


def test_build_panel_end_to_end():
    rows = [(f"{y}-{m:02d}-10", -10.1, -50.1, float(m)) for y in range(2003, 2008) for m in (8, 9)]
    p = build_panel(_fused(rows), res=0.5, period=("2003-01", "2007-12"), train_years=(2004, 2005))
    assert {"y_critico", *FEATURES} <= set(p.columns)
    assert p["ano_alvo"].between(2004, 2007).all()
    assert not p[FEATURES].isna().any().any()


# ---------- climatologia "deixando um ano de fora" nas linhas de treino ----------

def _history_one_cell(targets_n, years, test_years=()):
    rows = [{"cy": 0, "cx": 0, "mes_alvo": 8, "ano_alvo": y, "alvo_n": n, "alvo_frp": 10.0 * n}
            for y, n in zip([*years, *test_years], targets_n)]
    return pd.DataFrame(rows)


def test_train_rows_climatology_excludes_their_own_year():
    h = _history_one_cell([0, 2, 4, 6], years=[2004, 2005, 2006], test_years=[2017])
    t = add_target(h, train_years=(2004, 2016)).set_index("ano_alvo")
    # treino: anos 2004 (0 focos), 2005 (2), 2006 (4); fogo em 2 de 3 anos, média 2
    assert t.loc[2006, "p_fogo"] == pytest.approx(0.5)        # outros anos: 2004 sem fogo, 2005 com
    assert t.loc[2006, "n_med"] == pytest.approx(1.0)         # (0 + 2) / 2
    assert t.loc[2004, "p_fogo"] == pytest.approx(1.0) and t.loc[2004, "n_med"] == pytest.approx(3.0)
    # teste: climatologia completa do treino, sem nada do próprio teste
    assert t.loc[2017, "p_fogo"] == pytest.approx(2 / 3) and t.loc[2017, "n_med"] == pytest.approx(2.0)


def test_single_train_year_has_zero_climatology_in_its_own_row():
    h = _history_one_cell([3, 5], years=[2004], test_years=[2017])
    t = add_target(h, train_years=(2004, 2016)).set_index("ano_alvo")
    assert t.loc[2004, "p_fogo"] == 0.0 and t.loc[2004, "n_med"] == 0.0
    assert t.loc[2017, "p_fogo"] == pytest.approx(1.0) and t.loc[2017, "n_med"] == pytest.approx(3.0)


def test_critical_threshold_still_uses_all_train_years():
    h = _history_one_cell([0, 2, 4, 6], years=[2004, 2005, 2006], test_years=[2017])
    t = add_target(h, train_years=(2004, 2016))
    assert t["frp_p75"].nunique() == 1
    assert t["frp_p75"].iloc[0] == pytest.approx(np.percentile([0.0, 20.0, 40.0], 75))


# ---------- células definidas só pelo período de treino ----------

def test_cells_that_only_burn_after_training_are_left_out():
    f = _fused([("2010-08-01", -10.1, -50.1, 5.0),     # célula A: fogo no treino
                ("2018-08-01", -20.1, -40.1, 5.0)])    # célula B: só no teste
    agg = aggregate_cells(f, res=0.5, start="2003-01", end="2021-12")
    p = complete_panel(agg, "2003-01", "2021-12", cells_until="2016-12")
    assert set(map(tuple, p[["cy", "cx"]].drop_duplicates().to_numpy())) == {(-21, -101)}
    assert complete_panel(agg, "2003-01", "2021-12")[["cy", "cx"]].drop_duplicates().shape[0] == 2


def test_build_panel_uses_training_cells_only():
    rows = [("2004-08-10", -10.1, -50.1, 5.0), ("2007-08-10", -20.1, -40.1, 5.0)]
    p = build_panel(_fused(rows), res=0.5, period=("2003-01", "2007-12"), train_years=(2004, 2005))
    assert p[["cy", "cx"]].drop_duplicates().shape[0] == 1
