from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlmodel import select
import json
from app.db import init_db, get_session, Page
from app.tasks import scrape_url
from app.rag import retrieve, generate_answer
from app.scraper.paginated_scraper import discover_paginated_urls
app = FastAPI(title="Distributed RAG Scraper API")
init_db()


class ScrapeRequest(BaseModel):
    url: str
    source_type: str = "static"


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class DiscoverRequest(BaseModel):
    start_url: str
    next_link_selector: str
    max_pages: int = 30


@app.post("/discover-and-enqueue")
def discover_and_enqueue(req: DiscoverRequest):
    """Walks the 'next page' link to build a URL list (the pagination /
    large-site requirement), then enqueues every discovered URL onto the
    distributed worker pool in one call."""
    urls = discover_paginated_urls(req.start_url, req.next_link_selector, req.max_pages)
    task_ids = [scrape_url.delay(u, "static").id for u in urls]
    return {"discovered": len(urls), "urls": urls, "task_ids": task_ids}

@app.post("/scrape")
def enqueue_scrape(req: ScrapeRequest):
    """Enqueues a scrape job onto the distributed worker pool instead of
    scraping inline — this is what makes the API non-blocking and lets
    work fan out across worker containers."""
    task = scrape_url.delay(req.url, req.source_type)
    return {"task_id": task.id, "status": "queued"}


@app.get("/pages")
def list_raw_pages(limit: int = 20):
    with get_session() as session:
        pages = session.exec(
            select(Page).order_by(Page.fetched_at.desc()).limit(limit)
        ).all()
        return pages


@app.get("/pages/{url:path}/versions")
def page_versions(url: str):
    """Returns full version history for a URL (proves versioning works)."""
    with get_session() as session:
        versions = session.exec(
            select(Page).where(Page.url == url).order_by(Page.fetched_at.desc())
        ).all()
        if not versions:
            raise HTTPException(404, "No crawls found for this URL")
        return versions

@app.get("/pages/{url:path}/processed")
def processed_page(url: str):
    """Returns the normalized/structured breakdown of the latest crawl of a
    URL -- body text, extracted tables, and linked documents -- demonstrating
    content was separated by type rather than stored as one blob."""
    with get_session() as session:
        latest = session.exec(
            select(Page).where(Page.url == url).order_by(Page.fetched_at.desc())
        ).first()
        if not latest:
            raise HTTPException(404, "No crawls found for this URL")

        body_and_tables = latest.cleaned_text.split("\n\n[TABLES]\n", 1)
        return {
            "url": latest.url,
            "source_type": latest.source_type,
            "fetched_at": latest.fetched_at,
            "body_text": body_and_tables[0],
            "tables": body_and_tables[1].split("\n\n") if len(body_and_tables) > 1 else [],
            "linked_documents": json.loads(latest.linked_documents or "[]"),
        }

@app.get("/search")
def semantic_search(q: str, top_k: int = 5):
    """Semantic search against the vector index."""
    return retrieve(q, top_k=top_k)


@app.post("/ask")
def ask_question(req: QueryRequest):
    """Grounded QA endpoint: retrieves relevant chunks (possibly across
    multiple source URLs) and returns an LLM-generated answer with the
    source URLs actually used."""
    return generate_answer(req.query, top_k=req.top_k)
