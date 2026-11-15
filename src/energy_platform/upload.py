"""Upload the local landing zone to a Databricks Unity Catalog volume.

Incremental: a small manifest (data/.upload_manifest.json) remembers the size and modification
time of every file already uploaded, so each run only sends new or changed files.

Why this matters: Bronze uses Auto Loader with `allowOverwrites`, so a re-uploaded file is
ingested again. Uploading only what changed keeps Bronze free of needless copies, while files
that really changed (e.g. the daily job re-pulling the last 7 days) are picked up.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def _signature(f: Path) -> list[float]:
    st = f.stat()
    return [st.st_size, st.st_mtime]


def files_to_upload(landing_root: Path, manifest: dict[str, list[float]]) -> list[Path]:
    """Files that are new or whose size/mtime changed since the last upload."""
    out = []
    for f in sorted(landing_root.rglob("*.json")):
        rel = f.relative_to(landing_root).as_posix()
        if manifest.get(rel) != _signature(f):
            out.append(f)
    return out


def upload_landing(
    landing_root: Path, volume_path: str | None = None, manifest_path: Path | None = None
) -> int:
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('Install extras first: pip install -e ".[databricks]"') from e

    volume_path = (volume_path or os.environ["DATABRICKS_VOLUME_PATH"]).rstrip("/")
    manifest_path = manifest_path or landing_root.parent / ".upload_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    todo = files_to_upload(landing_root, manifest)
    log.info("%d new/changed files to upload (of %d)", len(todo), len(manifest) + len(todo))

    w = WorkspaceClient()  # reads DATABRICKS_HOST / DATABRICKS_TOKEN from the environment
    for i, f in enumerate(todo, 1):
        rel = f.relative_to(landing_root).as_posix()
        with f.open("rb") as fh:
            w.files.upload(f"{volume_path}/{rel}", fh, overwrite=True)
        manifest[rel] = _signature(f)
        if i % 100 == 0 or i == len(todo):
            # save progress regularly so an interrupted upload resumes
            manifest_path.write_text(json.dumps(manifest))
            log.info("uploaded %d/%d", i, len(todo))
    return len(todo)
