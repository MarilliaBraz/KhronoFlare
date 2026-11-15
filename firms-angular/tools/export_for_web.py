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
import calendar as _cal
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# Campos comparativos que perdem sentido num mês com só parte dos dias.
PARTIAL_NULL_FIELDS = ("anomalia_pct", "percentil")


def mark_partial_month(rows: list[dict], data_end: date) -> list[dict]:
    """Marca o mês mais recente como parcial quando os dados acabam antes do fim dele.

    Um mês incompleto comparado com meses cheios gera anomalia falsa (ex.: −57 %),
    então anomalia e percentil viram None e a linha ganha partial=True.
    """
    if not rows:
        return rows
    last = max(rows, key=lambda r: (r["year"], r["month"]))
    last_day = _cal.monthrange(last["year"], last["month"])[1]
    if data_end >= date(last["year"], last["month"], last_day):
        return rows
    return [
        {**r, **{k: None for k in PARTIAL_NULL_FIELDS}, "partial": True} if r is last else r
        for r in rows
    ]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def export_calendar(processed: Path, out: Path, data_end: date) -> None:
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
    rows = mark_partial_month(rows, data_end)
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


def export_mun(processed: Path, malhas: Path, out: Path, data_end: date) -> None:
    """FRP harmonizado por município (mun_join); stub vazio se faltar entrada."""
    fused = processed / "frp" / "frp_fused.parquet"
    if not fused.exists() or not malhas.is_dir():
        print(f"AVISO: falta {fused} ou {malhas} — harmonized_mun.json vazio")
        write_json(
            out / "harmonized_mun.json",
            {"kind": "harmonized-mun", "generated": None, "byId": {}},
        )
        return
    from mun_join import build_payload  # mesmo diretório; shapely só é exigido aqui

    now = datetime.now(timezone.utc).isoformat()
    write_json(out / "harmonized_mun.json", build_payload(fused, malhas, data_end, now))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--data-end",
        type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help="último dia coberto pelos dados brutos (AAAA-MM-DD); padrão: hoje",
    )
    ap.add_argument(
        "--malhas",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "web" / "tools" / "ibge-malhas",
        help="pasta com as malhas municipais do IBGE por UF (<UF>.json)",
    )
    args = ap.parse_args()
    if not args.processed.exists():
        print(f"AVISO: {args.processed} não encontrado — stubs vazios")
    export_calendar(args.processed, args.out, args.data_end)
    export_mun(args.processed, args.malhas, args.out, args.data_end)


if __name__ == "__main__":
    main()
