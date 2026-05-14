"""
scrapers/utils.py
=================
Shared HTTP utilities used by all site scrapers:

  - Realistic session with configurable User-Agent
  - build_session()       → plain requests.Session (Playwright-based scrapers)
  - build_cffi_session()  → curl_cffi.Session with Chrome TLS impersonation
                            (bypasses Cloudflare / Akamai TLS fingerprinting)
  - Polite random delay between requests
  - Exponential-backoff retry on 5xx / 429
  - robots.txt pre-flight check (fails loudly if disallowed)

Why curl_cffi?
--------------
Sites like fr.primor.eu and www.nocibe.fr use bot-protection stacks
(Cloudflare, Akamai) that reject requests whose TLS ClientHello doesn't
match a real browser fingerprint.  Plain requests/urllib3 is trivially
detected.  curl_cffi wraps libcurl with BoringSSL and can impersonate
Chrome's exact TLS fingerprint, resolving 400/403 responses.
"""
from __future__ import annotations

import logging
import os
import random
import time
import urllib.robotparser
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from env with sane defaults)
# ---------------------------------------------------------------------------

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

USER_AGENT: str = os.getenv("SCRAPER_USER_AGENT", DEFAULT_USER_AGENT)
REQUEST_DELAY_MS: int = int(os.getenv("SCRAPER_REQUEST_DELAY_MS", "750"))

# Jitter window: ± 50 % of the configured delay
_DELAY_JITTER = 0.5

# Chrome version to impersonate with curl_cffi
_CFFI_IMPERSONATE = "chrome110"


# ---------------------------------------------------------------------------
# Session factories
# ---------------------------------------------------------------------------

def build_session(
    *,
    retries: int = 3,
    backoff_factor: float = 1.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> Session:
    """Return a plain requests.Session with retry logic and a realistic User-Agent.

    Use this only when curl_cffi is not needed (e.g. the Frizbit CDN or
    other APIs that do not check TLS fingerprints).
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def build_cffi_session() -> Any:
    """Return a curl_cffi Session that impersonates Chrome's TLS fingerprint.

    This bypasses bot-protection stacks (Cloudflare, Akamai) that reject
    plain requests/urllib3 based on their TLS ClientHello signature.

    Returns a curl_cffi.requests.Session instance.  Its interface is
    intentionally compatible with requests.Session for GET calls.

    Falls back to a plain requests.Session with a warning if curl_cffi is
    not installed (so the codebase stays importable in environments where
    the dependency hasn't been installed yet).
    """
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore[import]

        session = cffi_requests.Session(impersonate=_CFFI_IMPERSONATE)
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        logger.debug("curl_cffi session created (impersonate=%s)", _CFFI_IMPERSONATE)
        return session
    except ImportError:
        logger.warning(
            "curl_cffi not installed — falling back to plain requests.Session. "
            "Bot-protected sites (Primor, Nocibé) will likely return 400/403. "
            "Install with: pip install curl_cffi"
        )
        return build_session()


# ---------------------------------------------------------------------------
# Polite delay
# ---------------------------------------------------------------------------

def polite_delay() -> None:
    """Sleep for REQUEST_DELAY_MS ± jitter milliseconds."""
    base_s = REQUEST_DELAY_MS / 1000.0
    jitter = base_s * _DELAY_JITTER
    delay = random.uniform(base_s - jitter, base_s + jitter)
    delay = max(delay, 0.2)  # never less than 200 ms
    logger.debug("polite_delay: sleeping %.2f s", delay)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# robots.txt guard
# ---------------------------------------------------------------------------

@lru_cache(maxsize=16)
def _get_robots_parser(base_url: str) -> urllib.robotparser.RobotFileParser:
    """Fetch and parse robots.txt for *base_url* (cached per origin)."""
    rp = urllib.robotparser.RobotFileParser()
    robots_url = base_url.rstrip("/") + "/robots.txt"
    rp.set_url(robots_url)
    try:
        rp.read()
        logger.debug("robots.txt loaded for %s", base_url)
    except Exception as exc:  # noqa: BLE001
        # If we can't fetch robots.txt, be conservative and allow (logged).
        logger.warning("Could not fetch robots.txt from %s: %s — assuming allowed", base_url, exc)
    return rp


def check_robots(url: str, *, user_agent: str = "*") -> None:
    """Raise RuntimeError if *url* is disallowed by the site's robots.txt.

    Call this once at scraper startup for each domain.
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = _get_robots_parser(base)
    if not rp.can_fetch(user_agent, url):
        raise RuntimeError(
            f"robots.txt disallows scraping {url} for user-agent '{user_agent}'. "
            "Aborting scraper. Respect the site's crawling policy."
        )
    logger.info("robots.txt OK: %s is allowed", url)


# ---------------------------------------------------------------------------
# Convenience GET with politeness + robots guard
# ---------------------------------------------------------------------------

def polite_get(
    session: Any,
    url: str,
    *,
    check_robots_first: bool = False,
    **kwargs: Any,
) -> Any:
    """GET *url* with a polite delay before the request.

    Works with both requests.Session and curl_cffi.Session.

    Set ``check_robots_first=True`` for the first request to a domain during
    a scrape pass.  Subsequent requests to the same domain can skip it.
    """
    if check_robots_first:
        check_robots(url)
    polite_delay()
    response = session.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response
