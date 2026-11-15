"""Linha de comando do pipeline.

    python -m firms_harmonize status          # saldo da chave e datas SP/NRT de cada sensor
    python -m firms_harmonize boundary        # baixa o contorno do Brasil (API do IBGE)
    python -m firms_harmonize fetch-recent    # NRT depois do fim do SP, via Area API
    python -m firms_harmonize aggregate       # CSVs (arquivo + API) → contagens por célula/mês
    python -m firms_harmonize harmonize       # contagens → série harmonizada + calendário
    python -m firms_harmonize validate        # teste fora da amostra Aqua→SNPP (--train/--test)
    python -m firms_harmonize all             # aggregate + harmonize + validate
    python -m firms_harmonize frp-prepare     # FRP: Aqua e S-NPP limpos (FRP ≤ 0, duplicatas) → data/processed/frp
    python -m firms_harmonize frp-match       # FRP: pares Aqua × S-NPP (pegada MODIS, Δt ≤ 5 min) → pairs.parquet
    python -m firms_harmonize frp-calibrate   # FRP: modelo ln V = a + b ln M + c VZA, validado fora da amostra
    python -m firms_harmonize frp-fuse        # FRP: fusão diária no pixel MODIS → frp_fused.parquet, frp_anual.csv
    python -m firms_harmonize risk-panel      # risco: painel célula 0,5° × mês com histórico e alvo de mês crítico
    python -m firms_harmonize risk-drivers    # risco: ONI (NOAA CPC) e bioma (IBGE) no painel
"""
from __future__ import annotations

import argparse
import json
import re

import pandas as pd

from . import aggregate as agg
from . import firecal as cal
from . import geo, harmonize
from .config import BOUNDARY, FRP_DIR, FRP_SOURCES, PROCESSED, RAW_API, RAW_ARCHIVE, ROOT
from .reader import find_csvs

COUNTS = PROCESSED / "counts.parquet"
JANELA = re.compile(r"\d{4}-(0[1-9]|1[0-2]):\d{4}-(0[1-9]|1[0-2])")


