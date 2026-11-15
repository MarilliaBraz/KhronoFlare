"""Gera web/forecast.json: onde o fogo tende a aparecer no próximo mês, para o gestor da Defesa Civil.

Estimativa pelo histórico, não pelo modelo de risco: para cada célula de 0,5°, em quantos anos
(2004–2021) houve fogo no mês seguinte e a média de focos (web/tools/climatologia.json), mais o fogo
ativo agora (focos das últimas 24 h do FIRMS em web/data.json). Cada município herda a classe da célula
onde fica a sede (web/cities.json). Só biblioteca padrão: roda na tarefa do GitHub sem instalar nada.

Regra (fica escrita no meta para a página mostrar):
  * alta:  fogo em ≥ 75 % dos anos naquele mês e média ≥ 15 focos;
  * média: fogo em ≥ 50 % dos anos e média ≥ 5 focos;
  * baixa: o resto;
  * ≥ 3 focos ativos agora na célula sobem um nível (1 foco isolado costuma ser queima pequena). Se web/data.json for a amostra de 12/11 (não "live"),
    o fogo ativo não conta;
  * modelo (web/tools/previsao_modelo.json, Random Forest, gerado à parte com `risk-forecast`): se ele
    for do mesmo mês-alvo, probabilidade ≥ 35 % de mês crítico (o dobro da chance normal de dezembro,
    ~17 %) sobe mais um nível. Mês crítico = ΣFRP acima do percentil 75 da própria célula.

    python3 web/tools/build_forecast.py web/forecast.json
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
CLIMATOLOGY = Path(__file__).resolve().parent / "climatologia.json"
MODEL = Path(__file__).resolve().parent / "previsao_modelo.json"
HIGH_SHARE = 0.75      # fração mínima de anos com fogo para "alta"
HIGH_MEAN = 15.0       # média mínima de focos no mês para "alta"
MEDIUM_SHARE = 0.5     # fração mínima de anos com fogo para "média"
MEDIUM_MEAN = 5.0      # média mínima de focos no mês para "média"
ACTIVE_MIN = 3         # focos ativos na célula para subir um nível
MODEL_MIN_PROB = 0.35  # probabilidade do modelo para subir um nível
CLASSES = ["low", "medium", "high"]


def target_month(generated_iso: str) -> tuple[int, int]:
    """(ano, mês) seguinte ao horário em que os dados ao vivo foram gerados."""
    t = datetime.fromisoformat(generated_iso)
    return (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)


def cell_of(lat: float, lon: float, res: float) -> tuple[int, int]:
    """Mesmo índice de célula do painel de risco (piso de lat/res e lon/res)."""
    return math.floor(lat / res), math.floor(lon / res)


def classify(years: int, n_years: int, mean: float, active: int, prob: float | None = None) -> str:
    share = years / n_years if n_years else 0.0
    if share >= HIGH_SHARE and mean >= HIGH_MEAN:
        level = 2
    elif share >= MEDIUM_SHARE and mean >= MEDIUM_MEAN:
        level = 1
    else:
        level = 0
    if active >= ACTIVE_MIN:
        level += 1
    if prob is not None and prob >= MODEL_MIN_PROB:
        level += 1
    return CLASSES[min(level, 2)]


def _active_points(live: dict) -> list[dict]:
    if live.get("meta", {}).get("kind") != "live":
        return []
    fields = live["point_fields"]
    points = (dict(zip(fields, p)) for p in live["points"])
    return [p for p in points if p.get("uf")]          # só focos atribuídos a um município do Brasil


def build_forecast(clim: dict, live: dict, cities: dict, model: dict | None = None) -> dict:
    res, n_years = clim["res"], clim["n_years"]
    year, month = target_month(live["meta"]["generated"])
    target = f"{year}-{month:02d}"
    probs = model["cells"] if model and model.get("target") == target else None
    active = _active_points(live)
    active_cell = Counter(cell_of(p["lat"], p["lon"], res) for p in active)
    active_mun = Counter(str(p["mun"]) for p in active)

    history = {}
    for key, months in clim["cells"].items():
        years, mean = months[month - 1]
        if years > 0:
            history[tuple(int(v) for v in key.split(","))] = (years, mean)

    cells = {}
    for c in sorted(set(history) | set(active_cell)):
        years, mean = history.get(c, (0, 0.0))
        prob = probs.get(f"{c[0]},{c[1]}") if probs is not None else None
        cells[c] = [c[0], c[1], classify(years, n_years, mean, active_cell[c], prob), years, mean, active_cell[c], prob]

    municipalities = []
    for cid, name, uf, lat, lon, *_ in cities["cities"]:
        cell = cells.get(cell_of(lat, lon, res))
        if not cell or cell[2] == "low":
            continue
        municipalities.append({"id": cid, "name": name, "uf": uf, "cls": cell[2], "years": cell[3],
                               "n_years": n_years, "mean": cell[4], "active_cell": cell[5],
                               "active_mun": active_mun[cid], "prob": cell[6]})
    municipalities.sort(key=lambda m: (-CLASSES.index(m["cls"]), -m["active_mun"], -m["years"], -m["mean"]))

    model_meta = None
    if probs is not None:
        model_meta = {"name": model["model"], "train_years": model["train_years"],
                      "roc_auc_temporal": model["validation"]["roc_auc_temporal"],
                      "roc_auc_spatial": model["validation"]["roc_auc_spatial"], "base_rate": model["base_rate"],
                      "data_until": model["data_until"], "generated": model["generated"], "min_prob": MODEL_MIN_PROB}
    meta = {"kind": "climatology+model" if model_meta else "climatology", "target": target, "model": model_meta,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "live_generated": live["meta"]["generated"], "active_counted": live["meta"].get("kind") == "live",
            "history_years": clim["years"], "n_years": n_years, "res": res,
            "rule": {"high_share": HIGH_SHARE, "high_mean": HIGH_MEAN, "medium_share": MEDIUM_SHARE,
                     "medium_mean": MEDIUM_MEAN, "active_min": ACTIVE_MIN}}
    return {"meta": meta, "cells": list(cells.values()), "municipalities": municipalities}


def same_content(old: dict | None, new: dict) -> bool:
    """Mesma previsão, só com outro horário de geração (evita commit a cada 3 h sem dado novo)."""
    if not old:
        return False
    strip = lambda fc: {**fc, "meta": {k: v for k, v in fc.get("meta", {}).items() if k != "generated"}}
    return strip(old) == strip(new)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    read = lambda p: json.loads(p.read_text(encoding="utf-8"))
    model = read(MODEL) if MODEL.exists() else None
    fc = build_forecast(read(CLIMATOLOGY), read(WEB / "data.json"), read(WEB / "cities.json"), model)
    previous = read(args.out) if args.out.exists() else None
    if same_content(previous, fc):
        print(f"{args.out}: sem mudança na previsão (mantido o arquivo de {previous['meta']['generated']})")
        return
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(args.out)
    by_cls = Counter(m["cls"] for m in fc["municipalities"])
    print(f"{args.out}: previsão para {fc['meta']['target']} | {len(fc['cells'])} células | "
          f"municípios alta {by_cls['high']}, média {by_cls['medium']} | "
          f"fogo ativo {'contado' if fc['meta']['active_counted'] else 'NÃO contado (amostra)'} | "
          f"modelo {'usado' if fc['meta']['model'] else 'não usado (sem previsão para este mês)'}")


if __name__ == "__main__":
    main()
