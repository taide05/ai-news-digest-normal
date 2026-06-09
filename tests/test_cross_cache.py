import json


def test_cross_analysis_cache_table_exists(test_db):
    cols = test_db.execute("PRAGMA table_info(cross_analysis_cache)").fetchall()
    col_names = [c[1] for c in cols]
    assert "cluster_id" in col_names
    assert "analysis_type" in col_names
    assert "article_ids" in col_names
    assert "content" in col_names


def test_cache_cross_analysis_write_read(test_db):
    from db.models import cache_cross_analysis, get_cached_cross_analysis
    cache_cross_analysis(test_db, "test-cluster-1", "cross_comparison",
                         "对比分析内容", ["art1", "art2", "art3"])
    result = get_cached_cross_analysis(test_db, "test-cluster-1", "cross_comparison")
    assert result == "对比分析内容"


def test_cache_cross_analysis_upsert(test_db):
    from db.models import cache_cross_analysis, get_cached_cross_analysis
    cache_cross_analysis(test_db, "test-cluster-2", "cross_comparison", "第一版", ["a1"])
    cache_cross_analysis(test_db, "test-cluster-2", "cross_comparison", "更新版", ["a1"])
    result = get_cached_cross_analysis(test_db, "test-cluster-2", "cross_comparison")
    assert result == "更新版"


def test_get_user_topics_empty(test_db):
    from web.routes.api import _get_user_topics
    topics = _get_user_topics(test_db)
    assert topics == []


def test_get_recent_read_titles_empty(test_db):
    from web.routes.api import _get_recent_read_titles
    titles = _get_recent_read_titles(test_db)
    assert titles == []
