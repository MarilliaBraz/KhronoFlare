"""Tendência em séries anuais curtas, sem supor forma linear nem normalidade.

  * Sen (Theil-Sen): mediana das inclinações entre pares de anos; resistente a anos extremos.
  * Mann-Kendall: existe tendência monotônica? (tau de Kendall contra o tempo).
  * Pettitt: existe uma mudança de patamar? Em que ano? (Pettitt, 1979, Appl. Stat. 28:126).

Limitação: os três supõem anos independentes. Nas séries FIRMS anuais o Durbin-Watson dos
resíduos ficou entre 2,1 e 2,6 (sem autocorrelação positiva), então não aplicamos pré-branqueamento.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

MIN_PONTOS = 3


def _serie(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or len(x) < MIN_PONTOS or not np.isfinite(x).all():
        raise ValueError(f"série precisa de pelo menos {MIN_PONTOS} valores finitos")
    return x


def sen_slope(anos, valores) -> dict:
    y, t = _serie(valores), np.asarray(anos, dtype=float)
    if t.shape != y.shape or not np.isfinite(t).all() or len(np.unique(t)) != len(t):
        raise ValueError("anos precisam ser distintos e ter o mesmo tamanho dos valores")
    r = stats.theilslopes(y, t)
    return {"inclinacao": float(r.slope), "ic95": [float(r.low_slope), float(r.high_slope)]}


def mann_kendall(valores) -> dict:
    y = _serie(valores)
    if np.ptp(y) == 0:  # série constante: kendalltau devolveria NaN (JSON inválido)
        return {"tau": 0.0, "p": 1.0}
    r = stats.kendalltau(np.arange(len(y)), y)
    return {"tau": float(r.statistic), "p": float(r.pvalue)}


def pettitt(valores) -> dict:
    """Ponto de mudança mais provável; `indice_quebra` é o último índice do patamar inicial.

    p é a aproximação assintótica p ≈ 2·exp(−6K²/(n³+n²)), limitada a 1.
    """
    x = _serie(valores)
    n = len(x)
    sinais = np.sign(x[:, None] - x[None, :])  # sinais[i, j] = sgn(x_i − x_j)
    u = np.array([sinais[:t, t:].sum() for t in range(1, n)])
    t = int(np.argmax(np.abs(u)))
    k = abs(u[t])
    p = min(1.0, 2 * np.exp(-6 * k**2 / (n**3 + n**2)))
    return {"indice_quebra": t, "K": float(k), "p": float(p)}
