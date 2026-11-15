"""Painel célula × mês para o modelo de mês crítico (passo 1).

Cada linha é uma célula de `res` graus no mês t. As variáveis usam só dados até t; o alvo é o mês t+1:

  * histórico: focos e ΣFRP em t, t−1, t−2; focos no mesmo mês do ano anterior ao alvo (t−11);
    focos nos últimos 12 meses;
  * climatologia da célula para o mês do alvo (probabilidade de fogo e média de focos), calculada só
    com os anos de treino;
  * alvo `y_critico`: ΣFRP em t+1 acima do 75º percentil da célula naquele mês do ano (anos de treino)
    e maior que zero.

Nas linhas de treino a climatologia "deixa o próprio ano de fora" (média dos outros anos de treino
daquela célula e mês): incluí-lo seria pôr o rótulo dentro da variável, e o modelo aprenderia a confiar
demais nela, perdendo desempenho no teste (revisão de 15/11/2026). Nas demais linhas, a climatologia é a
de todos os anos de treino. O percentil 75 que define o alvo usa todos os anos de treino.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KEYS = ["cy", "cx"]
HISTORY = ["n_lag0", "n_lag1", "n_lag2", "frp_lag0", "frp_lag1", "frp_lag2", "n_mesmo_mes_ano_ant", "n_12m"]
CLIMATOLOGY = ["p_fogo", "n_med"]
SEASON = ["mes_sin", "mes_cos"]
FEATURES = [*HISTORY, *CLIMATOLOGY, "cy", "cx", *SEASON]
CRITICAL_PERCENTILE = 75
MONTHS_OF_HISTORY = 12


def aggregate_cells(fused: pd.DataFrame, res: float, start: str, end: str) -> pd.DataFrame:
    """Focos (n) e ΣFRP harmonizado (MW) por célula × mês, só no período [start, end]."""
    ym = fused["date"].dt.to_period("M")
    keep = (ym >= pd.Period(start, "M")) & (ym <= pd.Period(end, "M"))
    f = fused[keep]
    df = pd.DataFrame({"cy": np.floor(f["lat"].to_numpy() / res).astype(int),
                       "cx": np.floor(f["lon"].to_numpy() / res).astype(int),
                       "ym": ym[keep].to_numpy(), "frp": f["frp_harm"].to_numpy(float)})
    return df.groupby([*KEYS, "ym"]).agg(n=("frp", "size"), frp=("frp", "sum")).reset_index()


def complete_panel(agg: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Todas as células que tiveram fogo × todos os meses; mês sem foco vira n = 0 e frp = 0."""
    months = pd.DataFrame({"ym": pd.period_range(start, end, freq="M")})
    grid = agg[KEYS].drop_duplicates().merge(months, how="cross")
    panel = grid.merge(agg, on=[*KEYS, "ym"], how="left").fillna({"n": 0, "frp": 0.0})
    return panel.astype({"n": int}).sort_values([*KEYS, "ym"]).reset_index(drop=True)


def add_history(panel: pd.DataFrame) -> pd.DataFrame:
    """Variáveis de histórico (até t) e o alvo bruto (t+1). Tira linhas sem 12 meses de passado ou sem futuro."""
    p = panel.sort_values([*KEYS, "ym"]).reset_index(drop=True)
    g = p.groupby(KEYS, sort=False)
    cols = {}
    for lag in (0, 1, 2):
        cols[f"n_lag{lag}"] = g["n"].shift(lag)
        cols[f"frp_lag{lag}"] = g["frp"].shift(lag)
    cols["n_mesmo_mes_ano_ant"] = g["n"].shift(MONTHS_OF_HISTORY - 1)
    cols["n_12m"] = g["n"].rolling(MONTHS_OF_HISTORY, min_periods=MONTHS_OF_HISTORY).sum().reset_index(
        level=KEYS, drop=True)
    cols["alvo_n"] = g["n"].shift(-1)
    cols["alvo_frp"] = g["frp"].shift(-1)
    target_month = p["ym"] + 1
    out = p.assign(**cols, mes_alvo=target_month.dt.month, ano_alvo=target_month.dt.year)
    return out.dropna(subset=["n_mesmo_mes_ano_ant", "n_12m", "alvo_n"]).reset_index(drop=True)


def add_target(history: pd.DataFrame, train_years: tuple[int, int]) -> pd.DataFrame:
    """Climatologia e alvo `y_critico`, com percentis e médias só dos anos de treino."""
    group = [*KEYS, "mes_alvo"]
    in_train = history["ano_alvo"].between(*train_years)
    train = history[in_train].assign(fogo=lambda d: (d["alvo_n"] > 0).astype(float))
    g = train.groupby(group)
    sums = pd.DataFrame({"k": g.size(), "s_fogo": g["fogo"].sum(), "s_n": g["alvo_n"].sum(),
                         "frp_p75": g["alvo_frp"].quantile(CRITICAL_PERCENTILE / 100)})
    out = history.join(sums, on=group)
    # Célula × mês sem nenhum ano de treino: climatologia zero (nunca queimou naquele mês no treino).
    out = out.fillna({"k": 0, "s_fogo": 0.0, "s_n": 0.0, "frp_p75": 0.0})
    # Linhas de treino: tira o próprio ano das somas ("deixar um ano de fora").
    own = in_train.to_numpy()
    k = out["k"].to_numpy(float) - own
    s_fogo = out["s_fogo"].to_numpy() - own * (out["alvo_n"].to_numpy() > 0)
    s_n = out["s_n"].to_numpy() - own * out["alvo_n"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        out = out.assign(p_fogo=np.where(k > 0, s_fogo / k, 0.0), n_med=np.where(k > 0, s_n / k, 0.0))
    out = out.drop(columns=["k", "s_fogo", "s_n"])
    angle = 2 * np.pi * out["mes_alvo"] / 12
    return out.assign(
        mes_sin=np.sin(angle), mes_cos=np.cos(angle),
        y_critico=((out["alvo_frp"] > out["frp_p75"]) & (out["alvo_frp"] > 0)).astype(int))


def build_panel(fused: pd.DataFrame, res: float, period: tuple[str, str],
                train_years: tuple[int, int]) -> pd.DataFrame:
    """Do FRP fundido (um foco por linha) ao painel pronto para o modelo."""
    agg = aggregate_cells(fused, res, *period)
    return add_target(add_history(complete_panel(agg, *period)), train_years)
