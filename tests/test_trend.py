import numpy as np
import pytest

from firms_harmonize.trend import mann_kendall, pettitt, resumo, sen_slope

ANOS = np.arange(2003, 2023)


# ---------- Sen ----------

def test_sen_recovers_linear_slope():
    r = sen_slope(ANOS, 2.0 * ANOS + 1)
    assert r["inclinacao"] == pytest.approx(2.0)
    assert r["ic95"][0] <= 2.0 <= r["ic95"][1]


def test_sen_is_resistant_to_one_extreme_year():
    y = 2.0 * ANOS + 1.0
    y[5] = 1e6
    assert sen_slope(ANOS, y)["inclinacao"] == pytest.approx(2.0)


def test_sen_rejects_mismatched_or_repeated_years():
    with pytest.raises(ValueError, match="anos"):
        sen_slope(ANOS[:-1], ANOS)
    with pytest.raises(ValueError, match="anos"):
        sen_slope([2003, 2003, 2004], [1.0, 2.0, 3.0])

# ---------- Mann-Kendall ----------

def test_mann_kendall_detects_monotonic_increase():
    r = mann_kendall(np.arange(20.0))
    assert r["tau"] == pytest.approx(1.0) and r["p"] < 0.001


def test_mann_kendall_constant_series_has_no_trend():
    assert mann_kendall(np.ones(10)) == {"tau": 0.0, "p": 1.0}


def test_mann_kendall_noise_is_not_significant():
    r = mann_kendall(np.random.default_rng(3).normal(size=20))
    assert r["p"] > 0.05

# ---------- Pettitt ----------

def test_pettitt_finds_step_change():
    x = np.r_[np.full(10, 5.0), np.full(10, 1.0)] + np.random.default_rng(0).normal(0, 0.1, 20)
    r = pettitt(x)
    assert r["indice_quebra"] == 9 and r["p"] < 0.01


def test_pettitt_constant_series_has_p_one():
    assert pettitt(np.ones(10))["p"] == 1.0

# ---------- validação ----------

@pytest.mark.parametrize("bad", [[1.0, 2.0], [1.0, np.nan, 3.0], np.ones((2, 3))])
def test_series_validation(bad):
    with pytest.raises(ValueError, match="pelo menos"):
        mann_kendall(bad)

# ---------- resumo ----------

def test_resumo_combines_the_three_tests_and_names_the_break_year():
    y = np.r_[np.full(10, 50.0), np.full(10, 20.0)] + np.random.default_rng(0).normal(0, 1, 20)
    r = resumo(ANOS, y)
    assert r["pettitt"]["ano_quebra"] == 2012            # último ano do patamar alto
    assert r["media_antes"] == pytest.approx(50.0, abs=1) and r["media_depois"] == pytest.approx(20.0, abs=1)
    assert r["mann_kendall"]["tau"] < 0 and r["sen"]["inclinacao"] < 0
    assert r["sen"]["inclinacao_pct_ano"] == pytest.approx(100 * r["sen"]["inclinacao"] / y.mean())
    assert r["n_anos"] == 20 and r["periodo"] == [2003, 2022]
