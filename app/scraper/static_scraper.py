import requests
from bs4 import BeautifulSoup

from app.robots import is_allowed, wait_for_politeness

HEADERS = {"User-Agent": "ScraperRAGBot/1.0 (student project; contact: you@example.com)"}


def fetch_static(url: str, prev_etag: str = None, prev_last_modified: str = None,
                  timeout: int = 10) -> dict:
    """Uses conditional GET when we have prior ETag/Last-Modified values --
    this is what actually skips re-fetching a page that hasn't changed.
    Returns {"not_modified": True} on a 304 response."""
    if not is_allowed(url):
        raise PermissionError(f"robots.txt disallows fetching {url}")

    wait_for_politeness(url)

    conditional_headers = dict(HEADERS)
    if prev_etag:
        conditional_headers["If-None-Match"] = prev_etag
    if prev_last_modified:
        conditional_headers["If-Modified-Since"] = prev_last_modified

    resp = requests.get(url, headers=conditional_headers, timeout=timeout)

    if resp.status_code == 304:
        return {"url": url, "not_modified": True, "source_type": "static"}

    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    return {
        "url": url,
        "raw_html": resp.text,
        "title": soup.title.string if soup.title else "",
        "source_type": "static",
        "not_modified": False,
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
    }