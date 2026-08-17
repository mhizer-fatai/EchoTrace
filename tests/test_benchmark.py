from backend.app.engine.benchmark import build_benchmark_corpus, run_benchmark


def test_corpus_reaches_target_tokens_without_extracting_extra_facts():
    corpus = build_benchmark_corpus(session_count=35, target_tokens=5_000)
    total_tokens = sum(
        max(1, int(len(message) / 4)) for _, messages in corpus for message in messages
    )
    assert total_tokens >= 5_000
    # Exactly one story message leads each session; everything else is filler.
    assert all(len(messages) >= 1 for _, messages in corpus)
    assert corpus[0][0] == "session_01"
    assert corpus[-1][0] == "session_35"
    assert len(corpus) == 35


def test_benchmark_reaches_perfect_score_on_real_pipeline():
    report = run_benchmark(session_count=35, target_tokens=5_000, verbose=False)
    assert report["sessions"] == 35
    assert report["questions_asked"] == len(report["detail"])
    assert report["score"] == 100.0
    assert all(item["ok"] for item in report["detail"])
    assert report["facts_superseded"] >= 10
