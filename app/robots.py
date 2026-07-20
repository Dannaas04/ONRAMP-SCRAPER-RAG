import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse

import requests

_parsers = {}
_last_fetch = {}

MIN_DELAY_SECONDS = 1.0  


ROBOTS_FETCH_HEADERS = {
    "User-Agent": "ScraperRAGBot/1.0 (student project; contact: danasayegh49@gmail.com)"
}


def _get_parser(url: str) -> robotparser.RobotFileParser:
    domain = urlparse(url).netloc
    if domain not in _parsers:
        robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)

        try:
            resp = requests.get(robots_url, headers=ROBOTS_FETCH_HEADERS, timeout=10)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            elif 400 <= resp.status_code < 500:
               
                rp.allow_all = True
            else:
  
                rp.allow_all = True
        except Exception:
          
            rp.allow_all = True

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