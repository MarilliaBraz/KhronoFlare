"""Gera web/data.json com os focos de incêndio das últimas 24 h no Brasil, direto do NASA FIRMS.

Baixa os arquivos públicos do FIRMS (sem chave) da América do Sul, 24 h, de três sensores:
VIIRS NOAA-20, VIIRS NOAA-21 e MODIS (Terra/Aqua). Cada foco ganha estado e município pela malha
municipal do IBGE; cada município com fogo vira um candidato a alerta, como no build_data.py.

O campo `meta` guarda a prova de origem que o painel mostra: quando o arquivo foi gerado, o endereço
de cada fonte, o horário em que a NASA atualizou cada arquivo (Last-Modified), quantas linhas vieram
e quantas caíram no Brasil, e a passagem de satélite mais recente.

    python3 web/tools/build_live.py web/data.json [--cache <pasta das malhas do IBGE>]

Os contornos dos estados vêm de web/data-sample.json (a amostra de 12/11, mantida como reserva).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
SOURCES = [  # (sensor, satélite como o painel mostra, código do satélite no CSV ou None, caminho no FIRMS)
    ("VIIRS", "NOAA-20", "N20", "noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_24h.csv"),
    ("VIIRS", "NOAA-21", "N21", "noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_24h.csv"),
    ("MODIS", "Terra/Aqua", None, "modis-c6.1/csv/MODIS_C6_1_South_America_24h.csv"),
]
IBGE_MESH = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{code}"
             "?intrarregiao=municipio&formato=application/vnd.geo%2Bjson&qualidade=minima")
# Área do mapa: focos fora dela (resto da América do Sul) não entram.
LAT_RANGE, LON_RANGE = (-34.5, 6.0), (-75.0, -32.0)
HULL_PAD = 0.05            # graus em volta de cada foco para a área "em volta dos focos"
MAX_VERTICES = 80          # por anel, no contorno do município guardado no data.json
HIGH_MODIS = 80            # confiança MODIS a partir da qual o foco conta como alta confiança
RETRIES = 4
# Pontos vão como listas (sem repetir os nomes dos campos), na ordem abaixo; o app.js remonta os objetos.
POINT_FIELDS = ["lat", "lon", "frp", "conf", "sensor", "sat", "date", "time", "dn", "mun", "uf"]
REQUIRED = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "frp", "daynight"}


def fetch(url: str) -> tuple[bytes, str]:
    """Conteúdo e cabeçalho Last-Modified, com novas tentativas espaçadas."""
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hotspot-alert-console/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read(), r.headers.get("Last-Modified", "")
        except OSError as err:
            if attempt == RETRIES - 1:
                raise SystemExit(f"falhou depois de {RETRIES} tentativas: {url} ({err})") from err
            time.sleep(5 * (attempt + 1))
    raise AssertionError("inalcançável")


def http_date_to_iso(value: str) -> str:
    if not value:
        return ""
    return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc).isoformat()


# ---------- geometria ----------
def polygons(geometry: dict) -> list:
    return geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]


def inside(x: float, y: float, ring: list) -> bool:
    ins, j = False, len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def in_polys(x: float, y: float, polys: list) -> bool:
    return any(inside(x, y, p[0]) and not any(inside(x, y, h) for h in p[1:]) for p in polys)


def bbox(polys: list) -> tuple[float, float, float, float]:
    xs = [c[0] for p in polys for r in p for c in r]
    ys = [c[1] for p in polys for r in p for c in r]
    return min(xs), min(ys), max(xs), max(ys)


def simplify(polys: list) -> list:
    """Reduz cada anel a no máximo MAX_VERTICES pontos (com 3 casas) para o arquivo ficar leve."""
    out = []
    for poly in polys:
        rings = []
        for ring in poly:
            step = max(1, math.ceil(len(ring) / MAX_VERTICES))
            rings.append([[round(x, 3), round(y, 3)] for x, y in ring[::step]])
        out.append(rings)
    return out


def hull(points: list) -> list:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


def hull_area_km2(ring: list, lat0: float) -> float:
    a = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))
    return abs(a) / 2 * 111.32 * 111.32 * math.cos(math.radians(lat0))


# ---------- leitura ----------
def load_meshes(cache: Path | None, uf_codes: list[str]) -> dict:
    """{código IBGE: (bbox, polígonos)} de todos os municípios."""
    shapes = {}
    for code in uf_codes:
        local = cache / f"{code}.json" if cache else None
        if local and local.exists():
            raw = local.read_bytes()
        else:
            raw, _ = fetch(IBGE_MESH.format(code=code))
            if local:
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(raw)
        for feat in json.loads(raw)["features"]:
            polys = polygons(feat["geometry"])
            shapes[feat["properties"]["codarea"]] = (bbox(polys), polys)
    return shapes


def read_points() -> tuple[list, list]:
    points, meta = [], []
    for sensor, label, sat_code, path in SOURCES:
        url = f"{FIRMS}/{path}"
        body, modified = fetch(url)
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
        if rows and not REQUIRED <= set(rows[0]):
            raise SystemExit(f"formato inesperado em {url}: {list(rows[0])}")
        kept = []
        for r in rows:
            lat, lon = float(r["latitude"]), float(r["longitude"])
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                continue
            kept.append({"lat": round(lat, 4), "lon": round(lon, 4), "frp": round(float(r["frp"]), 1),
                         "conf": r["confidence"], "sensor": sensor, "sat": r["satellite"],
                         "date": r["acq_date"], "time": r["acq_time"].zfill(4), "dn": r["daynight"]})
        points.extend(kept)
        meta.append({"sensor": sensor, "satellite": label, "sat_code": sat_code, "url": url,
                     "updated": http_date_to_iso(modified), "rows": len(rows), "in_map": len(kept)})
    return points, meta


def assign(points: list, shapes: dict, uf_of_code: dict) -> None:
    for p in points:
        p["mun"] = p["uf"] = None
        for code, (bb, polys) in shapes.items():
            if bb[0] <= p["lon"] <= bb[2] and bb[1] <= p["lat"] <= bb[3] and in_polys(p["lon"], p["lat"], polys):
                p["mun"], p["uf"] = code, uf_of_code[code[:2]]
                break


def candidates(points: list, shapes: dict, names: dict) -> list:
    groups: dict[str, list] = {}
    for p in points:
        if p["mun"]:
            groups.setdefault(p["mun"], []).append(p)
    cands = []
    for code, ps in groups.items():
        corners = [(round(p["lon"] + dx, 3), round(p["lat"] + dy, 3))
                   for p in ps for dx in (-HULL_PAD, HULL_PAD) for dy in (-HULL_PAD, HULL_PAD)]
        ring = hull(corners)
        lat0 = sum(p["lat"] for p in ps) / len(ps)
        last = max(ps, key=lambda p: (p["date"], p["time"]))
        cands.append({
            "id": code, "name": names.get(code, code), "uf": ps[0]["uf"], "n": len(ps),
            "nV": sum(p["sensor"] == "VIIRS" for p in ps), "nM": sum(p["sensor"] == "MODIS" for p in ps),
            "frpSum": round(sum(p["frp"] for p in ps), 1), "frpMax": round(max(p["frp"] for p in ps), 1),
            "high": sum(p["conf"] == "h" or (p["conf"].isdigit() and int(p["conf"]) >= HIGH_MODIS) for p in ps),
            "last": last["time"], "lastDate": last["date"], "dn": sorted({p["dn"] for p in ps}),
            "poly": [list(c) for c in ring], "areaKm2": round(hull_area_km2(ring, lat0)),
            "geom": simplify(shapes[code][1]),
        })
    cands.sort(key=lambda c: -c["frpSum"])
    return cands


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--cache", type=Path, help="pasta para guardar e reaproveitar as malhas do IBGE")
    args = ap.parse_args()

    sample = json.loads((WEB / "data-sample.json").read_text(encoding="utf-8"))
    cities = json.loads((WEB / "cities.json").read_text(encoding="utf-8"))
    names = {c[0]: c[1] for c in cities["cities"]}
    uf_of_code = {c[0][:2]: c[2] for c in cities["cities"]}

    points, sources = read_points()
    shapes = load_meshes(args.cache, sorted(uf_of_code))
    assign(points, shapes, uf_of_code)
    for s in sources:
        s["in_brazil"] = sum(1 for p in points if p["uf"] and p["sensor"] == s["sensor"]
                             and (s["sat_code"] is None or p["sat"] == s["sat_code"]))
        del s["sat_code"]
    newest = max(points, key=lambda p: (p["date"], p["time"])) if points else None
    in_br = [p for p in points if p["uf"]]           # fora do Brasil não entra: não pode receber alerta
    data = {
        "point_fields": POINT_FIELDS,
        "points": [[p[f] for f in POINT_FIELDS] for p in in_br],
        "cands": candidates(in_br, shapes, names),
        "states": sample["states"],
        "meta": {
            "kind": "live",
            "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "window_hours": 24,
            "sources": sources,
            "latest_pass": f"{newest['date']}T{newest['time'][:2]}:{newest['time'][2:]}:00+00:00" if newest else "",
        },
    }
    args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{args.out}: {len(points)} focos na área do mapa, {len(in_br)} no Brasil, {len(data['cands'])} municípios, "
          f"{args.out.stat().st_size // 1024} KB")
    for s in sources:
        print(f"  {s['sensor']} {s['satellite']}: {s['rows']} linhas, {s['in_brazil']} no Brasil, "
              f"NASA atualizou {s['updated']}")


if __name__ == "__main__":
    main()
