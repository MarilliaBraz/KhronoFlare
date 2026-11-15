"""Fatores externos do modelo de mês crítico (passos 2 e 3): ONI, TNA e bioma.

ONI (Oceanic Niño Index, NOAA CPC): anomalia da temperatura do mar no Niño 3.4, em médias móveis de
três meses (DJF, JFM, ...). O ano da linha é o do mês central (NDJ 2009 = nov/2009–jan/2010).
Cada trimestre é indexado pelo **último** mês: a variável do mês t usa o trimestre que termina em t,
porque o trimestre centrado em t já inclui t+1, que é o mês do alvo.

Biomas (IBGE, "Biomas_5000mil.zip", 1:5.000.000, SIRGAS 2000 em graus ≈ WGS84 dos focos): a API de
malhas do IBGE não tem biomas, então o shapefile vem do geoftp oficial. Só os 6 biomas terrestres
entram; cada célula recebe o bioma do seu centro ou, se o centro cair fora (mar, vãos), o mais próximo.
"""
from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import shapefile
import shapely
from shapely.geometry import shape

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
_SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                  "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}


def parse_oni(text: str) -> pd.DataFrame:
    """Texto do arquivo da NOAA → DataFrame (ym_fim, oni), em ordem e sem meses repetidos."""
    try:
        raw = pd.read_csv(io.StringIO(text), sep=r"\s+")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise ValueError(f"arquivo ONI ilegível: {e}") from None
    if not {"SEAS", "YR", "ANOM"} <= set(raw.columns) or raw.empty:
        raise ValueError(f"arquivo ONI sem as colunas SEAS, YR e ANOM: {list(raw.columns)[:5]}")
    center = raw["SEAS"].map(_SEASON_CENTER)
    if center.isna().any():
        raise ValueError(f"trimestre desconhecido no arquivo ONI: {raw.loc[center.isna(), 'SEAS'].iloc[0]}")
    ym_center = pd.PeriodIndex.from_fields(year=raw["YR"].astype(int), month=center.astype(int), freq="M")
    out = pd.DataFrame({"ym_fim": ym_center + 1, "oni": pd.to_numeric(raw["ANOM"], errors="raise")})
    out = out.sort_values("ym_fim").reset_index(drop=True)
    if out["ym_fim"].duplicated().any():
        raise ValueError("arquivo ONI com trimestre repetido")
    return out


def read_oni(path: Path) -> pd.DataFrame:
    return parse_oni(Path(path).read_text())


def fetch_oni(dest: Path, session: requests.Session | None = None, url: str = ONI_URL,
              timeout: int = 60) -> Path:
    """Baixa o ONI, valida e só então grava em `dest` (nunca salva uma página de erro)."""
    r = (session or requests.Session()).get(url, timeout=timeout)
    r.raise_for_status()
    parse_oni(r.text)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(r.text)
    return dest


def _add_monthly_index(panel: pd.DataFrame, series: pd.Series, prefix: str, label: str) -> pd.DataFrame:
    """`{prefix}_atual`: valor do mês t; `{prefix}_3m`: média de t−2..t. Falha se faltar algum mês."""
    s = series.reindex(pd.period_range(series.index.min(), series.index.max(), freq="M"))
    three = s.rolling(3, min_periods=3).mean()
    ym = pd.PeriodIndex(panel["ym"], freq="M")
    atual, media = s.reindex(ym).to_numpy(), three.reindex(ym).to_numpy()
    missing = np.isnan(atual) | np.isnan(media)
    if missing.any():
        meses = sorted({str(m) for m in ym[missing]})
        raise ValueError(f"{label} ausente para {len(meses)} mês(es) do painel, ex.: {meses[:3]}")
    return panel.assign(**{f"{prefix}_atual": atual, f"{prefix}_3m": media})


def add_oni(panel: pd.DataFrame, oni: pd.DataFrame) -> pd.DataFrame:
    """`oni_atual`: trimestre que termina em t; `oni_3m`: média dos trimestres que terminam em t−2..t."""
    return _add_monthly_index(panel, oni.set_index("ym_fim")["oni"], "oni", "ONI")


# ---------- TNA (Tropical Northern Atlantic, NOAA PSL) ----------
# Anomalia da temperatura do mar em 5,5°N–23,5°N, 15°W–57,5°W. Um valor por mês: a variável do mês t
# usa o próprio mês t. Explica meses críticos na Amazônia, no Cerrado e no Pantanal bem melhor que o ONI
# (correlação anual 0,42–0,45 contra 0,08–0,22, 2004–2021), mas fica no painel só para análise
# descritiva: nenhum índice climático melhorou o Random Forest fora da amostra.

TNA_URL = "https://psl.noaa.gov/data/correlation/tna.data"
_PSL_MISSING = -90.0  # a PSL marca meses sem dado com -99.99


def _psl_year_line(parts: list[str]) -> bool:
    return 2 <= len(parts) <= 13 and len(parts[0]) == 4 and parts[0].isdigit()


