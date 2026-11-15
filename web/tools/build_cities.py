"""Gera web/cities.json: sedes dos 5.571 códigos municipais do IBGE e os 27 estados com nome e região.

Fonte: tabelas públicas do repositório kelvins/municipios-brasileiros (códigos e coordenadas do IBGE):
  https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv
  https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/estados.csv

    python3 web/tools/build_cities.py <pasta com os dois CSV> web/cities.json

Saída compacta (o painel carrega no navegador):
  states: [{uf, name, region, lat, lon}]          27 estados, região em inglês (North, Northeast...)
  cities: [[ibge_id, name, uf, lat, lon, capital]] uma linha por município, capital = 1 ou 0
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

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


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]))
    out = Path(sys.argv[2])
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{out}: {len(data['states'])} estados, {len(data['cities'])} municípios, "
          f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
