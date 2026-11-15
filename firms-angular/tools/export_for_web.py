#!/usr/bin/env python3
"""Exporta saídas de firms_harmonize → firms-angular/public/data/*.json

Uso (a partir da raiz do monorepo ou de nasa-space-apps-2026):

  python firms-angular/tools/export_for_web.py \\
    --processed nasa-space-apps-2026/data/processed \\
    --out firms-angular/public/data

Se --processed não existir, escreve stubs vazios (UI continua em modo awaiting).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def export_calendar(processed: Path, out: Path) -> None:
    csv_path = processed / "calendar_brasil.csv"
    grid_path = processed / "calendar_brasil_grid.csv"
    now = datetime.now(timezone.utc).isoformat()
    if not csv_path.exists():
        write_json(
            out / "calendar.json",
            {
                "kind": "harmonized-calendar",
                "generated": None,
                "current_year": None,
                "current_month": None,
                "rows": [],
                "grid": {},
            },
        )
        return

    df = pd.read_csv(csv_path)
    rows = []
    for r in df.to_dict(orient="records"):
        rows.append(
            {
                "year": int(r["year"]),
                "month": int(r["month"]),
                "ym": str(r["ym"]),
                "value": float(r["value"]),
                "origin": r.get("origin"),
                "mediana": None if pd.isna(r.get("mediana")) else float(r["mediana"]),
                "p10": None if pd.isna(r.get("p10")) else float(r["p10"]),
                "p90": None if pd.isna(r.get("p90")) else float(r["p90"]),
                "anomalia_pct": None
                if pd.isna(r.get("anomalia_pct"))
                else float(r["anomalia_pct"]),
                "percentil": None if pd.isna(r.get("percentil")) else float(r["percentil"]),
            }
        )
    cur_year = max((x["year"] for x in rows), default=None)
    cur_month = None
    if cur_year is not None:
        cur_rows = [x for x in rows if x["year"] == cur_year]
        if cur_rows:
            cur_month = max(x["month"] for x in cur_rows)

    grid: dict = {}
    if grid_path.exists():
        g = pd.read_csv(grid_path, index_col=0)
        for year, row in g.iterrows():
            grid[str(int(year))] = {
                str(int(m)): (None if pd.isna(v) else float(v)) for m, v in row.items()
            }

    write_json(
        out / "calendar.json",
        {
            "kind": "harmonized-calendar",
            "generated": now,
            "current_year": cur_year,
            "current_month": cur_month,
            "rows": rows,
            "grid": grid,
        },
    )


def export_mun_stub(out: Path) -> None:
    """Placeholder: join célula→município fica a cargo do agente de dados."""
    write_json(
        out / "harmonized_mun.json",
        {"kind": "harmonized-mun", "generated": None, "byId": {}},
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if not args.processed.exists():
        print(f"AVISO: {args.processed} não encontrado — stubs vazios")
    export_calendar(args.processed, args.out)
    export_mun_stub(args.out)


if __name__ == "__main__":
    main()
