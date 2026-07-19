from playwright.sync_api import sync_playwright

from app.robots import is_allowed, wait_for_politeness


def fetch_js_rendered(url: str, wait_ms: int = 1500) -> dict:
    """Renders a JS-heavy page with a headless browser and returns the DOM
    after client-side rendering has completed."""
    if not is_allowed(url):
        raise PermissionError(f"robots.txt disallows fetching {url}")

    wait_for_politeness(url)

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=20000)
        page.wait_for_timeout(wait_ms)
        html = page.content()
        title = page.title()
        browser.close()

    return {
        "url": url,
        "raw_html": html,
        "title": title,
        "source_type": "js_rendered",
    }
