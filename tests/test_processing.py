from app.processing import clean_html, content_hash, chunk_text


def test_clean_html_strips_script_and_keeps_text():
    html = "<html><body><script>evil()</script><p>Hello world</p></body></html>"
    cleaned = clean_html(html)
    assert "evil()" not in cleaned
    assert "Hello world" in cleaned


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
