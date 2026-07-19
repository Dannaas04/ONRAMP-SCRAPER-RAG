import httpx
from sqlmodel import select

from app.config import OLLAMA_URL, EMBED_MODEL, GEN_MODEL
from app.db import Chunk, get_session


def embed(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def index_chunks(url: str, page_id: int, chunks: list[str]):
    """Embeds and stores chunks directly in Postgres via pgvector -- same
    database/transaction boundary as the raw page data, no separate store."""
    with get_session() as session:
        for i, chunk_text in enumerate(chunks):
            vector = embed(chunk_text)
            session.add(
                Chunk(
                    page_id=page_id,
                    url=url,
                    chunk_index=i,
                    text=chunk_text,
                    embedding=vector,
                )
            )
        session.commit()


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Cosine-distance nearest neighbor search using pgvector's <=> operator
    (exposed here via the .cosine_distance() comparator)."""
    query_vec = embed(query)

    with get_session() as session:
        results = session.exec(
            select(Chunk)
            .order_by(Chunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        ).all()

        return [{"text": c.text, "url": c.url} for c in results]


def generate_answer(query: str, top_k: int = 5) -> dict:
    """Retrieves relevant chunks (possibly from multiple source URLs) and
    asks the local LLM to answer, citing the URLs it actually used."""
    hits = retrieve(query, top_k=top_k)

    if not hits:
        return {"answer": "No indexed content available to answer this.", "sources": []}

    context_blocks = []
    for i, h in enumerate(hits):
        context_blocks.append(f"[Source {i+1}: {h['url']}]\n{h['text']}")
    context = "\n\n".join(context_blocks)

    prompt = (
        "Answer the question using ONLY the context below. "
        "Cite sources inline like [Source 1], [Source 2] matching the context blocks. "
        "If the context doesn't contain the answer, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
    )

    resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": GEN_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    answer_text = resp.json()["response"]

    unique_sources = list({h["url"] for h in hits})
    return {"answer": answer_text, "sources": unique_sources}
