const R = 6371;

export function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function circleAreaKm2(radiusKm: number): number {
  return Math.PI * radiusKm * radiusKm;
}

/** Compact MultiPolygon / Polygon rings as [lon, lat][][] or [lon, lat][][][] → Leaflet latlngs */
export function ringsToLatLngs(geom: number[][][] | number[][][][]): [number, number][][] {
  if (!geom?.length) return [];
  const first = geom[0];
  if (!first?.length) return [];
  // Polygon: [ring[]] where ring is [lon,lat][]
  if (typeof first[0][0] === 'number') {
    return (geom as number[][][]).map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number]));
  }
  // MultiPolygon
  return (geom as number[][][][]).flatMap((poly) =>
    poly.map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number])),
  );
}

/**
 * Estados no data.json: MultiPolygon [poligono[anel[[lon,lat]]]] (mesmo do web/app.js).
 * Retorna uma lista de polígonos Leaflet (cada um = anéis [lat,lon][]).
 */
export function statePolygonsToLatLngs(
  g: number[][][] | number[][][][],
): [number, number][][][] {
  if (!g?.length) return [];
  const first = g[0]?.[0];
  // Já é lista de anéis [[lon,lat],...]
  if (typeof first === 'number') {
    return [
      (g as unknown as number[][][]).map((ring) =>
        ring.map(([lon, lat]) => [lat, lon] as [number, number]),
      ),
    ];
  }
  return (g as number[][][][]).map((poly) =>
    poly.map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number])),
  );
}

export function ageColor(daysAgo: number): string {
  if (daysAgo <= 0) return '#fff1a8';
  if (daysAgo <= 2) return '#ffc53d';
  if (daysAgo <= 6) return '#ff7a1a';
  return '#c0292f';
}

export function sensorColor(sensor: string): string {
  return /viirs/i.test(sensor) ? '#ff7a1a' : '#ffd23f';
}

export function parseSearch(q: string): { lat: number; lon: number } | null {
  const m = q.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}
