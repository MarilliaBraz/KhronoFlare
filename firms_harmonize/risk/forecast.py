"""Previsão do mês seguinte com o Random Forest (passo 4 do painel do gestor).

O modelo foi treinado com o FRP harmonizado até 2021. Para prever hoje, as variáveis de histórico vêm
dos últimos 12 meses da mesma série, com duas correções:

  * deriva do Aqua: depois de 2021 o Aqua passa cada vez mais tarde e vê mais focos para o mesmo fogo
    (razão Aqua ÷ S-NPP de ~0,150 em 2012–2021 para 0,187 em 2026). Cada mês de 2022 em diante é
    multiplicado por `drift_factors`: a razão de referência dividida pela razão dos 12 meses até ele;
  * mês incompleto: o último mês da série termina antes do fim do mês; contagens e FRP dele são
    multiplicados por `partial_month_scale` (dias do mês ÷ dias com dado).

A climatologia de cada célula vem do painel de treino (todos os anos-alvo usados no ajuste final).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .panel import KEYS, MONTHS_OF_HISTORY, aggregate_cells


def drift_factors(aqua: pd.Series, snpp: pd.Series, ref: tuple[str, str], start: str,
                  window: int = 12) -> pd.Series:
    """Fator por mês (índice Period) que leva a contagem do Aqua de volta à relação de `ref` com o S-NPP."""
    idx = aqua.index.intersection(snpp.index).sort_values()
    a, s = aqua.reindex(idx).astype(float), snpp.reindex(idx).astype(float)
    in_ref = (idx >= pd.Period(ref[0], "M")) & (idx <= pd.Period(ref[1], "M"))
    ref_ratio = a[in_ref].sum() / s[in_ref].sum()
    rolling = a.rolling(window, min_periods=window).sum() / s.rolling(window, min_periods=window).sum()
    factors = pd.Series(1.0, index=idx)
    after = idx >= pd.Period(start, "M")
    factors[after] = (ref_ratio / rolling[after]).fillna(1.0)
    return factors


def partial_month_scale(last_day: pd.Timestamp) -> float:
    """Dias do mês ÷ dias com dado (1.0 se o mês está completo)."""
    return last_day.days_in_month / last_day.day


def prediction_features(fused: pd.DataFrame, res: float, last_month: str, last_scale: float,
                        factors: pd.Series, train_panel: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por célula do treino com as variáveis do mês t = `last_month` e o alvo t+1."""
    t = pd.Period(last_month, "M")
    months = pd.period_range(t - (MONTHS_OF_HISTORY - 1), t, freq="M")
    agg = aggregate_cells(fused, res, str(months[0]), str(t))
    scale = agg["ym"].map(lambda m: factors.get(m, 1.0)).to_numpy(float) * np.where(agg["ym"] == t, last_scale, 1.0)
    agg = agg.assign(n=agg["n"] * scale, frp=agg["frp"] * scale)

    cells = train_panel[KEYS].drop_duplicates()
    n = agg.pivot_table(index=KEYS, columns="ym", values="n", aggfunc="sum").reindex(columns=months)
    frp = agg.pivot_table(index=KEYS, columns="ym", values="frp", aggfunc="sum").reindex(columns=months)
    idx = pd.MultiIndex.from_frame(cells)
    n, frp = n.reindex(idx).fillna(0.0), frp.reindex(idx).fillna(0.0)

    target = t + 1
    clim = (train_panel[train_panel["mes_alvo"] == target.month]
            .assign(fogo=lambda d: (d["alvo_n"] > 0).astype(float))
            .groupby(KEYS).agg(p_fogo=("fogo", "mean"), n_med=("alvo_n", "mean")))
    angle = 2 * np.pi * target.month / 12
    out = pd.DataFrame({
        "n_lag0": n[t].to_numpy(), "n_lag1": n[t - 1].to_numpy(), "n_lag2": n[t - 2].to_numpy(),
        "frp_lag0": frp[t].to_numpy(), "frp_lag1": frp[t - 1].to_numpy(), "frp_lag2": frp[t - 2].to_numpy(),
        "n_mesmo_mes_ano_ant": n[t - (MONTHS_OF_HISTORY - 1)].to_numpy(), "n_12m": n.sum(axis=1).to_numpy(),
    }, index=idx).join(clim).fillna({"p_fogo": 0.0, "n_med": 0.0}).reset_index()
    return out.assign(mes_alvo=target.month, ano_alvo=target.year, mes_sin=np.sin(angle), mes_cos=np.cos(angle))
