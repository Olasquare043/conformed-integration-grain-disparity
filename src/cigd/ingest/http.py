"""One HTTP session for every download, with an honest User-Agent and retries."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cigd import __version__

USER_AGENT = (
    f"cigd-research-pipeline/{__version__} "
    "(+https://github.com/Olasquare043/conformed-integration-grain-disparity)"
)
TIMEOUT_SECONDS = 120


def make_session() -> requests.Session:
    """Return a session that retries transient server errors with backoff."""
    retry_policy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry_policy))
    return session
