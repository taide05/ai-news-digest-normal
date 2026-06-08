from pipeline.dedup import title_similarity, filter_duplicates_by_title


def test_exact_same_title():
    assert title_similarity("Hello World", "Hello World") == 1.0


def test_completely_different():
    assert title_similarity("Hello World", "Foo Bar Baz Qux") < 0.1


def test_similar_titles():
    sim = title_similarity("GPT-5 Released by OpenAI", "OpenAI Releases GPT-5 Model")
    assert sim > 0.4


def test_filter_duplicates_removes_similar():
    articles = [
        {"title": "GPT-5 Released by OpenAI"},
        {"title": "OpenAI Releases GPT-5 Model"},
        {"title": "MoE Training Breakthrough"},
    ]
    result = filter_duplicates_by_title(articles, threshold=0.4)
    assert len(result) == 2