def _window(texto: str) -> tuple[str, str]:
    """'2012-02:2018-12' → ('2012-02', '2018-12'); rejeita formato inválido ou janela invertida."""
    if not JANELA.fullmatch(texto):
        raise argparse.ArgumentTypeError(f"janela inválida {texto!r}; use AAAA-MM:AAAA-MM")
    ini, fim = texto.split(":")
    if ini > fim:  # AAAA-MM com zeros à esquerda ordena como texto
        raise argparse.ArgumentTypeError(f"janela invertida: {texto!r}")
    return ini, fim


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
    rep = harmonize.validate(counts, train=args.train, test=args.test, res=res, min_count=args.min_count)
    (PROCESSED / "validation.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(json.dumps(rep, indent=2, ensure_ascii=False))


def _frp_csvs(pattern: str) -> list:
    """CSVs da FIRMS nas pastas DL_FIRE_* da raiz e em data/raw/archive."""
    found = set(ROOT.glob(f"DL_FIRE_*/{pattern}"))
    if RAW_ARCHIVE.exists():
        found |= set(RAW_ARCHIVE.rglob(pattern))
    return sorted(found)


def cmd_frp_prepare(args):
    from .frp.prepare import prepare_platform
    boundary = _boundary(args)
    FRP_DIR.mkdir(parents=True, exist_ok=True)
    reports = {}
    for platform, (pattern, start, end) in FRP_SOURCES.items():
        paths = _frp_csvs(pattern)
        if not paths:
            raise SystemExit(f"Nenhum CSV {pattern} encontrado para {platform}.")
        print(f"{platform}: {[p.name for p in paths]} ({start} a {end or 'fim'})", flush=True)
        df, reports[platform] = prepare_platform(paths, platform, start, end, boundary)
        df.to_parquet(FRP_DIR / f"{platform.lower()}.parquet", index=False)
        print(json.dumps(reports[platform], ensure_ascii=False), flush=True)
    (FRP_DIR / "prepare_report.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False))


def _print_pairs_by_vza(pairs):
    faixa = pd.cut(pairs["vza"], range(0, 71, 10), include_lowest=True)
    razao = pairs["frp_viirs"] / pairs["frp_modis"]
    limpos = ~pairs["outlier"]
    resumo = pd.DataFrame({
        "pares": pairs.groupby(faixa, observed=True).size(),
        "anomalos": pairs["outlier"].groupby(faixa, observed=True).sum(),
        "razao_mediana_antes": razao.groupby(faixa, observed=True).median(),
        "razao_mediana_depois": razao[limpos].groupby(faixa[limpos], observed=True).median(),
        "razao_min_mantida": razao[limpos].groupby(faixa[limpos], observed=True).min(),
        "razao_max_mantida": razao[limpos].groupby(faixa[limpos], observed=True).max(),
    })
    print(resumo.round(2).to_string())


def cmd_frp_match(args):
    from .frp.match import match_pairs, outlier_mask
    viirs = pd.read_parquet(FRP_DIR / "snpp.parquet")
    modis = pd.read_parquet(FRP_DIR / "aqua.parquet")
    modis = modis[modis["date"].between(viirs["date"].min(), viirs["date"].max())]
    pairs = match_pairs(modis, viirs)
    pairs = pairs.assign(outlier=outlier_mask(pairs))
    pairs.to_parquet(FRP_DIR / "pairs.parquet", index=False)
    print(f"Focos Aqua na janela: {len(modis):,} | pareados: {len(pairs):,} ({len(pairs) / len(modis):.1%})")
    print(f"Focos S-NPP: {len(viirs):,} | usados em pares: {int(pairs['n_viirs'].sum()):,}")
    print(f"Pares anômalos (IQR por faixa de VZA): {int(pairs['outlier'].sum()):,} ({pairs['outlier'].mean():.1%})")
    _print_pairs_by_vza(pairs)
    print(pairs.groupby(pairs["date"].dt.year).size().rename("pares_por_ano").to_string())


FRP_TRAIN, FRP_TEST = ("2012-02", "2018-12"), ("2019-01", "2021-12")


def cmd_frp_calibrate(args):
    from .frp.calibrate import Calibration, fit, is_night, validate
    from .frp.prepare import in_window
    pairs = pd.read_parquet(FRP_DIR / "pairs.parquet")
    rep = validate(pairs, train=FRP_TRAIN, test=FRP_TEST)
    clean = pairs[~pairs["outlier"]]
    final = fit(clean["frp_modis"], clean["vza"], clean["frp_viirs"], night=is_night(clean))  # todos os anos
    out = {"validacao": rep, "modelo_final": final.to_dict()}
    (FRP_DIR / "frp_calibration.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print("Treino", FRP_TRAIN, "pares:", rep["treino"]["pares"], "| modelo:", rep["treino"]["modelo"])
    print("Teste", FRP_TEST, "pares:", rep["teste"]["pares"])
    print(pd.DataFrame(rep["teste"]["modelos"]).T.round(3).to_string())
    print(f"\nTeste incluindo os anômalos ({rep['teste_com_anomalos']['pares']} pares):")
    print(pd.DataFrame(rep["teste_com_anomalos"]["modelos"]).T.round(3).to_string())
    print("\nViés da soma anual no teste (%):")
    print(pd.DataFrame(rep["teste"]["vies_soma_anual_pct"]).T.to_string())
    print("\nViés da soma dia (D) e noite (N) no teste (%):")
    print(pd.DataFrame(rep["teste"]["vies_soma_dia_noite_pct"]).T.to_string())

    te = clean[in_window(clean["date"], *FRP_TEST)]
    cal, k = Calibration.from_dict(rep["treino"]["modelo"]), rep["treino"]["fator_unico"]
    faixa = pd.cut(te["vza"], range(0, 71, 10), include_lowest=True)
    soma = lambda s: s.groupby(faixa, observed=True).sum()  # noqa: E731
    obs = soma(te["frp_viirs"])
    print("\nViés da soma por faixa de VZA no teste (%):")
    print(pd.DataFrame({
        "fator_unico": 100 * (soma(k * te["frp_modis"]) / obs - 1),
        "modelo_vza": 100 * (soma(pd.Series(cal.predict(te["frp_modis"], te["vza"], is_night(te)), index=te.index)) / obs - 1),
    }).round(1).to_string())
    print("\nModelo final (2012-02 a 2021-12):", final.to_dict())


def cmd_frp_fuse(args):
    from .frp.calibrate import Calibration
    from .frp.fuse import annual_totals, fuse
    cal = Calibration.from_dict(json.loads((FRP_DIR / "frp_calibration.json").read_text())["modelo_final"])
    fused = fuse(pd.read_parquet(FRP_DIR / "aqua.parquet"), pd.read_parquet(FRP_DIR / "pairs.parquet"), cal)
    fused.to_parquet(FRP_DIR / "frp_fused.parquet", index=False)
    totals = annual_totals(fused)
    totals.to_csv(FRP_DIR / "frp_anual.csv", index=False)
    print(f"Focos Aqua fundidos: {len(fused):,} | fonte: {fused['fonte'].value_counts().to_dict()}")
    show = totals.assign(frp_modis_total_GW=totals["frp_modis_total"] / 1e3,
                         frp_harm_total_GW=totals["frp_harm_total"] / 1e3,
                         razao=totals["frp_harm_total"] / totals["frp_modis_total"])
    print(show[["ano", "focos", "frp_modis_total_GW", "frp_harm_total_GW", "razao",
                "frp_harm_mediana", "frac_viirs"]].round(3).to_string(index=False))


def cmd_risk_panel(args):
    from .config import RISK_DIR, RISK_PERIOD, RISK_RES, RISK_TEST_YEARS, RISK_TRAIN_YEARS
    from .risk.panel import build_panel
    fused = pd.read_parquet(FRP_DIR / "frp_fused.parquet", columns=["date", "lat", "lon", "frp_harm"])
    panel = build_panel(fused, RISK_RES, RISK_PERIOD, RISK_TRAIN_YEARS)
    RISK_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(RISK_DIR / "panel.parquet", index=False)
    cells = panel[["cy", "cx"]].drop_duplicates()
    print(f"Células de {RISK_RES}°: {len(cells):,} | linhas: {len(panel):,} | "
          f"meses-alvo {panel['ano_alvo'].min()}–{panel['ano_alvo'].max()}")
    for nome, anos in [("treino", RISK_TRAIN_YEARS), ("teste", RISK_TEST_YEARS)]:
        sel = panel["ano_alvo"].between(*anos)
        print(f"  {nome} {anos}: {sel.sum():,} linhas | mês crítico {panel.loc[sel, 'y_critico'].mean():.1%} "
              f"| com fogo {(panel.loc[sel, 'alvo_n'] > 0).mean():.1%}")
    por_ano = panel.groupby("ano_alvo")["y_critico"].mean().mul(100).round(1)
    print("  % de meses críticos por ano:", por_ano.to_dict())
    por_mes = panel.groupby("mes_alvo")["y_critico"].mean().mul(100).round(1)
    print("  % de meses críticos por mês do ano:", por_mes.to_dict())


def cmd_risk_drivers(args):
    from .config import BIOMES_FILE, ONI_FILE, RISK_DIR, RISK_RES
    from .risk.drivers import (BIOME_CODES, add_biome, add_oni, assign_biome, fetch_biomes, fetch_oni,
                               read_biomes, read_oni)
    if not ONI_FILE.exists():
        print("Baixando o ONI da NOAA CPC ...", flush=True)
        fetch_oni(ONI_FILE)
    if not BIOMES_FILE.exists():
        print("Baixando os biomas do IBGE (geoftp) ...", flush=True)
        fetch_biomes(BIOMES_FILE)
    oni, biomes = read_oni(ONI_FILE), read_biomes(BIOMES_FILE)
    print(f"ONI: {oni['ym_fim'].min()} a {oni['ym_fim'].max()} ({len(oni)} trimestres) em {ONI_FILE}")
    panel = pd.read_parquet(RISK_DIR / "panel.parquet")
    panel = panel.drop(columns=[c for c in panel.columns if c.startswith("bioma")])  # idempotente
    panel = add_biome(add_oni(panel, oni), biomes, RISK_RES)
    panel.to_parquet(RISK_DIR / "panel.parquet", index=False)
    cells = assign_biome(panel[["cy", "cx"]].drop_duplicates(), biomes, RISK_RES)
    print(f"Biomas: {len(cells):,} células; {int(cells['bioma_por_proximidade'].sum())} pelo bioma mais "
          "próximo (centro fora dos polígonos)")
    por_bioma = pd.DataFrame({
        "celulas": cells.groupby("bioma").size(),
        "mes_critico_pct": (100 * panel.groupby("bioma")["y_critico"].mean()).round(1),
        "com_fogo_pct": (100 * panel["alvo_n"].gt(0).groupby(panel["bioma"]).mean()).round(1),
    })
    print(por_bioma.rename(index=BIOME_CODES).to_string())
    fase = pd.cut(panel["oni_atual"], [-9, -0.5, 0.5, 9], labels=["La Niña", "neutro", "El Niño"])
    resumo = panel.groupby(fase, observed=True).agg(linhas=("y_critico", "size"),
                                                    mes_critico_pct=("y_critico", "mean"))
    resumo["mes_critico_pct"] = (100 * resumo["mes_critico_pct"]).round(1)
    print("Mês crítico por fase do ONI no mês t (todos os anos, descritivo):")
    print(resumo.to_string())


def main(argv=None):
    p = argparse.ArgumentParser(prog="firms_harmonize")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ["status", "boundary", "fetch-recent", "aggregate", "harmonize", "validate", "all",
                 "frp-prepare", "frp-match", "frp-calibrate", "frp-fuse", "risk-panel", "risk-drivers"]:
        sp = sub.add_parser(name)
        sp.add_argument("--res", type=float, default=0.25, help="lado da célula em graus")
        sp.add_argument("--min-conf", default="nominal", choices=["low", "nominal", "high"])
        sp.add_argument("--min-count", type=int, default=30,
                        help="focos mínimos da plataforma de origem para estimar um fator")
        sp.add_argument("--no-clip", action="store_true", help="não recortar pelo contorno do Brasil")
        sp.add_argument("--archive-only", action="store_true", help="ignorar o cache da API")
        if name in ("validate", "all"):
            sp.add_argument("--train", type=_window, default=("2012-02", "2018-12"),
                            help="janela de calibração AAAA-MM:AAAA-MM")
            sp.add_argument("--test", type=_window, default=("2019-01", "2025-12"),
                            help="janela de teste AAAA-MM:AAAA-MM (anos não vistos na calibração)")
    a = p.parse_args(argv)
    if hasattr(a, "train") and a.train[1] >= a.test[0]:
        p.error("--train precisa terminar antes do início de --test (senão o teste não é fora da amostra)")
    run = {"status": cmd_status, "boundary": cmd_boundary, "fetch-recent": cmd_fetch_recent,
           "aggregate": cmd_aggregate, "harmonize": cmd_harmonize, "validate": cmd_validate,
           "frp-prepare": cmd_frp_prepare, "frp-match": cmd_frp_match,
           "frp-calibrate": cmd_frp_calibrate, "frp-fuse": cmd_frp_fuse,
           "risk-panel": cmd_risk_panel, "risk-drivers": cmd_risk_drivers}
    if a.cmd == "all":
        for f in (cmd_aggregate, cmd_harmonize, cmd_validate):
            f(a)
    else:
        run[a.cmd](a)
