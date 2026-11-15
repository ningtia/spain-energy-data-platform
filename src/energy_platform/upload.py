"""Upload the local landing zone to a Databricks Unity Catalog volume.

Uses the Databricks SDK Files API. Relative paths are preserved, so the volume mirrors
the local layout and the Bronze notebook can read it with Auto Loader.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def upload_landing(landing_root: Path, volume_path: str | None = None) -> int:
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('Install extras first: pip install -e ".[databricks]"') from e

    volume_path = (volume_path or os.environ["DATABRICKS_VOLUME_PATH"]).rstrip("/")
    w = WorkspaceClient()  # reads DATABRICKS_HOST / DATABRICKS_TOKEN from the environment
    n = 0
    for f in sorted(landing_root.rglob("*.json")):
        target = f"{volume_path}/{f.relative_to(landing_root).as_posix()}"
        with f.open("rb") as fh:
            w.files.upload(target, fh, overwrite=True)
        n += 1
        log.debug("uploaded %s", target)
    log.info("uploaded %d files to %s", n, volume_path)
    return n
