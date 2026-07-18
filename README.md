# Distributed RAG Web Scraper — Minimal Build

## Stack 
- Language: Python 3.11
- Queue: Redis + Celery (workers scaled via `docker compose up --scale worker=N`)
- Database: **PostgreSQL + pgvector** — one database for both relational data
  (raw/cleaned pages, versioned by row) and vector embeddings, via the
  `pgvector/pgvector:pg16` Docker image. No separate vector store needed.
- LLM: Ollama, running locally (`llama3.2:1b` for generation, `nomic-embed-text` for embeddings)
- API: FastAPI
- UI: React via CDN (no npm/node_modules — kept light on disk/RAM)
- Scraping: `requests` + BeautifulSoup (static), Playwright + Chromium (JS-rendered)
- CI: GitHub Actions (lint + test on every push)

## Why these choices 
- **Postgres+pgvector over a dedicated vector DB (Chroma/Pinecone/Weaviate)**:
  keeps relational data and embeddings in one database and one transaction
  boundary — a chunk and its source page can never get out of sync, and
  there's one fewer moving part to run/debug. It's plain Postgres with an
  extension, not a new system to learn. Tradeoff: at very large scale (100M+
  vectors) a dedicated vector DB or `pgvectorscale` can out-perform plain
  pgvector — not a concern at this project's scale.
- **Ollama over OpenAI/Anthropic API**: zero cost, no API key, works offline;
  tradeoff is materially lower answer quality than a hosted frontier model.
- **Overlap-based chunking over fixed-length**: prevents a fact from being
  fully lost at a hard chunk boundary; tradeoff is slightly higher storage/embedding cost from redundant text.

## First-time setup

```bash
git clone https://github.com/Dannaas04/ONRAMP-SCRAPER-RAG.git
cd ONRAMP-SCRAPER-RAG
docker compose up -d redis postgres ollama
docker exec -it scraper-rag-ollama-1 ollama pull llama3.2:1b
docker exec -it scraper-rag-ollama-1 ollama pull nomic-embed-text
docker compose up --build
```

The `vector` extension and all tables (including the pgvector `Vector`
column) are created automatically on API/worker startup via `init_db()` —
no manual SQL needed.

Open the UI: just open `frontend/index.html` directly in your browser (no
build step needed). API docs: http://localhost:8000/docs

To inspect the database directly:
```bash
docker exec -it scraper-rag-postgres-1 psql -U scraper -d scraper_rag
# then: \dt   (list tables)   or   SELECT url, chunk_index FROM chunk LIMIT 5;
```

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
docker exec -it scraper-rag-postgres-1 psql -U scraper -d scraper_rag -c "SELECT * FROM deadletter;"
```

## Testing pagination / large-site target

Use `app/scraper/paginated_scraper.py`'s `discover_paginated_urls()` to walk
a "next page" link on a blog/forum/Wikipedia category page, then enqueue each
discovered URL via `/scrape`. 

## Compliance note 

`app/robots.py` checks `robots.txt` via `urllib.robotparser` before every
fetch and applies a 1-second per-domain delay between requests. Any URL
disallowed by robots.txt raises `PermissionError` instead of being fetched.
