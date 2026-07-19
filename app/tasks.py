from celery import Celery
from celery.signals import task_failure
from celery.utils.log import get_task_logger

from app.config import REDIS_URL
from app.db import init_db, get_session, DeadLetter
from app.scraper.static_scraper import fetch_static
from app.scraper.js_scraper import fetch_js_rendered
from app.processing import save_page_version, chunk_text
from app.rag import index_chunks
from app.config import CHUNK_SIZE, CHUNK_OVERLAP

celery_app = Celery("scraper_rag", broker=REDIS_URL, backend=REDIS_URL)
logger = get_task_logger(__name__)

init_db()


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,      
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def scrape_url(self, url: str, source_type: str = "static"):
    try:
        if source_type == "js_rendered":
            result = fetch_js_rendered(url)
        else:
            result = fetch_static(url)

        page = save_page_version(url, result["raw_html"], source_type)

        if not page.is_duplicate_of_latest:
            chunks = chunk_text(page.cleaned_text, CHUNK_SIZE, CHUNK_OVERLAP)
            index_chunks(url, page.id, chunks)
            logger.info(f"Indexed {len(chunks)} chunks for {url}")
        else:
            logger.info(f"No change detected for {url}, skipped re-indexing")

        return {"url": url, "page_id": page.id, "duplicate": page.is_duplicate_of_latest}

    except Exception as exc:
        logger.warning(f"Attempt failed for {url}: {exc}")
        raise self.retry(exc=exc)


@task_failure.connect(sender=scrape_url)
def handle_dead_letter(sender=None, task_id=None, exception=None, args=None, **kwargs):
    """Fires only once Celery has exhausted all retries for a task — this is
    the dead-letter mechanism for URLs that repeatedly fail to scrape."""
    url = args[0] if args else "unknown"
    with get_session() as session:
        session.add(DeadLetter(url=url, task_name="scrape_url", error=str(exception)))
        session.commit()
    logger.error(f"Moved {url} to dead-letter table after exhausting retries")
