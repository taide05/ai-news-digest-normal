import hashlib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def cluster_articles(articles: list[dict], threshold: float = 0.6) -> list[list[dict]]:
    if len(articles) <= 1:
        return [[a] for a in articles] if articles else []

    docs = [f"{a.get('title', '')} {a.get('summary', '')}" for a in articles]

    try:
        vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), max_features=2000)
        tfidf = vectorizer.fit_transform(docs)
        sim_matrix = cosine_similarity(tfidf)
        dist_matrix = 1.0 - sim_matrix
        dist_matrix[dist_matrix < 0] = 0
        Z = linkage(squareform(dist_matrix), method='single')
        labels = fcluster(Z, t=1.0 - threshold, criterion='distance')
    except Exception:
        return [[a] for a in articles]

    clusters: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(articles[i])

    return list(clusters.values())


def make_cluster_id(date_str: str, seq: int) -> str:
    raw = f"{date_str}:{seq}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def make_cluster_label(cluster: list[dict]) -> str:
    title = cluster[0].get("title", "未命名")
    if len(title) > 50:
        title = title[:47] + "..."
    return title
