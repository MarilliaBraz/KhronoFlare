"""Etapa 6 do fluxograma: calibrar o FRP do MODIS pela VZA e pelo FRP do VIIRS.

Modelo (mínimos quadrados em escala log, nos pares sem anomalia):

    ln ΣFRP_VIIRS = a + b · ln FRP_MODIS + c · VZA

Volta para MW com o fator de smearing de Duan (1983), média de exp(resíduo), calculado por faixa de
VZA de 10° (versão B, escolhida em 14/11/2026): sem ele, a exponencial
de uma média em log subestima a média em MW e as somas anuais ficam baixas.

A validação é fora da amostra (treino em anos antigos, teste em anos não vistos) e compara três
opções: sem correção, um fator único Σ VIIRS / Σ MODIS e o modelo com VZA.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .prepare import in_window

MIN_POINTS = 3  # três coeficientes
VZA_BIN_DEG = 10.0


def _bin_index(vza: np.ndarray, width: float, n_bins: int) -> np.ndarray:
    """Faixa de VZA de cada valor; fora das faixas treinadas vai para a mais próxima."""
    return np.clip(np.floor(np.nan_to_num(vza) / width), 0, n_bins - 1).astype(int)


@dataclass(frozen=True)
class Calibration:
    """Coeficientes do modelo. Com `bin_width`, o fator de Duan é um por faixa de VZA (versão B):
    o espalhamento dos resíduos muda com o ângulo, e um fator único erra as somas de cada faixa.
    `d` é o termo de noite: os limites de detecção de FRP do MODIS e do VIIRS são diferentes de dia
    e de noite (Sofiev & Kouznetsov 2026, GMD 19:10123); sem ele o FRP noturno saía +15 % alto."""
    a: float
    b: float
    c: float
    smearing: float
    n: int
    bin_width: float | None = None
    smearing_by_bin: tuple[float, ...] = ()
    d: float = 0.0

    def _smearing_for(self, vza: np.ndarray) -> np.ndarray | float:
        if not self.bin_width or not self.smearing_by_bin:
            return self.smearing
        return np.asarray(self.smearing_by_bin)[_bin_index(vza, self.bin_width, len(self.smearing_by_bin))]

    def predict(self, frp_modis, vza, night=None) -> np.ndarray:
        """FRP MODIS (MW) → FRP equivalente S-NPP VIIRS (MW). `night` ausente = dia."""
        x, z = np.asarray(frp_modis, dtype=float), np.asarray(vza, dtype=float)
        nt = np.zeros_like(x) if night is None else np.asarray(night, dtype=float)
        return self._smearing_for(z) * np.exp(self.a + self.b * np.log(x) + self.c * z + self.d * nt)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        return cls(**{**d, "smearing_by_bin": tuple(d.get("smearing_by_bin", ()))})


def _smearing_by_bin(resid: np.ndarray, vza: np.ndarray, width: float, overall: float) -> tuple[float, ...]:
    n_bins = int(np.floor(vza.max() / width)) + 1
    idx = _bin_index(vza, width, n_bins)
    factors = []
    for b in range(n_bins):
        sel = idx == b
        factors.append(float(np.mean(np.exp(resid[sel]))) if sel.any() else overall)
    return tuple(factors)


def fit(frp_modis, vza, frp_viirs, night=None, bin_width: float | None = VZA_BIN_DEG) -> Calibration:
    x, z, y = (np.asarray(v, dtype=float) for v in (frp_modis, vza, frp_viirs))
    if len(x) < MIN_POINTS:
        raise ValueError(f"poucos pares para calibrar ({len(x)} < {MIN_POINTS})")
    if (x <= 0).any() or (y <= 0).any() or not np.isfinite(z).all():
        raise ValueError("FRP precisa ser positivo e a VZA, finita, em todos os pares")
    columns = [np.ones_like(x), np.log(x), z]
    nt = np.zeros_like(x) if night is None else np.asarray(night, dtype=float)
    with_night = 0 < nt.sum() < len(nt)   # só estima d quando há pares de dia e de noite
    if with_night:
        columns.append(nt)
    design = np.column_stack(columns)
    coef, *_ = np.linalg.lstsq(design, np.log(y), rcond=None)
    resid = np.log(y) - design @ coef
    overall = float(np.mean(np.exp(resid)))
    by_bin = _smearing_by_bin(resid, z, bin_width, overall) if bin_width else ()
    return Calibration(a=float(coef[0]), b=float(coef[1]), c=float(coef[2]), smearing=overall,
                       n=int(len(x)), bin_width=bin_width, smearing_by_bin=by_bin,
                       d=float(coef[3]) if with_night else 0.0)


def evaluate(pred, obs) -> dict:
    """R² em log, viés da soma (%) e erro típico de um par (%, mediana de |ln pred − ln obs|)."""
    p, o = np.log(np.asarray(pred, dtype=float)), np.log(np.asarray(obs, dtype=float))
    ss_tot = np.sum((o - o.mean()) ** 2)
    return {
        "r2_log": float(1 - np.sum((o - p) ** 2) / ss_tot) if ss_tot > 0 else float("nan"),
        "vies_soma_pct": float(100 * (np.exp(p).sum() / np.exp(o).sum() - 1)),
        "erro_mediano_pct": float(100 * (np.exp(np.median(np.abs(p - o))) - 1)),
    }


def is_night(pairs: pd.DataFrame) -> np.ndarray:
    return pairs["daynight"].astype(str).eq("N").to_numpy()


def _predictions(test: pd.DataFrame, cal: Calibration, k: float) -> dict:
    m = test["frp_modis"].to_numpy(float)
    return {"sem_correcao": m, "fator_unico": k * m,
            "modelo_vza": cal.predict(m, test["vza"], is_night(test))}


def _group_bias(groups: np.ndarray, obs: np.ndarray, preds: dict) -> dict:
    """Viés da soma (%) de cada modelo dentro de cada grupo (ano, dia/noite...)."""
    return {str(g): {name: round(float(100 * (p[groups == g].sum() / obs[groups == g].sum() - 1)), 2)
                     for name, p in preds.items()}
            for g in np.unique(groups)}


def validate(pairs: pd.DataFrame, train: tuple[str, str], test: tuple[str, str]) -> dict:
    """Ajusta na janela de treino e mede nos anos de teste (pares anômalos ficam de fora)."""
    clean = pairs[~pairs["outlier"].astype(bool)]
    tr = clean[in_window(clean["date"], *train)]
    te = clean[in_window(clean["date"], *test)]
    cal = fit(tr["frp_modis"], tr["vza"], tr["frp_viirs"], night=is_night(tr))
    k = float(tr["frp_viirs"].sum() / tr["frp_modis"].sum())
    preds = _predictions(te, cal, k)
    obs = te["frp_viirs"].to_numpy(float)
    return {
        "treino": {"janela": list(train), "pares": int(len(tr)), "modelo": cal.to_dict(), "fator_unico": k},
        "teste": {"janela": list(test), "pares": int(len(te)),
                  "modelos": {name: evaluate(p, obs) for name, p in preds.items()},
                  "vies_soma_anual_pct": _group_bias(te["date"].dt.year.to_numpy(), obs, preds),
                  "vies_soma_dia_noite_pct": _group_bias(te["daynight"].astype(str).to_numpy(), obs, preds)},
    }
