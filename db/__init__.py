from db.url_utils import normalize_url, make_article_id
from db.models import (
    insert_article, get_article, set_full_text, record_read, set_feedback,
    get_or_create_concept, link_article_concept, get_concepts_list,
    cache_analysis, get_cached_analysis,
)
from db.queries import (
    get_clusters_for_date, search_articles, get_weekly_review, save_weekly_review,
    get_read_articles_with_insights, get_read_article_ids_since, get_feedback_articles,
)
from db.digest import (
    has_digest_today, create_digest, mark_webhook_sent,
    insert_cluster, insert_cluster_article, mark_article_exploration,
)
from db.maintenance import cleanup_old_data
from db.schema import init_db
