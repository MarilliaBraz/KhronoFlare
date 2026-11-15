import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "build_forecast", Path(__file__).resolve().parent.parent / "web" / "tools" / "build_forecast.py")
bf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bf)

FIELDS = ["lat", "lon", "frp", "conf", "sensor", "sat", "date", "time", "dn", "mun", "uf"]


def _clim(cells, n_years=18):
    return {"res": 0.5, "years": [2004, 2021], "n_years": n_years, "cells": cells}


def _months(dec):
    return [[0, 0.0]] * 11 + [dec]


def _live(points, kind="live", generated="2026-11-15T11:33:52+00:00"):
    return {"point_fields": FIELDS, "points": points, "meta": {"kind": kind, "generated": generated}}


def _point(lat, lon, mun="1500000", uf="PA"):
    return [lat, lon, 10.0, "nominal", "VIIRS", "N20", "2026-11-15", "0400", "N", mun, uf]


def _cities(rows):
    return {"states": [], "cities": [[cid, name, uf, lat, lon, 0] for cid, name, uf, lat, lon in rows]}


@pytest.mark.parametrize("generated, expected", [("2026-11-15T11:33:52+00:00", (2026, 12)),
                                                 ("2026-12-31T23:00:00+00:00", (2027, 1))])
def test_target_month_is_the_month_after_the_data(generated, expected):
    assert bf.target_month(generated) == expected


def test_cell_of_uses_floor_like_the_risk_panel():
    assert bf.cell_of(-9.8, -66.9, 0.5) == (-20, -134)
    assert bf.cell_of(2.39, -50.82, 0.5) == (4, -102)


@pytest.mark.parametrize("years, mean, active, expected", [
    (14, 15.0, 0, "high"),      # ≥ 75 % dos anos e média ≥ 15
    (14, 14.9, 0, "medium"),    # muitos anos, mas menos focos
    (9, 50.0, 0, "medium"),     # 50 % dos anos e média ≥ 5
    (9, 4.9, 0, "low"),         # 50 % dos anos, mas poucos focos
    (8, 50.0, 0, "low"),
    (8, 1.0, 3, "medium"),      # ≥ 3 focos ativos sobem um nível
    (8, 1.0, 2, "low"),         # 2 focos ativos não bastam
    (9, 5.0, 3, "high"),
    (14, 20.0, 9, "high"),      # alta continua alta
    (0, 0.0, 3, "medium"),      # sem histórico, mas queimando agora
])
def test_classify(years, mean, active, expected):
    assert bf.classify(years, 18, mean, active) == expected


def test_build_forecast_ranks_municipalities_and_explains_each():
    clim = _clim({"-20,-134": _months([16, 20.4]), "-10,-100": _months([10, 6.0]), "-30,-90": _months([3, 0.2])})
    live = _live([_point(-9.8, -66.9, mun="1200013", uf="AC"), _point(-9.9, -66.8, mun="1200013", uf="AC"),
                  _point(-9.7, -66.7, mun="1200013", uf="AC")])
    cities = _cities([("1200013", "Acrelândia", "AC", -9.8258, -66.8972),
                      ("1500001", "Cidade Média", "PA", -4.9, -49.9),
                      ("4300001", "Cidade Baixa", "RS", -14.9, -44.9)])
    fc = bf.build_forecast(clim, live, cities)

    assert fc["meta"]["target"] == "2026-12"
    assert fc["meta"]["active_counted"] is True
    assert [m["id"] for m in fc["municipalities"]] == ["1200013", "1500001"]      # baixa fica de fora
    top = fc["municipalities"][0]
    assert top == {"id": "1200013", "name": "Acrelândia", "uf": "AC", "cls": "high",
                   "years": 16, "n_years": 18, "mean": 20.4, "active_cell": 3, "active_mun": 3, "prob": None}
    assert fc["meta"]["model"] is None
    assert ["-20", "-134", "high", 16, 20.4, 3, None] == [str(c) if i < 2 else c for i, c in
                                                     enumerate(next(c for c in fc["cells"] if c[:2] == [-20, -134]))]


def test_sample_data_does_not_count_as_active_fire():
    clim = _clim({"-20,-134": _months([8, 1.0])})
    live = _live([_point(-9.8, -66.9)], kind="sample")
    fc = bf.build_forecast(clim, live, _cities([("1200013", "Acrelândia", "AC", -9.8258, -66.8972)]))
    assert fc["meta"]["active_counted"] is False
    assert fc["municipalities"] == []                  # 8/18 sem fogo ativo é baixa
    assert fc["cells"] == [[-20, -134, "low", 8, 1.0, 0, None]]


