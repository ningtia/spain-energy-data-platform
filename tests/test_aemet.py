import json
from datetime import date

import pytest
import responses

from energy_platform.http import make_session
from energy_platform.sources import aemet

DATOS_URL = "https://opendata.aemet.es/opendata/sh/abc123"
ROWS = [
    {
        "fecha": "2024-01-01",
        "indicativo": "3195",
        "nombre": "MADRID, RETIRO",
        "tmed": "8,4",
        "tmin": "3,1",
        "tmax": "13,7",
        "prec": "0,0",
    }
]


def test_build_url():
    url = aemet.build_url("3195", date(2024, 1, 1), date(2024, 1, 30))
    assert url.endswith(
        "/valores/climatologicos/diarios/datos/fechaini/2024-01-01T00:00:00UTC"
        "/fechafin/2024-01-30T23:59:59UTC/estacion/3195"
    )


@responses.activate
def test_two_step_fetch_and_latin1_decoding():
    responses.get(
        aemet.build_url("3195", date(2024, 1, 1), date(2024, 1, 1)),
        json={"estado": 200, "datos": DATOS_URL},
    )
    # Serve Latin-1 bytes, as AEMET does
    responses.get(
        DATOS_URL,
        body=json.dumps(ROWS, ensure_ascii=False).encode("latin-1"),
        content_type="text/plain",
    )
    rows = aemet.fetch_chunk(
        make_session(total_retries=0), "KEY", "3195", date(2024, 1, 1), date(2024, 1, 1)
    )
    assert rows[0]["tmed"] == "8,4"
    assert responses.calls[0].request.headers["api_key"] == "KEY"


@responses.activate
def test_no_data_returns_empty_list():
    responses.get(
        aemet.build_url("3195", date(2024, 1, 1), date(2024, 1, 1)),
        json={"estado": 404, "descripcion": "No hay datos que satisfagan esos criterios"},
        status=404,
    )
    assert (
        aemet.fetch_chunk(
            make_session(total_retries=0), "KEY", "3195", date(2024, 1, 1), date(2024, 1, 1)
        )
        == []
    )


@responses.activate
def test_bad_key_raises():
    responses.get(
        aemet.build_url("3195", date(2024, 1, 1), date(2024, 1, 1)),
        json={"estado": 401, "descripcion": "API key invalido"},
        status=401,
    )
    with pytest.raises(aemet.AemetApiError):
        aemet.fetch_chunk(
            make_session(total_retries=0), "BAD", "3195", date(2024, 1, 1), date(2024, 1, 1)
        )


@responses.activate
def test_ingest_never_writes_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AEMET_API_KEY", "SECRET-KEY")
    responses.get(
        aemet.build_url("3195", date(2024, 1, 1), date(2024, 1, 1)),
        json={"estado": 200, "datos": DATOS_URL},
    )
    responses.get(DATOS_URL, json=ROWS)
    paths, failed = aemet.ingest(
        make_session(total_retries=0),
        date(2024, 1, 1),
        date(2024, 1, 1),
        tmp_path,
        stations=["3195"],
        sleep_seconds=0,
    )
    assert failed == []
    assert "station=3195" in paths[0].as_posix()
    assert "SECRET-KEY" not in paths[0].read_text()


@responses.activate
def test_rate_limited_chunk_fails_without_stopping_the_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AEMET_API_KEY", "KEY")
    monkeypatch.setattr(aemet.time, "sleep", lambda s: None)
    url1 = aemet.build_url("3195", date(2024, 1, 1), date(2024, 1, 30))
    url2 = aemet.build_url("3195", date(2024, 1, 31), date(2024, 2, 1))
    responses.get(url1, json={"estado": 429}, status=429)
    responses.get(url2, json={"estado": 200, "datos": DATOS_URL})
    responses.get(DATOS_URL, json=ROWS)
    paths, failed = aemet.ingest(
        make_session(total_retries=0),
        date(2024, 1, 1),
        date(2024, 2, 1),
        tmp_path,
        stations=["3195"],
        sleep_seconds=0,
    )
    assert len(failed) == 1 and len(paths) == 1
