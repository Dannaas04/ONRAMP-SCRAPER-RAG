import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse

_parsers = {}
_last_fetch = {}

MIN_DELAY_SECONDS = 1.0


def _get_parser(url: str) -> robotparser.RobotFileParser:
    domain = urlparse(url).netloc
    if domain not in _parsers:
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{urlparse(url).scheme}://{domain}/robots.txt")
        try:
            rp.read()
        except Exception:

            pass
        _parsers[domain] = rp
    return _parsers[domain]


def is_allowed(url: str, user_agent: str = "ScraperRAGBot") -> bool:
    parser = _get_parser(url)
    return parser.can_fetch(user_agent, url)


def wait_for_politeness(url: str):
    """Blocks just long enough to respect per-domain rate limiting."""
    domain = urlparse(url).netloc
    now = time.time()
    last = _last_fetch.get(domain, 0)
    elapsed = now - last
    if elapsed < MIN_DELAY_SECONDS:
        time.sleep(MIN_DELAY_SECONDS - elapsed)
    _last_fetch[domain] = time.time()
