"""Regressão linear entre brilho (temperatura de brilho, K) e FRP dos focos MODIS.

Usa o arquivo histórico da NASA FIRMS (MODIS C6.1, 2000 em diante), baixado
para a pasta do projeto (não versionado no git).
Ajusta duas retas por mínimos quadrados sobre todos os focos de vegetação
(type == 0) com FRP > 0:

  1. FRP (MW) ~ brilho (K)
  2. log10(FRP) ~ brilho (K)   <- a relação física não é linear; o log a aproxima de uma reta

Saídas: gráfico de dispersão em PNG e um resumo em texto no mesmo diretório.
Uso: .venv/bin/python analises/regressao_frp_brilho.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "DL_FIRE_M-C61_846226" / "fire_archive_M-C61_846226.csv"
SAIDA = Path(__file__).resolve().parent
AMOSTRA_GRAFICO = 30_000
SEMENTE = 42


def carregar() -> pd.DataFrame:
    if not ARQUIVO.exists():
        raise FileNotFoundError(f"Arquivo da FIRMS não encontrado: {ARQUIVO}")
    df = pd.read_csv(ARQUIVO, usecols=["brightness", "frp", "type", "acq_date"])
    return df[(df["type"] == 0) & (df["frp"] > 0)].dropna()


def ajustar(x: np.ndarray, y: np.ndarray) -> dict:
    inclinacao, intercepto = np.polyfit(x, y, 1)
    residuo = y - (inclinacao * x + intercepto)
    r2 = 1 - np.sum(residuo**2) / np.sum((y - y.mean()) ** 2)
    n = len(x)
    erro_padrao = np.sqrt(np.sum(residuo**2) / (n - 2) / np.sum((x - x.mean()) ** 2))
    return {
        "inclinacao": inclinacao,
        "intercepto": intercepto,
        "r2": r2,
        "r": np.corrcoef(x, y)[0, 1],
        "erro_padrao_inclinacao": erro_padrao,
        "n": n,
    }


def desenhar(df: pd.DataFrame, lin: dict, log: dict) -> Path:
    amostra = df.sample(n=min(AMOSTRA_GRAFICO, len(df)), random_state=SEMENTE)
    x_reta = np.linspace(df["brightness"].min(), df["brightness"].max(), 200)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    paineis = [
        (ax1, amostra["frp"], lin, "FRP (MW)", "FRP × brilho"),
        (ax2, np.log10(amostra["frp"]), log, "log10(FRP)", "log10(FRP) × brilho"),
    ]
    for ax, y, ajuste, rotulo_y, titulo in paineis:
        ax.scatter(amostra["brightness"], y, s=4, alpha=0.25, color="#d95f02", label="Focos (amostra)")
        ax.plot(
            x_reta,
            ajuste["inclinacao"] * x_reta + ajuste["intercepto"],
            color="#1b4f72",
            linewidth=2,
            label=f"y = {ajuste['inclinacao']:.4f}x {ajuste['intercepto']:+.2f}\nR² = {ajuste['r2']:.3f}",
        )
        ax.set_xlabel("Temperatura de brilho, canal 21/22 (K)")
        ax.set_ylabel(rotulo_y)
        ax.set_title(titulo)
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left")

    periodo = f"{df['acq_date'].min()} a {df['acq_date'].max()}"
    n_total = f"{lin['n']:,}".replace(",", ".")
    n_amostra = f"{len(amostra):,}".replace(",", ".")
    fig.suptitle(
        f"Focos de calor MODIS (NASA FIRMS), {periodo}\n"
        f"Regressão com {n_total} focos; gráfico mostra amostra de {n_amostra}",
    )
    fig.tight_layout()
    destino = SAIDA / "regressao_frp_brilho.png"
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    return destino


def resumo(lin: dict, log: dict) -> str:
    linhas = []
    for nome, a in [("FRP ~ brilho", lin), ("log10(FRP) ~ brilho", log)]:
        linhas.append(
            f"{nome}: inclinação={a['inclinacao']:.5f} (EP {a['erro_padrao_inclinacao']:.2e}), "
            f"intercepto={a['intercepto']:.3f}, r={a['r']:.3f}, R²={a['r2']:.3f}, n={a['n']}"
        )
    return "\n".join(linhas)


AMOSTRA_JSON = 2_500


def salvar_json(df: pd.DataFrame, lin: dict, log: dict) -> None:
    """Grava os ajustes e uma amostra pequena de pontos para a página de estudo."""
    amostra = df.sample(n=min(AMOSTRA_JSON, len(df)), random_state=SEMENTE)
    dados = {
        "periodo": [df["acq_date"].min(), df["acq_date"].max()],
        "linear": {k: float(v) for k, v in lin.items()},
        "log": {k: float(v) for k, v in log.items()},
        "brilho_min": float(df["brightness"].min()),
        "brilho_max": float(df["brightness"].max()),
        "amostra": [[round(float(b), 1), round(float(f), 1)]
                    for b, f in zip(amostra["brightness"], amostra["frp"])],
    }
    (SAIDA / "regressao_frp_brilho.json").write_text(json.dumps(dados), encoding="utf-8")


def main() -> None:
    df = carregar()
    x = df["brightness"].to_numpy()
    lin = ajustar(x, df["frp"].to_numpy())
    log = ajustar(x, np.log10(df["frp"].to_numpy()))
    grafico = desenhar(df, lin, log)
    texto = resumo(lin, log)
    (SAIDA / "regressao_frp_brilho.txt").write_text(texto + "\n", encoding="utf-8")
    salvar_json(df, lin, log)
    print(texto)
    print(f"Gráfico salvo em {grafico}")


if __name__ == "__main__":
    main()
