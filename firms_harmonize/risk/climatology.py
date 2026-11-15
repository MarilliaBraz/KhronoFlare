"""Climatologia mensal por célula para o painel de previsão do gestor (web/forecast.html).

Para cada célula de `res` graus e cada mês do ano: em quantos anos houve fogo naquele mês e a média
de focos, a partir do painel de risco (`alvo_n` = focos do mês-alvo, anos-alvo 2004–2021 do FRP
harmonizado). O resultado é pequeno e vai para o repositório, porque `data/` não vai para o GitHub e
a tarefa do GitHub Actions precisa dele para refazer a previsão a cada 3 h.
"""
from __future__ import annotations

import pandas as pd

MONTHS = 12


def monthly_climatology(panel: pd.DataFrame, res: float) -> dict:
    """{"res", "years": [início, fim], "n_years", "cells": {"cy,cx": [[anos com fogo, média de focos] × 12]}}.

    Células sem fogo em nenhum mês ficam de fora. Mês sem linhas no painel vale [0, 0.0].
    """
    years = panel["ano_alvo"]
    n_years = int(years.nunique())
    g = panel.assign(fogo=panel["alvo_n"] > 0).groupby(["cy", "cx", "mes_alvo"])
    stats = pd.DataFrame({"anos": g["fogo"].sum(), "soma": g["alvo_n"].sum()}).reset_index()
    cells: dict[str, list] = {}
    for (cy, cx), rows in stats.groupby(["cy", "cx"]):
        if rows["anos"].sum() == 0:
            continue
        months = [[0, 0.0] for _ in range(MONTHS)]
        for r in rows.itertuples():
            months[int(r.mes_alvo) - 1] = [int(r.anos), round(float(r.soma) / n_years, 1)]
        cells[f"{int(cy)},{int(cx)}"] = months
    return {"res": res, "years": [int(years.min()), int(years.max())], "n_years": n_years, "cells": cells}
