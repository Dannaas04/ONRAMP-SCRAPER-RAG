from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.db import init_db, get_session, Page
from app.tasks import scrape_url
from app.rag import retrieve, generate_answer

app = FastAPI(title="Distributed RAG Scraper API")
init_db()


class ScrapeRequest(BaseModel):
    url: str
    source_type: str = "static"  


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


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
