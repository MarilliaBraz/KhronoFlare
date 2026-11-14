"""Geometria do pixel MODIS: ângulo de visada (VZA) a partir de `scan` e sobreposição de pegadas.

Os CSVs da FIRMS não trazem a VZA, mas trazem `scan` e `track`, o tamanho do pixel em km, que
crescem de forma conhecida com o ângulo de varredura θ (Ichoku & Kaufman 2005, IEEE TGRS 43(11)):

    scan(θ)  = R·s·( cosθ / √((R/r)² − sin²θ) − 1 )
    track(θ) = r·s·( cosθ − √((R/r)² − sin²θ) )
    sin(VZA) = (r/R)·sinθ

com R = raio da Terra, h = altitude do Aqua, r = R + h e s = 1 km / h (resolução angular no nadir).
Invertendo scan(θ) por interpolação obtemos a VZA de cada foco.

A pegada é aproximada por um retângulo `scan` (leste-oeste) × `track` (norte-sul) numa projeção
local equiretangular. A órbita real é inclinada ~8–12° em relação ao meridiano: limitação declarada.
"""
from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0
AQUA_ALTITUDE_KM = 705.0
MODIS_MAX_SCAN_ANGLE_DEG = 55.0
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQUATOR = 111.32

_R = EARTH_RADIUS_KM
_r = EARTH_RADIUS_KM + AQUA_ALTITUDE_KM
_s = 1.0 / AQUA_ALTITUDE_KM


def modis_pixel_size(scan_angle_deg):
    """Tamanho (scan, track) em km de um pixel MODIS de 1 km no nadir, dado o ângulo de varredura."""
    theta = np.radians(scan_angle_deg)
    root = np.sqrt((_R / _r) ** 2 - np.sin(theta) ** 2)
    scan = _R * _s * (np.cos(theta) / root - 1.0)
    track = _r * _s * (np.cos(theta) - root)
    return scan, track


def _vza_deg(scan_angle_deg):
    return np.degrees(np.arcsin(np.clip((_r / _R) * np.sin(np.radians(scan_angle_deg)), -1.0, 1.0)))


_THETA_TABLE = np.linspace(0.0, MODIS_MAX_SCAN_ANGLE_DEG, 2201)
_SCAN_TABLE = modis_pixel_size(_THETA_TABLE)[0]
_VZA_TABLE = _vza_deg(_THETA_TABLE)


def modis_vza_from_scan(scan_km) -> np.ndarray:
    """VZA em graus a partir do `scan` (km) do CSV. Fora de [1 km, máximo] fica no limite; NaN fica NaN."""
    scan = np.asarray(scan_km, dtype=float)
    vza = np.interp(scan, _SCAN_TABLE, _VZA_TABLE)  # np.interp já prende nos extremos da tabela
    return np.where(np.isnan(scan), np.nan, vza)


def offsets_km(lat1, lon1, lat2, lon2):
    """Deslocamento (leste, norte) em km do ponto 2 em relação ao ponto 1 (projeção local)."""
    lat1, lon1, lat2, lon2 = (np.asarray(v, dtype=float) for v in (lat1, lon1, lat2, lon2))
    coslat = np.cos(np.radians((lat1 + lat2) / 2.0))
    return (lon2 - lon1) * KM_PER_DEG_LON_EQUATOR * coslat, (lat2 - lat1) * KM_PER_DEG_LAT


def overlap_fraction(lat1, lon1, scan1, track1, lat2, lon2, scan2, track2):
    """Área da interseção das duas pegadas dividida pela área da menor (0 a 1)."""
    dx, dy = offsets_km(lat1, lon1, lat2, lon2)
    scan1, track1, scan2, track2 = (np.asarray(v, dtype=float) for v in (scan1, track1, scan2, track2))
    ix = np.clip((scan1 + scan2) / 2.0 - np.abs(dx), 0.0, np.minimum(scan1, scan2))
    iy = np.clip((track1 + track2) / 2.0 - np.abs(dy), 0.0, np.minimum(track1, track2))
    return ix * iy / np.minimum(scan1 * track1, scan2 * track2)
