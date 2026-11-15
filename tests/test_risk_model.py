import numpy as np
import pandas as pd
import pytest

from firms_harmonize.risk.model import (BASE_FEATURES, ONI_FEATURES, evaluate, spatial_folds,
                                        spatial_validation, temporal_validation)

TRAIN, TEST = (2004, 2010), (2011, 2013)


def _panel(n_cells=60, seed=0, signal=3.0):
    """Painel sintético: `n_lag0` prevê o alvo; o resto é ruído. Células espalhadas em vários blocos de 5°."""
    rng = np.random.default_rng(seed)
    cells = pd.DataFrame({"cy": rng.integers(-60, 10, n_cells), "cx": rng.integers(-140, -70, n_cells)})
    years = np.arange(TRAIN[0], TEST[1] + 1)
    df = cells.merge(pd.DataFrame({"ano_alvo": years}), how="cross")
    df = df.merge(pd.DataFrame({"mes_alvo": [3, 8]}), how="cross")
    n = len(df)
    y = (rng.random(n) < 0.3).astype(int)
    df["y_critico"] = y
    for col in ONI_FEATURES:
        if col not in ("cy", "cx"):
            df[col] = rng.normal(size=n)
    df["n_lag0"] = y * signal + rng.normal(size=n)
    df["frp_lag0"] = rng.random(n)
    df["p_fogo"] = rng.random(n)
    df["frp_p75"] = np.where(rng.random(n) < 0.3, 0.0, 10.0)
    df["bioma"] = np.where(df["cx"] < -100, "AMZ", "CER")
    return df


# ---------- métricas ----------

def test_evaluate_perfect_and_single_class():
    m = evaluate(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
    assert m["roc_auc"] == pytest.approx(1.0) and m["pr_auc"] == pytest.approx(1.0)
    assert m["prevalencia"] == pytest.approx(0.5) and m["n"] == 4
    single = evaluate(np.array([1, 1]), np.array([0.3, 0.4]))
    assert np.isnan(single["roc_auc"]) and np.isnan(single["pr_auc"])


def test_feature_sets_differ_only_by_oni():
    assert set(ONI_FEATURES) - set(BASE_FEATURES) == {"oni_atual", "oni_3m"}
    assert {"bioma_AMZ", "n_lag0", "p_fogo"} <= set(BASE_FEATURES)

# ---------- validação temporal ----------

def test_temporal_validation_learns_signal_and_reports_breakdowns():
    p = _panel()
    rep = temporal_validation(p, ONI_FEATURES, train_years=TRAIN, test_years=TEST, n_estimators=50)
    assert rep["treino"]["linhas"] == int(p["ano_alvo"].between(*TRAIN).sum())
    assert rep["teste"]["linhas"] == int(p["ano_alvo"].between(*TEST).sum())
    assert rep["teste"]["modelo"]["roc_auc"] > 0.9
    assert set(rep["teste"]["referencias"]) == {"sorteio", "repetir_mes_atual", "climatologia"}
    assert rep["teste"]["referencias"]["sorteio"]["roc_auc"] == pytest.approx(0.5)
    assert set(rep["teste"]["por_ano"]) == {"2011", "2012", "2013"}
    assert set(rep["teste"]["por_bioma"]) == {"AMZ", "CER"}
    assert set(rep["teste"]["por_tipo"]) == {"fora_de_epoca", "temporada"}


def test_temporal_validation_rejects_missing_features():
    with pytest.raises(ValueError, match="variáveis"):
        temporal_validation(_panel().drop(columns=["oni_3m"]), ONI_FEATURES, TRAIN, TEST, n_estimators=5)

# ---------- validação espacial ----------

def test_spatial_folds_never_share_a_block_between_train_and_test():
    p = _panel(n_cells=80)
    folds = spatial_folds(p, block_deg=5.0, res=0.5, n_folds=4)
    assert len(folds) == 4
    block = (np.floor((p["cy"] + 0.5) * 0.5 / 5).astype(int).astype(str) + "_" +
             np.floor((p["cx"] + 0.5) * 0.5 / 5).astype(int).astype(str))
    tested = np.zeros(len(p), dtype=bool)
    for train_mask, test_mask in folds:
        assert not (train_mask & test_mask).any()
        assert set(block[train_mask]).isdisjoint(set(block[test_mask]))
        tested |= test_mask
    assert tested.all()                       # cada linha é teste em exatamente um grupo


def test_spatial_validation_tests_only_held_out_blocks_in_test_years():
    p = _panel(n_cells=80)
    rep = spatial_validation(p, ONI_FEATURES, TRAIN, TEST, block_deg=5.0, res=0.5, n_folds=4,
                             n_estimators=30)
    assert rep["teste"]["linhas"] == int(p["ano_alvo"].between(*TEST).sum())
    assert len(rep["por_grupo"]) == 4 and rep["teste"]["modelo"]["roc_auc"] > 0.9


def test_spatial_folds_need_enough_blocks():
    p = _panel(n_cells=3).assign(cy=0, cx=0)          # uma célula só → um bloco
    with pytest.raises(ValueError, match="blocos"):
        spatial_folds(p, block_deg=5.0, res=0.5, n_folds=3)

# ---------- passo 5: importância por permutação agrupada ----------

from firms_harmonize.risk.model import FEATURE_GROUPS, fit_model, grouped_permutation_importance


def test_feature_groups_cover_every_base_feature_exactly_once():
    flat = [f for cols in FEATURE_GROUPS.values() for f in cols]
    assert sorted(flat) == sorted(BASE_FEATURES)


def test_grouped_importance_finds_the_informative_group():
    p = _panel(n_cells=60)
    model = fit_model(p, BASE_FEATURES, TRAIN, n_estimators=50)
    test = p[p["ano_alvo"].between(*TEST)]
    imp = grouped_permutation_importance(model, test, BASE_FEATURES, FEATURE_GROUPS, n_repeats=3, seed=0)
    assert imp.index[0] == "historico_recente"                  # onde está n_lag0
    assert imp.loc["historico_recente", "queda_auc"] > 0.2
    assert (imp.drop(index="historico_recente")["queda_auc"].abs() < 0.05).all()
    assert {"queda_auc", "desvio"} <= set(imp.columns)


def test_grouped_importance_does_not_modify_the_input():
    p = _panel(n_cells=30)
    model = fit_model(p, BASE_FEATURES, TRAIN, n_estimators=10)
    test = p[p["ano_alvo"].between(*TEST)].copy()
    before = test.copy()
    grouped_permutation_importance(model, test, BASE_FEATURES, FEATURE_GROUPS, n_repeats=2, seed=0)
    pd.testing.assert_frame_equal(test, before)

# ---------- mês do mapa escolhido sem olhar o resultado ----------

from firms_harmonize.risk.model import choose_map_month


def test_map_month_uses_fire_known_at_prediction_time_not_the_label():
    ym = pd.PeriodIndex(["2019-07", "2019-08", "2019-09", "2020-07"], freq="M")   # alvos ago, set, out/19 e ago/20
    test = pd.DataFrame({"ym": ym, "mes_alvo": [8, 9, 10, 8], "frp_lag0": [5.0, 50.0, 1.0, 20.0],
                         "y_critico": [1, 0, 1, 1]})
    assert choose_map_month(test) == pd.Period("2019-09", "M")    # alvo do mês com maior ΣFRP em t
    flipped = test.assign(y_critico=1 - test["y_critico"])
    assert choose_map_month(flipped) == pd.Period("2019-09", "M")  # o rótulo não muda a escolha
