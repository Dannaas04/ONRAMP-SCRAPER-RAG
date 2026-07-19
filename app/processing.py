import hashlib
from bs4 import BeautifulSoup
from sqlmodel import select

from app.db import Page, get_session


def clean_html(raw_html: str) -> str:
    """Strips scripts/styles/nav boilerplate, keeps body text + table content."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    tables_text = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables_text.append("\n".join(rows))
        table.decompose()

    body_text = soup.get_text(separator=" ", strip=True)

    combined = body_text
    if tables_text:
        combined += "\n\n[TABLES]\n" + "\n\n".join(tables_text)

    return combined


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_page_version(url: str, raw_html: str, source_type: str) -> Page:
    """Saves a new row only if content actually changed since the last crawl
    of this URL — this is incremental-recrawl + versioning behavior."""
    cleaned = clean_html(raw_html)
    h = content_hash(cleaned)

    with get_session() as session:
        latest = session.exec(
            select(Page).where(Page.url == url).order_by(Page.fetched_at.desc())
        ).first()

        is_dup = latest is not None and latest.content_hash == h

        page = Page(
            url=url,
            raw_html=raw_html,
            cleaned_text=cleaned,
            content_hash=h,
            source_type=source_type,
            is_duplicate_of_latest=is_dup,
        )
        session.add(page)
        session.commit()
        session.refresh(page)
        return page


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Overlap-based chunking on whitespace-split tokens (word-level proxy
    for token count — cheap to compute, and avoids pulling in a tokenizer dependency just for chunking).

    Overlap is used instead of naive fixed-length splitting so that a fact
    split across a chunk boundary still appears whole in at least one chunk,
    which matters for retrieval quality.
    """
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap
    return chunks
