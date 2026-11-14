import numpy as np
import pytest

from firms_harmonize.frp.pixel import (
    modis_pixel_size, modis_vza_from_scan, offsets_km, overlap_fraction,
)

# ---------- tamanho do pixel e ângulo de visada (Ichoku & Kaufman 2005) ----------

def test_pixel_is_1km_at_nadir_and_about_4p8_by_2km_at_swath_edge():
    scan0, track0 = modis_pixel_size(0.0)
    scan55, track55 = modis_pixel_size(55.0)        # ângulo máximo de varredura do MODIS
    assert scan0 == pytest.approx(1.0, abs=1e-6) and track0 == pytest.approx(1.0, abs=1e-6)
    assert scan55 == pytest.approx(4.8, abs=0.2)    # máximo de `scan` nos CSVs da FIRMS
    assert track55 == pytest.approx(2.0, abs=0.1)   # máximo de `track` nos CSVs da FIRMS


def test_vza_is_zero_at_nadir_and_about_65_degrees_at_swath_edge():
    vza = modis_vza_from_scan(np.array([1.0, 4.8]))
    assert vza[0] == pytest.approx(0.0, abs=1.0)
    assert 62.0 <= vza[1] <= 67.0


def test_vza_grows_with_scan_and_is_clipped_outside_valid_range():
    scans = np.array([0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 4.8, 9.0])
    vza = modis_vza_from_scan(scans)
    assert np.all(np.diff(vza) >= 0)
    assert vza[0] == pytest.approx(vza[1], abs=1e-6)  # abaixo de 1 km → nadir
    assert vza[-1] <= 67.0                           # acima do máximo → borda da faixa


def test_vza_returns_nan_for_missing_scan():
    assert np.isnan(modis_vza_from_scan(np.array([np.nan]))[0])

# ---------- deslocamento e sobreposição de pegadas ----------

def test_offsets_km_on_equator_and_at_20_degrees_south():
    dx, dy = offsets_km(0.0, 0.0, 0.0, 0.01)          # 0,01° de longitude no equador
    assert dx == pytest.approx(1.113, abs=0.01) and dy == pytest.approx(0.0)
    dx, dy = offsets_km(-20.0, 0.0, -20.01, 0.0)      # 0,01° de latitude
    assert dx == pytest.approx(0.0) and dy == pytest.approx(-1.106, abs=0.01)
    dx, _ = offsets_km(-20.0, 0.0, -20.0, 0.01)       # longitude encolhe com cos(lat)
    assert dx == pytest.approx(1.113 * np.cos(np.radians(20)), abs=0.01)


def _deg_lon(km, lat=0.0):
    return km / (111.32 * np.cos(np.radians(lat)))


def test_identical_pixels_overlap_fully():
    assert overlap_fraction(-10, -50, 1.0, 1.0, -10, -50, 1.0, 1.0) == pytest.approx(1.0)


def test_disjoint_pixels_do_not_overlap():
    assert overlap_fraction(0, 0, 1.0, 1.0, 0, _deg_lon(1.5), 1.0, 1.0) == pytest.approx(0.0)


def test_half_shifted_pixels_overlap_by_half():
    assert overlap_fraction(0, 0, 1.0, 1.0, 0, _deg_lon(0.5), 1.0, 1.0) == pytest.approx(0.5, abs=0.01)


def test_overlap_is_relative_to_the_smaller_pixel():
    # pixel pequeno (1 km) inteiro dentro de um grande (3 km) → 100 % do menor
    assert overlap_fraction(0, 0, 3.0, 3.0, 0, 0, 1.0, 1.0) == pytest.approx(1.0)


def test_overlap_is_vectorized():
    out = overlap_fraction(np.zeros(3), np.zeros(3), np.ones(3), np.ones(3),
                           np.zeros(3), _deg_lon(np.array([0.0, 0.5, 2.0])), np.ones(3), np.ones(3))
    assert out == pytest.approx([1.0, 0.5, 0.0], abs=0.01)
