"""Etapas 1 e 2 do fluxograma: remover FRP ≤ 0 e detecções duplicadas do mesmo sensor.

Duplicata (fluxograma: Δt < 8 s e sobreposição > 30 %): duas detecções da mesma plataforma, no
mesmo dia, com |Δt| ≤ 1 min e pegadas que se sobrepõem mais de 30 % da menor. O CSV da FIRMS só
tem horário com resolução de minuto, por isso 8 s vira "mesmo minuto ou minuto vizinho".
Fica a detecção mais perto do nadir (menor `scan`); em empate, a que aparece primeiro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .pixel import KM_PER_DEG_LAT, KM_PER_DEG_LON_EQUATOR, overlap_fraction

MAX_DT_MIN = 1
MIN_OVERLAP = 0.30


def drop_nonpositive_frp(df: pd.DataFrame) -> pd.DataFrame:
    """Etapa 1: só focos com FRP > 0 (NaN também sai)."""
    return df[df["frp"] > 0]


def minute_of_day(hhmm: pd.Series) -> np.ndarray:
    """'HHMM' → minutos desde 00:00 UTC."""
    t = pd.to_numeric(hhmm, errors="raise").to_numpy(dtype=int)
    return (t // 100) * 60 + t % 100


def _candidate_pairs(lat, lon, scan, track) -> np.ndarray:
    """Pares cujos centros estão perto o bastante para as pegadas se tocarem."""
    xy = np.column_stack([lon * KM_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat)), lat * KM_PER_DEG_LAT])
    radius = float(np.hypot(scan.max(), track.max()))
    return cKDTree(xy).query_pairs(radius, output_type="ndarray")


def _resolve(pairs: np.ndarray, rank: np.ndarray, n: int) -> np.ndarray:
    """Dado pares duplicados, marca para remoção o pior de cada par cujo melhor foi mantido."""
    a, b = pairs[:, 0], pairs[:, 1]
    swap = rank[a] > rank[b]
    best, worst = np.where(swap, b, a), np.where(swap, a, b)
    drop = np.zeros(n, dtype=bool)
    # Processa na ordem de qualidade do pior: quando chegamos a um par, o status do melhor já é final.
    for i in np.argsort(rank[worst], kind="stable"):
        if not drop[best[i]]:
            drop[worst[i]] = True
    return drop


def _group_duplicates(g: pd.DataFrame, minute: np.ndarray, max_dt_min: int, min_overlap: float) -> np.ndarray:
    lat, lon = g["lat"].to_numpy(float), g["lon"].to_numpy(float)
    scan, track = g["scan"].to_numpy(float), g["track"].to_numpy(float)
    pairs = _candidate_pairs(lat, lon, scan, track)
    if len(pairs) == 0:
        return np.zeros(len(g), dtype=bool)
    a, b = pairs[:, 0], pairs[:, 1]
    close_in_time = np.abs(minute[a] - minute[b]) <= max_dt_min
    overlap = overlap_fraction(lat[a], lon[a], scan[a], track[a], lat[b], lon[b], scan[b], track[b])
    dup = pairs[close_in_time & (overlap > min_overlap)]
    if len(dup) == 0:
        return np.zeros(len(g), dtype=bool)
    order = np.lexsort((np.arange(len(g)), scan))  # menor scan primeiro; empate → ordem original
    rank = np.empty(len(g), dtype=int)
    rank[order] = np.arange(len(g))
    return _resolve(dup, rank, len(g))


def duplicate_mask(df: pd.DataFrame, max_dt_min: int = MAX_DT_MIN,
                   min_overlap: float = MIN_OVERLAP) -> np.ndarray:
    """Etapa 2: True nas linhas que são duplicatas a remover (na ordem das linhas de `df`)."""
    minute = df["minute"].to_numpy(int) if "minute" in df else minute_of_day(df["hhmm"])
    drop = np.zeros(len(df), dtype=bool)
    for idx in df.groupby(["platform", "date"], sort=False).indices.values():
        if len(idx) > 1:
            drop[idx] = _group_duplicates(df.iloc[idx], minute[idx], max_dt_min, min_overlap)
    return drop
