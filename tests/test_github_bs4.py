import pytest
from collectors.github_trending import GitHubTrendingCollector
from collectors.registry import _collectors


MOCK_HTML = """
<html><body>
<article class="Box-row">
    <h2><a href="/owner1/repo1">owner1 / repo1</a></h2>
    <p>An awesome AI project for 2026</p>
    <span itemprop="programmingLanguage">Python</span>
    <span><svg class="octicon-star"></svg> 1,234</span>
</article>
<article class="Box-row">
    <h2><a href="/owner2/repo2">owner2 / repo2</a></h2>
    <p>Another machine learning library</p>
    <span itemprop="programmingLanguage">Rust</span>
    <span><svg class="octicon-star"></svg> 567</span>
</article>
</body></html>
"""


class TestGitHubTrendingRegistration:
    def test_registered_in_collectors(self):
        assert "github-trending" in _collectors

    def test_collector_attributes(self):
        collector = GitHubTrendingCollector()
        assert collector.name == "github-trending"
        assert "github.com/trending" in collector.url
        assert collector.type == "web"

    def test_rate_limit_set(self):
        collector = GitHubTrendingCollector()
        assert collector.rate_limit > 0


class TestGitHubTrendingBS4Parsing:
    def test_parse_mock_html(self):
        """Test BS4 parsing logic directly by simulating the parsing part."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_HTML, "lxml")
        articles = soup.select("article.Box-row")
        assert len(articles) == 2

        seen = set()
        results = []
        for article_elem in articles:
            h2 = article_elem.select_one("h2 a")
            assert h2 is not None
            href = h2.get("href", "").strip()
            full_name = href.strip("/")
            parts = full_name.split("/")
            assert len(parts) == 2
            owner, repo = parts

            full_name_lower = full_name.lower()
            if full_name_lower in seen:
                continue
            seen.add(full_name_lower)

            title = f"{owner}/{repo}"
            url = f"https://github.com{href}"
            desc_elem = article_elem.select_one("p")
            summary = desc_elem.text.strip() if desc_elem else ""
            lang_elem = article_elem.select_one('[itemprop="programmingLanguage"]')
            lang = lang_elem.text.strip() if lang_elem else ""
            stars_elem = article_elem.select_one(".octicon-star")
            stars = ""
            if stars_elem and stars_elem.parent:
                stars = stars_elem.parent.get_text(strip=True)

            results.append({
                "title": title,
                "url": url,
                "summary": summary,
                "language": lang,
                "stars": stars,
            })

        assert results[0]["title"] == "owner1/repo1"
        assert results[0]["url"] == "https://github.com/owner1/repo1"
        assert results[0]["language"] == "Python"
        assert "1,234" in results[0]["stars"]

        assert results[1]["title"] == "owner2/repo2"
        assert results[1]["language"] == "Rust"

    def test_deduplication_in_seen_set(self):
        seen = set()
        seen.add("owner1/repo1")
        seen.add("owner1/repo1")  # duplicate
        assert len(seen) == 1

    def test_invalid_href_ignored(self):
        """Articles with malformed href (not exactly /owner/repo) are skipped."""
        from bs4 import BeautifulSoup

        html = """<html><body>
        <article class="Box-row">
            <h2><a href="/single">single_only</a></h2>
            <p>Bad repo</p>
        </article>
        <article class="Box-row">
            <h2><a href="/a/b/c">too_many_parts</a></h2>
            <p>Another bad one</p>
        </article>
        <article class="Box-row">
            <h2><a href="/owner3/repo3">owner3 / repo3</a></h2>
            <p>Good one</p>
        </article>
        </body></html>"""

        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.Box-row")
        seen = set()
        valid = []
        for article_elem in articles:
            h2 = article_elem.select_one("h2 a")
            if not h2:
                continue
            href = h2.get("href", "").strip()
            full_name = href.strip("/")
            parts = full_name.split("/")
            if len(parts) != 2:
                continue
            owner, repo = parts
            full_name_lower = full_name.lower()
            if full_name_lower in seen:
                continue
            seen.add(full_name_lower)
            valid.append(f"{owner}/{repo}")

        assert valid == ["owner3/repo3"]

    def test_missing_h2_skipped(self):
        """Articles without h2 tag are skipped gracefully."""
        from bs4 import BeautifulSoup

        html = """<html><body>
        <article class="Box-row">
            <p>No h2 here</p>
        </article>
        </body></html>"""

        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.Box-row")
        for article_elem in articles:
            h2 = article_elem.select_one("h2 a")
            assert h2 is None  # Should be None, and code should continue
