import numpy as np
import pandas as pd
import pytest

from firms_harmonize.risk.forecast import drift_factors, partial_month_scale, prediction_features
from firms_harmonize.risk.panel import FEATURES

P = lambda s: pd.Period(s, "M")


def _monthly(start, end, value):
    idx = pd.period_range(start, end, freq="M")
    return pd.Series(value, index=idx, dtype=float)


def test_drift_factor_is_one_before_start_and_corrects_after():
    snpp = _monthly("2012-01", "2026-11", 1000.0)
    aqua = _monthly("2012-01", "2026-11", 150.0)
    aqua[aqua.index >= P("2025-01")] = 180.0                 # Aqua vê 20 % a mais depois de 2025
    f = drift_factors(aqua, snpp, ref=("2012-01", "2021-12"), start="2022-01", window=12)
    assert f[P("2021-06")] == 1.0
    assert f[P("2023-06")] == pytest.approx(1.0)              # sem deriva ainda
    assert f[P("2025-12")] == pytest.approx(150 / 180)        # 12 meses todos com deriva
    assert f[P("2025-06")] == pytest.approx(150 / ((150 * 6 + 180 * 6) / 12))   # janela mista


def test_partial_month_scale():
    assert partial_month_scale(pd.Timestamp("2026-11-13")) == pytest.approx(30 / 13)
    assert partial_month_scale(pd.Timestamp("2026-10-31")) == 1.0


def _fused(rows):
    return pd.DataFrame(rows, columns=["date", "lat", "lon", "frp_harm"]).assign(date=lambda d: pd.to_datetime(d["date"]))


def _train_panel():
    # célula (-20,-100): dezembro com fogo em 2 de 4 anos (n 4, 0, 2, 0); célula (-30,-90) sem dezembro com fogo
    rows = [(-20, -100, 12, y, n) for y, n in zip(range(2018, 2022), [4, 0, 2, 0])]
    rows += [(-30, -90, 12, y, 0) for y in range(2018, 2022)]
    return pd.DataFrame(rows, columns=["cy", "cx", "mes_alvo", "ano_alvo", "alvo_n"])


def test_prediction_features_history_climatology_and_corrections():
    fused = _fused([
        ("2026-11-02", -9.9, -49.9, 10.0), ("2026-11-05", -9.8, -49.8, 20.0),   # mês t (parcial)
        ("2026-10-10", -9.9, -49.9, 5.0),                                        # t−1
        ("2025-12-20", -9.9, -49.9, 7.0),                                        # t−11 (mesmo mês do alvo, ano anterior)
        ("2025-11-20", -9.9, -49.9, 100.0),                                      # fora dos 12 meses
    ])
    factors = pd.Series(1.0, index=pd.period_range("2025-01", "2026-11", freq="M"))
    factors[P("2026-11")] = 0.5
    rows = prediction_features(fused, res=0.5, last_month="2026-11", last_scale=2.0, factors=factors,
                               train_panel=_train_panel())
    assert set(FEATURES) <= set(rows.columns)
    r = rows.set_index(["cy", "cx"]).loc[(-20, -100)]
    assert r["n_lag0"] == pytest.approx(2 * 0.5 * 2.0)        # 2 focos × fator de deriva × escala do mês parcial
    assert r["frp_lag0"] == pytest.approx(30 * 0.5 * 2.0)
    assert r["n_lag1"] == 1 and r["frp_lag1"] == 5.0 and r["n_lag2"] == 0
    assert r["n_mesmo_mes_ano_ant"] == 1
    assert r["n_12m"] == pytest.approx(2.0 + 1 + 1)
    assert r["p_fogo"] == pytest.approx(0.5) and r["n_med"] == pytest.approx(1.5)
    assert r["mes_alvo"] == 12 and r["mes_sin"] == pytest.approx(np.sin(2 * np.pi))
    quiet = rows.set_index(["cy", "cx"]).loc[(-30, -90)]       # célula do treino sem fogo recente entra com zeros
    assert quiet["n_12m"] == 0 and quiet["p_fogo"] == 0


def test_prediction_features_only_cells_the_model_knows():
    fused = _fused([("2026-11-02", 0.1, 0.1, 1.0)])                # célula (0, 0) fora do treino
    rows = prediction_features(fused, 0.5, "2026-11", 1.0, pd.Series(dtype=float), _train_panel())
    assert sorted(map(tuple, rows[["cy", "cx"]].to_numpy())) == [(-30, -90), (-20, -100)]
