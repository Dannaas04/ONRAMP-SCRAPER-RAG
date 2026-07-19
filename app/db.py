from datetime import datetime
from typing import Optional, Any

from sqlalchemy import Column, text
from sqlmodel import SQLModel, Field, create_engine, Session
from pgvector.sqlalchemy import Vector
from sqlalchemy.exc import IntegrityError

from app.config import DATABASE_URL, EMBED_DIM

engine = create_engine(DATABASE_URL, echo=False)


class Page(SQLModel, table=True):
    """One row per crawl of a URL. Never overwritten -> gives us version history."""
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(index=True)
    content_hash: str = Field(index=True)
    raw_html: str
    cleaned_text: str
    source_type: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    is_duplicate_of_latest: bool = False


class Chunk(SQLModel, table=True):
    """A chunk of cleaned text plus its embedding, stored in the same
    database as the raw/relational data."""
    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    url: str = Field(index=True)
    chunk_index: int
    text: str
    embedding: Any = Field(sa_column=Column(Vector(EMBED_DIM)))


class DeadLetter(SQLModel, table=True):
    """Tasks that failed repeatedly after retries are exhausted."""
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    task_name: str
    error: str
    failed_at: datetime = Field(default_factory=datetime.utcnow)


def init_db():
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        except IntegrityError:
            conn.rollback()
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
