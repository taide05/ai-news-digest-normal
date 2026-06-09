import pytest
from db.models import normalize_url, make_article_id


class TestNormalizeUrl:
    def test_removes_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&a=1"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "a=1" in result

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        assert "#" not in result

    def test_preserves_root_path(self):
        assert normalize_url("https://example.com/") == "https://example.com/"
        assert normalize_url("https://example.com") == "https://example.com/"

    def test_empty_url_returns_empty(self):
        assert normalize_url("") == ""


class TestMakeArticleId:
    def test_generates_consistent_id(self):
        url = "https://example.com/article"
        id1 = make_article_id("hn", url)
        id2 = make_article_id("hn", url)
        assert id1 == id2
        assert len(id1) == 64

    def test_different_sources_produce_different_ids(self):
        url = "https://example.com/article"
        id1 = make_article_id("hn", url)
        id2 = make_article_id("arxiv", url)
        assert id1 != id2
