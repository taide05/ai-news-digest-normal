"""Extract candidate source URLs from article content."""
import json
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger("source_miner")

SKIP_DOMAINS = {
    "github.com", "twitter.com", "x.com", "reddit.com", "youtube.com",
    "facebook.com", "linkedin.com", "arxiv.org", "medium.com",
}


def _extract_domain_from_url(url: str) -> str | None:
    """Extract netloc from a URL string."""
    try:
        return urlparse(url).netloc
    except Exception:
        return None


def extract_source_candidates(db_conn, clusters: list, max_per_cluster: int = 3) -> list[str]:
    """Extract unique domain URLs from cluster-representative articles' full_text.
    Skips articles without full_text gracefully.
    """
    seen_domains = set()

    # Get existing source domains (url is embedded in config JSON)
    existing = db_conn.execute("SELECT config FROM sources").fetchall()
    for (cfg_json,) in existing:
        try:
            src_url = json.loads(cfg_json).get("url", "")
        except (json.JSONDecodeError, TypeError):
            continue
        domain = _extract_domain_from_url(src_url)
        if domain:
            seen_domains.add(domain)

    # Get already-discovered candidate domains
    existing_cand = db_conn.execute("SELECT url FROM source_candidates").fetchall()
    for (url,) in existing_cand:
        domain = _extract_domain_from_url(url)
        if domain:
            seen_domains.add(domain)

    candidates = []
    for cluster in clusters:
        for art in cluster[:max_per_cluster]:
            full_text = _get_full_text(db_conn, art.get("id", ""))
            if not full_text:
                continue
            urls = _extract_urls(full_text)
            for u in urls:
                domain = urlparse(u).netloc
                if domain and domain not in seen_domains and domain not in SKIP_DOMAINS:
                    if not any(blocked in domain for blocked in SKIP_DOMAINS):
                        seen_domains.add(domain)
                        candidates.append(u)
            if len(candidates) >= 20:
                break

    return candidates[:20]


def _get_full_text(db_conn, article_id: str) -> str | None:
    if not article_id:
        return None
    row = db_conn.execute(
        "SELECT full_text, content FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    if not row:
        return None
    ft = row[0] or row[1] or ""
    if ft.startswith("["):
        return None
    return ft


def _extract_urls(text: str) -> list[str]:
    """Extract HTTP URLs from text."""
    url_pattern = re.compile(r'https?://[^\s<>"\')\]]+')
    urls = url_pattern.findall(text)
    seen = set()
    result = []
    for u in urls:
        u = u.rstrip(".,;:")
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result
