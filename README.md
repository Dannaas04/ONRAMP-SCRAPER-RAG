# Distributed RAG Web Scraper — Minimal Build

## Stack 
- Language: Python 3.11
- Queue: Redis + Celery (workers scaled via `docker compose up --scale worker=N`)
- DB: SQLite (file-based, no separate container — versioned by row, not overwritten)
- Vector store: Chroma, running embedded in-process (no server container)
- LLM: Ollama, running locally (`llama3.2:1b` for generation, `nomic-embed-text` for embeddings) (Might change later)
- API: FastAPI
- UI: React via CDN (no npm/node_modules — kept light on disk/RAM)
- Scraping: `requests` + BeautifulSoup (static), Playwright + Chromium (JS-rendered)
- CI: GitHub Actions (lint + test on every push)

## Why these choices 
- **SQLite over Postgres**: no extra container/daemon running in the background;
  fine for a project of this scale; tradeoff is it doesn't handle concurrent
  writes as well, which matters less here since only workers write and API mostly reads.
- **Chroma embedded over a Chroma/Pinecone/Weaviate server**: removes a whole
  container from the stack; tradeoff is it can't be queried by multiple
  processes over the network the way a server-mode vector DB could.
- **Ollama over OpenAI/Anthropic API**: zero cost, no API key, works offline;
  tradeoff is materially lower answer quality than a hosted frontier model.
- **Overlap-based chunking over fixed-length**: prevents a fact from being
  fully lost at a hard chunk boundary; tradeoff is slightly higher storage/embedding cost from redundant text.

## First-time setup

```bash
git clone https://github.com/Dannaas04/ONRAMP-SCRAPER-RAG.git
cd ONRAMP-SCRAPER-RAG
docker compose up -d redis ollama
docker exec -it scraper-rag-ollama-1 ollama pull llama3.2:1b
docker exec -it scraper-rag-ollama-1 ollama pull nomic-embed-text
docker compose up --build
```

Open the UI: just open `frontend/index.html` directly in your browser (no
build step needed). API docs: http://localhost:8000/docs

## Demonstrating horizontal scaling 

```bash
# baseline: 1 worker
docker compose up --scale worker=1 -d
time (for u in $(cat urls.txt); do curl -X POST localhost:8000/scrape -d "{\"url\":\"$u\"}" -H "Content-Type: application/json"; done)

# then: 3 workers
docker compose up --scale worker=3 -d
# repeat the same batch and compare wall-clock time
```

## Demonstrating fault tolerance

```bash
# submit a URL that will 404 or an unreachable host to see retries in worker logs
curl -X POST localhost:8000/scrape -d '{"url":"http://localhost:9999/nope"}' -H "Content-Type: application/json"
# after 3 retries with backoff, check the dead-letter table:
docker exec -it scraper-rag-api-1 python -c "
from app.db import get_session, DeadLetter
from sqlmodel import select
with get_session() as s:
    print(s.exec(select(DeadLetter)).all())
"
```

## Testing pagination / large-site target

Use `app/scraper/paginated_scraper.py`'s `discover_paginated_urls()` to walk
a "next page" link on a blog/forum/Wikipedia category page, then enqueue each
discovered URL via `/scrape`. 

## Compliance note 

`app/robots.py` checks `robots.txt` via `urllib.robotparser` before every
fetch and applies a 1-second per-domain delay between requests. Any URL
disallowed by robots.txt raises `PermissionError` instead of being fetched.
