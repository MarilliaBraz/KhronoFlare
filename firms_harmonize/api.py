"""Cliente da FIRMS API (https://firms.modaps.eosdis.nasa.gov/api/).

Limites documentados: 5.000 transações a cada 10 minutos; Area API com DAY_RANGE de 1 a 5.
A chave nunca é impressa: mensagens de erro passam por `_redact`.
"""
from __future__ import annotations

import io
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from .config import BRAZIL_BBOX, FIRMS_BASE, RAW_API, map_key

SOURCE_TO_PLATFORM = {
    "MODIS_SP": "MODIS", "MODIS_NRT": "MODIS",
    "VIIRS_SNPP_SP": "SNPP", "VIIRS_SNPP_NRT": "SNPP",
    "VIIRS_NOAA20_SP": "NOAA20", "VIIRS_NOAA20_NRT": "NOAA20",
    "VIIRS_NOAA21_SP": "NOAA21", "VIIRS_NOAA21_NRT": "NOAA21",
}


class FirmsClient:
    def __init__(self, key: str | None = None, session: requests.Session | None = None,
                 safety_margin: int = 300, timeout: int = 180):
        self.key = key or map_key()
        self.timeout = timeout
        self.s = session or requests.Session()
        self.safety_margin = safety_margin

    def _redact(self, text: str) -> str:
        return text.replace(self.key, "***")

    def _get(self, url: str, timeout: int | None = None) -> str:
        try:
            r = self.s.get(url, timeout=timeout or self.timeout)
        except requests.RequestException as e:
            # A URL leva a chave; a mensagem original do requests a exporia no traceback.
            raise RuntimeError(f"FIRMS: falha de rede: {self._redact(str(e))}") from None
        if r.status_code != 200:
            raise RuntimeError(f"FIRMS HTTP {r.status_code}: {self._redact(r.text[:300])}")
        if r.text.lstrip().lower().startswith(("invalid", "error")):
            raise RuntimeError(f"FIRMS: {self._redact(r.text[:300])}")
        return r.text

    def status(self) -> dict:
        return requests.models.complexjson.loads(
            self._get(f"{FIRMS_BASE}/mapserver/mapkey_status/?MAP_KEY={self.key}", 60))

    def wait_if_needed(self):
        """Pausa se o saldo de transações estiver perto do limite."""
        st = self.status()
        if st["current_transactions"] > st["transaction_limit"] - self.safety_margin:
            print("  limite de transações perto do fim; aguardando 10 min ...", flush=True)
            time.sleep(600)

    def availability(self) -> pd.DataFrame:
        txt = self._get(f"{FIRMS_BASE}/api/data_availability/csv/{self.key}/ALL", 60)
        return pd.read_csv(io.StringIO(txt), parse_dates=["min_date", "max_date"])

    def area(self, source: str, start: date, days: int = 5, bbox=BRAZIL_BBOX) -> pd.DataFrame:
        if not 1 <= days <= 5:
            raise ValueError("DAY_RANGE deve ser de 1 a 5")
        area = ",".join(f"{v:g}" for v in bbox)
        url = f"{FIRMS_BASE}/api/area/csv/{self.key}/{source}/{area}/{days}/{start:%Y-%m-%d}"
        return pd.read_csv(io.StringIO(self._get(url)))

    def area_range(self, source: str, start: date, end: date, bbox=BRAZIL_BBOX,
                   cache: Path = RAW_API) -> list[Path]:
        """Baixa [start, end] em blocos de 5 dias, com cache em disco (um CSV por bloco).

        Blocos que terminam até anteontem ficam em cache definitivo; os mais recentes são
        sempre baixados de novo, porque o NRT ainda pode receber passagens atrasadas.
        """
        cache.mkdir(parents=True, exist_ok=True)
        files, d, fresh_limit = [], start, date.today() - timedelta(days=2)
        while d <= end:
            days = min(5, (end - d).days + 1)
            f = cache / f"{source}_{d:%Y%m%d}_{days}d.csv"
            last_day = d + timedelta(days=days - 1)
            if not (f.exists() and last_day < fresh_limit):
                self.wait_if_needed()
                self.area(source, d, days, bbox).to_csv(f, index=False)
                print(f"  {source} {d} (+{days}d) baixado", flush=True)
            files.append(f)
            d += timedelta(days=days)
        return files


def nrt_after_sp(client: FirmsClient,
                 sources=("MODIS", "VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21"),
                 until: date | None = None) -> list[Path]:
    """Baixa o NRT de cada sensor do dia seguinte ao fim do SP até `until` (padrão: ontem)."""
    av = client.availability().set_index("data_id")
    until = until or date.today() - timedelta(days=1)
    files = []
    for s in sources:
        sp_end = av.loc[f"{s}_SP", "max_date"].date()
        nrt_end = min(av.loc[f"{s}_NRT", "max_date"].date(), until)
        if nrt_end > sp_end:
            files += client.area_range(f"{s}_NRT", sp_end + timedelta(days=1), nrt_end)
    return files
