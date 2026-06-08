from datetime import datetime
from db.models import (
    insert_article, has_digest_today, create_digest, mark_webhook_sent,
)
from pipeline.dedup import filter_duplicates_by_title
from pipeline.cluster import cluster_articles


def test_full_pipeline_no_ai(test_db, test_config):
    """Test the full pipeline with mock data, no LLM calls."""
    articles = [
        {"source_id": "arxiv-cs-ai", "url": "http://arxiv.org/abs/2606.00001",
         "title": "GPT-5 Technical Report", "summary": "OpenAI releases GPT-5", "language": "en"},
        {"source_id": "hackernews", "url": "https://news.ycombinator.com/item?id=1",
         "title": "OpenAI Releases GPT-5 Model", "summary": "GPT-5 announced", "language": "en"},
        {"source_id": "jiqizhixin", "url": "https://jiqizhixin.com/articles/2026-06-08-1",
         "title": "GPT-5 正式发布", "summary": "OpenAI 发布 GPT-5", "language": "zh"},
        {"source_id": "reddit-ml", "url": "https://reddit.com/r/ml/comments/1",
         "title": "MoE Training Efficiency Breakthrough", "summary": "New MoE method", "language": "en"},
        {"source_id": "github-trending", "url": "https://github.com/user/repo",
         "title": "user/repo", "summary": "A cool AI tool", "language": "en"},
    ]

    inserted = []
    for art in articles:
        aid = insert_article(test_db, art["source_id"], art["url"], art["title"],
                             summary=art["summary"], language=art["language"])
        if aid:
            inserted.append({"id": aid, "title": art["title"], "summary": art["summary"],
                             "source_id": art["source_id"], "language": art["language"]})

    assert len(inserted) >= 4

    deduped = filter_duplicates_by_title(inserted)
    assert len(deduped) > 0

    clusters = cluster_articles(deduped, threshold=0.4)
    assert len(clusters) > 0

    ids = [a["id"] for cluster in clusters for a in cluster]
    digest_id = create_digest(test_db, ids[:test_config.max_daily_articles])
    if digest_id:
        mark_webhook_sent(test_db)

    assert has_digest_today(test_db)
