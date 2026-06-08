def title_similarity(t1: str, t2: str, n: int = 3) -> float:
    """Character n-gram Jaccard similarity."""
    def ngrams(s, n):
        s = s.lower()
        return {s[i:i + n] for i in range(len(s) - n + 1)}
    a = ngrams(t1, n)
    b = ngrams(t2, n)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def filter_duplicates_by_title(articles: list[dict], threshold: float = 0.85) -> list[dict]:
    result = []
    for art in articles:
        is_dup = False
        for existing in result:
            if title_similarity(art["title"], existing["title"]) > threshold:
                is_dup = True
                break
        if not is_dup:
            result.append(art)
    return result
