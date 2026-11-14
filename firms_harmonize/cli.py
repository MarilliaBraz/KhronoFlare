"""Linha de comando do pipeline.

    python -m firms_harmonize status          # saldo da chave e datas SP/NRT de cada sensor
    python -m firms_harmonize boundary        # baixa o contorno do Brasil (API do IBGE)
    python -m firms_harmonize fetch-recent    # NRT depois do fim do SP, via Area API
    python -m firms_harmonize aggregate       # CSVs (arquivo + API) → contagens por célula/mês
    python -m firms_harmonize harmonize       # contagens → série harmonizada + calendário
    python -m firms_harmonize validate        # teste fora da amostra Aqua→SNPP
    python -m firms_harmonize all             # aggregate + harmonize + validate
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from . import aggregate as agg
from . import firecal as cal
from . import geo, harmonize
from .config import BOUNDARY, PROCESSED, RAW_API, RAW_ARCHIVE
from .reader import find_csvs

COUNTS = PROCESSED / "counts.parquet"


def _boundary(args):
    if args.no_clip:
        return None
    if not BOUNDARY.exists():
        print(f"AVISO: {BOUNDARY} não existe; rode `boundary` primeiro ou use --no-clip. "
              "Sem o recorte, focos de países vizinhos entram na contagem.")
        return None
    return geo.load_boundary(BOUNDARY)


def cmd_status(args):
    from .api import FirmsClient
    c = FirmsClient()
    print("Chave:", c.status())
    print(c.availability().to_string(index=False))


def cmd_boundary(args):
    print("Contorno salvo em", geo.fetch_boundary_ibge(BOUNDARY))


def cmd_fetch_recent(args):
    from .api import FirmsClient, nrt_after_sp
    files = nrt_after_sp(FirmsClient())
    print(f"{len(files)} arquivos em {RAW_API}")


def cmd_aggregate(args):
    paths = find_csvs(RAW_ARCHIVE) + ([] if args.archive_only else find_csvs(RAW_API))
    if not paths:
        raise SystemExit(f"Nenhum CSV em {RAW_ARCHIVE} ou {RAW_API}.")
    print(f"Agregando {len(paths)} arquivos (grade {args.res}°) ...")
    counts = agg.aggregate_files(paths, res=args.res, boundary=_boundary(args),
                                 min_conf=args.min_conf)
    counts = agg.resolve_processing(counts)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    counts.to_parquet(COUNTS, index=False)
    (PROCESSED / "counts_meta.json").write_text(json.dumps({"res": args.res, "min_conf": args.min_conf}))
    print(counts.groupby("platform").agg(meses=("ym", "nunique"), focos=("n", "sum"),
                                         inicio=("ym", "min"), fim=("ym", "max")))


def _load_counts():
    meta = json.loads((PROCESSED / "counts_meta.json").read_text())
    return pd.read_parquet(COUNTS), meta["res"]


def cmd_harmonize(args):
    counts, res = _load_counts()
    series, factors = harmonize.build_series(counts, res=res, min_count=args.min_count)
    series.to_parquet(PROCESSED / "harmonized_cells.parquet", index=False)
    pd.concat([ft.table.assign(par=f"{ft.src}->{ft.ref}", janela="/".join(ft.window))
               for ft in factors.values()]).to_csv(PROCESSED / "factors.csv", index=False)
    c = cal.calendar(series)
    c.to_csv(PROCESSED / "calendar_brasil.csv", index=False)
    cal.grid(c).to_csv(PROCESSED / "calendar_brasil_grid.csv")
    print(cal.grid(c).to_string())
    print("\nFatores nacionais:", {n: round(float(ft.table.loc[ft.table.level == "brasil_geral", "k"].iloc[0]), 3)
                                    for n, ft in factors.items()
                                    if (ft.table.level == "brasil_geral").any()})


def cmd_validate(args):
    counts, res = _load_counts()
    rep = harmonize.validate(counts, res=res, min_count=args.min_count)
    (PROCESSED / "validation.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(json.dumps(rep, indent=2, ensure_ascii=False))


def main(argv=None):
    p = argparse.ArgumentParser(prog="firms_harmonize")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ["status", "boundary", "fetch-recent", "aggregate", "harmonize", "validate", "all"]:
        sp = sub.add_parser(name)
        sp.add_argument("--res", type=float, default=0.25, help="lado da célula em graus")
        sp.add_argument("--min-conf", default="nominal", choices=["low", "nominal", "high"])
        sp.add_argument("--min-count", type=int, default=30,
                        help="focos mínimos da plataforma de origem para estimar um fator")
        sp.add_argument("--no-clip", action="store_true", help="não recortar pelo contorno do Brasil")
        sp.add_argument("--archive-only", action="store_true", help="ignorar o cache da API")
    a = p.parse_args(argv)
    run = {"status": cmd_status, "boundary": cmd_boundary, "fetch-recent": cmd_fetch_recent,
           "aggregate": cmd_aggregate, "harmonize": cmd_harmonize, "validate": cmd_validate}
    if a.cmd == "all":
        for f in (cmd_aggregate, cmd_harmonize, cmd_validate):
            f(a)
    else:
        run[a.cmd](a)
