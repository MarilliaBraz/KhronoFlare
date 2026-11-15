"""Configuração central: caminhos, chave da API e períodos de cada satélite."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_ARCHIVE = DATA / "raw" / "archive"   # CSVs do FIRMS Archive Download
RAW_API = DATA / "raw" / "api"           # cache das chamadas da Area API
BOUNDARY = DATA / "boundary" / "brasil.geojson"
PROCESSED = DATA / "processed"

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov"

# Retângulo do Brasil (oeste, sul, leste, norte). Inclui vizinhos: recortar pelo polígono.
BRAZIL_BBOX = (-74.0, -34.0, -34.0, 6.0)

# Períodos de meses COMPLETOS em que cada plataforma tem dados.
# Meses de início ou fim parciais ficam de fora para não distorcer as contagens mensais.
# Fontes: formulário do Archive Download e endpoint data_availability (14/11/2026).
PLATFORM_PERIODS = {
    "Terra": ("2000-11", None),
    "Aqua": ("2002-08", None),     # dados desde 04/07/2002; julho é parcial
    "SNPP": ("2012-02", "2026-10"),  # 20/01/2012 a 02/11/2026
    "NOAA20": ("2018-04", None),
    "NOAA21": ("2023-03", None),
}

# Janelas de calibração (sobreposição entre sensores).
# Aqua→SNPP: os dois cruzam o equador às 13h30. A janela vai até 2021, porque o Aqua
# entrou em deriva livre em dez/2021 (science.nasa.gov/mission/aqua).
CALIBRATION = {
    ("Aqua", "SNPP"): ("2012-02", "2021-12"),
    ("Terra", "Aqua"): ("2002-08", "2011-12"),
    ("NOAA20", "SNPP"): ("2018-04", "2026-07"),
    ("NOAA21", "SNPP"): ("2023-03", "2026-07"),
}

REFERENCE = "SNPP"  # a série harmonizada fica em "unidades S-NPP VIIRS 375 m"

# Harmonização de FRP por pareamento de pixels: arquivos de cada plataforma e período lido.
# O Aqua é lido inteiro (vai para a série final); o S-NPP só na janela de calibração Aqua→SNPP.
FRP_DIR = PROCESSED / "frp"

# Modelo de risco de mês crítico (Aqua harmonizado, antes da deriva orbital de 2022).
RISK_DIR = PROCESSED / "risk"
RISK_RES = 0.5                           # graus
RISK_PERIOD = ("2003-01", "2021-12")
RISK_TRAIN_YEARS = (2004, 2016)          # anos do mês-alvo
RISK_TEST_YEARS = (2017, 2021)
ONI_FILE = DATA / "raw" / "oni" / "oni.ascii.txt"   # cópia local do ONI da NOAA CPC
BIOMES_FILE = DATA / "raw" / "biomas" / "Biomas_5000mil.zip"   # IBGE geoftp, 1:5.000.000
TNA_FILE = DATA / "raw" / "tna" / "tna.data"   # NOAA PSL, Atlântico Norte tropical
FRP_SOURCES = {
    "Aqua": ("fire_*_M-C61_*.csv", PLATFORM_PERIODS["Aqua"][0], None),
    "SNPP": ("fire_*_SV-C2_*.csv", *CALIBRATION[("Aqua", "SNPP")]),
}


def map_key() -> str:
    """Lê FIRMS_MAP_KEY do ambiente ou do arquivo .env da raiz (sem dependências externas)."""
    key = os.environ.get("FIRMS_MAP_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key or key == "COLE_SUA_CHAVE_AQUI":
        raise RuntimeError("FIRMS_MAP_KEY não encontrada. Coloque a chave no arquivo .env.")
    return key
