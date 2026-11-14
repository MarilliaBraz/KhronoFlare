"""Gera a página de estudo (estudo_regressao.html) a partir dos JSONs das análises.

Rode antes os dois scripts de regressão, que produzem focos_por_ano.json e
regressao_frp_brilho.json. Este script só embute esses dados no modelo HTML.
Uso: .venv/bin/python analises/gerar_estudo.py
"""

import json
from pathlib import Path

PASTA = Path(__file__).resolve().parent
MODELO = PASTA / "estudo_template.html"
DESTINO = PASTA / "estudo_regressao.html"
ENTRADAS = {"/*FOCOS*/null": PASTA / "focos_por_ano.json", "/*FRP*/null": PASTA / "regressao_frp_brilho.json"}


def main() -> None:
    html = MODELO.read_text(encoding="utf-8")
    for marcador, arquivo in ENTRADAS.items():
        if not arquivo.exists():
            raise FileNotFoundError(f"Rode a análise antes: falta {arquivo.name}")
        if marcador not in html:
            raise ValueError(f"Marcador {marcador} não encontrado em {MODELO.name}")
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        html = html.replace(marcador, json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
    DESTINO.write_text(html, encoding="utf-8")
    print(f"Página gerada em {DESTINO}")


if __name__ == "__main__":
    main()
