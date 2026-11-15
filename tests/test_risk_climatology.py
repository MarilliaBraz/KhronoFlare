import pandas as pd

from firms_harmonize.risk.climatology import monthly_climatology


def _panel(rows):
    return pd.DataFrame(rows, columns=["cy", "cx", "mes_alvo", "ano_alvo", "alvo_n"])


def test_counts_years_with_fire_and_mean_per_cell_and_month():
    panel = _panel([(-20, -100, 12, 2004, 4), (-20, -100, 12, 2005, 0), (-20, -100, 12, 2006, 2),
                    (-20, -100, 1, 2004, 0), (-20, -100, 1, 2005, 0), (-20, -100, 1, 2006, 3)])
    clim = monthly_climatology(panel, res=0.5)
    months = clim["cells"]["-20,-100"]
    assert len(months) == 12
    assert months[11] == [2, 2.0]                     # dezembro: fogo em 2 de 3 anos, média (4+0+2)/3
    assert months[0] == [1, 1.0]                      # janeiro
    assert months[5] == [0, 0.0]                      # mês sem linhas no painel
    assert clim["res"] == 0.5 and clim["years"] == [2004, 2006] and clim["n_years"] == 3


def test_cells_that_never_burned_are_left_out():
    panel = _panel([(-20, -100, 12, 2004, 0), (-20, -100, 12, 2005, 0), (-21, -101, 12, 2004, 1),
                    (-21, -101, 12, 2005, 0)])
    assert list(monthly_climatology(panel, res=0.5)["cells"]) == ["-21,-101"]


def test_mean_is_rounded_to_one_decimal():
    panel = _panel([(-20, -100, 3, 2004, 1), (-20, -100, 3, 2005, 0), (-20, -100, 3, 2006, 0)])
    assert monthly_climatology(panel, res=0.5)["cells"]["-20,-100"][2] == [1, 0.3]