def test_points_outside_brazil_are_ignored_and_new_fire_cells_appear():
    clim = _clim({})
    fora = [_point(-9.8, -66.9, mun="", uf="")] * 3
    live = _live([*fora, *[_point(-4.9, -49.9, mun="1500001", uf="PA")] * 3])
    fc = bf.build_forecast(clim, live, _cities([("1500001", "Nova", "PA", -4.95, -49.95)]))
    assert fc["cells"] == [[-10, -100, "medium", 0, 0.0, 3, None]]
    assert fc["municipalities"][0]["cls"] == "medium" and fc["municipalities"][0]["years"] == 0


def test_ranking_order_class_then_active_then_history():
    clim = _clim({"-10,-100": _months([18, 20.0]), "-12,-100": _months([14, 16.0]), "-14,-100": _months([15, 15.0])})
    live = _live([_point(-6.9, -49.9, mun="2", uf="PA")])
    cities = _cities([("1", "A", "PA", -4.9, -49.9), ("2", "B", "PA", -5.9, -49.9), ("3", "C", "PA", -6.9, -49.9)])
    fc = bf.build_forecast(clim, live, cities)
    assert [m["id"] for m in fc["municipalities"]] == ["2", "1", "3"]


def test_same_content_ignores_only_the_generation_time():
    a = {"meta": {"target": "2026-12", "generated": "2026-11-15T12:00:00+00:00"}, "cells": [[1, 2, "high", 3, 4.0, 0]],
         "municipalities": []}
    b = {**a, "meta": {**a["meta"], "generated": "2026-11-15T15:00:00+00:00"}}
    c = {**b, "cells": [[1, 2, "medium", 3, 4.0, 0]]}
    assert bf.same_content(a, b) is True
    assert bf.same_content(a, c) is False
    assert bf.same_content(None, a) is False


def _model(cells, target="2026-12"):
    return {"target": target, "generated": "2026-11-15T13:00:00+00:00", "model": "Random Forest",
            "train_years": [2004, 2021], "validation": {"roc_auc_temporal": 0.708, "roc_auc_spatial": 0.702},
            "base_rate": 0.167, "data_until": "2026-11-13", "partial_scale": 2.308, "drift_factor": 0.781,
            "cells": cells}


@pytest.mark.parametrize("years, mean, active, prob, expected", [
    (8, 1.0, 0, 0.35, "medium"),     # modelo ≥ 35 % sobe um nível
    (8, 1.0, 0, 0.34, "low"),
    (8, 1.0, 3, 0.40, "high"),       # fogo ativo e modelo: um nível cada
    (14, 20.0, 0, 0.50, "high"),     # alta continua alta
    (8, 1.0, 0, None, "low"),        # sem modelo
])
def test_classify_with_model(years, mean, active, prob, expected):
    assert bf.classify(years, 18, mean, active, prob) == expected


def test_model_is_used_when_its_month_matches():
    clim = _clim({"-10,-100": _months([8, 1.0]), "-12,-100": _months([14, 20.0])})
    cities = _cities([("1", "A", "PA", -4.9, -49.9), ("2", "B", "PA", -5.9, -49.9)])
    fc = bf.build_forecast(clim, _live([]), cities, _model({"-10,-100": 0.41, "-12,-100": 0.05}))
    assert fc["meta"]["model"]["min_prob"] == bf.MODEL_MIN_PROB
    assert fc["meta"]["model"]["roc_auc_temporal"] == 0.708 and fc["meta"]["model"]["base_rate"] == 0.167
    by_id = {m["id"]: m for m in fc["municipalities"]}
    assert by_id["1"]["cls"] == "medium" and by_id["1"]["prob"] == 0.41
    assert by_id["2"]["cls"] == "high" and by_id["2"]["prob"] == 0.05
    assert [-10, -100, "medium", 8, 1.0, 0, 0.41] in fc["cells"]


def test_model_for_another_month_is_ignored():
    clim = _clim({"-10,-100": _months([8, 1.0])})
    fc = bf.build_forecast(clim, _live([]), _cities([("1", "A", "PA", -4.9, -49.9)]),
                           _model({"-10,-100": 0.9}, target="2026-11"))
    assert fc["meta"]["model"] is None
    assert fc["municipalities"] == [] and fc["cells"] == [[-10, -100, "low", 8, 1.0, 0, None]]
