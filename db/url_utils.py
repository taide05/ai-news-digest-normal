import hashlib
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "ref_src", "source", "fbclid", "gclid", "gclsrc",
    "_ga", "_gl", "mc_cid", "mc_eid",
}


def normalize_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    url = raw_url.strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.hostname or ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    qs = parse_qs(parsed.query, keep_blank_values=True)
    clean_qs = {k: v for k, v in qs.items() if k not in TRACKING_PARAMS}
    query = urlencode(sorted(clean_qs.items()), doseq=True)
    result = urlunparse((scheme, netloc, path, parsed.params, query, ""))
    return result


def make_article_id(source_id: str, url: str) -> str:
    raw = f"{source_id}:{normalize_url(url)}"
    return hashlib.sha256(raw.encode()).hexdigest()
