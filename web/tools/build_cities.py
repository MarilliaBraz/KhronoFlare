"""Gera web/cities.json: sedes dos 5.571 códigos municipais do IBGE e os 27 estados com nome e região.

Fonte: tabelas públicas do repositório kelvins/municipios-brasileiros (códigos e coordenadas do IBGE):
  https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv
  https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/estados.csv

    python3 web/tools/build_cities.py <pasta com os dois CSV> web/cities.json [<pasta com malhas do IBGE>]

Com a pasta de malhas (um GeoJSON por estado, de
https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo_uf}?intrarregiao=municipio&formato=application/vnd.geo%2Bjson&qualidade=minima),
cada sede é conferida contra o contorno do próprio município. Sede a mais de MAX_OFF graus do
contorno é um erro da tabela de origem (ex.: Pau d'Arco, PA, estava a 6,7° do município) e passa a
usar o centroide do maior polígono do município. Desvios menores vêm do contorno simplificado.

Saída compacta (o painel carrega no navegador):
  states: [{uf, name, region, lat, lon}]          27 estados, região em inglês (North, Northeast...)
  cities: [[ibge_id, name, uf, lat, lon, capital]] uma linha por município, capital = 1 ou 0
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

MAX_OFF = 0.1  # graus; acima disso a sede da tabela está em outro lugar

REGIONS = {"Norte": "North", "Nordeste": "Northeast", "Centro-Oeste": "Central-West",
           "Sudeste": "Southeast", "Sul": "South"}
# Caixa do Brasil com folga: coordenada fora dela indica linha corrompida.
LAT_RANGE, LON_RANGE = (-34.0, 5.5), (-74.5, -28.5)
# 5.569 municípios + Brasília (DF) + Fernando de Noronha (distrito estadual de PE), códigos do IBGE.
EXPECTED_CITIES, EXPECTED_STATES = 5571, 27


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def coord(row: dict, key: str, bounds: tuple[float, float]) -> float:
    value = round(float(row[key]), 4)
    if not bounds[0] <= value <= bounds[1]:
        raise ValueError(f"{key} fora do Brasil em {row}")
    return value


def build(src: Path) -> dict:
    states_rows = read_csv(src / "estados.csv")
    uf_by_code = {r["codigo_uf"]: r["uf"] for r in states_rows}
    states = [{"uf": r["uf"], "name": r["nome"], "region": REGIONS[r["regiao"]],
               "lat": coord(r, "latitude", LAT_RANGE), "lon": coord(r, "longitude", LON_RANGE)}
              for r in states_rows]
    cities = [[r["codigo_ibge"], r["nome"], uf_by_code[r["codigo_uf"]],
               coord(r, "latitude", LAT_RANGE), coord(r, "longitude", LON_RANGE), int(r["capital"])]
              for r in read_csv(src / "municipios.csv")]
    if len(states) != EXPECTED_STATES or len(cities) != EXPECTED_CITIES:
        raise ValueError(f"esperava {EXPECTED_STATES} estados e {EXPECTED_CITIES} municípios, "
                         f"veio {len(states)} e {len(cities)}")
    capitals = sum(c[5] for c in cities)
    if capitals != EXPECTED_STATES:
        raise ValueError(f"esperava {EXPECTED_STATES} capitais, veio {capitals}")
    states.sort(key=lambda s: s["uf"])
    cities.sort(key=lambda c: (c[2], c[1]))
    return {"states": states, "cities": cities}


def _polygons(geometry: dict) -> list:
    return geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]


def _inside(x: float, y: float, ring: list) -> bool:
    inside, j = False, len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _centroid(ring: list) -> tuple[float, float]:
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a, cx, cy = a + cross, cx + (x1 + x2) * cross, cy + (y1 + y2) * cross
    return cx / (3 * a), cy / (3 * a)


def _area(ring: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def fix_seats(cities: list, meshes: Path) -> list[str]:
    """Troca a coordenada das sedes muito fora do próprio município pelo centroide dele."""
    shapes = {}
    for f in sorted(meshes.glob("*.json")):
        for feat in json.loads(f.read_text(encoding="utf-8"))["features"]:
            shapes[feat["properties"]["codarea"]] = _polygons(feat["geometry"])
    fixed = []
    for city in cities:
        polys = shapes.get(city[0])
        if not polys or any(_inside(city[4], city[3], p[0]) for p in polys):
            continue
        off = min(((city[4] - x) ** 2 + (city[3] - y) ** 2) ** 0.5 for p in polys for ring in p for x, y in ring)
        if off > MAX_OFF:
            lon, lat = _centroid(max((p[0] for p in polys), key=_area))
            fixed.append(f"{city[1]} ({city[2]}): {city[3]}, {city[4]} -> {lat:.4f}, {lon:.4f}")
            city[3], city[4] = round(lat, 4), round(lon, 4)
    return fixed


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]))
    if len(sys.argv) == 4:
        for line in fix_seats(data["cities"], Path(sys.argv[3])):
            print("corrigida:", line)
    out = Path(sys.argv[2])
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{out}: {len(data['states'])} estados, {len(data['cities'])} municípios, "
          f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
