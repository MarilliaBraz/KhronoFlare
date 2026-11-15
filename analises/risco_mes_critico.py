"""Saídas do modelo de mês crítico para o pitch (passo 6).

Treina o modelo principal (sem índice climático) nos anos-alvo 2004–2016, prevê 2017–2021 e gera:
  * risco_mes_critico_mapa.png: risco previsto × meses críticos observados no mês-alvo de pico (ago–out)
    com maior ΣFRP no mês anterior, informação disponível na hora da previsão (o resultado não entra);
  * risco_mes_critico_desempenho.png: ROC-AUC por bioma (modelo × referências) e importância por grupo;
  * risco_mes_critico.json: os números dos dois gráficos.

Pré-requisitos: `python -m firms_harmonize risk-panel`, `risk-drivers` e `risk-explain`.

    python analises/risco_mes_critico.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, ListedColormap  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from firms_harmonize import geo  # noqa: E402
from firms_harmonize.config import (BOUNDARY, RISK_DIR, RISK_RES, RISK_TEST_YEARS,  # noqa: E402
                                    RISK_TRAIN_YEARS)
from firms_harmonize.risk.drivers import BIOME_CODES  # noqa: E402
from firms_harmonize.risk.model import BASE_FEATURES, choose_map_month, evaluate, fit_model  # noqa: E402

SAIDA = Path(__file__).resolve().parent

# Paleta validada (categórica: azul, laranja, verde-água; o verde-água exige rótulos visíveis).
AZUL, LARANJA, VERDE = "#2a78d6", "#eb6834", "#1baf7a"
SUPERFICIE, TEXTO, TEXTO_2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
RAMPA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
def _br(valor: float, casas: int = 2) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    return f"{valor:.{casas}f}".replace(".", ",")


def _eixo_br(casas: int) -> FuncFormatter:
    return FuncFormatter(lambda v, _: _br(v, casas))


GRUPOS_PT = {"climatologia": "Climatologia da célula", "historico_recente": "Fogo nos últimos 3 meses",
             "sazonalidade": "Mês do ano", "posicao": "Posição (lat/lon)",
             "ano_anterior_e_12m": "Ano anterior e 12 meses", "bioma": "Bioma"}


def prever(panel: pd.DataFrame) -> pd.DataFrame:
    model = fit_model(panel, BASE_FEATURES, RISK_TRAIN_YEARS)
    test = panel[panel["ano_alvo"].between(*RISK_TEST_YEARS)].copy()
    test["prob"] = model.predict_proba(test[BASE_FEATURES])[:, 1]
    return test


def desempenho_por_bioma(test: pd.DataFrame) -> pd.DataFrame:
    linhas = {}
    grupos = [("Brasil", test), *[(BIOME_CODES[b], g) for b, g in test.groupby("bioma")]]
    for nome, g in grupos:
        y = g["y_critico"].to_numpy()
        linhas[nome] = {"Random Forest": evaluate(y, g["prob"])["roc_auc"],
                        "Climatologia": evaluate(y, g["p_fogo"], probabilistic=False)["roc_auc"],
                        "Repetir o mês atual": evaluate(y, g["frp_lag0"], probabilistic=False)["roc_auc"],
                        "celulas": int(g[["cy", "cx"]].drop_duplicates().shape[0])}
    return pd.DataFrame(linhas).T


def _grade(df: pd.DataFrame, coluna: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ys = np.arange(df["cy"].min(), df["cy"].max() + 2)
    xs = np.arange(df["cx"].min(), df["cx"].max() + 2)
    z = np.full((len(ys) - 1, len(xs) - 1), np.nan)
    z[df["cy"] - ys[0], df["cx"] - xs[0]] = df[coluna].to_numpy(float)
    return xs * RISK_RES, ys * RISK_RES, z


def _contorno(ax, contorno) -> None:
    for g in getattr(contorno, "geoms", [contorno]):
        x, y = g.exterior.xy
        ax.plot(x, y, color=TEXTO_2, lw=0.6)


def mapa(test: pd.DataFrame, mes: pd.Period, destino: Path, auc_teste: float) -> dict:
    sel = test[(test["ym"] + 1) == mes]
    contorno = geo.load_boundary(BOUNDARY) if BOUNDARY.exists() else None
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.2), facecolor=SUPERFICIE)
    x, y, prob = _grade(sel, "prob")
    _, _, obs = _grade(sel, "y_critico")
    im = axes[0].pcolormesh(x, y, prob, cmap=LinearSegmentedColormap.from_list("azul", RAMPA_AZUL),
                            vmin=0, vmax=1, shading="flat")
    axes[1].pcolormesh(x, y, obs, cmap=ListedColormap([GRADE, LARANJA]), vmin=0, vmax=1, shading="flat")
    titulos = ["Risco previsto (probabilidade de mês crítico)",
               f"Observado: {int(sel['y_critico'].sum())} células com mês crítico"]
    for ax, titulo in zip(axes, titulos):
        ax.set_facecolor(SUPERFICIE)
        if contorno is not None:
            _contorno(ax, contorno)
        ax.set_aspect("equal")
        ax.set_title(titulo, color=TEXTO, fontsize=11, loc="left")
        ax.tick_params(colors=TEXTO_2, labelsize=8)
        for lado in ax.spines.values():
            lado.set_color(GRADE)
    cb = fig.colorbar(im, ax=axes[0], fraction=0.04, pad=0.02)
    cb.ax.tick_params(colors=TEXTO_2, labelsize=8)
    cb.ax.yaxis.set_major_formatter(_eixo_br(1))
    axes[1].legend(handles=[plt.Rectangle((0, 0), 1, 1, color=LARANJA), plt.Rectangle((0, 0), 1, 1, color=GRADE)],
                   labels=["mês crítico", "normal"], frameon=False, loc="lower left", fontsize=9)
    y_mes, p_mes = sel["y_critico"].to_numpy(), sel["prob"].to_numpy()
    m = evaluate(y_mes, p_mes)
    fig.suptitle(f"Brasil, {mes.strftime('%m/%Y')}: previsão feita com dados até {(mes - 1).strftime('%m/%Y')}\n"
                 f"ROC-AUC deste mês {_br(m['roc_auc'])} · média do teste 2017–2021 {_br(auc_teste)} "
                 "· mês escolhido pelo maior ΣFRP no mês anterior", color=TEXTO, x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(destino, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)
    return {"mes": str(mes), "criterio": "mês-alvo de pico (ago–out) com maior ΣFRP no mês anterior",
            "celulas": int(len(sel)), "criticas": int(y_mes.sum()), **m}


def grafico_desempenho(tab: pd.DataFrame, importancia: dict, destino: Path) -> None:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.4), facecolor=SUPERFICIE,
                                 gridspec_kw={"width_ratios": [1.6, 1]})
    series = [("Random Forest", AZUL), ("Climatologia", LARANJA), ("Repetir o mês atual", VERDE)]
    x = np.arange(len(tab))
    largura = 0.26
    for i, (nome, cor) in enumerate(series):
        barras = a1.bar(x + (i - 1) * largura, tab[nome].astype(float), largura - 0.02, color=cor, label=nome)
        a1.bar_label(barras, labels=[_br(v) for v in tab[nome].astype(float)], fontsize=7,
                     color=TEXTO_2, padding=2)
    a1.axhline(0.5, color=TEXTO_2, lw=1, ls=":")
    a1.annotate("sorteio", (-0.5, 0.5), xytext=(2, 3), textcoords="offset points",
                ha="left", fontsize=8, color=TEXTO_2)
    a1.set_xticks(x, [f"{n}\n({int(c)} células)" for n, c in zip(tab.index, tab["celulas"])], fontsize=8)
    a1.set_ylim(0.4, 0.85)
    a1.yaxis.set_major_formatter(_eixo_br(2))
    a1.set_ylabel("ROC-AUC no teste 2017–2021", color=TEXTO_2)
    a1.set_title("Desempenho por bioma", color=TEXTO, loc="left")
    a1.legend(frameon=False, ncol=3, fontsize=9, loc="upper left")

    grupos = pd.DataFrame(importancia["grupos"]).T.sort_values("queda_auc")
    barras = a2.barh([GRUPOS_PT.get(g, g) for g in grupos.index], grupos["queda_auc"], color=AZUL)
    a2.bar_label(barras, labels=[_br(v, 3) for v in grupos["queda_auc"]], fontsize=8, color=TEXTO_2, padding=3)
    a2.xaxis.set_major_formatter(_eixo_br(3))
    a2.set_xlabel("Queda do ROC-AUC ao embaralhar o grupo", color=TEXTO_2)
    a2.set_title("O que o modelo usa", color=TEXTO, loc="left")
    a2.set_xlim(0, grupos["queda_auc"].max() * 1.25)
    for ax in (a1, a2):
        ax.set_facecolor(SUPERFICIE)
        ax.tick_params(colors=TEXTO_2)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(GRADE)
    a1.grid(axis="y", color=GRADE, lw=0.8)
    fig.tight_layout()
    fig.savefig(destino, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)


def main() -> None:
    for arquivo in ("panel.parquet", "importancia.json"):
        if not (RISK_DIR / arquivo).exists():
            raise SystemExit(f"{RISK_DIR / arquivo} não existe; rode risk-panel, risk-drivers e risk-explain.")
    panel = pd.read_parquet(RISK_DIR / "panel.parquet")
    importancia = json.loads((RISK_DIR / "importancia.json").read_text())
    print("Treinando o modelo principal e prevendo 2017–2021 ...", flush=True)
    test = prever(panel)
    mes = choose_map_month(test)
    auc_teste = evaluate(test["y_critico"], test["prob"])["roc_auc"]
    resumo_mapa = mapa(test, mes, SAIDA / "risco_mes_critico_mapa.png", auc_teste)
    tab = desempenho_por_bioma(test)
    grafico_desempenho(tab, importancia, SAIDA / "risco_mes_critico_desempenho.png")
    saida = {"modelo": "Random Forest sem índice climático", "treino": list(RISK_TRAIN_YEARS),
             "teste": list(RISK_TEST_YEARS), "mapa": resumo_mapa,
             "roc_auc_por_bioma": tab.round(3).to_dict(orient="index"),
             "importancia_grupos": importancia["grupos"]}
    (SAIDA / "risco_mes_critico.json").write_text(json.dumps(saida, indent=2, ensure_ascii=False))
    print(f"Mês do mapa: {mes} | células críticas: {resumo_mapa['criticas']} de {resumo_mapa['celulas']} "
          f"| ROC-AUC do mês: {resumo_mapa['roc_auc']:.3f}")
    print(tab.round(3).to_string())


if __name__ == "__main__":
    main()
