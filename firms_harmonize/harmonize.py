"""Harmonização MODIS ↔ VIIRS em "unidades S-NPP VIIRS 375 m".

Método (ver dossiê, seção 6):
  * fator k = Σ referência / Σ origem, por unidade espacial e mês do calendário,
    calculado no período em que as duas plataformas observam juntas;
  * hierarquia de recuo: célula 1° → bloco 4° → Brasil inteiro (por mês do ano) → Brasil (geral),
    usando a escala mais fina que tenha contagem suficiente;
  * encadeamento: Terra→Aqua→SNPP para nov/2000–jul/2002; Aqua→SNPP até jan/2012;
    SNPP observado de fev/2012 a out/2026; NOAA-20→SNPP depois (NOAA-21 se faltar NOAA-20).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import CALIBRATION, PLATFORM_PERIODS, REFERENCE

DEFAULT_LEVELS = (1.0, 4.0, None)  # graus; None = Brasil inteiro


def months(start: str, end: str | None, last: str) -> pd.PeriodIndex:
    return pd.period_range(start, end or last, freq="M")


def available(platform: str, last: str) -> set[str]:
    s, e = PLATFORM_PERIODS[platform]
    return {str(p) for p in months(s, e, last)}


@dataclass
class FactorTable:
    src: str
    ref: str
    window: tuple[str, str]
    res: float
    levels: tuple
    min_count: int
    table: pd.DataFrame = field(repr=False)  # level, uy, ux, month, k, n_src, n_ref

    def lookup(self, cy: np.ndarray, cx: np.ndarray, month: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Fator para cada (célula, mês do calendário), escolhendo a escala mais fina disponível."""
        k = np.full(len(cy), np.nan)
        level_used = np.full(len(cy), "", dtype=object)
        lat, lon = (np.asarray(cy) + 0.5) * self.res, (np.asarray(cx) + 0.5) * self.res
        for lvl in self.levels:
            todo = np.isnan(k)
            if not todo.any():
                break
            t = self.table[self.table.level == _lvl_name(lvl)]
            if lvl is None:
                key = pd.MultiIndex.from_arrays([np.zeros(todo.sum(), int), np.zeros(todo.sum(), int), month[todo]])
            else:
                key = pd.MultiIndex.from_arrays([np.floor(lat[todo] / lvl).astype(int),
                                                 np.floor(lon[todo] / lvl).astype(int), month[todo]])
            s = t.set_index(["uy", "ux", "month"])["k"]
            vals = s.reindex(key).to_numpy()
            idx = np.flatnonzero(todo)
            ok = ~np.isnan(vals)
            k[idx[ok]] = vals[ok]
            level_used[idx[ok]] = _lvl_name(lvl)
        # último recurso: fator nacional único (sem separar por mês)
        if np.isnan(k).any():
            g = self.table[self.table.level == "brasil_geral"]["k"]
            if len(g):
                level_used[np.isnan(k)] = "brasil_geral"
                k[np.isnan(k)] = g.iloc[0]
        return k, level_used


def _lvl_name(lvl) -> str:
    return "brasil_mes" if lvl is None else f"{lvl:g}deg"


def _wide(counts: pd.DataFrame, platforms: list[str]) -> pd.DataFrame:
    w = (counts[counts.platform.isin(platforms)]
         .pivot_table(index=["ym", "cy", "cx"], columns="platform", values="n",
                      aggfunc="sum", fill_value=0)
         .reindex(columns=platforms, fill_value=0)
         .reset_index())
    return w


def calibrate(counts: pd.DataFrame, src: str, ref: str, window: tuple[str, str] | None = None,
              res: float = 0.25, levels=DEFAULT_LEVELS, min_count: int = 30) -> FactorTable:
    """Calcula k = Σref/Σsrc por unidade espacial e mês do calendário, dentro da janela.

    Só entram meses em que AS DUAS plataformas estavam operando (zeros contam: mês sem fogo
    é informação). Uma unidade só recebe fator se Σsrc >= min_count.
    """
    window = window or CALIBRATION[(src, ref)]
    last = counts.ym.max()
    both = (available(src, last) & available(ref, last)
            & {str(p) for p in months(window[0], window[1], last)})
    w = _wide(counts, [src, ref])
    w = w[w.ym.isin(both)]
    lat, lon = (w.cy + 0.5) * res, (w.cx + 0.5) * res
    w = w.assign(month=w.ym.str[5:7].astype(int))

    rows = []
    for lvl in levels:
        if lvl is None:
            uy = ux = np.zeros(len(w), int)
        else:
            uy, ux = np.floor(lat / lvl).astype(int), np.floor(lon / lvl).astype(int)
        g = (w.assign(uy=uy, ux=ux).groupby(["uy", "ux", "month"])[[src, ref]].sum().reset_index())
        g = g[g[src] >= min_count]
        rows.append(pd.DataFrame({"level": _lvl_name(lvl), "uy": g.uy, "ux": g.ux, "month": g.month,
                                  "k": g[ref] / g[src], "n_src": g[src], "n_ref": g[ref]}))
    tot_s, tot_r = w[src].sum(), w[ref].sum()
    if tot_s > 0:
        rows.append(pd.DataFrame({"level": ["brasil_geral"], "uy": [0], "ux": [0], "month": [0],
                                  "k": [tot_r / tot_s], "n_src": [tot_s], "n_ref": [tot_r]}))
    table = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["level", "uy", "ux", "month", "k", "n_src", "n_ref"])
    return FactorTable(src, ref, tuple(window), res, tuple(levels), min_count, table)


