from pathlib import Path

import pandas as pd
import pytest

from firms_harmonize.risk.drivers import add_oni, fetch_oni, read_oni

FIX = Path(__file__).parent / "fixtures" / "oni_2009_2011.txt"


# ---------- leitura do ONI (NOAA CPC, trimestres móveis) ----------

def test_read_oni_indexes_each_season_by_its_last_month():
    oni = read_oni(FIX).set_index("ym_fim")["oni"]
    assert oni[pd.Period("2010-01", "M")] == pytest.approx(1.50)    # NDJ 2009 = nov/09–jan/10
    assert oni[pd.Period("2010-02", "M")] == pytest.approx(1.47)    # DJF 2010 = dez/09–fev/10
    assert oni[pd.Period("2010-06", "M")] == pytest.approx(-0.16)   # AMJ 2010
    assert oni[pd.Period("2010-08", "M")] == pytest.approx(-0.98)   # JJA 2010
    assert oni.index.is_monotonic_increasing and oni.index.is_unique


def test_read_oni_rejects_unexpected_format(tmp_path):
    bad = tmp_path / "oni.txt"
    bad.write_text("SEAS YR TOTAL\nDJF 2010 28.1\n")
    with pytest.raises(ValueError, match="ONI"):
        read_oni(bad)

# ---------- junção ao painel, sem olhar o mês do alvo ----------

def _panel(months):
    return pd.DataFrame({"cy": 0, "cx": 0, "ym": pd.PeriodIndex(months, freq="M")})


def test_add_oni_uses_the_season_ending_in_month_t():
    p = add_oni(_panel(["2010-06", "2010-08"]), read_oni(FIX)).set_index("ym")
    assert p.loc[pd.Period("2010-06", "M"), "oni_atual"] == pytest.approx(-0.16)   # AMJ, não MJJ
    assert p.loc[pd.Period("2010-08", "M"), "oni_atual"] == pytest.approx(-0.98)   # JJA


def test_add_oni_three_month_mean_uses_seasons_ending_t_minus_2_to_t():
    oni = read_oni(FIX).set_index("ym_fim")["oni"]
    p = add_oni(_panel(["2010-08"]), read_oni(FIX))
    expected = oni[pd.period_range("2010-06", "2010-08", freq="M")].mean()
    assert p["oni_3m"].iloc[0] == pytest.approx(expected)


def test_add_oni_fails_loudly_when_months_are_missing():
    with pytest.raises(ValueError, match="ONI"):
        add_oni(_panel(["2015-06"]), read_oni(FIX))

# ---------- download ----------

class _FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, response):
        self.response, self.urls = response, []

    def get(self, url, timeout):
        self.urls.append(url)
        return self.response


def test_fetch_oni_saves_valid_file(tmp_path):
    dest = tmp_path / "oni" / "oni.ascii.txt"
    session = _FakeSession(_FakeResponse(FIX.read_text()))
    assert fetch_oni(dest, session=session) == dest
    assert len(read_oni(dest)) == 36 and session.urls[0].startswith("https://")


def test_fetch_oni_does_not_save_invalid_content(tmp_path):
    dest = tmp_path / "oni.ascii.txt"
    with pytest.raises(ValueError, match="ONI"):
        fetch_oni(dest, session=_FakeSession(_FakeResponse("<html>manutenção</html>")))
    assert not dest.exists()


@pytest.mark.parametrize("text, msg", [
    ("", "ilegível"),
    (" SEAS  YR   TOTAL   ANOM\n  XYZ 2010  28.15   1.47\n", "desconhecido"),
    (" SEAS  YR   TOTAL   ANOM\n  DJF 2010  28.15   1.47\n  DJF 2010  28.15   1.47\n", "repetido"),
])
def test_parse_oni_errors(text, msg):
    from firms_harmonize.risk.drivers import parse_oni
    with pytest.raises(ValueError, match=msg):
        parse_oni(text)