def parse_psl(text: str, label: str) -> pd.DataFrame:
    """Formato PSL → DataFrame (ym, valor).

    A 1ª linha "ano_inicial ano_final" é cabeçalho; depois, "ano v1 … vN" com até 12 meses (o ano
    corrente pode vir incompleto); o rodapé (marcador de ausência, nome do índice) é ignorado.
    """
    rows = []
    lines = text.splitlines()
    header = lines[0].split() if lines else []
    start = 1 if len(header) == 2 and all(h.isdigit() for h in header) else 0
    for line in lines[start:]:
        parts = line.split()
        if not _psl_year_line(parts):
            continue
        year = int(parts[0])
        for month, value in enumerate(parts[1:], start=1):
            try:
                v = float(value)
            except ValueError:
                raise ValueError(f"arquivo {label}: valor não numérico {value!r} em {year}-{month:02d}") from None
            if v > _PSL_MISSING:
                rows.append((pd.Period(year=year, month=month, freq="M"), v))
    if not rows:
        raise ValueError(f"arquivo {label} sem linhas mensais no formato da NOAA PSL")
    out = pd.DataFrame(rows, columns=["ym", "valor"]).sort_values("ym").reset_index(drop=True)
    if out["ym"].duplicated().any():
        raise ValueError(f"arquivo {label} com mês repetido")
    return out


def read_tna(path: Path) -> pd.DataFrame:
    return parse_psl(Path(path).read_text(), "TNA")


def fetch_tna(dest: Path, session: requests.Session | None = None, url: str = TNA_URL,
              timeout: int = 60) -> Path:
    """Baixa o TNA, valida e só então grava em `dest`."""
    r = (session or requests.Session()).get(url, timeout=timeout)
    r.raise_for_status()
    parse_psl(r.text, "TNA")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(r.text)
    return dest


def add_tna(panel: pd.DataFrame, tna: pd.DataFrame) -> pd.DataFrame:
    """`tna_atual`: TNA do mês t; `tna_3m`: média de t−2..t."""
    return _add_monthly_index(panel, tna.set_index("ym")["valor"], "tna", "TNA")


# ---------- biomas ----------

BIOMES_URL = ("https://geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/biomas/vetores/"
              "Biomas_5000mil.zip")
BIOME_CODES = {"AMZ": "Amazônia", "CAAT": "Caatinga", "CER": "Cerrado",
               "MAT": "Mata Atlântica", "PMP": "Pampa", "PTN": "Pantanal"}


def read_biomes(zip_path: Path) -> dict:
    """Zip do IBGE → {código: geometria shapely}, só com os biomas terrestres."""
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("arquivo de biomas não é um zip válido") from None
    with z:
        bases = [n[:-4] for n in z.namelist() if n.lower().endswith(".shp")]
        if not bases:
            raise ValueError("zip de biomas sem arquivo .shp")
        try:
            features = _read_shapefile(z.read(bases[0] + ".shp"), z.read(bases[0] + ".dbf"))
        except (KeyError, struct.error, shapefile.ShapefileException) as e:
            raise ValueError(f"shapefile de biomas inválido: {e}") from None
    out = {}
    for code, geom in features:
        if code in BIOME_CODES:   # mais de uma feição com o mesmo código vira uma só geometria
            out[code] = shapely.union(out[code], geom) if code in out else geom
    if not out:
        raise ValueError("shapefile sem nenhum bioma terrestre conhecido")
    return out


def _read_shapefile(shp: bytes, dbf: bytes) -> list[tuple[str, object]]:
    with shapefile.Reader(shp=io.BytesIO(shp), dbf=io.BytesIO(dbf), encoding="latin-1") as reader:
        fields = [f[0] for f in reader.fields[1:]]
        if "COD_BIOMA" not in fields:
            raise ValueError(f"shapefile de biomas sem o campo COD_BIOMA: {fields}")
        return [(str(rec["COD_BIOMA"]).strip(), shapely.make_valid(shape(shp_.__geo_interface__)))
                for rec, shp_ in zip(reader.records(), reader.shapes())]


def fetch_biomes(dest: Path, session: requests.Session | None = None, url: str = BIOMES_URL,
                 timeout: int = 120) -> Path:
    """Baixa o zip de biomas, valida e só então grava em `dest`."""
    r = (session or requests.Session()).get(url, timeout=timeout)
    r.raise_for_status()
    dest = Path(dest)
    tmp = dest.with_suffix(".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp.write_bytes(r.content)
        read_biomes(tmp)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)   # nunca deixa o .part, qualquer que seja o erro
    return dest


def assign_biome(cells: pd.DataFrame, biomes: dict, res: float) -> pd.DataFrame:
    """Bioma do centro de cada célula; fora de todos, o bioma mais próximo (marcado)."""
    lat = (cells["cy"].to_numpy() + 0.5) * res
    lon = (cells["cx"].to_numpy() + 0.5) * res
    codes = np.full(len(cells), "", dtype=object)
    for code, geom in biomes.items():
        inside = shapely.contains_xy(geom, lon, lat) & (codes == "")
        codes[inside] = code
    outside = codes == ""
    if outside.any():
        points = shapely.points(lon[outside], lat[outside])
        names = list(biomes)
        dist = np.column_stack([shapely.distance(points, biomes[c]) for c in names])
        codes[outside] = np.array(names, dtype=object)[np.argmin(dist, axis=1)]
    return cells.assign(bioma=codes, bioma_por_proximidade=outside)


def add_biome(panel: pd.DataFrame, biomes: dict, res: float) -> pd.DataFrame:
    """`bioma` e uma coluna 0/1 por bioma (`bioma_AMZ`, ...), iguais em todos os meses da célula."""
    cells = assign_biome(panel[["cy", "cx"]].drop_duplicates(), biomes, res)
    out = panel.merge(cells[["cy", "cx", "bioma"]], on=["cy", "cx"], how="left")
    return out.assign(**{f"bioma_{c}": out["bioma"].eq(c).astype(int) for c in BIOME_CODES})
