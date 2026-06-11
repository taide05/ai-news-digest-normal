import logging
import math
import random
from collections import Counter
from datetime import datetime

logger = logging.getLogger(__name__)

_profile_cache = None
_profile_cache_ts = 0

# ── Backward-compatible: compute_user_profile (used by cold-start + orchestrator) ──


def compute_user_profile(db_conn, cfg, force_refresh: bool = False) -> dict:
    global _profile_cache, _profile_cache_ts
    now = datetime.now().timestamp()
    if not force_refresh and _profile_cache is not None and (now - _profile_cache_ts) < 300:
        return _profile_cache

    feedback_count = db_conn.execute(
        "SELECT COUNT(*) FROM read_records WHERE feedback IS NOT NULL"
    ).fetchone()[0]

    half_life = cfg.preference.half_life_days

    if feedback_count < cfg.ranking.cold_start_threshold:
        topics = {kw: 1.0 / len(cfg.preference.initial_keywords) for kw in cfg.preference.initial_keywords}
        sources = {}
    else:
        rows = db_conn.execute(
            "SELECT r.topics, r.opened_at FROM read_records r "
            "WHERE r.feedback = 'interested' AND r.topics != ''"
        ).fetchall()
        topic_counts = {}
        for topics_str, opened_at in rows:
            if not topics_str:
                continue
            try:
                opened_dt = datetime.fromisoformat(opened_at)
                days = (datetime.now() - opened_dt).days
                decay = math.exp(-days / max(1, half_life))
            except (ValueError, TypeError):
                decay = 1.0
            for t in topics_str.split(","):
                t = t.strip().lower()
                if t:
                    topic_counts[t] = topic_counts.get(t, 0) + decay
        max_count = max(topic_counts.values()) if topic_counts else 1
        topics = {t: c / max_count for t, c in topic_counts.items()}

        src_rows = db_conn.execute(
            "SELECT a.source_id, COUNT(*), SUM(CASE WHEN r.feedback='interested' THEN 1 ELSE 0 END) "
            "FROM read_records r JOIN articles a ON r.article_id = a.id "
            "WHERE r.feedback IS NOT NULL GROUP BY a.source_id"
        ).fetchall()
        sources = {}
        for src_id, total, interested in src_rows:
            sources[src_id] = interested / max(1, total)

    _profile_cache = {
        "topics": topics,
        "sources": sources,
        "feedback_count": feedback_count,
    }
    _profile_cache_ts = now
    return _profile_cache


def invalidate_profile_cache():
    global _profile_cache
    _profile_cache = None


# ── RatingEngine: multi-signal preference scoring ──────────────────────────


