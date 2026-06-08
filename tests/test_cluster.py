from pipeline.cluster import cluster_articles, make_cluster_label


def test_single_article_returns_single_cluster():
    articles = [{"title": "Hello World", "summary": "test"}]
    clusters = cluster_articles(articles)
    assert len(clusters) == 1
    assert len(clusters[0]) == 1


def test_empty_list():
    assert cluster_articles([]) == []


def test_similar_articles_cluster_together():
    articles = [
        {"title": "GPT-5 Released by OpenAI", "summary": "OpenAI announced GPT-5 today"},
        {"title": "OpenAI Releases GPT-5 Model", "summary": "GPT-5 has been released by OpenAI"},
        {"title": "Python 4.0 Announced Today", "summary": "Python language version 4 released"},
    ]
    clusters = cluster_articles(articles, threshold=0.3)
    assert len(clusters) <= 2


def test_different_articles_stay_separate():
    articles = [
        {"title": "AlphaFold Wins Nobel", "summary": "protein folding breakthrough"},
        {"title": "New JavaScript Framework", "summary": "frontend framework released"},
        {"title": "Quantum Computing Advance", "summary": "qubits milestone"},
    ]
    clusters = cluster_articles(articles)
    assert len(clusters) == 3


def test_make_cluster_label_truncates():
    label = make_cluster_label([{"title": "A" * 100}])
    assert len(label) <= 50
