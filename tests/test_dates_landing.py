import json
from datetime import date

import pytest

from energy_platform.dates import chunk_range
from energy_platform.landing import landing_path, write_raw


def test_chunk_range_covers_range_without_gaps_or_overlap():
    chunks = list(chunk_range(date(2024, 1, 1), date(2024, 1, 10), 4))
    assert chunks == [
        (date(2024, 1, 1), date(2024, 1, 4)),
        (date(2024, 1, 5), date(2024, 1, 8)),
        (date(2024, 1, 9), date(2024, 1, 10)),
    ]


def test_chunk_range_single_day():
    assert list(chunk_range(date(2024, 3, 31), date(2024, 3, 31), 7)) == [
        (date(2024, 3, 31), date(2024, 3, 31))
    ]


def test_chunk_range_rejects_reversed_range():
    with pytest.raises(ValueError):
        list(chunk_range(date(2024, 1, 2), date(2024, 1, 1), 7))


def test_landing_path_with_partition(tmp_path):
    p = landing_path(
        tmp_path, "aemet", "daily_climate", date(2024, 1, 1), date(2024, 1, 30), "station=3195"
    )
    assert p.relative_to(tmp_path).as_posix() == (
        "aemet/daily_climate/station=3195/date=2024-01-01/2024-01-01_2024-01-30.json"
    )


def test_write_raw_is_idempotent(tmp_path):
    args = dict(
        root=tmp_path,
        source="ree",
        dataset="demand",
        start=date(2024, 1, 1),
        end=date(2024, 1, 2),
        request_meta={},
    )
    p1 = write_raw(payload={"v": 1}, **args)
    p2 = write_raw(payload={"v": 2}, **args)
    assert p1 == p2
    assert len(list(tmp_path.rglob("*.json"))) == 1
    env = json.loads(p2.read_text())
    assert env["payload"] == {"v": 2}
    assert {"source", "dataset", "chunk_start", "chunk_end", "ingested_at"} <= env.keys()
