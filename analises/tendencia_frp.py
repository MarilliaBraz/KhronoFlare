"""Tendência do FRP anual do Brasil, harmonizado em escala S-NPP VIIRS (passo 7).

Lê data/processed/frp/frp_anual.csv (gerado por `python -m firms_harmonize frp-fuse`), usa só os
anos completos e aplica Sen, Mann-Kendall e Pettitt à série harmonizada e à original do MODIS.

    python analises/tendencia_frp.py   →  analises/tendencia_frp.json e analises/tendencia_frp.png
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from firms_harmonize.trend import resumo  # noqa: E402

ENTRADA = ROOT / "data" / "processed" / "frp" / "frp_anual.csv"
SAIDA = Path(__file__).resolve().parent
ANOS_COMPLETOS = (2003, 2025)   # 2002 começa em agosto; 2026 vai só até novembro
MW_POR_GW = 1e3

SERIES = {
    "frp_harmonizado_GW": ("frp_harm_total", MW_POR_GW),
    "frp_modis_original_GW": ("frp_modis_total", MW_POR_GW),
    "focos": ("focos", 1),
    "frp_mediano_por_foco_MW": ("frp_harm_mediana", 1),
}

# Paleta categórica validada (slot 1 azul, slot 2 laranja) e tokens de texto do tema claro.
AZUL, LARANJA = "#2a78d6", "#eb6834"
SUPERFICIE, TEXTO, TEXTO_2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def carregar() -> pd.DataFrame:
    if not ENTRADA.exists():
        raise SystemExit(f"{ENTRADA} não existe; rode `python -m firms_harmonize frp-fuse` antes.")
    df = pd.read_csv(ENTRADA)
    return df[df["ano"].between(*ANOS_COMPLETOS)].reset_index(drop=True)


def analisar(df: pd.DataFrame) -> dict:
    return {nome: resumo(df["ano"], df[col] / escala) for nome, (col, escala) in SERIES.items()}


def grafico(df: pd.DataFrame, res: dict, destino: Path) -> None:
    anos = df["ano"].to_numpy()
    harm, orig = df["frp_harm_total"] / MW_POR_GW, df["frp_modis_total"] / MW_POR_GW
    r = res["frp_harmonizado_GW"]
    fig, ax = plt.subplots(figsize=(10, 5.2), facecolor=SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)
    ax.plot(anos, orig, color=LARANJA, lw=2, marker="o", ms=4, ls="--", label="MODIS Aqua original")
    ax.plot(anos, harm, color=AZUL, lw=2, marker="o", ms=4, label="Harmonizado (escala S-NPP VIIRS)")
    ax.set_ylim(0, max(orig.max(), harm.max()) * 1.15)

    quebra = r["pettitt"]["ano_quebra"]
    ax.axvline(quebra + 0.5, color=TEXTO_2, lw=1, ls=":")
    for x0, x1, media in [(anos[0], quebra, r["media_antes"]), (quebra + 1, anos[-1], r["media_depois"])]:
        ax.hlines(media, x0, x1, color=TEXTO_2, lw=1)
        ax.annotate(f"média {media:,.0f} GW".replace(",", "."), (x1, media), xytext=(4, 4),
                    textcoords="offset points", color=TEXTO_2, fontsize=9)
    ax.annotate(f"quebra de Pettitt após {quebra}\n(p = {r['pettitt']['p']:.3f})", (quebra + 0.5, ax.get_ylim()[1]),
                xytext=(6, -28), textcoords="offset points", color=TEXTO_2, fontsize=9)

    sen = r["sen"]
    ax.set_title("Brasil: soma anual do FRP dos focos do Aqua, 2003–2025", color=TEXTO, loc="left",
                 fontsize=13, pad=22)
    ax.text(0, 1.02, f"Sen {sen['inclinacao']:+.0f} GW/ano ({sen['inclinacao_pct_ano']:+.1f} %/ano) · "
                     f"Mann-Kendall τ = {r['mann_kendall']['tau']:+.2f}, p = {r['mann_kendall']['p']:.3f}",
            transform=ax.transAxes, color=TEXTO_2, fontsize=9)
    ax.set_ylabel("ΣFRP (GW)", color=TEXTO_2)
    ax.set_xticks(anos[::2])
    ax.tick_params(colors=TEXTO_2)
    ax.grid(axis="y", color=GRADE, lw=0.8)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.set_xlim(anos[0] - 0.5, anos[-1] + 2)
    ax.legend(frameon=False, loc="upper right", labelcolor=TEXTO)
    fig.tight_layout()
    fig.savefig(destino, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)


def main() -> None:
    df = carregar()
    res = analisar(df)
    tabela = {nome: dict(zip(df["ano"].astype(str), np.round(df[col] / esc, 3).tolist()))
              for nome, (col, esc) in SERIES.items()}
    (SAIDA / "tendencia_frp.json").write_text(
        json.dumps({"anos": list(ANOS_COMPLETOS), "testes": res, "series": tabela}, indent=2, ensure_ascii=False))
    grafico(df, res, SAIDA / "tendencia_frp.png")
    for nome, r in res.items():
        print(f"{nome:26s} Sen {r['sen']['inclinacao_pct_ano']:+5.1f} %/ano  "
              f"IC95 [{r['sen']['ic95'][0]:+.1f}, {r['sen']['ic95'][1]:+.1f}]  "
              f"MK τ {r['mann_kendall']['tau']:+.2f} p {r['mann_kendall']['p']:.3f}  "
              f"Pettitt após {r['pettitt']['ano_quebra']} p {r['pettitt']['p']:.3f}  "
              f"média {r['media_antes']:.1f} → {r['media_depois']:.1f}")


if __name__ == "__main__":
    main()
