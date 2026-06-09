import pytest


def test_extract_urls_from_text():
    from pipeline.source_miner import _extract_urls
    text = "Check out https://example.com/article and https://blog.ai/post"
    urls = _extract_urls(text)
    assert len(urls) == 2
    assert "https://example.com/article" in urls


def test_extract_urls_empty():
    from pipeline.source_miner import _extract_urls
    assert _extract_urls("") == []


def test_extract_urls_dedup():
    from pipeline.source_miner import _extract_urls
    text = "See https://example.com also https://example.com"
    urls = _extract_urls(text)
    assert len(urls) == 1


def test_extract_source_candidates_empty(test_db):
    from pipeline.source_miner import extract_source_candidates
    result = extract_source_candidates(test_db, [])
    assert result == []


def test_parse_evaluation_valid():
    from ai.discovery import _parse_evaluation
    result = _parse_evaluation(
        '{"title": "AI Blog", "description": "Great content", "score": 0.8, "is_source": true}',
        "https://example.com"
    )
    assert result is not None
    assert result["title"] == "AI Blog"
    assert result["url"] == "https://example.com"


def test_parse_evaluation_invalid():
    from ai.discovery import _parse_evaluation
    result = _parse_evaluation("not json", "https://example.com")
    assert result is None


def test_get_pending_candidates_empty(test_db):
    from db.models import get_pending_candidates
    result = get_pending_candidates(test_db)
    assert result == []


def test_store_candidates_respects_cap(test_db, test_config):
    from orchestrator import _store_candidates
    candidates = [
        {"url": f"https://example{i}.com", "title": f"Source {i}",
         "description": "Test", "score": 0.5}
        for i in range(100)
    ]
    _store_candidates(test_db, candidates, max_pending=3)
    cur = test_db.execute("SELECT COUNT(*) FROM source_candidates WHERE verified = 0")
    count = cur.fetchone()[0]
    assert count <= 3


def test_extract_urls_skips_common_media():
    """URLs like .mp4, .pdf, .png should not be stripped of valid paths."""
    from pipeline.source_miner import _extract_urls
    text = "File at https://site.com/data.csv"
    urls = _extract_urls(text)
    assert "https://site.com/data.csv" in urls


def test_get_full_text_returns_content_when_full_text_is_none(test_db, test_config):
    """When full_text is NULL but content exists, content should be returned."""
    from db.models import add_source, insert_article
    from pipeline.source_miner import _get_full_text

    add_source(test_db, "t1", "Test", "rss", '{"url": "http://ex.com"}')
    aid = insert_article(test_db, "t1", "http://ex.com/1", "Test Article",
                         content="Some content with https://news.ai link")

    ft = _get_full_text(test_db, aid)
    assert ft is not None
    assert "news.ai" in ft


def test_reject_candidate(test_db):
    from db.models import reject_candidate

    test_db.execute(
        "INSERT INTO source_candidates (url, title) VALUES (?, ?)",
        ("https://bad.com", "Bad Source")
    )
    test_db.commit()
    cur = test_db.execute("SELECT id FROM source_candidates WHERE url = ?", ("https://bad.com",))
    row = cur.fetchone()
    assert row is not None

    reject_candidate(test_db, row[0])
    cur2 = test_db.execute("SELECT id FROM source_candidates WHERE url = ?", ("https://bad.com",))
    assert cur2.fetchone() is None


def test_verify_candidate_adds_source(test_db):
    from db.models import verify_candidate, get_pending_candidates

    test_db.execute(
        "INSERT INTO source_candidates (url, title, relevance_score) VALUES (?, ?, ?)",
        ("https://good.ai/blog", "Good AI Blog", 0.9)
    )
    test_db.commit()
    cur = test_db.execute("SELECT id FROM source_candidates WHERE url = ?", ("https://good.ai/blog",))
    row = cur.fetchone()

    verify_candidate(test_db, row[0])

    # Candidate should be marked verified
    cur2 = test_db.execute(
        "SELECT verified, confirmed_at FROM source_candidates WHERE id = ?", (row[0],)
    )
    v = cur2.fetchone()
    assert v[0] == 1
    assert v[1] is not None

    # Source should be added to sources table
    sources = test_db.execute("SELECT id, name, type FROM sources WHERE id LIKE 'discovered-%'").fetchall()
    assert len(sources) == 1
    assert "good-ai" in sources[0][0]
