"""Gera web/fallback-relief.jpg: fundo de relevo do Brasil guardado no projeto.

Fica por baixo das imagens do NASA GIBS no mapa; se o GIBS falhar na hora (sem internet ou
respondendo 503), o mapa continua com relevo em vez de fundo vazio. Monta os tiles Blue Marble
(relevo sombreado e batimetria) do nível de zoom ZOOM que cobrem a área do mapa.

    python3 web/tools/build_fallback.py web/fallback-relief.jpg

Imprime os limites (sul, oeste, norte, leste) que o app.js usa no L.imageOverlay.
"""
from __future__ import annotations

import io
import math
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

ZOOM = 5
TILE = 256
LAYER = ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/"
         "2004-08-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg")
# Área máxima do mapa no app.js (BRAZIL.pad(0.6)), arredondada para fora.
SOUTH, WEST, NORTH, EAST = -58.0, -99.5, 29.5, -8.0
RETRIES = 4


def tile_x(lon: float, z: int) -> int:
    return int((lon + 180) / 360 * 2 ** z)


def tile_y(lat: float, z: int) -> int:
    r = math.radians(lat)
    return int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * 2 ** z)


def tile_lon(x: int, z: int) -> float:
    return x / 2 ** z * 360 - 180


def tile_lat(y: int, z: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def fetch(url: str) -> Image.Image:
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGB")
        except OSError as err:
            if attempt == RETRIES - 1:
                raise RuntimeError(f"falhou depois de {RETRIES} tentativas: {url}") from err
            time.sleep(2 * (attempt + 1))
    raise AssertionError("inalcançável")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    x0, x1 = tile_x(WEST, ZOOM), tile_x(EAST, ZOOM)
    y0, y1 = tile_y(NORTH, ZOOM), tile_y(SOUTH, ZOOM)
    canvas = Image.new("RGB", ((x1 - x0 + 1) * TILE, (y1 - y0 + 1) * TILE))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            canvas.paste(fetch(LAYER.format(z=ZOOM, y=y, x=x)), ((x - x0) * TILE, (y - y0) * TILE))
    out = Path(sys.argv[1])
    canvas.save(out, "JPEG", quality=78, optimize=True, progressive=True)
    bounds = (tile_lat(y1 + 1, ZOOM), tile_lon(x0, ZOOM), tile_lat(y0, ZOOM), tile_lon(x1 + 1, ZOOM))
    print(f"{out}: {canvas.width}x{canvas.height}, {out.stat().st_size // 1024} KB")
    print("bounds [[sul, oeste], [norte, leste]] = [[%.4f, %.4f], [%.4f, %.4f]]" % bounds)


if __name__ == "__main__":
    main()
