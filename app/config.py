import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://scraper:scraper@localhost:5432/scraper_rag"
)

EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
GEN_MODEL = os.getenv("GEN_MODEL", "llama3.2:1b")
EMBED_DIM = 768  

CHUNK_SIZE = 500       
CHUNK_OVERLAP = 50
