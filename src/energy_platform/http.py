"""HTTP session with retries and exponential backoff."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "spain-energy-data-platform/0.1 (portfolio project)"


def make_session(total_retries: int = 5, backoff: float = 2.0) -> requests.Session:
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff,  # waits 2s, 4s, 8s, ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session
