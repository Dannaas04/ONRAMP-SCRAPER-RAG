from celery import Celery
from celery import Celery, Task
from celery.utils.log import get_task_logger

from app.config import REDIS_URL
from app.db import init_db, get_session, DeadLetter
from app.scraper.static_scraper import fetch_static
from app.scraper.js_scraper import fetch_js_rendered
from app.processing import save_page_version, chunk_text, get_latest_page  
from app.rag import index_chunks
from app.config import CHUNK_SIZE, CHUNK_OVERLAP

celery_app = Celery("scraper_rag", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_acks_late=True,             
    worker_prefetch_multiplier=1,    
    task_reject_on_worker_lost=True, 
)
logger = get_task_logger(__name__)

init_db()
class DeadLetterTask(Task):
    """Overriding on_failure directly on the Task class -- fires once
    Celery has exhausted all retries for a task. This is our dead-letter
    mechanism for URLs that repeatedly fail to scrape."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        url = args[0] if args else kwargs.get("url", "unknown")
        try:
            with get_session() as session:
                session.add(DeadLetter(url=url, task_name=self.name, error=str(exc)))
                session.commit()
            logger.error(f"Moved {url} to dead-letter table after exhausting retries")
        except Exception as db_exc:
            logger.error(f"FAILED to write dead-letter row for {url}: {db_exc}")

@celery_app.task(
    base=DeadLetterTask,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def scrape_url(self, url: str, source_type: str = "static"):

    if source_type == "js_rendered":
        result = fetch_js_rendered(url)
        page = save_page_version(url, result["raw_html"], source_type)
    else:
        prior = get_latest_page(url)
        result = fetch_static(
            url,
            prev_etag=prior.etag if prior else None,
            prev_last_modified=prior.last_modified if prior else None,
        )
        if result.get("not_modified"):
            logger.info(f"304 Not Modified for {url} — skipped re-fetch entirely")
            return {"url": url, "skipped": True, "reason": "not_modified"}

        page = save_page_version(
            url, result["raw_html"], source_type,
            etag=result.get("etag"), last_modified=result.get("last_modified"),
        )

    if not page.is_duplicate_of_latest:
        chunks = chunk_text(page.cleaned_text, CHUNK_SIZE, CHUNK_OVERLAP)
        index_chunks(url, page.id, chunks)
        logger.info(f"Indexed {len(chunks)} chunks for {url}")
    else:
        logger.info(f"No change detected for {url}, skipped re-indexing")

    return {"url": url, "page_id": page.id, "duplicate": page.is_duplicate_of_latest}
