"""Regressão linear do número de focos de calor por ano no Brasil (NASA FIRMS).

Séries analisadas (só focos de vegetação, type == 0, e só anos completos):
  - MODIS Terra + Aqua, 2003–2025 (os dois satélites operando o ano todo)
  - MODIS só Aqua, 2003–2025 (um único satélite, horário de passagem fixo)
  - VIIRS S-NPP, 2012–2025 (sensor de 375 m, detecta focos menores)

Para cada série: reta de mínimos quadrados (MQO), intervalo de 95% da
inclinação, valor-p, R², e duas checagens robustas a anos extremos
(inclinação de Theil-Sen e teste de Mann-Kendall via tau de Kendall).

Saídas em analises/: focos_por_ano.png, focos_por_ano.txt, focos_por_ano.json
Uso: .venv/bin/python analises/regressao_focos_por_ano.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = Path(__file__).resolve().parent
MODIS = RAIZ / "DL_FIRE_M-C61_846226" / "fire_archive_M-C61_846226.csv"
VIIRS_SNPP = RAIZ / "DL_FIRE_SV-C2_846227" / "fire_archive_SV-C2_846227.csv"
ANO_FINAL = 2025  # 2026 ainda está incompleto no arquivo histórico
ANO_INICIAL_MODIS = 2003  # primeiro ano completo com Terra e Aqua
ANO_INICIAL_VIIRS = 2012


def contar_por_ano(arquivo: Path, satelite: str | None = None) -> pd.Series:
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo da FIRMS não encontrado: {arquivo}")
    df = pd.read_csv(arquivo, usecols=["acq_date", "type", "satellite"])
    df = df[df["type"] == 0]
    if satelite is not None:
        df = df[df["satellite"] == satelite]
    return df["acq_date"].str[:4].astype(int).value_counts().sort_index()


def ajustar(anos: np.ndarray, focos: np.ndarray) -> dict:
    reg = stats.linregress(anos, focos)
    gl = len(anos) - 2
    t_critico = stats.t.ppf(0.975, gl)
    sen = stats.theilslopes(focos, anos)
    tau = stats.kendalltau(anos, focos)
    previsto = reg.slope * anos + reg.intercept
    return {
        "inclinacao": reg.slope,
        "intercepto": reg.intercept,
        "ic95": [reg.slope - t_critico * reg.stderr, reg.slope + t_critico * reg.stderr],
        "erro_padrao": reg.stderr,
        "r": reg.rvalue,
        "r2": reg.rvalue**2,
        "p": reg.pvalue,
        "n": len(anos),
        "media": float(focos.mean()),
        "variacao_pct_ano": 100 * reg.slope / focos.mean(),
        "theil_sen": sen.slope,
        "theil_sen_ic95": [sen.low_slope, sen.high_slope],
        "kendall_tau": tau.statistic,
        "kendall_p": tau.pvalue,
        "residuos": (focos - previsto).tolist(),
    }


def montar_series() -> dict:
    total = contar_por_ano(MODIS)
    aqua = contar_por_ano(MODIS, "Aqua")
    snpp = contar_por_ano(VIIRS_SNPP)
    definicoes = {
        "modis_total": ("MODIS Terra + Aqua", total, ANO_INICIAL_MODIS),
        "modis_aqua": ("MODIS só Aqua", aqua, ANO_INICIAL_MODIS),
        "viirs_snpp": ("VIIRS S-NPP", snpp, ANO_INICIAL_VIIRS),
    }
    series = {}
    for chave, (nome, contagem, inicio) in definicoes.items():
        janela = contagem.loc[inicio:ANO_FINAL]
        anos = janela.index.to_numpy(dtype=float)
        focos = janela.to_numpy(dtype=float)
        series[chave] = {
            "nome": nome,
            "anos": janela.index.tolist(),
            "focos": janela.astype(int).tolist(),
            "todos_anos": {int(a): int(v) for a, v in contagem.items()},
            "ajuste": ajustar(anos, focos),
        }
    return series


JANELAS_SENSIBILIDADE = [(2003, 2025), (2003, 2023), (2008, 2025), (2012, 2025)]


def sensibilidade(contagem: dict) -> list[dict]:
    """Refaz a regressão do MODIS Terra + Aqua em janelas diferentes de anos."""
    resultado = []
    for inicio, fim in JANELAS_SENSIBILIDADE:
        anos = np.arange(inicio, fim + 1)
        focos = np.array([contagem[int(a)] for a in anos], dtype=float)
        reg = stats.linregress(anos, focos)
        resultado.append({"inicio": inicio, "fim": fim, "inclinacao": reg.slope,
                          "r2": reg.rvalue**2, "p": reg.pvalue})
    return resultado


def desenhar(series: dict) -> Path:
    fig, eixos = plt.subplots(1, 3, figsize=(18, 5.5))
    for ax, s in zip(eixos, series.values()):
        anos = np.array(s["anos"])
        focos = np.array(s["focos"]) / 1000
        aj = s["ajuste"]
        ax.scatter(anos, focos, color="#d95f02", zorder=3, label="Focos no ano")
        ax.plot(anos, (aj["inclinacao"] * anos + aj["intercepto"]) / 1000, color="#1b4f72", linewidth=2,
                label=f"MQO: {aj['inclinacao'] / 1000:+.1f} mil/ano (p = {aj['p']:.3f})")
        ax.set_title(f"{s['nome']}, {anos[0]}–{anos[-1]}  ·  R² = {aj['r2']:.3f}")
        ax.set_xlabel("Ano")
        ax.set_ylabel("Focos (milhares)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=9)
    fig.suptitle("Focos de calor por ano no Brasil (NASA FIRMS, focos de vegetação)")
    fig.tight_layout()
    destino = SAIDA / "focos_por_ano.png"
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    return destino


def resumo(series: dict) -> str:
    linhas = []
    for s in series.values():
        a = s["ajuste"]
        linhas.append(
            f"{s['nome']} ({s['anos'][0]}–{s['anos'][-1]}, n={a['n']}): "
            f"inclinação={a['inclinacao']:+.0f} focos/ano "
            f"(IC95% {a['ic95'][0]:+.0f} a {a['ic95'][1]:+.0f}; {a['variacao_pct_ano']:+.2f}% da média/ano), "
            f"R²={a['r2']:.3f}, p={a['p']:.4f}; Theil-Sen={a['theil_sen']:+.0f}; "
            f"Kendall tau={a['kendall_tau']:+.3f} (p={a['kendall_p']:.4f})"
        )
    return "\n".join(linhas)


def main() -> None:
    series = montar_series()
    grafico = desenhar(series)
    texto = resumo(series)
    (SAIDA / "focos_por_ano.txt").write_text(texto + "\n", encoding="utf-8")
    saida_json = {**series, "sensibilidade": sensibilidade(series["modis_total"]["todos_anos"])}
    (SAIDA / "focos_por_ano.json").write_text(json.dumps(saida_json, ensure_ascii=False, indent=1), encoding="utf-8")
    print(texto)
    print(f"Gráfico salvo em {grafico}")


if __name__ == "__main__":
    main()
