"""Landing zone: raw API responses written to disk exactly as received.

Layout:
    <landing>/<source>/<dataset>/[<partition>/]date=<chunk_start>/<chunk_start>_<chunk_end>.json

The file name is deterministic, so re-running the same range overwrites the same file
instead of creating duplicates (idempotent landing). Bronze is append-only; duplicates
that reach Bronze through re-uploads are removed in Silver.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def landing_path(
    root: Path, source: str, dataset: str, start: date, end: date, partition: str | None = None
) -> Path:
    base = root / source / dataset
    if partition:  # e.g. "station=3195"
        base = base / partition
    return base / f"date={start.isoformat()}" / f"{start}_{end}.json"


def exists(
    root: Path, source: str, dataset: str, start: date, end: date, partition: str | None = None
) -> bool:
    return landing_path(root, source, dataset, start, end, partition).exists()


def write_raw(
    root: Path,
    source: str,
    dataset: str,
    start: date,
    end: date,
    payload: Any,
    request_meta: dict[str, Any],
    partition: str | None = None,
) -> Path:
    """Wrap the payload with ingestion metadata and write it atomically."""
    path = landing_path(root, source, dataset, start, end, partition)
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "source": source,
        "dataset": dataset,
        "chunk_start": start.isoformat(),
        "chunk_end": end.isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "request": request_meta,
        "payload": payload,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic on the same filesystem: no half-written files
    return path
