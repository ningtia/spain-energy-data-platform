"""AEMET OpenData client for daily climatological values. Requires a free API key.

AEMET uses a two-step pattern:
  1. GET the endpoint with header `api_key` -> {"estado": 200, "datos": <url>, "metadatos": <url>}
  2. GET the `datos` URL -> the actual JSON list
The data is served as Latin-1 and numbers use a decimal comma ("12,4"); we keep the raw
values in landing and convert types in Silver.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from energy_platform import config
from energy_platform.dates import chunk_range
from energy_platform.landing import exists, write_raw

log = logging.getLogger(__name__)


class AemetApiError(RuntimeError):
    pass


def build_url(station_id: str, start: date, end: date) -> str:
    ini = f"{start.isoformat()}T00:00:00UTC"
    fin = f"{end.isoformat()}T23:59:59UTC"
    return (
        f"{config.AEMET_BASE_URL}/valores/climatologicos/diarios/datos/"
        f"fechaini/{ini}/fechafin/{fin}/estacion/{station_id}"
    )


def _decode_json(resp: requests.Response) -> Any:
    # AEMET often omits or mislabels the charset; decode explicitly.
    try:
        return resp.json()
    except (ValueError, UnicodeDecodeError):
        return json.loads(resp.content.decode("latin-1"))


def fetch_chunk(
    session: requests.Session, api_key: str, station_id: str, start: date, end: date
) -> list[dict[str, Any]]:
    resp = session.get(build_url(station_id, start, end), headers={"api_key": api_key}, timeout=60)
    meta = _decode_json(resp)
    estado = meta.get("estado", resp.status_code)
    if estado == 404:
        # "No hay datos que satisfagan esos criterios": a real gap, not a failure.
        log.warning(
            "aemet %s %s..%s: no data (%s)", station_id, start, end, meta.get("descripcion")
        )
        return []
    if estado != 200 or "datos" not in meta:
        raise AemetApiError(f"{station_id} {start}..{end}: {meta}")

    data_resp = session.get(meta["datos"], timeout=60)
    if data_resp.status_code != 200:
        raise AemetApiError(f"{station_id} datos URL: HTTP {data_resp.status_code}")
    data = _decode_json(data_resp)
    if not isinstance(data, list):
        raise AemetApiError(f"{station_id}: expected a list, got {type(data).__name__}")
    return data


def ingest(
    session: requests.Session,
    start: date,
    end: date,
    landing_root: Path,
    stations: list[str] | None = None,
    sleep_seconds: float = config.AEMET_SLEEP_SECONDS,
    skip_existing: bool = True,
) -> tuple[list[Path], list[str]]:
    """Download every (station, chunk). Returns (files written, failed chunks).

    - skip_existing: chunks already in landing are not requested again, so an interrupted
      backfill resumes where it stopped instead of starting over.
    - A failing chunk is logged and skipped; the run continues with the next one.
    """
    api_key = config.aemet_api_key()
    stations = stations or list(config.AEMET_STATIONS)
    written: list[Path] = []
    failed: list[str] = []
    for station_id in stations:
        partition = f"station={station_id}"
        for c_start, c_end in chunk_range(start, end, config.AEMET_CHUNK_DAYS):
            if skip_existing and exists(
                landing_root, "aemet", "daily_climate", c_start, c_end, partition
            ):
                continue
            try:
                rows = fetch_chunk(session, api_key, station_id, c_start, c_end)
            except (AemetApiError, requests.RequestException) as e:
                log.error("aemet %s %s..%s FAILED: %s", station_id, c_start, c_end, e)
                failed.append(f"{station_id} {c_start}..{c_end}")
                time.sleep(sleep_seconds * 10)  # back off harder after a failure
                continue
            path = write_raw(
                landing_root,
                source="aemet",
                dataset="daily_climate",
                partition=partition,
                start=c_start,
                end=c_end,
                payload=rows,
                # never store the api_key in the landing files
                request_meta={
                    "station_id": station_id,
                    "url": build_url(station_id, c_start, c_end),
                },
            )
            log.info("aemet %s %s..%s -> %d rows", station_id, c_start, c_end, len(rows))
            written.append(path)
            time.sleep(sleep_seconds)
    return written, failed
