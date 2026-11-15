import os
from pathlib import Path

from energy_platform.upload import _signature, files_to_upload


def _make(root: Path, rel: str, text: str) -> Path:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return f


def test_only_new_or_changed_files_are_uploaded(tmp_path):
    a = _make(tmp_path, "ree/demand/date=2024-01-01/a.json", "{}")
    b = _make(tmp_path, "ree/demand/date=2024-02-01/b.json", "{}")
    assert files_to_upload(tmp_path, {}) == [a, b]

    manifest = {
        "ree/demand/date=2024-01-01/a.json": _signature(a),
        "ree/demand/date=2024-02-01/b.json": _signature(b),
    }
    assert files_to_upload(tmp_path, manifest) == []

    b.write_text('{"changed": true}')
    os.utime(b, (b.stat().st_atime, b.stat().st_mtime + 10))
    assert files_to_upload(tmp_path, manifest) == [b]
