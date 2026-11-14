import numpy as np
import pandas as pd
import pytest

from firms_harmonize.frp.calibrate import Calibration, evaluate, fit, validate

A, B, C = -0.2, 0.9, -0.003


def _synthetic(n=4000, sigma=0.0, seed=0, start="2012-02-01", end="2021-12-31"):
    rng = np.random.default_rng(seed)
    frp_m = np.exp(rng.normal(3.0, 1.0, n))
    vza = rng.uniform(0, 65, n)
    frp_v = np.exp(A + B * np.log(frp_m) + C * vza + rng.normal(0, sigma, n))
    dates = pd.to_datetime(rng.integers(pd.Timestamp(start).value, pd.Timestamp(end).value, n))
    return pd.DataFrame({"date": dates, "frp_modis": frp_m, "frp_viirs": frp_v, "vza": vza,
                         "outlier": False})


def test_fit_recovers_known_coefficients_without_noise():
    p = _synthetic()
    cal = fit(p["frp_modis"], p["vza"], p["frp_viirs"])
    assert (cal.a, cal.b, cal.c) == pytest.approx((A, B, C), abs=1e-9)
    assert cal.smearing == pytest.approx(1.0) and cal.n == len(p)


def test_smearing_corrects_the_retransformation_bias_of_sums():
    p = _synthetic(n=50_000, sigma=0.6)
    cal = fit(p["frp_modis"], p["vza"], p["frp_viirs"])
    assert cal.smearing == pytest.approx(np.exp(0.6 ** 2 / 2), rel=0.03)
    pred = cal.predict(p["frp_modis"], p["vza"])
    assert pred.sum() / p["frp_viirs"].sum() == pytest.approx(1.0, abs=0.02)
    naive = pred / cal.smearing                       # sem Duan a soma fica baixa
    assert naive.sum() / p["frp_viirs"].sum() < 0.9


def test_identity_calibration_returns_input():
    cal = Calibration(a=0.0, b=1.0, c=0.0, smearing=1.0, n=1)
    assert cal.predict(np.array([1.0, 25.0]), np.array([0.0, 60.0])) == pytest.approx([1.0, 25.0])


def test_dict_roundtrip():
    cal = Calibration(a=-0.1, b=0.95, c=-0.002, smearing=1.2, n=10)
    assert Calibration.from_dict(cal.to_dict()) == cal


def test_fit_rejects_nonpositive_frp_and_too_few_points():
    with pytest.raises(ValueError, match="positivo"):
        fit(np.array([1.0, 0.0, 2.0, 3.0]), np.zeros(4), np.ones(4))
    with pytest.raises(ValueError, match="poucos"):
        fit(np.array([1.0, 2.0]), np.zeros(2), np.ones(2))


def test_evaluate_perfect_prediction():
    obs = np.array([1.0, 5.0, 20.0])
    m = evaluate(obs, obs)
    assert m["r2_log"] == pytest.approx(1.0) and m["vies_soma_pct"] == pytest.approx(0.0)
    assert m["erro_mediano_pct"] == pytest.approx(0.0)


def test_evaluate_reports_sum_bias_in_percent():
    m = evaluate(np.array([1.1, 2.2]), np.array([1.0, 2.0]))
    assert m["vies_soma_pct"] == pytest.approx(10.0)
    assert m["erro_mediano_pct"] == pytest.approx(10.0)


def test_validate_trains_only_on_train_window_and_ignores_outliers():
    p = _synthetic(sigma=0.3)
    p.loc[p.index[:50], "outlier"] = True
    rep = validate(p, train=("2012-02", "2018-12"), test=("2019-01", "2021-12"))
    ym = p["date"].dt.to_period("M")
    in_train = ym.between(pd.Period("2012-02"), pd.Period("2018-12")) & ~p["outlier"]
    in_test = ym.between(pd.Period("2019-01"), pd.Period("2021-12")) & ~p["outlier"]
    assert rep["treino"]["pares"] == int(in_train.sum())
    assert rep["teste"]["pares"] == int(in_test.sum())
    assert set(rep["teste"]["modelos"]) == {"sem_correcao", "fator_unico", "modelo_vza"}
    assert set(rep["teste"]["vies_soma_anual_pct"]) == {"2019", "2020", "2021"}


