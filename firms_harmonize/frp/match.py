"""Etapa 3 do fluxograma: pareamento espaço-temporal do FRP Aqua MODIS com o S-NPP VIIRS.

Um foco VIIRS pertence a um pixel MODIS quando:
  * é do mesmo dia e da mesma passagem (dia/noite);
  * o centro do VIIRS cai dentro da pegada MODIS (retângulo `scan` leste-oeste × `track` norte-sul);
  * |Δt| ≤ 5 min (o CSV tem resolução de minuto).
Se cair em duas pegadas que se sobrepõem, vai só para a de centro mais próximo (distância
normalizada pelo tamanho da pegada), para nenhum FRP VIIRS ser contado duas vezes.
Cada par = um pixel MODIS e a soma do FRP dos VIIRS dentro dele.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .pixel import KM_PER_DEG_LAT, KM_PER_DEG_LON_EQUATOR, offsets_km

MAX_DT_MIN = 5
N_CANDIDATES = 8  # pixels MODIS mais próximos examinados para cada foco VIIRS
GROUP = ["date", "daynight"]
PAIR_COLUMNS = ["date", "minute", "daynight", "lat", "lon", "scan", "track", "vza",
                "frp_modis", "frp_viirs", "n_viirs", "dt_min"]


def _xy(lat, lon):
    return np.column_stack([lon * KM_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat)), lat * KM_PER_DEG_LAT])


def _assign(m: pd.DataFrame, v: pd.DataFrame, max_dt_min: int) -> np.ndarray:
    """Para cada VIIRS, a posição do pixel MODIS que o contém (ou -1)."""
    mlat, mlon = m["lat"].to_numpy(float), m["lon"].to_numpy(float)
    half_s, half_t = m["scan"].to_numpy(float) / 2, m["track"].to_numpy(float) / 2
    if np.isnan(half_s).all() or np.isnan(half_t).all():
        return np.full(len(v), -1)
    radius = float(np.hypot(np.nanmax(half_s), np.nanmax(half_t))) + 1e-6  # NaN não zera o grupo
    k = min(N_CANDIDATES, len(m))
    _, idx = cKDTree(_xy(mlat, mlon)).query(_xy(v["lat"].to_numpy(float), v["lon"].to_numpy(float)),
                                            k=k, distance_upper_bound=radius)
    idx = idx.reshape(len(v), k)
    found = idx < len(m)
    c = np.where(found, idx, 0)
    vlat = np.repeat(v["lat"].to_numpy(float)[:, None], k, axis=1)
    vlon = np.repeat(v["lon"].to_numpy(float)[:, None], k, axis=1)
    dx, dy = offsets_km(mlat[c], mlon[c], vlat, vlon)
    dt = np.abs(v["minute"].to_numpy(int)[:, None] - m["minute"].to_numpy(int)[c])
    score = np.maximum(np.abs(dx) / half_s[c], np.abs(dy) / half_t[c])
    ok = found & (score <= 1.0) & (dt <= max_dt_min)
    score = np.where(ok, score, np.inf)
    best = np.argmin(score, axis=1)
    rows = np.arange(len(v))
    return np.where(np.isfinite(score[rows, best]), c[rows, best], -1)


def _pairs_for_group(m: pd.DataFrame, v: pd.DataFrame, max_dt_min: int) -> pd.DataFrame:
    owner = _assign(m, v, max_dt_min)
    hit = owner >= 0
    if not hit.any():
        return pd.DataFrame(columns=PAIR_COLUMNS)
    dt = v["minute"].to_numpy(int)[hit] - m["minute"].to_numpy(int)[owner[hit]]
    agg = (pd.DataFrame({"owner": owner[hit], "frp": v["frp"].to_numpy(float)[hit], "dt": dt})
           .groupby("owner").agg(frp_viirs=("frp", "sum"), n_viirs=("frp", "size"), dt_min=("dt", "mean")))
    base = m.iloc[agg.index].reset_index(drop=True)
    return pd.DataFrame({
        **{c: base[c].to_numpy() for c in ["date", "minute", "daynight", "lat", "lon", "scan", "track", "vza"]},
        "frp_modis": base["frp"].to_numpy(float),
        "frp_viirs": agg["frp_viirs"].to_numpy(float),
        "n_viirs": agg["n_viirs"].to_numpy(int),
        "dt_min": np.rint(agg["dt_min"].to_numpy()).astype(int),
    })


def _slim(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[cols].assign(daynight=df["daynight"].astype(str).astype("category"))


def match_pairs(modis: pd.DataFrame, viirs: pd.DataFrame, max_dt_min: int = MAX_DT_MIN) -> pd.DataFrame:
    """Pares (pixel MODIS, ΣFRP VIIRS dentro dele) da mesma passagem."""
    if modis.empty or viirs.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    # Só as colunas usadas, com daynight categórico: recortar colunas de texto (pyarrow) de um
    # DataFrame grande custa ~0,1 s por grupo, independente do tamanho do grupo.
    modis = _slim(modis, ["date", "minute", "daynight", "lat", "lon", "scan", "track", "vza", "frp"])
    viirs = _slim(viirs, ["date", "minute", "daynight", "lat", "lon", "frp"])
    vgroups = viirs.groupby(GROUP, sort=False).indices
    parts = []
    for key, midx in modis.groupby(GROUP, sort=False).indices.items():
        vidx = vgroups.get(key)
        if vidx is not None:
            parts.append(_pairs_for_group(modis.iloc[midx], viirs.iloc[vidx], max_dt_min))
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    return pd.concat(parts, ignore_index=True)[PAIR_COLUMNS]


# ---------- etapa 5 do fluxograma: remoção de pares anômalos pelo IQR ----------

IQR_K = 1.5
VZA_BIN_DEG = 10


def _iqr_limits(values: np.ndarray, k: float) -> tuple[float, float]:
    q1, q3 = np.percentile(values, [25, 75])
    return q1 - k * (q3 - q1), q3 + k * (q3 - q1)


def outlier_mask(pairs: pd.DataFrame, bin_width: float | None = VZA_BIN_DEG, k: float = IQR_K,
                 reference=None) -> np.ndarray:
    """True nos pares anômalos: ln(ΣFRP_V / FRP_M) fora de [Q1 − k·IQR, Q3 + k·IQR].

    Os limites são calculados por faixa de VZA (padrão 10°), porque a razão muda com o ângulo e
    é justamente esse efeito que a calibração precisa enxergar. Pares sem VZA ou com FRP ≤ 0
    também saem (não dá para calcular a razão ou a faixa).

    `reference` (máscara booleana) escolhe os pares usados para calcular os limites, que depois
    valem para todos. Na validação fora da amostra, a referência é só o treino: assim os anos de
    teste não influenciam o próprio filtro. Faixa sem pares de referência usa os limites globais.
    """
    frp_m, frp_v = pairs["frp_modis"].to_numpy(float), pairs["frp_viirs"].to_numpy(float)
    vza = pairs["vza"].to_numpy(float)
    valid = (frp_m > 0) & (frp_v > 0) & np.isfinite(vza)
    log_ratio = np.full(len(pairs), np.nan)
    log_ratio[valid] = np.log(frp_v[valid] / frp_m[valid])
    group = np.zeros(len(pairs), dtype=int) if bin_width is None else np.floor(np.nan_to_num(vza) / bin_width)
    ref = valid if reference is None else valid & np.asarray(reference, dtype=bool)
    if not ref.any():
        raise ValueError("nenhum par válido na referência para calcular os limites do IQR")
    global_limits = _iqr_limits(log_ratio[ref], k)
    out = ~valid
    for g in np.unique(group[valid]):
        sel, rsel = valid & (group == g), ref & (group == g)
        low, high = _iqr_limits(log_ratio[rsel], k) if rsel.any() else global_limits
        out[sel] = (log_ratio[sel] < low) | (log_ratio[sel] > high)
    return out
