"""Central configuration: datasets, stations and settings.

Everything a reviewer might want to change lives here, not inside the fetch code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ReeDataset:
    """One REData widget we ingest.

    chunk_days keeps each request small; REData rejects very long ranges at fine granularity.
    """

    name: str  # our dataset name (used in folder paths and table names)
    category: str  # REData category, e.g. "mercados"
    widget: str  # REData widget, e.g. "precios-mercados-tiempo-real"
    time_trunc: str  # "hour" or "day"
    chunk_days: int


REE_BASE_URL = "https://apidatos.ree.es"
REE_LANG = "en"

# Verify each widget with a one-day request before backfilling (see docs/WEEK1-2_zh.md).
REE_DATASETS: dict[str, ReeDataset] = {
    d.name: d
    for d in [
        ReeDataset("market_prices", "mercados", "precios-mercados-tiempo-real", "hour", 7),
        ReeDataset("demand", "demanda", "evolucion", "day", 30),
        ReeDataset("generation_mix", "generacion", "estructura-generacion", "day", 30),
    ]
}


AEMET_BASE_URL = "https://opendata.aemet.es/opendata/api"
AEMET_CHUNK_DAYS = 30
AEMET_SLEEP_SECONDS = 3.0  # AEMET rate-limits aggressively (HTTP 429); be polite
AEMET_RETRIES = 8  # with backoff 5s -> waits 5, 10, 20, 40, 80, 120... seconds
AEMET_BACKOFF = 5.0

# Main stations of the five largest metro areas. `weight` = approximate metro population
# (millions), used later in Silver to build a population-weighted national temperature.
AEMET_STATIONS: dict[str, dict] = {
    "3195": {"name": "Madrid Retiro", "weight": 6.8},
    "0076": {"name": "Barcelona Aeropuerto", "weight": 5.7},
    "8416": {"name": "Valencia", "weight": 1.6},
    "5783": {"name": "Sevilla Aeropuerto", "weight": 1.5},
    "1082": {"name": "Bilbao Aeropuerto", "weight": 1.0},
}


def landing_dir() -> Path:
    return Path(os.getenv("LANDING_DIR", "data/landing"))


def aemet_api_key() -> str:
    key = os.getenv("AEMET_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AEMET_API_KEY is not set. Copy .env.example to .env and add it.")
    return key
