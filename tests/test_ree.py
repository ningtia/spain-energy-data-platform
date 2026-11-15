from datetime import date

import pytest
import responses

from energy_platform import config
from energy_platform.http import make_session
from energy_platform.sources import ree

DS = config.REE_DATASETS["market_prices"]

SAMPLE = {
    "data": {"type": "Precios mercado peninsular en tiempo real"},
    "included": [
        {
            "type": "Spot market price",
            "id": "600",
            "attributes": {
                "title": "Spot market price",
                "values": [
                    {"value": 85.1, "percentage": 0.5, "datetime": "2024-01-01T00:00:00.000+01:00"},
                    {"value": -0.5, "percentage": 0.5, "datetime": "2024-01-01T01:00:00.000+01:00"},
                ],
            },
        }
    ],
}


def test_build_url_and_params():
    assert ree.build_url(DS) == (
        "https://apidatos.ree.es/en/datos/mercados/precios-mercados-tiempo-real"
    )
    assert ree.build_params(DS, date(2024, 1, 1), date(2024, 1, 7)) == {
        "start_date": "2024-01-01T00:00",
        "end_date": "2024-01-07T23:59",
        "time_trunc": "hour",
    }


@responses.activate
def test_ingest_writes_one_file_per_chunk(tmp_path):
    responses.get(ree.build_url(DS), json=SAMPLE)
    paths, failed = ree.ingest(
        make_session(total_retries=0),
        "market_prices",
        date(2024, 1, 1),
        date(2024, 1, 10),
        tmp_path,
    )
    assert len(paths) == 2  # 7-day chunks
    assert failed == []
    assert len(responses.calls) == 2
    # second run skips chunks already in landing: no new requests
    paths2, _ = ree.ingest(
        make_session(total_retries=0),
        "market_prices",
        date(2024, 1, 1),
        date(2024, 1, 10),
        tmp_path,
    )
    assert paths2 == [] and len(responses.calls) == 2
    assert ree.count_values(SAMPLE) == 2


@responses.activate
def test_error_body_with_http_200_raises():
    responses.get(ree.build_url(DS), json={"errors": [{"code": 500, "detail": "bad range"}]})
    with pytest.raises(ree.ReeApiError):
        ree.fetch_chunk(make_session(total_retries=0), DS, date(2024, 1, 1), date(2024, 1, 1))


@responses.activate
def test_failed_chunk_is_reported_and_run_continues(tmp_path):
    responses.get(ree.build_url(DS), status=500)
    responses.get(ree.build_url(DS), json=SAMPLE)
    paths, failed = ree.ingest(
        make_session(total_retries=0),
        "market_prices",
        date(2024, 1, 1),
        date(2024, 1, 10),
        tmp_path,
    )
    assert len(failed) == 1 and len(paths) == 1
