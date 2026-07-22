from pydantic import ValidationError
import pytest

from app.processing import clean_html, content_hash, chunk_text


def test_clean_html_strips_script_and_keeps_text():
    html = "<html><body><script>evil()</script><p>Hello world</p></body></html>"
    cleaned = clean_html(html, url="https://example.com/page")
    assert "evil()" not in cleaned.body_text
    assert "Hello world" in cleaned.body_text


def test_clean_html_extracts_linked_documents():
    html = '<html><body><a href="/report.pdf">Report</a><a href="/page2">Page 2</a></body></html>'
    cleaned = clean_html(html, url="https://example.com/")
    assert cleaned.linked_documents == ["https://example.com/report.pdf"]


def test_clean_html_rejects_empty_body_text():
    """Schema validation should refuse a page with no real content -- this
    is what makes validation an enforced rule rather than decoration."""
    html = "<html><body><script>only_js()</script></body></html>"
    with pytest.raises(ValidationError):
        clean_html(html, url="https://example.com/empty")


def test_content_hash_is_deterministic():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")


def test_chunk_text_overlap():
    words = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_text(words, chunk_size=500, overlap=50)
  
    assert len(chunks) == 3
    
    tail = chunks[0].split()[-50:]
    head = chunks[1].split()[:50]
    assert tail == head