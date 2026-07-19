from bs4 import BeautifulSoup

from app.scraper.static_scraper import fetch_static

MAX_PAGES_DEFAULT = 500


def discover_paginated_urls(start_url: str, next_link_selector: str,
                            max_pages: int = MAX_PAGES_DEFAULT) -> list[str]:
    """Follows a 'next page' link (CSS selector) repeatedly to build a list
    of URLs to enqueue. Kept separate from actual fetching so discovery
    can be capped/aborted without wasting scrape work.

    Example: a paginated blog might use next_link_selector='a.next-page'
    """
    urls = [start_url]
    current = start_url

    while len(urls) < max_pages:
        page = fetch_static(current)
        soup = BeautifulSoup(page["raw_html"], "html.parser")
        next_tag = soup.select_one(next_link_selector)
        if not next_tag or not next_tag.get("href"):
            break
        next_url = next_tag["href"]
        if next_url in urls:
            break
        urls.append(next_url)
        current = next_url

    return urls