def convert(counts: pd.DataFrame, platform: str, ft: FactorTable) -> pd.DataFrame:
    """Converte as contagens de `platform` para unidades de `ft.ref`."""
    c = counts[counts.platform == platform]
    k, lvl = ft.lookup(c.cy.to_numpy(), c.cx.to_numpy(), c.ym.str[5:7].astype(int).to_numpy())
    return c.assign(value=c.n * k, k=k, factor_level=lvl)


def build_series(counts: pd.DataFrame, res: float = 0.25, levels=DEFAULT_LEVELS,
                 min_count: int = 30) -> tuple[pd.DataFrame, dict[str, FactorTable]]:
    """Série harmonizada por célula × mês, em unidades da plataforma de referência (SNPP).

    Retorna colunas: ym, cy, cx, value, origin (plataforma usada), k, factor_level.
    """
    last = counts.ym.max()
    kw = dict(res=res, levels=levels, min_count=min_count)
    f = {
        "Aqua": calibrate(counts, "Aqua", REFERENCE, **kw),
        "Terra_Aqua": calibrate(counts, "Terra", "Aqua", **kw),
        "NOAA20": calibrate(counts, "NOAA20", REFERENCE, **kw),
        "NOAA21": calibrate(counts, "NOAA21", REFERENCE, **kw),
    }

    # Ordem de preferência para cada mês: SNPP observado > NOAA20 > NOAA21 > Aqua > Terra.
    plan = []
    taken: set[str] = set()
    for plat in [REFERENCE, "NOAA20", "NOAA21", "Aqua", "Terra"]:
        ms = available(plat, last) - taken
        if ms:
            plan.append((plat, ms))
            taken |= ms

    parts = []
    for plat, ms in plan:
        c = counts[(counts.platform == plat) & counts.ym.isin(ms)]
        if c.empty:
            continue
        if plat == REFERENCE:
            part = c.assign(value=c.n.astype(float), k=1.0, factor_level="observado")
        elif plat == "Terra":
            a = convert(c, "Terra", f["Terra_Aqua"])            # Terra → Aqua
            k2, l2 = f["Aqua"].lookup(a.cy.to_numpy(), a.cx.to_numpy(),
                                      a.ym.str[5:7].astype(int).to_numpy())  # Aqua → SNPP
            part = a.assign(value=a.value * k2, k=a.k * k2,
                            factor_level=a.factor_level + ">" + l2)
        else:
            part = convert(c, plat, f[plat])
        parts.append(part.assign(origin=plat))
    series = pd.concat(parts, ignore_index=True)[["ym", "cy", "cx", "value", "origin", "k", "factor_level"]]
    return series, f


def validate(counts: pd.DataFrame, src: str = "Aqua", ref: str = REFERENCE,
             train: tuple[str, str] = ("2012-02", "2016-12"),
             test: tuple[str, str] = ("2017-01", "2021-12"),
             res: float = 0.25, levels=DEFAULT_LEVELS, min_count: int = 30,
             block: float = 2.0) -> dict:
    """Calibra no período `train` e testa no `test`, contra a série observada de `ref`.

    Compara três estimativas da contagem de `ref`: sem correção (k=1), fator nacional único
    e o fator hierárquico regional/mensal. Métricas no total nacional mensal e por bloco de
    `block` graus × mês.
    """
    last = counts.ym.max()
    ft = calibrate(counts, src, ref, window=train, res=res, levels=levels, min_count=min_count)
    test_ms = ({str(p) for p in months(test[0], test[1], last)}
               & available(src, last) & available(ref, last))
    w = _wide(counts, [src, ref])
    w = w[w.ym.isin(test_ms)].copy()
    if w.empty:
        return {"erro": "sem meses de teste com as duas plataformas"}
    k, _ = ft.lookup(w.cy.to_numpy(), w.cx.to_numpy(), w.ym.str[5:7].astype(int).to_numpy())
    k_nat = ft.table.loc[ft.table.level == "brasil_geral", "k"].iloc[0]
    w["pred_raw"], w["pred_nat"], w["pred_hier"] = w[src], w[src] * k_nat, w[src] * k

    def metrics(df, by):
        g = df.groupby(by)[[ref, "pred_raw", "pred_nat", "pred_hier"]].sum()
        out = {}
        for col in ["pred_raw", "pred_nat", "pred_hier"]:
            obs, pred = g[ref].to_numpy(float), g[col].to_numpy(float)
            m = obs > 0
            out[col] = {
                "r": float(np.corrcoef(obs, pred)[0, 1]) if len(obs) > 2 and pred.std() > 0 else None,
                "mape_pct": float(np.mean(np.abs(pred[m] - obs[m]) / obs[m]) * 100) if m.any() else None,
                "vies_pct": float((pred.sum() / obs.sum() - 1) * 100) if obs.sum() else None,
                "n": int(len(obs)),
            }
        return out

    w["by"] = np.floor((w.cy + 0.5) * res / block).astype(int)
    w["bx"] = np.floor((w.cx + 0.5) * res / block).astype(int)
    return {
        "par": f"{src}->{ref}", "treino": train, "teste": test,
        "fator_nacional_treino": float(k_nat),
        "brasil_mensal": metrics(w, "ym"),
        f"bloco_{block:g}deg_mensal": metrics(w, ["by", "bx", "ym"]),
        "legenda": {"pred_raw": "sem correção (k=1)", "pred_nat": "fator nacional único",
                    "pred_hier": "fator hierárquico região × mês do ano"},
    }
