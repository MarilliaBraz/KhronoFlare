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

# ---------- biomas (IBGE, shapefile 1:5.000.000) ----------

import io
import zipfile

import shapefile

from firms_harmonize.risk.drivers import BIOME_CODES, add_biome, assign_biome, fetch_biomes, read_biomes


def _square(x0, y0, size):
    return [[(x0, y0), (x0, y0 + size), (x0 + size, y0 + size), (x0 + size, y0), (x0, y0)]]


def _biomes_zip(path, features):
    """features: (código, nome, anel) → zip com Biomas5000.shp/.shx/.dbf, como o do IBGE."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON, encoding="latin-1")
    w.field("COD_BIOMA", "C", 10)
    w.field("NOM_BIOMA", "C", 60)
    for code, name, ring in features:
        w.poly(ring)
        w.record(code, name)
    w.close()
    with zipfile.ZipFile(path, "w") as z:
        for ext, buf in [("shp", shp), ("shx", shx), ("dbf", dbf)]:
            z.writestr(f"Biomas5000.{ext}", buf.getvalue())
    return path


FEATURES_BIOMA = [("AMZ", "Amazônia", _square(-60, -10, 10)),
                  ("CER", "Cerrado", _square(-50, -20, 10)),
                  ("000Magua", "Massa Dagua Continental", _square(-60, -20, 10))]


def test_read_biomes_keeps_only_land_biomes(tmp_path):
    b = read_biomes(_biomes_zip(tmp_path / "b.zip", FEATURES_BIOMA))
    assert set(b) == {"AMZ", "CER"}
    assert b["AMZ"].contains(__import__("shapely").geometry.Point(-55, -5))


def test_read_biomes_rejects_zip_without_shapefile(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("leia-me.txt", "nada")
    with pytest.raises(ValueError, match="bioma"):
        read_biomes(bad)


def test_assign_biome_by_cell_center_and_nearest_when_outside(tmp_path):
    b = read_biomes(_biomes_zip(tmp_path / "b.zip", FEATURES_BIOMA))
    cells = pd.DataFrame({"cy": [-10, -30, -25], "cx": [-110, -90, -150]})   # res 0,5°
    # centros: (−4,75; −54,75) Amazônia; (−14,75; −44,75) Cerrado; (−12,25; −74,75) fora → mais próximo AMZ
    out = assign_biome(cells, b, res=0.5)
    assert out["bioma"].tolist() == ["AMZ", "CER", "AMZ"]
    assert out["bioma_por_proximidade"].tolist() == [False, False, True]


def test_add_biome_adds_one_hot_columns_constant_per_cell(tmp_path):
    b = read_biomes(_biomes_zip(tmp_path / "b.zip", FEATURES_BIOMA))
    panel = pd.DataFrame({"cy": [-10, -10, -30], "cx": [-110, -110, -90],
                          "ym": pd.PeriodIndex(["2010-01", "2010-02", "2010-01"], freq="M")})
    out = add_biome(panel, b, res=0.5)
    assert out["bioma"].tolist() == ["AMZ", "AMZ", "CER"]
    cols = [f"bioma_{c}" for c in BIOME_CODES]
    assert set(cols) <= set(out.columns)
    assert out[cols].sum(axis=1).eq(1).all()
    assert out["bioma_AMZ"].tolist() == [1, 1, 0] and out["bioma_PMP"].eq(0).all()


def test_fetch_biomes_saves_only_valid_zip(tmp_path):
    good = _biomes_zip(tmp_path / "src.zip", FEATURES_BIOMA).read_bytes()

    class Resp:
        def __init__(self, content): self.content, self.status_code = content, 200
        def raise_for_status(self): pass

    class Sess:
        def __init__(self, content): self.content = content
        def get(self, url, timeout): return Resp(self.content)

    dest = tmp_path / "biomas" / "Biomas_5000mil.zip"
    assert fetch_biomes(dest, session=Sess(good)) == dest and set(read_biomes(dest)) == {"AMZ", "CER"}
    bad_dest = tmp_path / "x.zip"
    with pytest.raises(ValueError, match="bioma"):
        fetch_biomes(bad_dest, session=Sess(b"<html>erro</html>"))
    assert not bad_dest.exists()


def test_read_biomes_rejects_only_water_features(tmp_path):
    with pytest.raises(ValueError, match="bioma terrestre"):
        read_biomes(_biomes_zip(tmp_path / "agua.zip", [FEATURES_BIOMA[2]]))


def test_read_biomes_rejects_shapefile_without_code_field(tmp_path):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("NOME", "C", 20)
    w.poly(_square(0, 0, 1))
    w.record("x")
    w.close()
    path = tmp_path / "sem_campo.zip"
    with zipfile.ZipFile(path, "w") as z:
        for ext, buf in [("shp", shp), ("shx", shx), ("dbf", dbf)]:
            z.writestr(f"B.{ext}", buf.getvalue())
    with pytest.raises(ValueError, match="COD_BIOMA"):
        read_biomes(path)
