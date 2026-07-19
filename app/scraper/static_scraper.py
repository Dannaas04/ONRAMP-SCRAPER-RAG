import requests
from bs4 import BeautifulSoup

from app.robots import is_allowed, wait_for_politeness

HEADERS = {"User-Agent": "ScraperRAGBot/1.0 (student project; contact: you@example.com)"}


def fetch_static(url: str, timeout: int = 10) -> dict:
    """Fetches a static HTML page. Raises on disallowed / network failure
    so Celery's retry logic can handle it."""
    if not is_allowed(url):
        raise PermissionError(f"robots.txt disallows fetching {url}")

    wait_for_politeness(url)
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    return {
        "url": url,
        "raw_html": resp.text,
        "title": soup.title.string if soup.title else "",
        "source_type": "static",
    }
