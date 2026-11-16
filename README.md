# KhronoFlare

**NASA Space Apps Challenge 2026 — *Harmonization of MODIS and VIIRS Hot Spots***

KhronoFlare turns 26 years of NASA FIRMS active-fire detections over Brazil into one consistent record and puts it to work: a harmonized fire calendar, a next-month risk outlook and an alert console for civil-defense teams.

MODIS (Terra and Aqua, since 2000) and VIIRS (S-NPP, NOAA-20, NOAA-21, since 2012) see fire differently: VIIRS has a 375 m pixel and detects about 4–5× more hotspots than MODIS at 1 km. Comparing them directly makes every year after 2012 look worse than it was. KhronoFlare calibrates both sensors to a common reference so trends, anomalies and forecasts mean the same thing across the whole period.

## What is in this repository

| Path | Contents |
|---|---|
| [`firms_harmonize/`](firms_harmonize/) | Python pipeline: download, clean, harmonize, calibrate FRP, trend analysis and risk model |
| [`web/`](web/) | Static alert console and manager outlook (vanilla JS, Leaflet, NASA GIBS) — the deployed site |
| [`firms-angular/`](firms-angular/) | Angular version of the explorer, alert console, phone receiver and outlook |
| [`analises/`](analises/) | Analysis scripts, figures and results (trends, regression, critical-month model) |
| [`data/processed/`](data/processed/) | Harmonized outputs used by the dashboards (`frp_fused.parquet` via Git LFS) |
| [`tests/`](tests/) | Test suite (pytest) with small FIRMS fixtures |
| [`.github/workflows/firms-24h.yml`](.github/workflows/firms-24h.yml) | Refreshes the last-24 h hotspots and the outlook every 3 hours |
| `dossie-modis-viirs-hotspots.md`, `resumo-space-apps-2026.md` | Team research notes (Portuguese) |
| `comentarios-da-equipe/`, `ideias/` | Team reflections and ideas (Portuguese) |

## How it works

### 1. Hotspot-count harmonization
- Same filters for every sensor: nominal + high confidence, vegetation fires (`type = 0` when available), clipped to Brazil's border (IBGE).
- Standard Processing (SP) data first, Near Real-Time (NRT) only after SP ends.
- Reference sensor: **S-NPP VIIRS 375 m**, which crosses the equator at 13:30 like Aqua and overlaps it from 2012 on.
- Conversion factor `k = Σ reference / Σ source` per spatial unit and calendar month, with a hierarchical fallback (1° block → 4° block → Brazil by month → Brazil overall).
- Chaining: Terra → Aqua → S-NPP (2000–2002), Aqua → S-NPP (2002–2012, calibrated on 2012–2021, before Aqua's orbital drift), NOAA-20/21 → S-NPP after S-NPP.
- Out-of-sample validation of the Aqua → S-NPP factor (`python -m firms_harmonize validate`).

### 2. Fire Radiative Power (FRP) harmonization
Pixel-level pairing of Aqua MODIS and VIIRS detections: drop FRP ≤ 0, deduplicate overlapping scans, pair VIIRS pixels inside each MODIS footprint within 5 minutes, remove outliers (1.5 × IQR), then calibrate MODIS FRP against summed VIIRS FRP by view-zenith-angle band, with a separate night term. The main trend uses 2003–2021 because Aqua drifts after 2022.

### 3. Trend and fire calendar
Sen's slope, Mann-Kendall and Pettitt change-point tests on the harmonized annual series; a monthly calendar with historical median, p10/p90, anomaly and percentile for each month.

### 4. Critical-month risk model
A Random Forest on a 0.5° grid predicts whether next month's total FRP in a cell will exceed that cell's own 75th percentile (train 2004–2016, test 2017–2021). ROC-AUC ≈ 0.72 on both temporal and spatial hold-outs. Climate indices (ONI, TNA) were tested and kept as descriptive only, since they did not improve the model.

### 5. Dashboards
- **Alert console** (`web/index.html`): municipalities ranked by active hotspots, alert drafting with checks, four-eyes approval, CAP export and a simulated phone alert through [ntfy.sh](https://ntfy.sh). English by default, Portuguese on demand, high-contrast and font-size controls.
- **Manager outlook** (`web/forecast.html`): next-month risk class for each 0.5° cell and municipality from the 2004–2021 climatology, raised by current active fires and by the Random Forest probability.

## Quick start

Requires Python 3.12 (and Node.js for the Angular app).

```bash
git clone https://github.com/MarilliaBraz/KhronoFlare.git
cd KhronoFlare
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

### Run the static dashboard

```bash
cd web
python -m http.server 8000   # open http://localhost:8000
```

### Run the Angular app

```bash
cd firms-angular
npm install
npm start                    # open http://localhost:4200
```

### Run the pipeline

Raw FIRMS archives exceed GitHub's 100 MB file limit and are not versioned. Request them at the [FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/) and unzip the CSVs into `data/raw/archive/`.

Some commands call the FIRMS API and need a free [MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key). Put it in a `.env` file at the repository root (already git-ignored):

```
FIRMS_MAP_KEY=your-key-here
```

```bash
.venv/bin/python -m firms_harmonize status         # key quota + SP/NRT dates per sensor
.venv/bin/python -m firms_harmonize boundary       # Brazil border (IBGE)
.venv/bin/python -m firms_harmonize fetch-recent   # NRT data after the end of SP
.venv/bin/python -m firms_harmonize all            # aggregate + harmonize + validate
.venv/bin/python -m firms_harmonize frp-prepare    # FRP: prepare → match → calibrate → fuse
.venv/bin/python -m firms_harmonize risk-forecast  # next-month critical-month probabilities
```

Run `python -m firms_harmonize --help` for every subcommand. See [`firms_harmonize/README.md`](firms_harmonize/README.md) for options and output files.

## Data sources

- **NASA FIRMS** — MODIS C6.1 (Terra, Aqua) and VIIRS C2 (S-NPP, NOAA-20, NOAA-21) active fires, archive and NRT.
- **NASA GIBS** — VIIRS true color, Blue Marble and Black Marble map layers.
- **IBGE** — state and municipality boundaries, biome map.
- **NOAA** — ONI and TNA climate indices (descriptive analysis only).
- City locations from [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros), checked against IBGE.

## Known limitations

- NRT products have no `type` field, so static sources (industry, gas flares) are not removed in NRT-only months.
- Terra and Aqua are drifting in orbit; Aqua calibration stops in 2021 for that reason.
- The count factor fixes scale, not detection: a cell where MODIS saw zero fires stays at zero.
- The risk model is weakest at predicting a worse-than-normal season and in the Cerrado biome; local rainfall (CHIRPS/ERA5) is the most promising next feature.
- ntfy.sh channels are public to anyone who knows the name; the phone alert is a simulation only.

## Use of AI

AI assistants (Claude Code, Cursor) helped write code, tests and documentation. The challenge choice, the solution idea and the method decisions are the team's.

## Team

[@MarilliaBraz](https://github.com/MarilliaBraz) · [@ERICASSOUSA](https://github.com/ERICASSOUSA) · [@jhenniferdepaula](https://github.com/jhenniferdepaula) · [@nilvarafaelcorrea-cmd](https://github.com/nilvarafaelcorrea-cmd) · [@prof-outro-planeta](https://github.com/prof-outro-planeta) · [@VictorinoMatias](https://github.com/VictorinoMatias)
