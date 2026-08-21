from triage.data import article_ids, load_articles, load_tickets, ticket_text
from triage.tools.kb_search import format_results, search_kb

import pytest


def test_kb_assets_wellformed():
    articles = load_articles()
    assert len(articles) >= 30
    assert {a["category"] for a in articles} == {
        "billing", "troubleshooting", "account", "features",
    }


def test_labels_only_reference_real_articles():
    ids = article_ids()
    for ticket in load_tickets():
        expected = ticket["expected_article"]
        assert expected is None or expected in ids


def test_search_finds_relevant_article():
    hits = search_kb("charged twice duplicate invoice")
    assert hits
    assert any(h["id"] == "kb_billing_02" for h in hits)


def test_search_is_bounded_and_deterministic():
    hits = search_kb("sync notes devices", top_k=3)
    assert len(hits) <= 3
    assert hits == search_kb("sync notes devices", top_k=3)


def test_stopwords_only_query_returns_nothing():
    assert search_kb("the and is a to of") == []


def test_oversized_query_does_not_hang():
    """Length cap plus a non-backtracking token scan: hostile input stays cheap."""
    assert isinstance(search_kb("sync " * 20000), list)


def test_format_results_handles_empty():
    assert format_results([]) == "NO_MATCHES"


def test_ticket_text_returns_text_only():
    text = ticket_text("t01")
    assert isinstance(text, str) and text
    # The runtime must never be handed the labels.
    assert "expected_route" not in text


@pytest.mark.parametrize("bad", ["../../etc/passwd", "t 1", "x" * 40, ""])
def test_ticket_id_validation(bad):
    with pytest.raises((ValueError, KeyError)):
        ticket_text(bad)
