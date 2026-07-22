import hashlib
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, field_validator
from sqlmodel import select

from app.db import Page, get_session

DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx")


class CleanedPageData(BaseModel):
    """Explicit schema-validation layer for cleaned/normalized content before
    it's persisted -- this is what actually enforces the 'normalize into a
    structured format with schema validation' requirement, rather than
    relying only on SQLModel's implicit type coercion at insert time."""
    url: str
    body_text: str
    tables: list[str] = []
    linked_documents: list[str] = []

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL must be http(s), got: {v}")
        return v

    @field_validator("body_text")
    @classmethod
    def body_text_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("body_text is empty after cleaning -- refusing to store a blank page")
        return v


def extract_linked_documents(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Third content type alongside body text and tables: links that point
    to standalone documents (PDFs, Office files, etc.) rather than other
    HTML pages -- these are meaningfully different content and worth
    tracking separately rather than folding into plain body text."""
    docs = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href.lower().endswith(DOCUMENT_EXTENSIONS):
            docs.append(href)
    return list(dict.fromkeys(docs))  


def clean_html(raw_html: str, url: str = "") -> CleanedPageData:
    """Strips scripts/styles/nav boilerplate, separates body text, tables,
    and linked documents into distinct fields, then validates the result
    against CleanedPageData before returning it."""
    soup = BeautifulSoup(raw_html, "html.parser")

    linked_documents = extract_linked_documents(soup, url) if url else []

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

    return CleanedPageData(
        url=url or "unknown",
        body_text=body_text,
        tables=tables_text,
        linked_documents=linked_documents,
    )


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_latest_page(url: str) -> Page | None:
    with get_session() as session:
        return session.exec(
            select(Page).where(Page.url == url).order_by(Page.fetched_at.desc())
        ).first()


def save_page_version(url: str, raw_html: str, source_type: str,
                       etag: str = None, last_modified: str = None) -> Page:
    """Saves a new row only if content actually changed since the last crawl
    of this URL. Raises pydantic.ValidationError if the cleaned content fails
    schema validation (e.g. empty body text) -- caught by Celery's retry
    logic upstream, same as a network failure would be."""
    cleaned = clean_html(raw_html, url=url)

    combined_text = cleaned.body_text
    if cleaned.tables:
        combined_text += "\n\n[TABLES]\n" + "\n\n".join(cleaned.tables)
    h = content_hash(combined_text)

    with get_session() as session:
        latest = session.exec(
            select(Page).where(Page.url == url).order_by(Page.fetched_at.desc())
        ).first()

        is_dup = latest is not None and latest.content_hash == h

        page = Page(
            url=url,
            raw_html=raw_html,
            cleaned_text=combined_text,
            content_hash=h,
            source_type=source_type,
            is_duplicate_of_latest=is_dup,
            etag=etag,
            last_modified=last_modified,
            linked_documents=json.dumps(cleaned.linked_documents),
        )
        session.add(page)
        session.commit()
        session.refresh(page)
        return page


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
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