class RatingEngine:
    """Learns user preferences from 1-5 ratings and scores new articles.

    Six scoring layers, all additive, with exponential time decay on the
    profile side (older ratings count less) and mild freshness decay on
    the candidate side (older articles slightly penalised).
    """
    _STOP_WORDS = {"a", "an", "the", "is", "of", "in", "to", "for", "and", "or",
                   "on", "at", "with", "by", "from", "it", "its", "be", "as", "but",
                   "this", "that", "are", "was", "were", "been", "has", "have", "had",
                   "not", "no", "can", "will", "would", "could", "should", "may", "do",
                   "does", "did", "so", "if", "we", "you", "he", "she", "they", "them",
                   "their", "our", "my", "your", "his", "her", "all", "just", "about",
                   "more", "than", "into", "also", "new", "some", "one", "two", "very"}

    def __init__(self, db_conn, cfg):
        self.db = db_conn
        self.cfg = cfg
        self._cache = None
        self._cache_ts = 0.0

    # ── public API ──────────────────────────────────────────────────────

    def feedback_count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM ratings").fetchone()
        return row[0] if row else 0

    def rank_articles(self, articles: list) -> list:
        """Score and sort articles, highest first."""
        if not articles:
            return articles
        profile = self._get_profile()
        for art in articles:
            score = 0.5
            score += self._keyword_boost(art, profile)
            score += self._term_overlap(art, profile)
            score += self._bigram_overlap(art, profile)
            score += self._tfidf_cosine(art, profile)
            score += self._source_score(art, profile)
            score *= self._freshness_decay(art)
            if getattr(art, "_highlight", False):
                score += 0.08
            score += random.uniform(0, 0.03)
            art["score"] = round(max(0.0, score), 4)
        return sorted(articles, key=lambda a: a.get("score", 0), reverse=True)

    def invalidate(self):
        self._cache = None

    # ── profile building (cached) ───────────────────────────────────────

    def _get_profile(self) -> dict:
        now = datetime.now().timestamp()
        if self._cache is not None and (now - self._cache_ts) < 300:
            return self._cache
        self._cache = self._build_profile()
        self._cache_ts = now
        return self._cache

    def _build_profile(self) -> dict:
        """Build scoring profile from ratings table + implicit signals with time decay."""
        from db.models import get_ratings, get_implicit_signals, get_synonym_groups
        ratings = list(get_ratings(self.db))
        half_life = self.cfg.preference.half_life_days

        # Merge implicit signals as virtual ratings
        signals = get_implicit_signals(self.db)
        signal_rating_map = {"read": 3.5, "saved": 4.5, "dismissed": 1.5}
        for sig in signals:
            aid = sig["article_id"]
            if not any(r["article_id"] == aid for r in ratings):
                ratings.append({
                    "article_id": aid,
                    "rating": signal_rating_map.get(sig["signal_type"], 3),
                    "rated_at": sig["created_at"],
                    "title": aid,  # placeholder; actual match via article_id
                    "summary": "",
                    "source_id": "",
                })

        # Build synonym expansion map
        synonym_map = {}
        for sg in get_synonym_groups(self.db):
            import json
            try:
                terms = json.loads(sg["terms"])
                if isinstance(terms, list):
                    base = terms[0].lower() if terms else ""
                    for t in terms:
                        synonym_map[t.lower()] = base
            except (json.JSONDecodeError, TypeError):
                pass

        liked_terms = Counter()
        disliked_terms = Counter()
        liked_bigrams = Counter()
        source_scores = {}
        liked_docs = []
        total_weight = 0.0
        source_rating_sum = {}
        source_rating_count = {}

        for r in ratings:
            try:
                rated_dt = datetime.fromisoformat(r["rated_at"])
                days = max(0, (datetime.now() - rated_dt).days)
                decay = math.exp(-days / max(1, half_life))
            except (ValueError, TypeError):
                decay = 1.0

            title = (r.get("title") or "").lower()
            summary = (r.get("summary") or "").lower()
            text = title + " " + summary
            rating = r["rating"]
            src = r.get("source_id", "")

            # Source reputation
            source_rating_sum[src] = source_rating_sum.get(src, 0.0) + rating * decay
            source_rating_count[src] = source_rating_count.get(src, 0) + 1

            tokens = self._tokenize(text)
            bigrams = self._bigrams(tokens)

            if rating >= 4:  # liked
                for t in tokens:
                    liked_terms[t] += decay
                for bg in bigrams:
                    liked_bigrams[bg] += decay
                liked_docs.append((tokens, rating, decay))
                total_weight += decay
            elif rating <= 2:  # disliked
                for t in tokens:
                    disliked_terms[t] += decay

        # Normalise source scores to [-0.15, +0.15] around neutral (rating 3)
        sources = {}
        for src in source_rating_sum:
            avg = source_rating_sum[src] / max(1, source_rating_count[src])
            sources[src] = (avg - 3.0) * 0.1  # 5→+0.2, 1→-0.2

        # Build TF-IDF vocabulary from liked documents
        vocab, idf = self._build_tfidf(liked_docs)

        self._cache = {
            "liked_terms": liked_terms,
            "disliked_terms": disliked_terms,
            "liked_bigrams": liked_bigrams,
            "sources": sources,
            "vocab": vocab,
            "idf": idf,
            "profile_vector": self._profile_tfidf_vector(liked_docs, vocab, idf),
            "total_weight": total_weight,
            "synonym_map": synonym_map,
        }
        return self._cache

    # ── scoring layers ──────────────────────────────────────────────────

    def _keyword_boost(self, art, profile) -> float:
        """Boost by config-level preference keywords in title/summary."""
        text = ((art.get("title") or "") + " " + (art.get("summary") or "")).lower()
        boost = 0.0
        for kw in self.cfg.preference.initial_keywords:
            if kw.lower() in text:
                boost += 0.03
        return min(0.15, boost)

    def _term_overlap(self, art, profile) -> float:
        """Score by overlap between article tokens and liked/disliked terms.

        Synonym-group terms are expanded: matching a synonym counts toward
        the canonical form.
        """
        text = ((art.get("title") or "") + " " + (art.get("summary") or "")).lower()
        tokens = set(self._tokenize(text))
        # Expand tokens via synonym map
        synonym_map = profile.get("synonym_map", {})
        expanded = set(tokens)
        for t in tokens:
            if t in synonym_map:
                expanded.add(synonym_map[t])
        liked = profile.get("liked_terms", Counter())
        disliked = profile.get("disliked_terms", Counter())

        if not liked and not disliked:
            return 0.0

        pos = sum(liked.get(t, 0) for t in expanded) / max(1, sum(liked.values()))
        neg = sum(disliked.get(t, 0) for t in expanded) / max(1, sum(disliked.values()))
        return round((pos - neg * 0.5) * 0.25, 4)

    def _bigram_overlap(self, art, profile) -> float:
        """Score by title bigram overlap with liked-article bigrams."""
        title = (art.get("title") or "").lower()
        tokens = self._tokenize(title)
        bigrams = set(self._bigrams(tokens))
        liked_bg = profile.get("liked_bigrams", Counter())
        if not liked_bg or not bigrams:
            return 0.0
        overlap = sum(liked_bg.get(bg, 0) for bg in bigrams)
        return round(min(0.15, overlap / max(1, sum(liked_bg.values())) * 0.15), 4)

    def _tfidf_cosine(self, art, profile) -> float:
        """Cosine similarity between article TF-IDF and profile vector."""
        vocab = profile.get("vocab", {})
        idf = profile.get("idf", {})
        profile_vec = profile.get("profile_vector", [])
        if not vocab or not profile_vec:
            return 0.0

        text = ((art.get("title") or "") + " " + (art.get("summary") or "")).lower()
        tokens = self._tokenize(text)
        tf = Counter(tokens)
        total = max(1, len(tokens))

        vec = []
        for word in vocab:
            vec.append(tf.get(word, 0) / total * idf.get(word, 0))

        dot = sum(a * b for a, b in zip(vec, profile_vec))
        norm_a = math.sqrt(sum(a * a for a in vec)) or 1
        norm_b = math.sqrt(sum(b * b for b in profile_vec)) or 1
        return round(dot / (norm_a * norm_b) * 0.25, 4)

    def _source_score(self, art, profile) -> float:
        """Source reputation score based on average rating per source."""
        sources = profile.get("sources", {})
        src = art.get("source_id", "")
        return sources.get(src, 0.0)

    def _freshness_decay(self, art) -> float:
        """Mild freshness multiplier: older articles get slight penalty."""
        pub = art.get("published_at", "")
        if not pub:
            return 1.0
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00").split("+")[0])
            hours = max(0, (datetime.now() - pub_dt).total_seconds() / 3600)
            return max(0.7, 1.0 - hours / 240)  # 10-day half-life
        except (ValueError, TypeError):
            return 1.0

    # ── NLP helpers (pure Python, no deps) ──────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace/punctuation tokenisation with stop-word removal."""
        import re
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        return [t for t in tokens if len(t) > 1 and t not in self._STOP_WORDS]

    def _bigrams(self, tokens: list[str]) -> list[str]:
        return [tokens[i] + "_" + tokens[i + 1] for i in range(len(tokens) - 1)]

    def _build_tfidf(self, liked_docs: list) -> tuple[dict, dict]:
        """Build vocabulary and IDF from liked documents."""
        df = Counter()
        for tokens, _rating, _decay in liked_docs:
            for word in set(tokens):
                df[word] += 1
        doc_count = max(1, len(liked_docs))
        idf = {w: math.log(doc_count / (1 + c)) for w, c in df.items()}
        vocab = {w: i for i, w in enumerate(sorted(idf.keys()))}
        return vocab, idf

    def _profile_tfidf_vector(self, liked_docs: list, vocab: dict, idf: dict) -> list[float]:
        """Compute average TF-IDF vector across all liked documents."""
        if not liked_docs:
            return []
        vec = [0.0] * len(vocab)
        total_weight = 0.0
        for tokens, rating, decay in liked_docs:
            w = decay * (rating / 5.0)
            total_weight += w
            tf = Counter(tokens)
            total_terms = max(1, len(tokens))
            for word, idx in vocab.items():
                vec[idx] += tf.get(word, 0) / total_terms * idf.get(word, 0) * w
        if total_weight > 0:
            vec = [v / total_weight for v in vec]
        return vec
