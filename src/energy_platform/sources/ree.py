"""Red Eléctrica (REE) REData API client. No token required.

Docs: https://www.ree.es/en/apidatos
URL pattern: /{lang}/datos/{category}/{widget}?start_date=...&end_date=...&time_trunc=...
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import requests

from energy_platform import config
from energy_platform.dates import chunk_range
from energy_platform.landing import exists, write_raw

log = logging.getLogger(__name__)


class ReeApiError(RuntimeError):
    pass


def build_url(ds: config.ReeDataset) -> str:
    return f"{config.REE_BASE_URL}/{config.REE_LANG}/datos/{ds.category}/{ds.widget}"


def build_params(ds: config.ReeDataset, start: date, end: date) -> dict[str, str]:
    return {
        "start_date": f"{start.isoformat()}T00:00",
        "end_date": f"{end.isoformat()}T23:59",
        "time_trunc": ds.time_trunc,
    }


def fetch_chunk(
    session: requests.Session, ds: config.ReeDataset, start: date, end: date
) -> dict[str, Any]:
    url = build_url(ds)
    params = build_params(ds, start, end)
    resp = session.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        raise ReeApiError(f"{ds.name} {start}..{end}: HTTP {resp.status_code} {resp.text[:300]}")
    body = resp.json()
    # REData returns {"errors": [...]} with HTTP 200 in some failure cases.
    if "errors" in body:
        raise ReeApiError(f"{ds.name} {start}..{end}: {body['errors']}")
    if "included" not in body:
        raise ReeApiError(f"{ds.name} {start}..{end}: unexpected response keys {list(body)}")
    return body


def count_values(body: dict[str, Any]) -> int:
    return sum(len(item.get("attributes", {}).get("values", [])) for item in body["included"])


def ingest(
    session: requests.Session,
    dataset_name: str,
    start: date,
    end: date,
    landing_root: Path,
    skip_existing: bool = True,
) -> tuple[list[Path], list[str]]:
    """Download every chunk of one dataset. Returns (files written, failed chunks)."""
    ds = config.REE_DATASETS[dataset_name]
    written: list[Path] = []
    failed: list[str] = []
    for c_start, c_end in chunk_range(start, end, ds.chunk_days):
        if skip_existing and exists(landing_root, "ree", ds.name, c_start, c_end):
            continue
        try:
            body = fetch_chunk(session, ds, c_start, c_end)
        except (ReeApiError, requests.RequestException) as e:
            log.error("ree/%s %s..%s FAILED: %s", ds.name, c_start, c_end, e)
            failed.append(f"{ds.name} {c_start}..{c_end}")
            continue
        path = write_raw(
            landing_root,
            source="ree",
            dataset=ds.name,
            start=c_start,
            end=c_end,
            payload=body,
            request_meta={"url": build_url(ds), "params": build_params(ds, c_start, c_end)},
        )
        log.info("ree/%s %s..%s -> %d values", ds.name, c_start, c_end, count_values(body))
        written.append(path)
    return written, failed
