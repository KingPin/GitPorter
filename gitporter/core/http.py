import re
import time
import logging
import requests

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def parse_next_link(link_header: str | None) -> str | None:
    """Extract the 'next' URL from a Link response header."""
    if not link_header:
        return None
    m = _LINK_RE.search(link_header)
    return m.group(1) if m else None


def http_get_with_backoff(
    session: requests.Session,
    url: str,
    max_retries: int = 5,
    initial_delay: float = 10.0,
    **kwargs,
) -> requests.Response:
    """GET a URL with exponential backoff on 403/429 rate limits.

    Raises requests.HTTPError on non-200, non-rate-limit responses.
    Raises requests.HTTPError after exhausting max_retries on rate limits.
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        response = session.get(url, **kwargs)
        if response.status_code == 200:
            return response
        if response.status_code in (403, 429):
            logger.warning(
                "Rate limited (HTTP %s). Sleeping %.0fs (attempt %d/%d)...",
                response.status_code, delay, attempt, max_retries,
            )
            time.sleep(delay)
            delay *= 2
        else:
            response.raise_for_status()
    raise requests.HTTPError(f"Exceeded {max_retries} retries for {url}")
