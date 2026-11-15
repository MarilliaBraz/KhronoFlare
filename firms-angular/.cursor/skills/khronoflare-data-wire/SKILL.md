---
name: khronoflare-data-wire
description: >-
  Wires firms_harmonize processed outputs (parquet/CSV on the local PC) into the
  Khronoflare Angular app (public/data JSON, HotspotDataService, calendar, FRP,
  anomaly). Use when the user has data/processed ready, asks to connect
  harmonized data, calendar_brasil, frp_fused, or replace UI placeholders ("—",
  burn awaiting, synthetic timeline).
---

# Khronoflare — wire processed data

## Goal

Fill the **already wired** contracts under `public/data/` from local `firms_harmonize` outputs. Do **not** commit large parquet files. UI must keep working with empty stubs.

## Contracts (already in the app)

| File | Kind | Consumed by |
|---|---|---|
| `public/data/calendar.json` | `harmonized-calendar` | `HotspotDataService.calendar` → Layers month ramp |
| `public/data/harmonized_mun.json` | `harmonized-mun` | `HotspotDataService.harmonizedMun` → Alerts FRP/anomaly |
| Types | `HarmonizedCalendarPayload`, `HarmonizedMunPayload` | `src/app/core/models/hotspot.ts` |

Empty stubs ship with `rows: []` / `byId: {}` → UI shows awaiting / `—`.

## Before coding

1. Locate processed dir (typical `nasa-space-apps-2026/data/processed/`).
2. Confirm `calendar_brasil.csv` (and optionally `calendar_brasil_grid.csv`, `harmonized_cells.parquet`, `frp/frp_fused.parquet`).
3. Prefer `python firms-angular/tools/export_for_web.py --processed … --out firms-angular/public/data`.

## Source → export

### `calendar_brasil.csv`

Columns: `year`, `month`, `ym`, `value`, `origin`, `mediana`, `p10`, `p90`, `anomalia_pct`, `percentil`.

Export shape (`calendar.json`):

```json
{
  "kind": "harmonized-calendar",
  "generated": "ISO",
  "current_year": 2026,
  "current_month": 11,
  "rows": [{ "year": 2026, "month": 11, "ym": "2026-11", "value": 123, "anomalia_pct": 12.3 }],
  "grid": { "2026": { "1": 10, "2": 20 } }
}
```

### Municipal join → `harmonized_mun.json`

```json
{
  "kind": "harmonized-mun",
  "generated": "ISO",
  "byId": {
    "5208707": { "value": 1.2, "mediana": 1.0, "anomalia_pct": 20, "percentil": 80, "frpHarm": 45.2, "ym": "2026-11" }
  }
}
```

Use IBGE mun id matching `cands[].id`. Optional key `"*"` = national fallback.

## Steps when data arrives

1. Run `tools/export_for_web.py` (or extend it for mun join from parquet).
2. Verify `npm start`: chip “calendar.json loaded”; alerts show numbers when `byId` has the selected mun.
3. Do not require a backend; static files only.
4. Soft-fail if processed missing (stubs stay empty).

## Out of scope

- Re-running full FIRMS archive download unless asked.
- Re-adding world mask / Brazil spotlight basemap.
- Committing multi‑GB raw CSVs or parquet.

## Touch points

| Area | Path |
|---|---|
| Export | `tools/export_for_web.py` |
| Data load | `src/app/core/services/hotspot-data.service.ts` |
| Types | `src/app/core/models/hotspot.ts` |
| Burn / calendar UI | `src/app/features/explorer/*` |
| Alert harm slots | `src/app/features/alerts/alerts.page.*` |
| Static assets | `public/data/` |
| Pipeline docs | `../nasa-space-apps-2026/firms_harmonize/README.md` |