def test_validate_vza_model_beats_baselines_out_of_sample():
    rep = validate(_synthetic(sigma=0.3), train=("2012-02", "2018-12"), test=("2019-01", "2021-12"))
    m = rep["teste"]["modelos"]
    assert m["modelo_vza"]["r2_log"] > m["fator_unico"]["r2_log"]
    assert abs(m["modelo_vza"]["vies_soma_pct"]) < abs(m["sem_correcao"]["vies_soma_pct"])
    assert abs(m["modelo_vza"]["vies_soma_pct"]) < 3.0

# ---------- versão B: fator de Duan por faixa de VZA ----------

def _heteroscedastic(n=60_000, seed=1):
    """Ruído pequeno no nadir (σ = 0,2) e grande na borda (σ = 0,8)."""
    p = _synthetic(n=n, seed=seed)
    rng = np.random.default_rng(seed + 1)
    sigma = np.where(p["vza"] < 30, 0.2, 0.8)
    return p.assign(frp_viirs=p["frp_viirs"] * np.exp(rng.normal(0, sigma)))


def test_smearing_by_bin_follows_the_noise_of_each_vza_bin():
    p = _heteroscedastic()
    cal = fit(p["frp_modis"], p["vza"], p["frp_viirs"], bin_width=10)
    assert cal.bin_width == 10 and len(cal.smearing_by_bin) == 7          # 0–10° … 60–70°
    assert cal.smearing_by_bin[0] == pytest.approx(np.exp(0.2 ** 2 / 2), rel=0.03)
    assert cal.smearing_by_bin[5] == pytest.approx(np.exp(0.8 ** 2 / 2), rel=0.05)


def test_smearing_by_bin_keeps_sums_unbiased_in_every_bin():
    p = _heteroscedastic()
    cal = fit(p["frp_modis"], p["vza"], p["frp_viirs"], bin_width=10)
    pred = pd.Series(cal.predict(p["frp_modis"], p["vza"]), index=p.index)
    faixa = np.floor(p["vza"] / 10)
    ratio = pred.groupby(faixa).sum() / p["frp_viirs"].groupby(faixa).sum()
    assert ratio.to_numpy() == pytest.approx(np.ones(len(ratio)), abs=0.04)


def test_vza_outside_trained_bins_uses_the_nearest_bin():
    p = _heteroscedastic()
    cal = fit(p["frp_modis"], p["vza"], p["frp_viirs"], bin_width=10)
    base = np.exp(cal.a + cal.b * np.log(20.0) + cal.c * 80.0)
    assert cal.predict([20.0], [80.0])[0] == pytest.approx(base * cal.smearing_by_bin[-1])


def test_empty_bin_falls_back_to_global_smearing():
    p = _synthetic(sigma=0.3)
    p = p[(p["vza"] < 20) | (p["vza"] >= 30)]                            # faixa 20–30° vazia
    cal = fit(p["frp_modis"], p["vza"], p["frp_viirs"], bin_width=10)
    assert cal.smearing_by_bin[2] == pytest.approx(cal.smearing)


def test_dict_roundtrip_with_bins():
    cal = Calibration(a=-0.1, b=0.95, c=-0.002, smearing=1.2, n=10, bin_width=10.0,
                      smearing_by_bin=(1.1, 1.2, 1.3))
    assert Calibration.from_dict(cal.to_dict()) == cal


def test_validate_uses_smearing_by_bin():
    rep = validate(_heteroscedastic(), train=("2012-02", "2018-12"), test=("2019-01", "2021-12"))
    assert rep["treino"]["modelo"]["bin_width"] == 10
    assert len(rep["treino"]["modelo"]["smearing_by_bin"]) == 7
