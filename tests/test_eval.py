"""Unit tests for the eval scorer itself — a metric you cannot trust is worse than none."""

from eval.run_eval import score
from triage.data import load_tickets


def _perfect_predictions() -> dict[str, dict]:
    """Derive a flawless prediction set from the labels."""
    return {
        t["id"]: {
            "category": t["expected_category"],
            "confidence": 0.95 if t["expected_route"] == "auto_answer" else 0.2,
            "kb_article_id": t["expected_article"],
            "drafted_reply": "reply",
            "route": t["expected_route"],
        }
        for t in load_tickets()
    }


def test_perfect_predictions_score_one():
    report = score(load_tickets(), _perfect_predictions())
    assert report["scored_tickets"] == 25
    assert report["escalation_recall"] == 1.0
    assert report["routing_accuracy"] == 1.0
    assert report["category_accuracy"] == 1.0
    assert report["article_hit_rate"] == 1.0
    assert report["escalation_misses"] == []


def test_missed_escalation_is_caught_and_attributed():
    """A single missed must-escalate must drop recall and name the trigger."""
    predictions = _perfect_predictions()
    predictions["t01"]["route"] = "auto_answer"
    predictions["t01"]["confidence"] = 0.9

    report = score(load_tickets(), predictions)
    assert report["escalation_recall"] < 1.0
    assert report["must_escalate_caught"] == 5
    assert report["per_trigger_recall"]["refund_demand"] == 0.0
    assert [m["id"] for m in report["escalation_misses"]] == ["t01"]


def test_all_six_triggers_are_measured():
    report = score(load_tickets(), _perfect_predictions())
    assert set(report["per_trigger_recall"]) == {
        "refund_demand", "legal_threat", "data_loss",
        "security_incident", "gdpr_deletion", "abusive_tone",
    }
    assert report["must_escalate_total"] == 6


def test_over_escalation_shows_up_as_precision_loss():
    """Escalating everything would give perfect recall; precision is what catches it."""
    predictions = {
        t["id"]: {
            "category": t["expected_category"], "confidence": 0.1,
            "kb_article_id": None, "drafted_reply": "", "route": "escalate",
        }
        for t in load_tickets()
    }
    report = score(load_tickets(), predictions)
    assert report["escalation_recall"] == 1.0
    assert report["escalation_precision"] < 0.3


def test_partial_prediction_sets_are_scored_on_what_exists():
    predictions = _perfect_predictions()
    trimmed = {k: predictions[k] for k in list(predictions)[:5]}
    report = score(load_tickets(), trimmed)
    assert report["scored_tickets"] == 5
